"""The single FIFO worker for submissions and every entry control."""

import asyncio
import logging
import time
import unicodedata
import uuid
from collections.abc import Callable, Coroutine
from contextlib import aclosing, suppress
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from echo_words.anki import Added
from echo_words.backend import Cascade
from echo_words.broker import BackendError
from echo_words.card import Meaning, Note, ParsedAnswer, ParsedText, ParsedUnit
from echo_words.events import EventHub
from echo_words.history import Entry, History, UndoState
from echo_words.i18n import DEFAULT_LOCALE, message
from echo_words.languages import (
    MAX_CONTEXT_LENGTH,
    Language,
    fold_for_match,
    split_words,
)
from echo_words.prompt import (
    CARD_DELIMITER,
    Verdict,
    build_attestation_prompt,
    build_extended_prompt,
    build_prompt,
    extract_answer,
    parse_attestation,
)
from echo_words.sanitizer import sanitize_html
from echo_words.segments import Segment, display_text

UPDATE_INTERVAL_SECONDS = 0.5
# Codes, not sentences: the client owns every user-facing wording, so a
# stored entry re-renders in whatever interface language is picked later.
ANALYSIS_FAILED_CODE = "analysis_failed"
ADDED_STATUS = "added"
LOOKUP_ONLY_STATUS = "lookup_only"
TEXT_STATUS = "text"
CARD_FAILED_STATUS = "failed"
UNATTESTED_STATUS = "unattested"
MISSPELLED_STATUS = "misspelled"
REQUEST_EXPIRED = "request expired"
MAX_POST_GENERATION_AUDIO_WAIT_SECONDS = 10
# How long the judgement may still take once the article is complete. It is one line
# and normally lands long before; past this the answer stands unjudged rather than the
# reader waiting on a call that is not coming back.
ATTESTATION_GRACE_SECONDS = 5
# How long the first characters wait on the judgement. It normally answers well inside
# this; past it the answer stays withheld anyway, so the wait only decides whether the
# reader sees the article as it streams or all at once when the judgement lands.
FIRST_PAINT_SECONDS = 2
# The judgement has not been read yet; distinct from "read, and it said nothing".
_PENDING = object()

logger = logging.getLogger(__name__)


class Clock(Protocol):
    def __call__(self) -> float: ...


class CardStore(Protocol):
    async def add_note(
        self,
        note: Note,
        deck: str,
        audio_path: Path | None = None,
    ) -> Added: ...

    async def remove_note(self, note_id: int, media_filename: str | None = None) -> None: ...

    async def replace_note(
        self,
        note_id: int,
        note: Note,
        deck: str,
        audio_path: Path | None = None,
        old_media_filename: str | None = None,
    ) -> Added: ...


AudioFetcher = Callable[[str, Language], Coroutine[Any, Any, Path | None]]
DictionaryLookup = Callable[[str, Language], Coroutine[Any, Any, bool | None]]
JobKind = Literal["submit", "rebuild", "switch"]


async def _no_audio(_word: str, _language: Language) -> Path | None:
    return None


async def _no_lookup(_word: str, _language: Language) -> bool | None:
    """No dictionary configured, which says nothing about any word."""
    return None


@dataclass(frozen=True)
class Job:
    entry_id: str
    revision: int
    language: Language
    word: str
    lookup_only: bool
    context: str
    intent: Literal["unit"] | None = None
    kind: JobKind = "submit"
    paid_only: bool = False
    kept_audio: Path | None = None
    kept_card_audio: Path | None = None
    carded_word: str | None = None
    kept_context_audio: Path | None = None
    replace_note_id: int | None = None
    replace_media: str | None = None
    replaced_audio: Path | None = None
    replaced_card_audio: Path | None = None


@dataclass(frozen=True)
class DetailJob:
    entry_id: str
    revision: int
    language: Language
    word: str
    context: str


@dataclass
class ControlState:
    input_word: str
    suggestion: str | None
    language: Language
    lookup_only: bool
    shown_spelling: str
    context: str
    note_id: int | None = None
    media_filename: str | None = None
    audio_path: Path | None = None
    context_audio_path: Path | None = None
    card_audio_path: Path | None = None
    carded_word: str | None = None


@dataclass(frozen=True)
class StoreResult:
    status: str
    action: str
    note_id: int | None = None
    media_filename: str | None = None
    error: str | None = None
    kinds: tuple[str, ...] = ()


QueueJob = Job | DetailJob


