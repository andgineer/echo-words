"""The single FIFO word worker and its in-memory, restart-ephemeral registry."""

import asyncio
import logging
import time
import uuid
from collections import deque
from collections.abc import Callable, Coroutine
from contextlib import aclosing, suppress
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

from echo_words.anki import Added, Duplicate
from echo_words.backend import Cascade
from echo_words.broker import BackendError
from echo_words.card import Note, ParsedCard
from echo_words.events import EventHub
from echo_words.languages import Language
from echo_words.prompt import CARD_DELIMITER, build_prompt, extract_card
from echo_words.sanitizer import sanitize_html

UPDATE_INTERVAL_SECONDS = 0.5
ERROR_MESSAGE = "Не удалось получить разбор. Попробуйте отправить слово ещё раз."
ADDED_STATUS = "✅ added to Anki"
DUPLICATE_STATUS = "📌 already in Anki"
LOOKUP_ONLY_STATUS = "👁 lookup only"
CARD_FAILED_STATUS = "⚠️ card failed"
NO_AUDIO_STATUS = "🔇 no audio"

logger = logging.getLogger(__name__)


class Clock(Protocol):
    def __call__(self) -> float: ...


class CardStore(Protocol):
    async def add_note(
        self,
        note: Note,
        deck: str,
        audio_path: Path | None = None,
    ) -> Added | Duplicate: ...


AudioFetcher = Callable[[str, Language], Coroutine[Any, Any, Path | None]]


async def _no_audio(_word: str, _language: Language) -> Path | None:
    return None


