"""The FastAPI application: health, the languages table, word submission, and the built PWA."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import partial

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from echo_words import __version__
from echo_words.anki import AnkiStore
from echo_words.audio import fetch_pronunciation, is_audio_filename, prepare_configured_voices
from echo_words.backend import Cascade
from echo_words.broker import create_broker
from echo_words.config import Settings
from echo_words.config import settings as default_settings
from echo_words.events import EventHub
from echo_words.languages import (
    MAX_CONTEXT_LENGTH,
    MAX_WORD_LENGTH,
    Language,
    load_languages,
    normalize_submission,
    sanitize_context,
    unknown_language_hint,
    validate_word,
)
from echo_words.pipeline import WordPipeline

# Transport guards only, kept far above the real limits so that the short
# Russian hints stay the rejection a user actually meets.
_MAX_WORD_INPUT = MAX_WORD_LENGTH * 4
_MAX_CONTEXT_INPUT = MAX_CONTEXT_LENGTH * 4
_MAX_LANG_INPUT = 32

logger = logging.getLogger(__name__)
SSE_KEEP_ALIVE_SECONDS = 15


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
        )
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
    context: str = Field(default="", max_length=_MAX_CONTEXT_INPUT)


class SubmissionAccepted(BaseModel):
    entry_id: str


class LanguageOption(BaseModel):
    code: str
    name: str


def create_app(settings: Settings | None = None) -> FastAPI:
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
        language = _resolve_language(request.app.state.languages, submission.lang)
        word, lookup_only = normalize_submission(submission.word, submission.lookup_only)
        hint = validate_word(word, language)
        if hint:
            raise HTTPException(status_code=400, detail=hint)
        context = sanitize_context(submission.context)
        entry = await request.app.state.pipeline.enqueue(
            language,
            word,
            lookup_only,
            context=context,
        )
        return SubmissionAccepted(entry_id=entry.entry_id)

    @app.get("/api/words/recent")
    async def recent_words(
        request: Request,
        limit: int = Query(default=20, ge=1, le=100),
    ) -> list[dict[str, object]]:
        return request.app.state.pipeline.recent(limit)

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


def _resolve_language(languages: dict[str, Language], code: str) -> Language:
    language = languages.get(code)
    if language is None:
        raise HTTPException(status_code=400, detail=unknown_language_hint(code))
    return language


app = create_app()