class WordPipeline:
    """Register immediately, then process all entry work through one FIFO worker."""

    def __init__(  # noqa: PLR0913 - dependencies and bounded knobs are explicit.
        self,
        cascade: Cascade | None,
        *,
        target_lang: str,
        events: EventHub | None = None,
        anki: CardStore | None = None,
        audio: AudioFetcher = _no_audio,
        dictionary: DictionaryLookup = _no_lookup,
        audio_timeout: float = 10,
        audio_dir: Path | None = None,
        history_size: int = 50,
        clock: Clock = time.monotonic,
    ) -> None:
        self.cascade = cascade
        self.events = events or EventHub()
        self.anki = anki
        self.audio = audio
        self.dictionary = dictionary
        self.audio_timeout = audio_timeout
        self.audio_dir = audio_dir
        self.target_lang = target_lang
        self._clock = clock
        self._queue: asyncio.Queue[QueueJob] = asyncio.Queue()
        self.history = History(history_size)
        self._entries = self.history.entries
        self._order = self.history.order
        self._revisions: dict[str, int] = {}
        self._detail_revisions: dict[str, int] = {}
        self._latest_submissions: dict[str, str] = {}
        self._controls: dict[str, ControlState] = {}
        self._details_pending: set[str] = set()
        self._worker: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._worker is None:
            self._worker = asyncio.create_task(self._work(), name="echo-words-pipeline")

    async def close(self) -> None:
        if self._worker is None:
            return
        self._worker.cancel()
        with suppress(asyncio.CancelledError):
            await self._worker
        self._worker = None

    async def join(self) -> None:
        await self._queue.join()

    async def enqueue(  # noqa: PLR0913 - public queue API carries the complete job.
        self,
        language: Language,
        word: str,
        lookup_only: bool,
        *,
        intent: Literal["unit"] | None = None,
        context: str = "",
        entry_id: str | None = None,
        reuse_entry: str | None = None,
        kind: JobKind = "submit",
        paid_only: bool = False,
        kept_audio: Path | None = None,
        kept_card_audio: Path | None = None,
        carded_word: str | None = None,
        kept_context_audio: Path | None = None,
        replace_note_id: int | None = None,
        replace_media: str | None = None,
        replaced_audio: Path | None = None,
        replaced_card_audio: Path | None = None,
    ) -> Entry:
        if reuse_entry is not None:
            entry = self._entries[reuse_entry]
            revision = self._revisions[reuse_entry] + 1
            self._revisions[reuse_entry] = revision
            if kind == "switch":
                self._detail_revisions[reuse_entry] += 1
            # A paid rebuild stays completely unchanged until its queued call has
            # actually been admitted. Another paid job can spend the last daily
            # slot while this one waits, and a refusal must not blank the entry.
            if kind != "rebuild":
                self._reset_reused_entry(entry, language, word, lookup_only, context, kind)
                await self.events.publish(
                    "reset",
                    {
                        "entry_id": entry.entry_id,
                        **({"detail_html": ""} if kind == "switch" else {}),
                    },
                )
        else:
            entry = Entry(
                entry_id=entry_id or uuid.uuid4().hex,
                word=word,
                lang=language.code,
                language=language.name,
                lookup_only=lookup_only,
                shape=None,
                context=context,
            )
            self.history.add(entry)
            revision = 0
            self._revisions[entry.entry_id] = revision
            self._detail_revisions[entry.entry_id] = 0
            if kind == "submit":
                # Undo always follows the latest send, not the latest job to
                # finish. Invalidate it before queueing so a pending duplicate,
                # lookup, or failure can never expose the previous card.
                self._latest_submissions[language.code] = entry.entry_id
                self.history.undo.pop(language.code, None)
            self._drop_evicted_state()
        await self._queue.put(
            Job(
                entry.entry_id,
                revision,
                language,
                word,
                lookup_only,
                context,
                intent,
                kind,
                paid_only,
                kept_audio,
                kept_card_audio,
                carded_word,
                kept_context_audio,
                replace_note_id,
                replace_media,
                replaced_audio,
                replaced_card_audio,
            ),
        )
        await self.events.publish("accepted", entry.public())
        return entry

    def recent(self, limit: int = 20) -> list[dict[str, object]]:
        return self.history.recent(limit)

    def counters(self, lang: str) -> dict[str, int]:
        return self.history.counts(lang)

    async def request_rebuild(self, entry_id: str, *, locale: str = DEFAULT_LOCALE) -> Entry:
        entry, state = self._active_control(entry_id)
        if entry.shape != "unit":
            raise BackendError(message("text.no_rebuild", locale))
        if entry.action != "added" or state.note_id is None:
            raise BackendError(message("card.no_rebuild", locale))
        refusal = await self._paid_refusal_fresh(state.language)
        if refusal is not None:
            raise BackendError(refusal)
        return await self.enqueue(
            state.language,
            state.carded_word or state.shown_spelling,
            state.lookup_only,
            intent="unit",
            context=state.context,
            reuse_entry=entry.entry_id,
            kind="rebuild",
            paid_only=True,
            kept_audio=state.audio_path,
            kept_card_audio=state.card_audio_path,
            carded_word=state.carded_word,
            kept_context_audio=state.context_audio_path,
            replace_note_id=state.note_id,
            replace_media=state.media_filename,
        )

    async def request_switch(self, entry_id: str) -> Entry:
        entry, state = self._active_control(entry_id)
        if not state.suggestion:
            raise ValueError("no correction is available")
        reverting = state.shown_spelling.casefold() != state.input_word.casefold()
        target = state.input_word if reverting else state.suggestion
        return await self.enqueue(
            state.language,
            target,
            state.lookup_only,
            intent="unit",
            context=state.context,
            reuse_entry=entry.entry_id,
            kind="switch",
            replace_note_id=state.note_id,
            replace_media=state.media_filename,
            replaced_audio=state.audio_path,
            replaced_card_audio=state.card_audio_path,
        )

    async def request_detail(
        self,
        entry_id: str,
        *,
        locale: str = DEFAULT_LOCALE,
    ) -> dict[str, object]:
        entry, state = self._active_control(entry_id)
        if entry.shape != "unit":
            raise BackendError(message("text.no_detail", locale))
        if entry.detail_html:
            return {"entry_id": entry_id, "detail_html": entry.detail_html, "cached": True}
        if entry_id in self._details_pending:
            return {"entry_id": entry_id, "queued": True}
        refusal = await self._paid_refusal_fresh(state.language)
        if refusal is not None:
            raise BackendError(refusal)
        self._details_pending.add(entry_id)
        await self._queue.put(
            DetailJob(
                entry_id,
                self._detail_revisions[entry_id],
                state.language,
                state.carded_word or state.shown_spelling,
                state.context,
            ),
        )
        return {"entry_id": entry_id, "queued": True}

    async def undo(self, language: Language) -> str | None:
        state = self.history.undo.get(language.code)
        if state is None or state.action != "added" or state.note_id is None:
            return None
        if self.anki is None:
            return None
        await self.anki.remove_note(state.note_id, state.media_filename)
        self._delete_audio(self._audio_path(state.audio_file))
        if state.card_audio_file != state.audio_file:
            self._delete_audio(self._audio_path(state.card_audio_file))
        self.history.undo.pop(language.code, None)
        for control in self._controls.values():
            if control.note_id == state.note_id:
                control.note_id = None
                control.media_filename = None
        return state.word

    async def _work(self) -> None:
        while True:
            job = await self._queue.get()
            try:
                if isinstance(job, DetailJob):
                    await self._process_detail(job)
                else:
                    await self.process_word(job)
            except Exception:  # noqa: BLE001
                logger.exception("word processing failed unexpectedly")
                if isinstance(job, DetailJob):
                    self._details_pending.discard(job.entry_id)
                else:
                    await self._fail(job)
            finally:
                self._queue.task_done()

    async def process_word(self, job: Job) -> None:  # noqa: C901, PLR0912, PLR0915
        if not self._is_current(job):
            return
        entry = self._entries[job.entry_id]
        audio_task = None
        context_audio_task = None
        if job.kind != "rebuild":
            audio_task = asyncio.create_task(
                self.audio(job.word, job.language),
                name=f"echo-words-audio-{job.entry_id}",
            )
        # The text a unit was taken from is voiced too: its card can only carry the unit.
        context = _voiced_context(job)
        if job.kind != "rebuild" and context:
            context_audio_task = asyncio.create_task(
                self.audio(context, job.language),
                name=f"echo-words-context-audio-{job.entry_id}",
            )
        raw = ""
        last_published = ""
        last_update_at: float | None = None
        entry_reset = job.kind != "rebuild"

        async def reset() -> None:
            nonlocal raw, last_published, last_update_at
            if not self._is_current(job):
                return
            raw = ""
            last_published = ""
            last_update_at = None
            entry.text = ""
            await self.events.publish("reset", {"entry_id": entry.entry_id})

        attestation = _Attestation(self._attestation_task(job))
        try:
            if self.cascade is None:
                await self._fail(job)
                return
            prompt = build_prompt(
                job.language,
                job.word,
                self.target_lang,
                context=job.context,
                unit_intent=job.intent == "unit",
            )
            parsed: ParsedAnswer | None = None

            def read_answer(answer: str) -> None:
                nonlocal parsed
                parsed = extract_answer(
                    answer,
                    job.word,
                    job.language,
                    unit_intent=job.intent == "unit",
                    context=job.context,
                )

            def complete(answer: str) -> bool:
                """Whether the answer is one the caller can use."""
                read_answer(answer)
                return parsed is not None

            def hand_over(answer: str) -> bool:
                """Whether the paid model decides instead, over a usable pool answer.

                Only a declared misspelling: the paid models correct all six registered
                ones against the pool's four, while they withhold fewer coinages, so a
                refusal stays here rather than being overturned by a weaker judge.
                """
                read_answer(answer)
                return parsed is not None and _declares_a_typo(parsed)

            paint_waited = False
            try:
                if job.paid_only:
                    completion = self.cascade.stream_paid(
                        prompt,
                        job.language,
                        trace_id=job.entry_id,
                    )
                else:
                    completion = self.cascade.stream_completion(
                        prompt,
                        job.language,
                        trace_id=job.entry_id,
                        on_reset=reset,
                        usable=complete,
                        hand_over=hand_over,
                    )
                async with aclosing(completion):
                    async for delta in completion:
                        if not self._is_current(job):
                            return
                        if not entry_reset:
                            self._reset_reused_entry(
                                entry,
                                job.language,
                                job.word,
                                job.lookup_only,
                                job.context,
                                job.kind,
                            )
                            await self.events.publish("reset", {"entry_id": entry.entry_id})
                            entry_reset = True
                        raw += delta
                        if attestation.pending:
                            # Waited for once, briefly, so the first characters are not
                            # held back until the article's next chunk happens to
                            # arrive; after that the judgement is read, never waited
                            # for, and it keeps the answer withheld until it lands.
                            if not paint_waited:
                                paint_waited = True
                                await attestation.lands_within(FIRST_PAINT_SECONDS)
                            attestation.poll()
                        # Nothing is shown until the wording has been vouched for, and
                        # an unfinished judgement has not vouched for anything.
                        # Streaming first and blanking afterwards is the reader having
                        # seen the fabrication.
                        withheld = attestation.pending or attestation.refuses
                        visible = "" if withheld else sanitize_html(visible_analysis(raw))
                        entry.text = visible
                        last_published, last_update_at = await self._publish_progress(
                            entry,
                            visible,
                            last_published,
                            last_update_at,
                        )
                    if getattr(completion, "oversized", False):
                        parsed = None
                        quality = 0.0
                    else:
                        quality = 1.0 if complete(raw) else 0.0
                    await completion.record_quality(quality)
            except BackendError as exc:
                if job.kind == "rebuild" and not entry_reset:
                    await self.events.publish(
                        "control_error",
                        {"entry_id": entry.entry_id, "message": str(exc)},
                    )
                    return
                await self._handle_backend_error(job, entry, last_published)
                return
            if not self._is_current(job):
                return
            audio_path, context_audio_path, card_audio_path = await self._audio_paths(
                job,
                parsed,
                audio_task,
                context_audio_task,
                context,
            )
            audio_task = None
            context_audio_task = None
            attested = await attestation.result()
            # A correction overrules the standalone refusal: nobody writes `recieve` —
            # being a misspelling is what that means (spec/decision-answer-shape.md).
            # What the note then carries is the correction, and the judgement never saw
            # it, so it is asked again about that wording. Without this a coinage the
            # judgement refused is carded whenever the answer "corrects" it into a
            # second invention, which is the one case where the refusal is discarded
            # and nothing takes its place.
            refused = _refuses(attested)
            if refused and _declares_a_typo(parsed):
                corrected = _corrected_headword(parsed, job)
                refused = corrected is not None and _refuses(
                    await self._attest(job, corrected, suffix="-correction"),
                )
            stored = (
                # A refused lookup is still a lookup: it made no card either way.
                StoreResult(UNATTESTED_STATUS, "lookup" if job.lookup_only else "unattested")
                if refused
                else await self._store_card(job, parsed, card_audio_path)
            )
            if job.kind == "switch" and not _kept_previous_note(job, stored):
                # The switch stored its own note, so what the replaced one used goes —
                # except a cached file the new spelling happens to share with it.
                if job.replaced_audio != audio_path:
                    self._delete_audio(job.replaced_audio)
                if job.replaced_card_audio != card_audio_path:
                    self._delete_audio(job.replaced_card_audio)
            elif job.kind == "switch":
                if audio_path != job.replaced_audio:
                    self._delete_audio(audio_path)
                if card_audio_path not in (job.replaced_card_audio, job.replaced_audio):
                    self._delete_audio(card_audio_path)
                audio_path = job.replaced_audio
            if stored.status == UNATTESTED_STATUS:
                # Speaking a string the answer would not vouch for tells the reader it
                # is a word, which is the claim the answer refused to make. Detaching is
                # all that is done here: a recording is addressed by its text, so the
                # same file may already be serving another live entry.
                audio_path = context_audio_path = card_audio_path = None
            entry.audio_file = audio_path.name if audio_path else None
            entry.no_audio = audio_path is None and stored.status != UNATTESTED_STATUS
            entry.no_card_audio = stored.action == "added" and card_audio_path is None
            # A status that says nothing was carded must not stand over a surviving note.
            entry.card_kept = _kept_previous_note(job, stored)
            entry.analysed_as = _analysed_as(job, parsed)
            entry.typo_suspected = _declares_a_typo(parsed)
            entry.not_in_dictionary = await self._dictionary_miss(job, parsed)
            withheld = stored.status == UNATTESTED_STATUS
            if withheld:
                # Everything read out of a withheld answer goes with it: a chip is the
                # same invention one tap away, and a detail is the article again.
                entry.text = raw = ""
                last_published = ""
                parsed = None
                entry.analysed_as, entry.typo_suspected = None, False
            entry.context_audio_file = context_audio_path.name if context_audio_path else None
            suggestion = self._correction_target(job, parsed)
            chips, segment_kind = _segments_for(parsed, job)
            entry.segments = [asdict(segment) for segment in chips]
            entry.segment_kind = segment_kind
            entry.shape = parsed.kind if parsed is not None else None
            entry.model = getattr(completion, "llm_name", None)
            entry.detail_available = (
                isinstance(parsed, ParsedUnit)
                and await self._paid_refusal_fresh(job.language) is None
            )
            self._update_state(
                job,
                parsed,
                stored,
                audio_path,
                context_audio_path,
                card_audio_path,
            )
            await self._finish_entry(entry, raw, last_published, suggestion, stored)
        finally:
            for pending in (audio_task, context_audio_task):
                if pending is not None:
                    _cancel_task(pending)
            attestation.cancel()

    async def _dictionary_miss(self, job: Job, parsed: ParsedAnswer | None) -> bool:
        """Whether no dictionary has the wording this note would carry.

        Asked of the headword rather than the submission, because the headword is what
        the note teaches. Only a definite absence is reported: an unreachable service
        says nothing, and a text answer teaches no single wording.
        """
        if not isinstance(parsed, ParsedUnit):
            return False
        return await self.dictionary(parsed.note.word, job.language) is False

    def _attestation_task(self, job: Job) -> "asyncio.Task[Verdict | None] | None":
        """Ask the pool in parallel whether the submitted wording is used at all.

        A judgement asked on its own withholds measurably more coinages than the same
        judgement asked at the head of the answer that has a dictionary entry to write.
        """
        # A rebuild is about a note the reader already has and already accepted;
        # re-deciding that here would delete it over an action they asked for.
        if self.cascade is None or job.intent != "unit" or job.paid_only or job.kind == "rebuild":
            return None
        return asyncio.create_task(
            self._attest(job, job.word),
            name=f"echo-words-attestation-{job.entry_id}",
        )

    async def _attest(self, job: Job, word: str, suffix: str = "") -> Verdict | None:
        if self.cascade is None:
            return None
        answer = ""
        try:
            completion = self.cascade.stream_completion(
                build_attestation_prompt(job.language, word),
                job.language,
                trace_id=f"{job.entry_id}-attestation{suffix}",
                pool_only=True,
                reported=False,
            )
            async with aclosing(completion):
                async for delta in completion:
                    answer += delta
            verdict = parse_attestation(answer)
            await completion.record_quality(1.0 if verdict is not None else 0.0)
        except BackendError:
            # An attestation that never arrived is not an objection; refusing on the
            # pool's silence would withhold real words, which is the worse error.
            return None
        else:
            return verdict

    async def _process_detail(self, job: DetailJob) -> None:
        entry = self._entries.get(job.entry_id)
        if entry is None or self.cascade is None or not self._is_detail_current(job):
            self._details_pending.discard(job.entry_id)
            return
        raw = ""
        prompt = build_extended_prompt(
            job.language,
            job.word,
            self.target_lang,
            context=job.context,
        )
        try:
            completion = self.cascade.stream_paid(
                prompt,
                job.language,
                trace_id=f"{job.entry_id}-detail",
            )
            async with aclosing(completion):
                async for delta in completion:
                    if not self._is_detail_current(job):
                        return
                    raw += delta
                    entry.detail_html = sanitize_html(visible_analysis(raw))
                    await self.events.publish(
                        "detail",
                        {"entry_id": entry.entry_id, "text": entry.detail_html},
                    )
        except BackendError as exc:
            if not self._is_detail_current(job):
                return
            entry.detail_html = ""
            await self.events.publish(
                "detail",
                {"entry_id": entry.entry_id, "error": str(exc)},
            )
        finally:
            self._details_pending.discard(job.entry_id)

    async def _audio_paths(  # noqa: C901, PLR0912 - three roles share one deadline.
        self,
        job: Job,
        parsed: ParsedAnswer | None,
        submitted_task: asyncio.Task[Path | None] | None,
        context_task: asyncio.Task[Path | None] | None,
        context: str,
    ) -> tuple[Path | None, Path | None, Path | None]:
        tasks: dict[asyncio.Task[Path | None], str] = {}
        if submitted_task is not None:
            tasks[submitted_task] = job.word
        if context_task is not None:
            tasks[context_task] = context

        card_task: asyncio.Task[Path | None] | None = None
        card_audio = None
        if not job.lookup_only and isinstance(parsed, ParsedUnit):
            headword = parsed.note.word
            if job.carded_word and _same_text(job.carded_word, headword):
                card_audio = job.kept_card_audio
            elif _same_text(job.word, headword):
                card_task = submitted_task
                if card_task is None:
                    card_audio = job.kept_audio
            else:
                card_task = asyncio.create_task(
                    self.audio(headword, job.language),
                    name=f"echo-words-card-audio-{job.entry_id}",
                )
                tasks[card_task] = headword

        pending: set[asyncio.Task[Path | None]] = set()
        try:
            if tasks:
                _done, pending = await asyncio.wait(
                    set(tasks),
                    timeout=min(self.audio_timeout, MAX_POST_GENERATION_AUDIO_WAIT_SECONDS),
                )
        except BaseException:
            for task in tasks:
                _cancel_task(task)
            raise
        for task in pending:
            logger.warning(
                "pronunciation timed out for %s/%r",
                job.language.code,
                tasks[task],
            )
            _cancel_task(task)

        submitted_audio = job.kept_audio
        if submitted_task is not None and submitted_task not in pending:
            submitted_audio = _audio_result(submitted_task, job.language, job.word)
        context_audio = job.kept_context_audio
        if context_task is not None and context_task not in pending:
            context_audio = _audio_result(context_task, job.language, context)
        # No task means card_audio is already the reused file chosen above; an
        # identity test alone would call that case a shared submitted-word task.
        if card_task is not None:
            if card_task is submitted_task:
                card_audio = submitted_audio
            elif card_task not in pending:
                card_audio = _audio_result(card_task, job.language, parsed.note.word)
        return submitted_audio, context_audio, card_audio

    async def _store_card(
        self,
        job: Job,
        parsed: ParsedAnswer | None,
        audio_path: Path | None,
    ) -> StoreResult:
        if isinstance(parsed, ParsedText) or job.lookup_only:
            # Action "lookup" keeps the existing counters and lets undo answer
            # "nothing to undo" with no branch of its own.
            status = TEXT_STATUS if isinstance(parsed, ParsedText) else LOOKUP_ONLY_STATUS
            return StoreResult(status, "lookup")
        if not isinstance(parsed, ParsedUnit) or self.anki is None:
            return StoreResult(CARD_FAILED_STATUS, "failed")
        if _kept_the_misspelling(job, parsed):
            # The answer called the submission misspelled and still headed itself with
            # it, so the only card it offers teaches the spelling it just called wrong.
            return StoreResult(MISSPELLED_STATUS, "misspelled")
        note = parsed.note
        try:
            if job.replace_note_id is not None:
                result = await self.anki.replace_note(
                    job.replace_note_id,
                    note,
                    job.language.deck,
                    audio_path,
                    job.replace_media,
                )
            else:
                result = await self.anki.add_note(note, job.language.deck, audio_path)
        except Exception as exc:  # noqa: BLE001
            logger.exception("could not add %r to Anki", job.word)
            return StoreResult(CARD_FAILED_STATUS, "failed", error=str(exc) or None)
        return StoreResult(
            ADDED_STATUS,
            "added",
            result.note_id,
            result.media_filename,
            kinds=result.kinds,
        )

    async def _finish_entry(  # noqa: PLR0913, PLR0917
        self,
        entry: Entry,
        raw: str,
        last_published: str,
        suggestion: str | None,
        stored: StoreResult,
    ) -> None:
        final = sanitize_html(visible_analysis(raw))
        entry.text = final
        if final != last_published:
            await self._publish_update(entry)
        entry.action = stored.action
        entry.card_status = stored.status
        entry.card_kinds = list(stored.kinds)
        entry.card_error = stored.error
        entry.suggestion = suggestion
        entry.shown_spelling = entry.word
        control = self._controls.get(entry.entry_id)
        # Which way the offer points: towards the suggestion, or back to what was
        # typed. Without it the entry would call the learner's own spelling the
        # usual one as soon as they switched away from it.
        entry.showing_other_spelling = bool(
            control
            and control.suggestion
            and control.shown_spelling.casefold() != control.input_word.casefold(),
        )
        await self.events.publish(
            "done",
            {
                "entry_id": entry.entry_id,
                "text": final,
                "suggestion": suggestion,
                "shown_spelling": entry.shown_spelling,
                "card_status": stored.status,
                "card_kinds": entry.card_kinds,
                "card_error": stored.error,
                "no_audio": entry.no_audio,
                "no_card_audio": entry.no_card_audio,
                "card_kept": entry.card_kept,
                "analysed_as": entry.analysed_as,
                "typo_suspected": entry.typo_suspected,
                "showing_other_spelling": entry.showing_other_spelling,
                "segments": entry.segments,
                "segment_kind": entry.segment_kind,
                "shape": entry.shape,
                "audio_url": entry.audio_url,
                "context_audio_url": entry.context_audio_url,
                "model": entry.model,
                "detail_available": entry.detail_available,
            },
        )
        self.history.trim()
        self._drop_evicted_state()

    def _update_state(  # noqa: PLR0913, PLR0917 - the complete result is explicit.
        self,
        job: Job,
        parsed: ParsedAnswer | None,
        stored: StoreResult,
        audio_path: Path | None,
        context_audio_path: Path | None,
        card_audio_path: Path | None,
    ) -> None:
        parsed_suggestion = _suggestion_from(parsed)
        existing = self._controls.get(job.entry_id)
        if existing is None:
            existing = ControlState(
                input_word=job.word,
                suggestion=parsed_suggestion,
                language=job.language,
                lookup_only=job.lookup_only,
                shown_spelling=job.word,
                context=job.context,
            )
            self._controls[job.entry_id] = existing
        elif job.kind == "submit":
            existing.input_word = job.word
            existing.suggestion = parsed_suggestion
        if job.kind != "rebuild":
            existing.shown_spelling = job.word
        existing.context_audio_path = context_audio_path
        replacement_failed = _kept_previous_note(job, stored)
        if not replacement_failed:
            existing.note_id = stored.note_id
            existing.media_filename = stored.media_filename
            existing.audio_path = audio_path
            existing.card_audio_path = card_audio_path
            existing.carded_word = parsed.note.word if isinstance(parsed, ParsedUnit) else None
        if job.kind == "submit":
            self.history.bump(job.language.code, stored.action)
            if self._latest_submissions.get(job.language.code) == job.entry_id:
                self.history.undo[job.language.code] = UndoState(
                    word=job.word,
                    action=stored.action,
                    note_id=stored.note_id,
                    media_filename=stored.media_filename,
                    audio_file=audio_path.name if audio_path else None,
                    card_audio_file=card_audio_path.name if card_audio_path else None,
                    lookup_only=job.lookup_only,
                )
        elif not replacement_failed:
            undo = self.history.undo.get(job.language.code)
            # A switch over an entry that never stored a note — a refusal, a card that
            # failed, a misspelling left uncarded — has nothing to replace, so it writes
            # the first undo state this entry ever had.
            cards_first = (
                job.replace_note_id is None
                and stored.note_id is not None
                and self._latest_submissions.get(job.language.code) == job.entry_id
            )
            replaces_undone_note = (
                job.replace_note_id is not None
                and undo is not None
                and undo.note_id == job.replace_note_id
            )
            if cards_first or replaces_undone_note:
                self.history.undo[job.language.code] = UndoState(
                    word=job.word,
                    action=stored.action,
                    note_id=stored.note_id,
                    media_filename=stored.media_filename,
                    audio_file=audio_path.name if audio_path else None,
                    card_audio_file=card_audio_path.name if card_audio_path else None,
                    lookup_only=job.lookup_only,
                )

    def _correction_target(self, job: Job, parsed: ParsedAnswer | None) -> str | None:
        if job.kind == "switch":
            state = self._controls.get(job.entry_id)
            if state is None or not state.suggestion:
                return None
            if job.word.casefold() == state.input_word.casefold():
                return state.suggestion
            return state.input_word
        if job.kind == "rebuild":
            state = self._controls.get(job.entry_id)
            if state is not None and state.suggestion:
                # A rebuild carries the carded headword, not the spelling on screen.
                return (
                    state.input_word
                    if state.shown_spelling.casefold() != state.input_word.casefold()
                    else state.suggestion
                )
        return _suggestion_from(parsed)

    async def _handle_backend_error(self, job: Job, entry: Entry, last_published: str) -> None:
        if not self._is_current(job):
            return
        if entry.text != last_published:
            await self._publish_update(entry)
        await self._fail(job)

    async def _publish_progress(
        self,
        entry: Entry,
        visible: str,
        last_published: str,
        last_update_at: float | None,
    ) -> tuple[str, float | None]:
        if visible == last_published:
            return last_published, last_update_at
        now = self._clock()
        if last_update_at is not None and now - last_update_at < UPDATE_INTERVAL_SECONDS:
            return last_published, last_update_at
        await self._publish_update(entry)
        return visible, now

    async def _publish_update(self, entry: Entry) -> None:
        await self.events.publish("update", {"entry_id": entry.entry_id, "text": entry.text})

    async def _fail(self, job: Job) -> None:
        if not self._is_current(job):
            return
        entry = self._entries.get(job.entry_id)
        if entry is None:
            return
        entry.action = "failed"
        entry.error = ANALYSIS_FAILED_CODE
        await self.events.publish(
            "error",
            {"entry_id": entry.entry_id, "code": ANALYSIS_FAILED_CODE},
        )
        self.history.trim()
        self._drop_evicted_state()

    def _active_control(self, entry_id: str) -> tuple[Entry, ControlState]:
        entry = self._entries.get(entry_id)
        state = self._controls.get(entry_id)
        if entry is None or state is None or entry.action == "pending":
            raise KeyError(REQUEST_EXPIRED)
        return entry, state

    def _paid_refusal(self, language: Language) -> str | None:
        if self.cascade is None:
            return "no paid model is configured"
        refusal = getattr(self.cascade, "paid_refusal", None)
        return refusal(language) if refusal is not None else None

    async def _paid_refusal_fresh(self, language: Language) -> str | None:
        if self.cascade is None:
            return "no paid model is configured"
        refresh = getattr(self.cascade, "refresh_paid_availability", None)
        if refresh is not None:
            return await refresh(language)
        return self._paid_refusal(language)

    @staticmethod
    def _reset_reused_entry(  # noqa: PLR0913, PLR0917 - complete entry reset is explicit.
        entry: Entry,
        language: Language,
        word: str,
        lookup_only: bool,
        context: str,
        kind: JobKind,
    ) -> None:
        if kind != "rebuild":
            entry.word = word
        entry.lang = language.code
        entry.language = language.name
        entry.lookup_only = lookup_only
        entry.context = context
        entry.text = ""
        entry.action = "pending"
        entry.card_status = None
        entry.card_kinds = []
        entry.card_error = None
        entry.shape = None
        entry.segments = []
        entry.segment_kind = None
        entry.detail_available = False
        entry.no_audio = False
        entry.no_card_audio = False
        entry.card_kept = False
        entry.analysed_as = None
        entry.typo_suspected = False
        entry.showing_other_spelling = False
        entry.error = None
        entry.model = None
        if kind != "rebuild":
            entry.audio_file = None
            entry.context_audio_file = None
        if kind == "switch":
            entry.detail_html = ""

    def _drop_evicted_state(self) -> None:
        live = set(self._entries)
        for entry_id in set(self._revisions) - live:
            self._revisions.pop(entry_id, None)
            self._detail_revisions.pop(entry_id, None)
            self._controls.pop(entry_id, None)
            self._details_pending.discard(entry_id)

    def _is_current(self, job: Job) -> bool:
        return self._revisions.get(job.entry_id) == job.revision

    def _is_detail_current(self, job: DetailJob) -> bool:
        return self._detail_revisions.get(job.entry_id) == job.revision

    def _audio_path(self, audio_file: str | None) -> Path | None:
        if not audio_file or self.audio_dir is None:
            return None
        return self.audio_dir / audio_file

    @staticmethod
    def _delete_audio(path: Path | None) -> None:
        if path is not None:
            path.unlink(missing_ok=True)


