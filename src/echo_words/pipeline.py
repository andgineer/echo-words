"""The single FIFO worker for submissions and every entry control."""

import asyncio
import logging
import time
import uuid
from collections.abc import Callable, Coroutine
from contextlib import aclosing, suppress
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Literal, Protocol

from echo_words.anki import Added
from echo_words.backend import Cascade
from echo_words.broker import BackendError
from echo_words.card import Meaning, Note, ParsedCard
from echo_words.events import EventHub
from echo_words.history import Entry, History, UndoState
from echo_words.i18n import DEFAULT_LOCALE, message
from echo_words.languages import Language
from echo_words.prompt import (
    CARD_DELIMITER,
    build_extended_prompt,
    build_prompt,
    build_text_prompt,
    extract_card,
    extract_segments,
)
from echo_words.sanitizer import sanitize_html
from echo_words.segments import MAX_SURFACE_LENGTH, Segment, display_text
from echo_words.shape import Shape

UPDATE_INTERVAL_SECONDS = 0.5
# Codes, not sentences: the client owns every user-facing wording, so a
# stored entry re-renders in whatever interface language is picked later.
ANALYSIS_FAILED_CODE = "analysis_failed"
ADDED_STATUS = "added"
LOOKUP_ONLY_STATUS = "lookup_only"
TEXT_STATUS = "text"
FRAGMENT_STATUS = "fragment"
CARD_FAILED_STATUS = "failed"
REQUEST_EXPIRED = "request expired"

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
JobKind = Literal["submit", "rebuild", "switch"]


async def _no_audio(_word: str, _language: Language) -> Path | None:
    return None


@dataclass(frozen=True)
class Job:
    entry_id: str
    revision: int
    language: Language
    word: str
    lookup_only: bool
    context: str
    shape: Shape = "unit"
    kind: JobKind = "submit"
    paid_only: bool = False
    kept_audio: Path | None = None
    kept_context_audio: Path | None = None
    replace_note_id: int | None = None
    replace_media: str | None = None
    replaced_audio: Path | None = None


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


