from pathlib import Path

import pytest

from echo_words.config import ENV_FILE, REPO_ROOT, Settings


def test_defaults_match_the_specification():
    settings = Settings(_env_file=None)
    assert settings.host == "127.0.0.1"
    assert settings.port == 8080
    assert settings.target_lang == "Russian"
    assert settings.languages_config == Path.home() / ".echo-words" / "languages.toml"
    assert settings.data_dir == Path.home() / ".echo-words"
    assert settings.static_dir == REPO_ROOT / "_static"
    assert settings.llmbroker_operation == "vocab"
    assert settings.api_model == "gpt-fast"
    assert settings.api_daily_cap == 100
    assert settings.anki_sync is True
    assert settings.audio_timeout == 10


def test_the_deployment_secrets_file_is_never_read_by_the_app():
    # systemd hands .deploy/.env to the server; reading it locally would point
    # a dev box at the production AnkiWeb account.
    assert ENV_FILE == REPO_ROOT / ".env"


def test_the_data_dir_carries_its_children(tmp_path: Path):
    settings = Settings(_env_file=None, data_dir=tmp_path)
    assert settings.llmbroker_home == tmp_path / "llmbroker"
    assert settings.languages_config == tmp_path / "languages.toml"


def test_the_data_dir_children_can_be_set_apart(tmp_path: Path):
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path,
        llmbroker_home=tmp_path / "broker",
        languages_config=tmp_path / "elsewhere.toml",
    )
    assert settings.llmbroker_home == tmp_path / "broker"
    assert settings.languages_config == tmp_path / "elsewhere.toml"


def test_the_data_dir_env_var_alone_moves_its_children(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("ECHOWORDS_DATA_DIR", str(tmp_path))
    settings = Settings(_env_file=None)
    assert settings.languages_config == tmp_path / "languages.toml"
    assert settings.llmbroker_home == tmp_path / "llmbroker"


@pytest.mark.parametrize(
    ("accent", "voice"),
    [("us", "en-US-AriaNeural"), ("uk", "en-GB-SoniaNeural")],
)
def test_the_default_edge_voice_follows_the_accent(accent, voice):
    assert Settings(_env_file=None, accent=accent).edge_tts_voice == voice


def test_an_explicit_edge_voice_wins():
    settings = Settings(_env_file=None, accent="uk", edge_tts_voice="sr-RS-SophieNeural")
    assert settings.edge_tts_voice == "sr-RS-SophieNeural"


def test_the_environment_prefix_is_echowords(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("ECHOWORDS_PORT", "9001")
    monkeypatch.setenv("ECHOWORDS_LANGUAGES_CONFIG", str(tmp_path / "languages.toml"))
    settings = Settings(_env_file=None)
    assert settings.port == 9001
    assert settings.languages_config == tmp_path / "languages.toml"


def test_the_documented_target_code_becomes_the_prompt_display_name():
    assert Settings(_env_file=None, target_lang="ru").target_lang == "Russian"
    assert Settings(_env_file=None, target_lang="Italian").target_lang == "Italian"