def visible_analysis(raw: str) -> str:
    """Hide the card payload and every partial delimiter from display."""
    delimiter_at = raw.find(CARD_DELIMITER)
    if delimiter_at >= 0:
        return raw[:delimiter_at]
    for length in range(min(len(raw), len(CARD_DELIMITER) - 1), 0, -1):
        if raw.endswith(CARD_DELIMITER[:length]):
            return raw[:-length]
    return raw


def _suggestion_from(parsed: ParsedAnswer | None) -> str | None:
    return parsed.suggestion if isinstance(parsed, ParsedUnit) else None


def _segments_for(
    parsed: ParsedAnswer | None,
    job: Job,
) -> tuple[list[Segment], str | None]:
    if isinstance(parsed, ParsedText):
        return parsed.segments, "text"
    if not isinstance(parsed, ParsedUnit):
        return [], None
    if job.intent == "unit" or len(split_words(job.word)) == 1:
        return _sense_segments(parsed), "senses"
    if parsed.segments:
        return parsed.segments, "expression"
    return _sense_segments(parsed), "senses"


def _sense_segments(parsed: ParsedUnit) -> list[Segment]:
    """Offer every sense, including the one just carded, with its own example context."""
    return [
        Segment(
            label=parsed.note.word,
            reason=", ".join(meaning.translations),
            context=_sense_sentence(meaning),
        )
        for meaning in parsed.note.meanings
    ]


