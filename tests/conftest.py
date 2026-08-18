import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from echo_words.api import create_app
from echo_words.config import Settings

LANGUAGES_TOML = """
[languages.en]
name       = "English"
deck       = "English::Vocabulary"
dict_api   = "en"
tts        = "piper"
tts_voice  = "en_US-lessac-medium"
accent     = "us"
script     = "latin"

[languages.de]
name      = "Deutsch"
deck      = "German::Vocabulary"
dict_api  = "de"
tts       = "piper"
tts_voice = "de_DE-thorsten-medium"
script    = "latin"

[languages.sr]
name      = "Српски"
deck      = "Serbian::Vocabulary"
api_model = "gpt-fast"
tts       = "edge"
edge_tts_voice = "sr-RS-SophieNeural"
script    = "latin+cyrillic"
prompt_hints = "for nouns give gender and plural"
"""


@pytest.fixture(autouse=True)
def _no_ambient_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    # The suite must not inherit the developer's or the deploy box's ECHOWORDS_*.
    for name in [name for name in os.environ if name.startswith("ECHOWORDS_")]:
        monkeypatch.delenv(name)


@pytest.fixture
def languages_file(tmp_path: Path) -> Path:
    path = tmp_path / "languages.toml"
    path.write_text(LANGUAGES_TOML, encoding="utf-8")
    return path


@pytest.fixture
def static_dir(tmp_path: Path) -> Path:
    path = tmp_path / "_static"
    path.mkdir()
    (path / "index.html").write_text("<!doctype html><title>echo-words</title>", encoding="utf-8")
    return path


@pytest.fixture
def settings(languages_file: Path, static_dir: Path, tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        languages_config=languages_file,
        data_dir=tmp_path / "data",
        static_dir=static_dir,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client
