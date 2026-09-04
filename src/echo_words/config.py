"""Application settings, read from the environment with the ``ECHOWORDS_`` prefix."""

from pathlib import Path
from typing import Literal, Self

from pydantic import Field, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from echo_words.languages import DEFAULT_TARGET_LANGUAGE

# Anchored to the repo root so systemd, cron and an interactive ``uv run`` all
# resolve the same paths regardless of CWD. Only meaningful in a source
# checkout, which is the single supported way to run the app; an installed
# copy overrides what it needs through the environment.
REPO_ROOT = Path(__file__).resolve().parents[2]

# .deploy/.env is not loaded here because systemd hands it to the server process
# as an EnvironmentFile. A local run may still source it for the provider keys —
# with ECHOWORDS_ANKI_SYNC=false, or the dev box syncs the real AnkiWeb account.
ENV_FILE = REPO_ROOT / ".env"

_DEFAULT_EDGE_TTS_VOICE = {"us": "en-US-AriaNeural", "uk": "en-GB-SoniaNeural"}

# Settings that live inside the data dir unless pointed elsewhere, so moving the
# data dir moves them with it. Declared after ``data_dir`` so it is validated first.
_DATA_DIR_CHILDREN = {"languages_config": "languages.toml", "llmbroker_home": "llmbroker"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ECHOWORDS_",
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = 8080

    target_lang: str = Field(default="ru", validate_default=True)
    data_dir: Path = Path.home() / ".echo-words"
    languages_config: Path = Field(default=None, validate_default=True)
    static_dir: Path = REPO_ROOT / "_static"

    llmbroker_home: Path = Field(default=None, validate_default=True)
    llmbroker_operation: str = "vocab"
    api_model: str = "gpt-fast"
    api_daily_cap: int = 100

    ankiweb_user: str = ""
    ankiweb_password: str = ""
    sync_endpoint: str = ""
    anki_sync: bool = True

    accent: Literal["us", "uk"] = "us"
    edge_tts_voice: str = ""
    audio_timeout: int = 10

    @field_validator("target_lang", mode="before")
    @classmethod
    def _target_language_display_name(cls, value: object) -> object:
        # The documented default is the ISO code, while the LLM contract requires
        # a display name. Other target languages may be configured by display name.
        return DEFAULT_TARGET_LANGUAGE if value == "ru" else value

    @field_validator("languages_config", "llmbroker_home", mode="before")
    @classmethod
    def _under_the_data_dir(cls, value: object, info: ValidationInfo) -> object:
        return value or info.data["data_dir"] / _DATA_DIR_CHILDREN[info.field_name]

    @model_validator(mode="after")
    def _derive_defaults(self) -> Self:
        if not self.edge_tts_voice:
            self.edge_tts_voice = _DEFAULT_EDGE_TTS_VOICE[self.accent]
        return self


settings = Settings()