def _sense_sentence(meaning: Meaning) -> str:
    """The sentence a tap submits as its context, or nothing beyond the context bound.

    Cutting one to length would card a mangled sentence forever; a chip without a
    sentence still reaches the deck, as an ordinary bare submission of the word.
    """
    for example in meaning.examples:
        text = display_text(example.text, None)
        if text and len(text) <= MAX_CONTEXT_LENGTH:
            return text
    return ""


def _analysed_as(job: Job, parsed: ParsedAnswer | None) -> str | None:
    """The wording the entry is about, when that is not the wording submitted.

    Said for a lookup and a failed card as much as for a stored one, and whatever the
    answer called the difference: the reader typed one thing and is reading about
    another, which is theirs to know. What the difference is called is decided
    separately — a dictionary lemma for an inflected form is not a misspelling.
    """
    if not isinstance(parsed, ParsedUnit):
        return None
    # Folded as the relation itself was decided, so a case fold or the other Serbian
    # script is the same wording rather than another word to announce.
    same = fold_for_match(parsed.note.word, job.language) == fold_for_match(
        job.word,
        job.language,
    )
    return None if same else parsed.note.word


def _refuses(verdict: "Verdict | None | object") -> bool:
    return isinstance(verdict, Verdict) and not verdict.used


class _Attestation:
    """The parallel judgement: the task, and every way of reading it without losing it.

    It owns the task for the whole of a word, so the one place that ends it is the
    caller's ``finally`` — a judgement read past its grace is still running.
    """

    def __init__(self, task: "asyncio.Task[Verdict | None] | None") -> None:
        self._task = task
        self._verdict: Verdict | None = None
        self.pending = task is not None

    @property
    def refuses(self) -> bool:
        return _refuses(self._verdict)

    def poll(self) -> None:
        """Read the judgement if it has landed, leaving it running otherwise."""
        if self._task is not None and self._task.done():
            self._verdict, self.pending = _task_verdict(self._task), False

    async def lands_within(self, seconds: float) -> None:
        """Give the judgement a moment to arrive; a cancellation here is not swallowed."""
        if self._task is not None and self.pending:
            with suppress(TimeoutError):
                await asyncio.wait_for(asyncio.shield(self._task), seconds)
        self.poll()

    async def result(self) -> Verdict | None:
        """The judgement, waited for only as long as it can still matter."""
        await self.lands_within(ATTESTATION_GRACE_SECONDS)
        return self._verdict

    def cancel(self) -> None:
        if self._task is not None:
            _cancel_task(self._task)


