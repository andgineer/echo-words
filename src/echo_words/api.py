"""The FastAPI application: health, the languages table, word submission, and the built PWA."""

import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from echo_words import __version__
from echo_words.backend import Cascade
from echo_words.broker import create_broker
from echo_words.config import Settings
from echo_words.config import settings as default_settings
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

# Transport guards only, kept far above the real limits so that the short
# Russian hints stay the rejection a user actually meets.
_MAX_WORD_INPUT = MAX_WORD_LENGTH * 4
_MAX_CONTEXT_INPUT = MAX_CONTEXT_LENGTH * 4
_MAX_LANG_INPUT = 32

logger = logging.getLogger(__name__)


class WordSubmission(BaseModel):
    word: str = Field(max_length=_MAX_WORD_INPUT)
    lang: str = Field(max_length=_MAX_LANG_INPUT)
    lookup_only: bool = False
    context: str = Field(default="", max_length=_MAX_CONTEXT_INPUT)


class SubmissionAccepted(BaseModel):
    entry_id: str
    word: str
    lang: str
    language: str
    lookup_only: bool
    context: str


class LanguageOption(BaseModel):
    code: str
    name: str


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or default_settings

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.languages = load_languages(settings.languages_config)
        app.state.cascade = None
        broker = None
        try:
            broker = create_broker(settings, app.state.languages)
        except Exception as exc:  # noqa: BLE001
            logger.error("no LLM backend: %s: %s", type(exc).__name__, exc)
        else:
            app.state.cascade = Cascade(broker, settings)
        try:
            yield
        finally:
            if broker is not None:
                await broker.aclose()

    app = FastAPI(title="echo-words", version=__version__, lifespan=lifespan)

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
        return SubmissionAccepted(
            entry_id=uuid.uuid4().hex,
            word=word,
            lang=language.code,
            language=language.name,
            lookup_only=lookup_only,
            context=sanitize_context(submission.context),
        )

    if settings.static_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(settings.static_dir), html=True), name="static")

    return app


def _resolve_language(languages: dict[str, Language], code: str) -> Language:
    language = languages.get(code)
    if language is None:
        raise HTTPException(status_code=400, detail=unknown_language_hint(code))
    return language


app = create_app()
