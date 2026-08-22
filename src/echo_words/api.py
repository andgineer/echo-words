"""The FastAPI application: health, the languages table, word submission, and the built PWA."""

import asyncio
import json
import logging
import time
from collections import OrderedDict
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime
from functools import partial
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from echo_words import __version__
from echo_words.anki import AnkiStore
from echo_words.audio import fetch_pronunciation, is_audio_filename, prepare_configured_voices
from echo_words.backend import Cascade
from echo_words.broker import BackendError, create_broker
from echo_words.config import Settings
from echo_words.config import settings as default_settings
from echo_words.events import EventHub
from echo_words.history import Entry
from echo_words.i18n import pick_locale
from echo_words.languages import (
    MAX_CONTEXT_LENGTH,
    MAX_TEXT_LENGTH,
    Language,
    load_languages,
    normalize_submission,
    plain_text,
    plain_unit,
    sanitize_context,
    unknown_language_hint,
    validate_text,
    validate_word,
)
from echo_words.pipeline import WordPipeline
from echo_words.shape import Shape, classify

# Transport guards only, kept far above the real limits so that the short
# localized hints stay the rejection a user actually meets.
_MAX_WORD_INPUT = MAX_TEXT_LENGTH * 4
_MAX_CONTEXT_INPUT = MAX_CONTEXT_LENGTH * 4
_MAX_LANG_INPUT = 32

logger = logging.getLogger(__name__)
SSE_KEEP_ALIVE_SECONDS = 15
SUBMISSION_RECEIPT_TTL_SECONDS = 7 * 24 * 60 * 60
SUBMISSION_RECEIPT_LIMIT = 4096
SubmissionFingerprint = tuple[str, str, bool, str, str]
Clock = Callable[[], float]
SubmissionReceipt = tuple[SubmissionFingerprint, str, float]


class SubmissionRegistry:
    """Bounded process-local receipts for idempotent offline resends."""

    def __init__(
        self,
        *,
        ttl_seconds: float = SUBMISSION_RECEIPT_TTL_SECONDS,
        max_entries: int = SUBMISSION_RECEIPT_LIMIT,
        clock: Clock = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0 or max_entries <= 0:
            raise ValueError("receipt TTL and limit must be positive")
        self._lock = asyncio.Lock()
        self._accepted: OrderedDict[UUID, SubmissionReceipt] = OrderedDict()
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._clock = clock

    def _expire(self, now: float) -> None:
        cutoff = now - self._ttl_seconds
        while self._accepted:
            _request_id, (_fingerprint, _entry_id, accepted_at) = next(
                iter(self._accepted.items()),
            )
            if accepted_at > cutoff:
                return
            self._accepted.popitem(last=False)

    async def accept(
        self,
        request_id: UUID | None,
        fingerprint: SubmissionFingerprint,
        enqueue: Callable[[], Awaitable[Entry]],
    ) -> str:
        if request_id is None:
            return (await enqueue()).entry_id
        async with self._lock:
            now = self._clock()
            self._expire(now)
            accepted = self._accepted.get(request_id)
            if accepted is not None:
                accepted_fingerprint, entry_id, _accepted_at = accepted
                if accepted_fingerprint != fingerprint:
                    raise ValueError("request_id was already used for another submission")
                return entry_id
            entry = await enqueue()
            while len(self._accepted) >= self._max_entries:
                self._accepted.popitem(last=False)
            self._accepted[request_id] = (fingerprint, entry.entry_id, self._clock())
            return entry.entry_id


def _report_voice_task(task: asyncio.Task[None]) -> None:
    try:
        task.result()
    except asyncio.CancelledError:
        pass
    except Exception:  # noqa: BLE001 - background provisioning cannot break the app.
        logger.exception("Piper voice provisioning failed unexpectedly")


async def _event_messages(events: EventHub) -> AsyncIterator[str]:
    async with events.subscribe() as subscriber:
        while True:
            try:
                event = await asyncio.wait_for(
                    subscriber.get(),
                    timeout=SSE_KEEP_ALIVE_SECONDS,
                )
            except TimeoutError:
                yield ": keep-alive\n\n"
                continue
            if event.name == "_disconnect":
                return
            data = json.dumps(event.data, ensure_ascii=False, separators=(",", ":"))
            yield f"event: {event.name}\ndata: {data}\n\n"


def _audio_response(settings: Settings, name: str) -> FileResponse:
    if not is_audio_filename(name):
        raise HTTPException(status_code=404, detail="audio not found")
    path = settings.data_dir / "audio" / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="audio not found")
    return FileResponse(path, media_type="audio/mpeg")