def _task_verdict(task: "asyncio.Task[Verdict | None]") -> Verdict | None:
    if not task.done() or task.cancelled() or task.exception() is not None:
        return None
    return task.result()


def _corrected_headword(parsed: ParsedAnswer | None, job: Job) -> str | None:
    """The second wording a note would carry, where the answer replaced the submission.

    None where it declared a misspelling and still headed itself with the submission:
    there is no second wording to ask about, and asking the same question twice would
    let a re-roll of it overturn the answer the first call already gave.
    """
    if not isinstance(parsed, ParsedUnit) or parsed.word_relation != "typo":
        return None
    word = parsed.note.word
    if fold_for_match(word, job.language) == fold_for_match(job.word, job.language):
        return None
    return word


def _declares_a_typo(parsed: ParsedAnswer | None) -> bool:
    return isinstance(parsed, ParsedUnit) and parsed.word_relation == "typo"


def _kept_the_misspelling(job: Job, parsed: ParsedUnit) -> bool:
    # Folded exactly as the relation itself was decided: a headword the parser called
    # a different spelling is one, and a headword it called the same wording is the
    # submission however its case or script is written.
    return (
        _declares_a_typo(parsed)
        and parsed.suggestion is not None
        and fold_for_match(parsed.note.word, job.language) == fold_for_match(job.word, job.language)
    )


