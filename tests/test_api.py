from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from echo_words import __version__
from echo_words.api import create_app
from echo_words.config import Settings
from echo_words.languages import MAX_CONTEXT_LENGTH, MAX_WORD_LENGTH, LanguagesConfigError


def submit(client: TestClient, **body):
    return client.post("/api/words", json={"lang": "en", **body})


def test_health_answers_without_any_backend(client: TestClient):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_languages_feed_the_selector(client: TestClient):
    response = client.get("/api/languages")
    assert response.status_code == 200
    assert response.json() == [
        {"code": "en", "name": "English"},
        {"code": "de", "name": "Deutsch"},
        {"code": "sr", "name": "Српски"},
    ]


def test_accepted_submission_names_the_resolved_language(client: TestClient):
    response = submit(client, word="receive")
    assert response.status_code == 200
    body = response.json()
    assert body["entry_id"]
    assert body["word"] == "receive"
    assert body["lang"] == "en"
    assert body["language"] == "English"
    assert body["lookup_only"] is False
    assert body["context"] == ""


def test_every_entry_gets_its_own_id(client: TestClient):
    first = submit(client, word="receive").json()["entry_id"]
    second = submit(client, word="receive").json()["entry_id"]
    assert first != second


def test_question_mark_prefix_means_lookup_only(client: TestClient):
    body = submit(client, word="? receive").json()
    assert body["word"] == "receive"
    assert body["lookup_only"] is True


def test_lookup_only_flag_is_honored(client: TestClient):
    assert submit(client, word="receive", lookup_only=True).json()["lookup_only"] is True


def test_context_travels_with_the_word_sanitized(client: TestClient):
    body = submit(client, word="bucket", context="  he kicked  the\tbucket ").json()
    assert body["word"] == "bucket"
    assert body["context"] == "he kicked the bucket"


def test_context_is_capped(client: TestClient):
    body = submit(client, word="bucket", context="x" * (MAX_CONTEXT_LENGTH + 100)).json()
    assert len(body["context"]) == MAX_CONTEXT_LENGTH


def test_unknown_language_gets_a_hint_and_no_processing(client: TestClient):
    response = submit(client, word="bonjour", lang="fr")
    assert response.status_code == 400
    assert response.json()["detail"] == "Неизвестный язык «fr» — выберите язык из списка."


def test_the_word_is_validated_for_the_selected_language(client: TestClient):
    response = submit(client, word="слово", lang="en")
    assert response.status_code == 400
    assert response.json()["detail"] == "Для «English» нужна латиница."


def test_serbian_takes_cyrillic(client: TestClient):
    assert submit(client, word="Београд", lang="sr").status_code == 200


def test_an_absurd_body_is_refused_before_the_hints(client: TestClient):
    response = submit(client, word="x" * (MAX_WORD_LENGTH * 4 + 1))
    assert response.status_code == 422
    huge_context = submit(client, word="bucket", context="x" * (MAX_CONTEXT_LENGTH * 4 + 1))
    assert huge_context.status_code == 422


def test_a_merely_long_word_still_gets_the_short_hint(client: TestClient):
    response = submit(client, word="a" * (MAX_WORD_LENGTH + 1))
    assert response.status_code == 400
    assert response.json()["detail"].startswith("Слишком длинно")


def test_empty_word_gets_a_hint(client: TestClient):
    response = submit(client, word="   ")
    assert response.status_code == 400
    assert response.json()["detail"] == "Введите слово."


def test_built_page_is_served_at_the_root(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    assert "echo-words" in response.text


def test_app_starts_without_a_built_page(settings: Settings, tmp_path: Path):
    app = create_app(settings.model_copy(update={"static_dir": tmp_path / "never-built"}))
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/").status_code == 404


def test_missing_languages_config_stops_the_startup(tmp_path: Path):
    app = create_app(Settings(_env_file=None, languages_config=tmp_path / "absent.toml"))
    with pytest.raises(LanguagesConfigError), TestClient(app):
        pass  # pragma: no cover