@dataclass(frozen=True)
class StoreResult:
    status: str
    action: str
    note_id: int | None = None
    media_filename: str | None = None
    error: str | None = None
    kinds: tuple[str, ...] = ()
    context_dropped: bool = False


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
        audio_timeout: float = 20,
        audio_dir: Path | None = None,
        history_size: int = 50,
        clock: Clock = time.monotonic,
    ) -> None:
        self.cascade = cascade
        self.events = events or EventHub()
        self.anki = anki
        self.audio = audio
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
        shape: Shape = "unit",
        context: str = "",
        entry_id: str | None = None,
        reuse_entry: str | None = None,
        kind: JobKind = "submit",
        paid_only: bool = False,
        kept_audio: Path | None = None,
        kept_context_audio: Path | None = None,
        replace_note_id: int | None = None,
        replace_media: str | None = None,
        replaced_audio: Path | None = None,
    ) -> Entry:
        if shape == "text":
            lookup_only = True
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
                shape=shape,
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
                shape,
                kind,
                paid_only,
                kept_audio,
                kept_context_audio,
                replace_note_id,
                replace_media,
                replaced_audio,
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
        if entry.shape == "text":
            raise BackendError(message("text.no_rebuild", locale))
        refusal = await self._paid_refusal_fresh(state.language)
        if refusal is not None:
            raise BackendError(refusal)
        return await self.enqueue(
            state.language,
            state.shown_spelling,
            state.lookup_only,
            context=state.context,
            reuse_entry=entry.entry_id,
            kind="rebuild",
            paid_only=True,
            kept_audio=state.audio_path,
            kept_context_audio=state.context_audio_path,
            replace_note_id=state.note_id,
            replace_media=state.media_filename,
        )

    async def request_switch(self, entry_id: str) -> Entry:
        entry, state = self._active_control(entry_id)
        if not state.suggestion:
            raise ValueError("no correction is available")
        target = (
            state.input_word
            if state.shown_spelling.casefold() != state.input_word.casefold()
            else state.suggestion
        )
        return await self.enqueue(
            state.language,
            target,
            state.lookup_only,
            context=state.context,
            reuse_entry=entry.entry_id,
            kind="switch",
            replace_note_id=state.note_id,
            replace_media=state.media_filename,
            replaced_audio=state.audio_path,
        )

    async def request_detail(
        self,
        entry_id: str,
        *,
        locale: str = DEFAULT_LOCALE,
    ) -> dict[str, object]:
        entry, state = self._active_control(entry_id)
        if entry.shape == "text":
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
                state.shown_spelling,
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

        try:
            if self.cascade is None:
                await self._fail(job)
                return
            prompt = (
                build_text_prompt(job.language, job.word, self.target_lang)
                if job.shape == "text"
                else build_prompt(job.language, job.word, self.target_lang, context=job.context)
            )
            parsed: ParsedCard | None = None
            segments: list[Segment] | None = None

            def parse_payload(answer: str) -> bool:
                nonlocal parsed, segments
                if job.shape == "text":
                    segments = extract_segments(answer, job.language)
                    return segments is not None
                parsed = extract_card(answer, job.word, job.language)
                return parsed is not None

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
                        usable=parse_payload,
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
                        visible = sanitize_html(visible_analysis(raw))
                        entry.text = visible
                        last_published, last_update_at = await self._publish_progress(
                            entry,
                            visible,
                            last_published,
                            last_update_at,
                        )
                    await completion.record_quality(1.0 if parse_payload(raw) else 0.0)
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
            if audio_task is None:
                audio_path = job.kept_audio
            else:
                audio_path = await self._await_audio(audio_task, job.language, job.word)
                audio_task = None
            if context_audio_task is None:
                context_audio_path = job.kept_context_audio
            else:
                context_audio_path = await self._await_audio(
                    context_audio_task,
                    job.language,
                    context,
                )
                context_audio_task = None
            stored = await self._store_card(job, parsed, audio_path)
            if job.kind == "switch" and stored.action != "failed":
                self._delete_audio(job.replaced_audio)
            elif job.kind == "switch" and stored.action == "failed":
                self._delete_audio(audio_path)
                audio_path = job.replaced_audio
            entry.audio_file = audio_path.name if audio_path else None
            entry.no_audio = audio_path is None
            entry.context_audio_file = context_audio_path.name if context_audio_path else None
            suggestion = self._correction_target(job, parsed)
            chips = segments or _candidate_segments(parsed)
            senses = _sense_segments(job, parsed) if not chips else []
            entry.segments = [asdict(segment) for segment in chips or senses]
            entry.segments_are_senses = bool(senses)
            entry.model = getattr(completion, "llm_name", None)
            entry.detail_available = (
                job.shape != "text" and await self._paid_refusal_fresh(job.language) is None
            )
            self._update_state(job, parsed, stored, audio_path, context_audio_path)
            await self._finish_entry(entry, raw, last_published, suggestion, stored)
        finally:
            for pending in (audio_task, context_audio_task):
                if pending is not None:
                    _cancel_task(pending)

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

    async def _await_audio(
        self,
        task: asyncio.Task[Path | None],
        language: Language,
        text: str,
    ) -> Path | None:
        done, _ = await asyncio.wait({task}, timeout=self.audio_timeout)
        if not done:
            logger.warning("pronunciation timed out for %s/%r", language.code, text)
            _cancel_task(task)
            return None
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

    async def _store_card(
        self,
        job: Job,
        parsed: ParsedCard | None,
        audio_path: Path | None,
    ) -> StoreResult:
        if (
            job.shape == "text"
            or job.lookup_only
            or (parsed is not None and not parsed.input_is_unit)
        ):
            # Action "lookup" keeps the existing counters and lets undo answer
            # "nothing to undo" with no branch of its own.
            if job.shape == "text":
                status = TEXT_STATUS
            elif job.lookup_only:
                status = LOOKUP_ONLY_STATUS
            else:
                status = FRAGMENT_STATUS
            return StoreResult(status, "lookup")
        if parsed is None or self.anki is None:
            return StoreResult(CARD_FAILED_STATUS, "failed")
        note = _note_for(job, parsed)
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
            context_dropped=bool(_voiced_context(job)) and note.narrowed_sense is None,
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
        entry.context_dropped = stored.context_dropped
        entry.suggestion = suggestion
        entry.shown_spelling = entry.word
        control = self._controls.get(entry.entry_id)
        entry.correction_reversed = bool(
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
                "context_dropped": entry.context_dropped,
                "no_audio": entry.no_audio,
                "segments": entry.segments,
                "segments_are_senses": entry.segments_are_senses,
                "audio_url": entry.audio_url,
                "context_audio_url": entry.context_audio_url,
                "model": entry.model,
                "detail_available": entry.detail_available,
                "correction_reversed": entry.correction_reversed,
            },
        )
        self.history.trim()
        self._drop_evicted_state()

    def _update_state(  # noqa: PLR0913 - the finished job's complete result is explicit.
        self,
        job: Job,
        parsed: ParsedCard | None,
        stored: StoreResult,
        audio_path: Path | None,
        context_audio_path: Path | None,
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
        existing.shown_spelling = job.word
        existing.context_audio_path = context_audio_path
        replacement_failed = job.replace_note_id is not None and stored.action == "failed"
        if not replacement_failed:
            existing.note_id = stored.note_id
            existing.media_filename = stored.media_filename
            existing.audio_path = audio_path
        if job.kind == "submit":
            self.history.bump(job.language.code, stored.action)
            if self._latest_submissions.get(job.language.code) == job.entry_id:
                self.history.undo[job.language.code] = UndoState(
                    word=job.word,
                    action=stored.action,
                    note_id=stored.note_id,
                    media_filename=stored.media_filename,
                    audio_file=audio_path.name if audio_path else None,
                    lookup_only=job.lookup_only,
                )
        elif job.replace_note_id is not None and not replacement_failed:
            undo = self.history.undo.get(job.language.code)
            if undo is not None and undo.note_id == job.replace_note_id:
                self.history.undo[job.language.code] = UndoState(
                    word=job.word,
                    action=stored.action,
                    note_id=stored.note_id,
                    media_filename=stored.media_filename,
                    audio_file=audio_path.name if audio_path else None,
                    lookup_only=job.lookup_only,
                )

    def _correction_target(self, job: Job, parsed: ParsedCard | None) -> str | None:
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
                return (
                    state.input_word
                    if job.word.casefold() != state.input_word.casefold()
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
        entry.context_dropped = False
        entry.no_audio = False
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
    """Hide the card payload and every partial delimiter suffix from display."""
    delimiter_at = raw.find(CARD_DELIMITER)
    if delimiter_at >= 0:
        return raw[:delimiter_at]
    for length in range(min(len(raw), len(CARD_DELIMITER) - 1), 0, -1):
        if raw.endswith(CARD_DELIMITER[:length]):
            return raw[:-length]
    return raw


def _candidate_segments(parsed: ParsedCard | None) -> list[Segment]:
    """The units a vocabulary answer offers, in the shape the chip row already renders."""
    if parsed is None or parsed.input_is_unit:
        return []
    return [
        Segment(label=label, surface="", reason="")
        for label in [parsed.analysed, *parsed.candidates]
    ]


def _suggestion_from(parsed: ParsedCard | None) -> str | None:
    return parsed.suggestion if parsed is not None else None


def _note_for(job: Job, parsed: ParsedCard) -> Note:
    """The note this submission makes: carded under its context, or bare."""
    carded = replace(parsed.note, context=_voiced_context(job), context_sense=parsed.context_sense)
    return carded if carded.narrowed_sense is not None else parsed.note


def _sense_segments(job: Job, parsed: ParsedCard | None) -> list[Segment]:
    """The senses the context did not use, each a chip carrying a sentence that shows it.

    A tap on one is an ordinary submission of the same word with that sentence as
    its context, which is how a sense the answer led away from still reaches the deck.
    """
    if parsed is None or not parsed.input_is_unit:
        return []
    sense = _note_for(job, parsed).narrowed_sense
    if sense is None:
        return []
    return [
        Segment(
            label=parsed.note.word,
            surface=_sense_sentence(meaning),
            reason=", ".join(meaning.translations),
        )
        for index, meaning in enumerate(parsed.note.meanings)
        if index != sense
    ]


def _sense_sentence(meaning: Meaning) -> str:
    """The sentence a tap submits as its context, or nothing when none is short enough.

    Cutting one to length would card a mangled sentence forever; a chip without a
    sentence still reaches the deck, as an ordinary bare submission of the word.
    """
    for example in meaning.examples:
        text = display_text(example.text, None)
        if text and len(text) <= MAX_SURFACE_LENGTH:
            return text
    return ""


def _voiced_context(job: Job) -> str:
    """The text a unit came from, when the unit's own audio does not already cover it."""
    return job.context if job.context and job.context != job.word else ""


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