def _kept_previous_note(job: Job, stored: StoreResult) -> bool:
    """A job meant to replace a note stored none, so the note it had still stands."""
    return job.replace_note_id is not None and stored.note_id is None


def _voiced_context(job: Job) -> str:
    """The text a unit came from, when the unit's own audio does not already cover it."""
    return job.context if job.context and job.context != job.word else ""


def _same_text(left: str, right: str) -> bool:
    """Compare already-normalized identities without folding meaningful case."""
    return unicodedata.normalize("NFC", left) == unicodedata.normalize("NFC", right)


def _audio_result(task: asyncio.Task[Path | None], language: Language, text: str) -> Path | None:
    try:
        return task.result()
    except asyncio.CancelledError:
        worker = asyncio.current_task()
        if worker is not None and worker.cancelling():
            raise
        return None
    except Exception:  # noqa: BLE001
        logger.exception("pronunciation failed for %s/%r", language.code, text)
        return None


def _cancel_task(task: asyncio.Task[Path | None]) -> None:
    task.add_done_callback(_consume_audio_task)
    if not task.done():
        task.cancel()


def _consume_audio_task(task: asyncio.Task[Path | None]) -> None:
    with suppress(asyncio.CancelledError):
        try:
            task.result()
        except Exception:  # noqa: BLE001
            logger.exception("abandoned pronunciation task failed")