def _lifespan(settings: Settings):
    @asynccontextmanager
    async def manage(app: FastAPI) -> AsyncIterator[None]:
        app.state.languages = load_languages(settings.languages_config)
        app.state.anki = AnkiStore(settings)
        await app.state.anki.open()
        voice_task = asyncio.create_task(
            prepare_configured_voices(app.state.languages.values(), settings),
            name="echo-words-piper-voices",
        )
        voice_task.add_done_callback(_report_voice_task)
        app.state.cascade = None
        app.state.events = EventHub()
        broker = None
        try:
            broker = create_broker(settings, app.state.languages)
        except Exception as exc:  # noqa: BLE001
            logger.error("no LLM backend: %s: %s", type(exc).__name__, exc)
        else:
            app.state.cascade = Cascade(broker, settings)
        app.state.pipeline = WordPipeline(
            app.state.cascade,
            target_lang=settings.target_lang,
            events=app.state.events,
            anki=app.state.anki,
            audio=partial(fetch_pronunciation, settings=settings),
            audio_timeout=settings.audio_timeout,
            audio_dir=settings.data_dir / "audio",
        )
        app.state.submissions = SubmissionRegistry()
        app.state.pipeline.start()
        try:
            yield
        finally:
            await app.state.pipeline.close()
            if not voice_task.done():
                voice_task.cancel()
            await app.state.anki.close()
            if broker is not None:
                await broker.aclose()

    return manage


class WordSubmission(BaseModel):
    word: str = Field(max_length=_MAX_WORD_INPUT)
    lang: str = Field(max_length=_MAX_LANG_INPUT)
    lookup_only: bool = False
    # Absent means "classify it"; a suggested unit sends "unit" so that its own
    # length can never route it back into another running-text answer.
    shape: Shape | None = None
    context: str = Field(default="", max_length=_MAX_CONTEXT_INPUT)
    request_id: UUID | None = None


class SubmissionAccepted(BaseModel):
    entry_id: str


class LanguageOption(BaseModel):
    code: str
    name: str


def create_app(settings: Settings | None = None) -> FastAPI:  # noqa: C901, PLR0915
    settings = settings or default_settings
    app = FastAPI(title="echo-words", version=__version__, lifespan=_lifespan(settings))

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/api/languages")
    async def languages(request: Request) -> list[LanguageOption]:
        return [
            LanguageOption(code=language.code, name=language.name)
            for language in request.app.state.languages.values()
        ]

    @app.post("/api/words")
    async def submit_word(request: Request, submission: WordSubmission) -> SubmissionAccepted:
        locale = pick_locale(request.headers.get("accept-language"))
        language = _resolve_language(request.app.state.languages, submission.lang, locale)
        word, lookup_only = normalize_submission(submission.word, submission.lookup_only)
        # Classified before the edges are trimmed: the terminal mark a shared
        # selection carries is what routes that selection to running text.
        shape = submission.shape or classify(word)
        if shape == "text":
            word = plain_text(word)
            hint = validate_text(word, language, locale)
        else:
            word = plain_unit(word)
            hint = validate_word(word, language, locale)
        if hint:
            raise HTTPException(status_code=400, detail=hint)
        context = sanitize_context(submission.context)
        fingerprint = (language.code, word, lookup_only, context, shape)
        try:
            entry_id = await request.app.state.submissions.accept(
                submission.request_id,
                fingerprint,
                partial(
                    request.app.state.pipeline.enqueue,
                    language,
                    word,
                    lookup_only,
                    shape=shape,
                    context=context,
                ),
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return SubmissionAccepted(entry_id=entry_id)

    @app.get("/api/words/recent")
    async def recent_words(
        request: Request,
        limit: int = Query(default=20, ge=1, le=100),
    ) -> list[dict[str, object]]:
        return request.app.state.pipeline.recent(limit)

    @app.post("/api/words/{entry_id}/switch")
    async def switch_word(request: Request, entry_id: str) -> dict[str, object]:
        try:
            entry = await request.app.state.pipeline.request_switch(entry_id)
        except KeyError as exc:
            raise HTTPException(status_code=410, detail="request expired") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"entry_id": entry.entry_id, "queued": True}

    @app.post("/api/words/{entry_id}/rebuild")
    async def rebuild_word(request: Request, entry_id: str) -> dict[str, object]:
        locale = pick_locale(request.headers.get("accept-language"))
        try:
            entry = await request.app.state.pipeline.request_rebuild(entry_id, locale=locale)
        except KeyError as exc:
            raise HTTPException(status_code=410, detail="request expired") from exc
        except BackendError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"entry_id": entry.entry_id, "queued": True}

    @app.post("/api/words/{entry_id}/detail")
    async def detail_word(request: Request, entry_id: str) -> dict[str, object]:
        locale = pick_locale(request.headers.get("accept-language"))
        try:
            return await request.app.state.pipeline.request_detail(entry_id, locale=locale)
        except KeyError as exc:
            raise HTTPException(status_code=410, detail="request expired") from exc
        except BackendError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/languages/{code}/undo")
    async def undo_word(request: Request, code: str) -> dict[str, object]:
        locale = pick_locale(request.headers.get("accept-language"))
        language = _resolve_language(request.app.state.languages, code, locale)
        word = await request.app.state.pipeline.undo(language)
        if word is None:
            return {"undone": False, "message": "nothing to undo"}
        return {"undone": True, "word": word}

    @app.get("/api/stats")
    async def stats(request: Request) -> dict[str, object]:
        languages = request.app.state.languages
        counts = await request.app.state.anki.note_counts(
            {code: language.deck for code, language in languages.items()},
        )
        return {
            "languages": {
                code: {
                    "name": language.name,
                    **counts[code],
                    **request.app.state.pipeline.counters(code),
                }
                for code, language in languages.items()
            },
            "session_counters_since": "startup",
        }

    @app.get("/api/status")
    async def status(request: Request) -> dict[str, object]:
        return await _status_payload(request, settings)

    @app.get("/api/events")
    async def event_stream(request: Request) -> StreamingResponse:
        return StreamingResponse(
            _event_messages(request.app.state.events),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/audio/{name}")
    async def pronunciation_audio(name: str) -> FileResponse:
        return _audio_response(settings, name)

    if settings.static_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(settings.static_dir), html=True), name="static")

    return app