@dataclass
class Entry:
    entry_id: str
    word: str
    lang: str
    language: str
    lookup_only: bool
    context: str
    text: str = ""
    status: str = "pending"
    audio_url: str | None = None
    card_status: str | None = None
    error: str | None = None

    def public(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class Job:
    entry_id: str
    revision: int
    language: Language
    word: str
    lookup_only: bool
    context: str


class WordPipeline:
    """Register immediately, then process all languages through one FIFO worker."""

    def __init__(  # noqa: PLR0913 - dependencies and bounded knobs are explicit.
        self,
        cascade: Cascade | None,
        *,
        target_lang: str,
        events: EventHub | None = None,
        anki: CardStore | None = None,
        audio: AudioFetcher = _no_audio,
        audio_timeout: float = 20,
        history_size: int = 100,
        clock: Clock = time.monotonic,
    ) -> None:
        self.cascade = cascade
        self.events = events or EventHub()
        self.anki = anki
        self.audio = audio
        self.audio_timeout = audio_timeout
        self.target_lang = target_lang
        self._clock = clock
        self._queue: asyncio.Queue[Job] = asyncio.Queue()
        self._entries: dict[str, Entry] = {}
        self._revisions: dict[str, int] = {}
        self._order: deque[str] = deque()
        self._history_size = history_size
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
        context: str = "",
        entry_id: str | None = None,
        reuse_entry: str | None = None,
    ) -> Entry:
        if reuse_entry is not None:
            entry = self._entries[reuse_entry]
            revision = self._revisions[reuse_entry] + 1
            self._revisions[reuse_entry] = revision
            entry.word = word
            entry.lang = language.code
            entry.language = language.name
            entry.lookup_only = lookup_only
            entry.context = context
            entry.text = ""
            entry.status = "pending"
            entry.audio_url = None
            entry.card_status = None
            entry.error = None
            await self.events.publish("reset", {"entry_id": entry.entry_id})
        else:
            entry = Entry(
                entry_id=entry_id or uuid.uuid4().hex,
                word=word,
                lang=language.code,
                language=language.name,
                lookup_only=lookup_only,
                context=context,
            )
            self._entries[entry.entry_id] = entry
            revision = 0
            self._revisions[entry.entry_id] = revision
            self._order.append(entry.entry_id)
            self._trim_history()
        await self._queue.put(
            Job(entry.entry_id, revision, language, word, lookup_only, context),
        )
        await self.events.publish("accepted", entry.public())
        return entry

    def recent(self, limit: int = 20) -> list[dict[str, object]]:
        ids = list(reversed(self._order))[:limit]
        return [self._entries[entry_id].public() for entry_id in ids]

    async def _work(self) -> None:
        while True:
            job = await self._queue.get()
            try:
                await self.process_word(job)
            except Exception:  # noqa: BLE001
                # A programming or dependency fault must not kill the sole worker and
                # strand every word behind it. BackendError gets the same user-safe text.
                logger.exception("word processing failed unexpectedly")
                await self._fail(job)
            finally:
                self._queue.task_done()

    async def process_word(self, job: Job) -> None:
        if not self._is_current(job):
            return
        entry = self._entries[job.entry_id]
        audio_task = asyncio.create_task(
            self.audio(job.word, job.language),
            name=f"echo-words-audio-{job.entry_id}",
        )
        audio_consumed = False
        raw = ""
        last_published = ""
        last_update_at: float | None = None

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

            prompt = build_prompt(job.language, job.word, self.target_lang, context=job.context)
            completion = self.cascade.stream_completion(
                prompt,
                job.language,
                trace_id=job.entry_id,
                on_reset=reset,
            )
            parsed = None
            try:
                async with aclosing(completion):
                    async for delta in completion:
                        if not self._is_current(job):
                            return
                        raw += delta
                        visible = sanitize_html(visible_analysis(raw))
                        entry.text = visible
                        last_published, last_update_at = await self._publish_progress(
                            entry,
                            visible,
                            last_published,
                            last_update_at,
                        )
                    parsed = extract_card(raw, job.word, job.language)
                    await completion.record_quality(1.0 if parsed is not None else 0.0)
            except BackendError:
                await self._handle_backend_error(job, entry, last_published)
                return

            if self._is_current(job):
                suggestion = _suggestion_from(parsed)
                audio_path = await self._await_audio(audio_task, job)
                audio_consumed = True
                card_status = await self._store_card(job, parsed, audio_path)
                card_status, entry.audio_url = _audio_result(card_status, audio_path)
                await self._finish_entry(
                    entry,
                    raw,
                    last_published,
                    suggestion,
                    card_status,
                )
        finally:
            if not audio_consumed:
                _cancel_task(audio_task)

    async def _await_audio(self, task: asyncio.Task[Path | None], job: Job) -> Path | None:
        done, _ = await asyncio.wait({task}, timeout=self.audio_timeout)
        if not done:
            logger.warning("pronunciation timed out for %s/%r", job.language.code, job.word)
            _cancel_task(task)
            return None
        try:
            return task.result()
        except asyncio.CancelledError:
            worker = asyncio.current_task()
            if worker is not None and worker.cancelling():
                raise
            logger.warning("pronunciation was cancelled for %s/%r", job.language.code, job.word)
            return None
        except Exception:  # noqa: BLE001 - an injected/custom audio source must degrade too.
            logger.exception("pronunciation failed for %s/%r", job.language.code, job.word)
            return None

    async def _store_card(
        self,
        job: Job,
        parsed: ParsedCard | None,
        audio_path: Path | None,
    ) -> str:
        if job.lookup_only:
            return LOOKUP_ONLY_STATUS
        if parsed is None or self.anki is None:
            return CARD_FAILED_STATUS
        try:
            result = await self.anki.add_note(parsed[0], job.language.deck, audio_path)
        except Exception as exc:  # noqa: BLE001 - the text answer must always survive.
            logger.exception("could not add %r to Anki", job.word)
            return f"⚠️ {exc}" if str(exc) else CARD_FAILED_STATUS
        if isinstance(result, Added):
            return ADDED_STATUS
        if isinstance(result, Duplicate):
            return DUPLICATE_STATUS
        return CARD_FAILED_STATUS

    async def _handle_backend_error(
        self,
        job: Job,
        entry: Entry,
        last_published: str,
    ) -> None:
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

    async def _finish_entry(
        self,
        entry: Entry,
        raw: str,
        last_published: str,
        suggestion: str | None,
        card_status: str,
    ) -> None:
        final = sanitize_html(visible_analysis(raw))
        entry.text = final
        if final != last_published:
            await self._publish_update(entry)
        entry.status = "done"
        entry.card_status = card_status
        await self.events.publish(
            "done",
            {
                "entry_id": entry.entry_id,
                "text": final,
                "suggestion": suggestion,
                "card_status": card_status,
                "audio_url": entry.audio_url,
            },
        )
        self._trim_history()

    async def _publish_update(self, entry: Entry) -> None:
        await self.events.publish("update", {"entry_id": entry.entry_id, "text": entry.text})

    async def _fail(self, job: Job) -> None:
        if not self._is_current(job):
            return
        entry = self._entries.get(job.entry_id)
        if entry is None:
            logger.error("cannot mark missing history entry %s as failed", job.entry_id)
            return
        entry.status = "error"
        entry.error = ERROR_MESSAGE
        await self.events.publish(
            "error",
            {"entry_id": entry.entry_id, "message": ERROR_MESSAGE},
        )
        self._trim_history()

    def _trim_history(self) -> None:
        """Evict only terminal entries; queued work must remain addressable."""
        while len(self._order) > self._history_size:
            expired = next(
                (
                    entry_id
                    for entry_id in self._order
                    if self._entries[entry_id].status != "pending"
                ),
                None,
            )
            if expired is None:
                return
            self._order.remove(expired)
            self._entries.pop(expired)
            self._revisions.pop(expired)

    def _is_current(self, job: Job) -> bool:
        return self._revisions.get(job.entry_id) == job.revision


def visible_analysis(raw: str) -> str:
    """Hide the card payload and every partial delimiter suffix from display."""
    delimiter_at = raw.find(CARD_DELIMITER)
    if delimiter_at >= 0:
        return raw[:delimiter_at]
    for length in range(min(len(raw), len(CARD_DELIMITER) - 1), 0, -1):
        if raw.endswith(CARD_DELIMITER[:length]):
            return raw[:-length]
    return raw


def _suggestion_from(parsed: ParsedCard | None) -> str | None:
    return parsed[1] if parsed is not None else None


def _audio_result(card_status: str, audio_path: Path | None) -> tuple[str, str | None]:
    if audio_path is None:
        return f"{card_status} · {NO_AUDIO_STATUS}", None
    return card_status, f"/api/audio/{audio_path.name}"


def _cancel_task(task: asyncio.Task[Path | None]) -> None:
    """Request cancellation without letting uncooperative cleanup stall the FIFO."""
    task.add_done_callback(_consume_audio_task)
    if not task.done():
        task.cancel()


def _consume_audio_task(task: asyncio.Task[Path | None]) -> None:
    with suppress(asyncio.CancelledError):
        try:
            task.result()
        except Exception:  # noqa: BLE001 - an abandoned audio task is best-effort.
            logger.exception("abandoned pronunciation task failed")