def _resolve_language(languages: dict[str, Language], code: str, locale: str) -> Language:
    language = languages.get(code)
    if language is None:
        raise HTTPException(status_code=400, detail=unknown_language_hint(code, locale))
    return language


async def _status_payload(request: Request, settings: Settings) -> dict[str, object]:
    cascade = request.app.state.cascade
    languages = request.app.state.languages
    pool: dict[str, object]
    journal: dict[str, object] = {}
    if cascade is None:
        pool = {"available": False, "error": "no LLM backend"}
    else:
        try:
            snapshot = await cascade.broker.snapshot()
        except Exception as exc:  # noqa: BLE001 - status must surface a broken backend.
            pool = {"available": False, "error": f"{type(exc).__name__}: {exc}"}
        else:
            cascade.note_snapshot(snapshot)
            pool = {
                "available": True,
                "providers_usable": snapshot.providers_usable,
                "providers_total": snapshot.providers_total,
                "degraded": snapshot.degraded,
                "missing_keys": [_pending_key(value) for value in snapshot.missing_keys],
                "direct_missing_keys": [
                    _pending_key(value) for value in snapshot.direct_missing_keys
                ],
            }
        for code in languages:
            try:
                journal[code] = await cascade.broker.stats(
                    operation=f"{settings.llmbroker_operation}-{code}",
                )
            except Exception:  # noqa: BLE001 - memory status remains useful without a journal.
                journal[code] = {}
    language_status = {}
    for code, language in languages.items():
        alias = cascade.paid_alias(language) if cascade is not None else ""
        last = cascade.last_calls.get(code) if cascade is not None else None
        fallback = _journal_last(journal.get(code, {}))
        paid_refusal = cascade.paid_refusal(language) if cascade is not None else "no LLM backend"
        language_status[code] = {
            "name": language.name,
            "deck": language.deck,
            "paid_alias": alias or None,
            "paid_available_today": paid_refusal is None,
            "paid_refusal": paid_refusal,
            "last_call": _call_record(last) if last is not None else fallback,
            "journal": _journal_counts(journal.get(code, {})),
        }
    sync = await request.app.state.anki.status()
    return {
        "pool": pool,
        "paid_calls": {
            "today": cascade.calls_today if cascade is not None else 0,
            "daily_cap": settings.api_daily_cap,
        },
        "languages": language_status,
        "anki": {
            **asdict(sync),
            "last_sync_at": sync.last_sync_at.isoformat() if sync.last_sync_at else None,
            "error": request.app.state.anki.sync_error,
        },
    }


def _pending_key(value: object) -> dict[str, object]:
    return {
        "api_key_ref": getattr(value, "api_key_ref", ""),
        "help": getattr(value, "help", ""),
        "entry_names": list(getattr(value, "entry_names", ())),
    }


def _call_record(value: object) -> dict[str, object]:
    at = getattr(value, "at", None)
    return {
        "model": getattr(value, "llm_name", None),
        "paid": getattr(value, "paid", False),
        "ok": getattr(value, "ok", False),
        "at": at.isoformat() if at is not None else None,
        "error": getattr(value, "error", None),
        "source": "memory",
    }


def _journal_last(stats: object) -> dict[str, object] | None:
    items = getattr(stats, "items", lambda: ())()
    latest = max(
        items,
        key=lambda item: _last_timestamp(item[1]),
        default=None,
    )
    if latest is None:
        return None
    model, value = latest
    at = getattr(value, "last_at", None)
    status = getattr(value, "last_status", None)
    return {
        "model": model,
        "paid": False,
        "ok": getattr(status, "value", status) == "ok",
        "at": at.isoformat() if at is not None else None,
        "error": None,
        "source": "journal",
    }


def _journal_counts(stats: object) -> dict[str, int]:
    return {
        model: getattr(value, "total", 0) for model, value in getattr(stats, "items", lambda: ())()
    }


def _last_timestamp(value: object) -> float:
    last_at = getattr(value, "last_at", None)
    return last_at.timestamp() if isinstance(last_at, datetime) else 0


app = create_app()
