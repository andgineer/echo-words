import asyncio
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fakes import FakeBroker
from fastapi.testclient import TestClient

from echo_words import __version__
from echo_words.api import create_app
from echo_words.config import Settings
from echo_words.events import EventHub
from echo_words.languages import MAX_CONTEXT_LENGTH, MAX_WORD_LENGTH, LanguagesConfigError


class BlockingHandle:
    def __init__(self) -> None:
        self.llm_name = "waiting-model"
        self.started = threading.Event()
        self.release = threading.Event()
        self._iterator = self._stream()

    def __aiter__(self):
        return self._iterator

    async def _stream(self):
        self.started.set()
        yield "<b>part"
        while not self.release.is_set():
            await asyncio.sleep(0.01)
        yield "ial</b>"

    async def aclose(self):
        await self._iterator.aclose()

    async def record_quality(self, _score):
        return None


def submit(client: TestClient, **body):
    return client.post("/api/words", json={"lang": "en", **body})


def recent_entry(client: TestClient, entry_id: str):
    return next(
        entry for entry in client.get("/api/words/recent").json() if entry["entry_id"] == entry_id
    )


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
    assert list(body) == ["entry_id"]
    entry = recent_entry(client, body["entry_id"])
    assert entry["word"] == "receive"
    assert entry["lang"] == "en"
    assert entry["language"] == "English"
    assert entry["lookup_only"] is False
    assert entry["context"] == ""


def test_every_entry_gets_its_own_id(client: TestClient):
    first = submit(client, word="receive").json()["entry_id"]
    second = submit(client, word="receive").json()["entry_id"]
    assert first != second


def test_recent_words_contains_the_accumulated_text_while_a_word_is_in_progress(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
):
    handle = BlockingHandle()
    broker = FakeBroker(handles=[handle])
    monkeypatch.setattr("echo_words.api.create_broker", lambda *_args: broker)
    with TestClient(create_app(settings)) as live_client:
        entry_id = submit(live_client, word="partial").json()["entry_id"]
        assert handle.started.wait(timeout=1)
        deadline = time.monotonic() + 1
        recent = []
        while time.monotonic() < deadline:
            recent = live_client.get("/api/words/recent").json()
            if recent and recent[0]["text"]:
                break
            time.sleep(0.01)
        assert recent[0]["entry_id"] == entry_id
        assert recent[0]["status"] == "pending"
        assert recent[0]["text"] == "<b>part</b>"
        handle.release.set()


def test_question_mark_prefix_means_lookup_only(client: TestClient):
    entry_id = submit(client, word="? receive").json()["entry_id"]
    entry = recent_entry(client, entry_id)
    assert entry["word"] == "receive"
    assert entry["lookup_only"] is True


def test_lookup_only_flag_is_honored(client: TestClient):
    entry_id = submit(client, word="receive", lookup_only=True).json()["entry_id"]
    assert recent_entry(client, entry_id)["lookup_only"] is True


def test_context_travels_with_the_word_sanitized(client: TestClient):
    entry_id = submit(client, word="bucket", context="  he kicked  the\tbucket ").json()["entry_id"]
    entry = recent_entry(client, entry_id)
    assert entry["word"] == "bucket"
    assert entry["context"] == "he kicked the bucket"


def test_context_is_capped(client: TestClient):
    entry_id = submit(client, word="bucket", context="x" * (MAX_CONTEXT_LENGTH + 100)).json()[
        "entry_id"
    ]
    assert len(recent_entry(client, entry_id)["context"]) == MAX_CONTEXT_LENGTH


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


def test_audio_endpoint_serves_only_generated_bare_filenames(
    client: TestClient,
    settings: Settings,
):
    audio_dir = settings.data_dir / "audio"
    audio_dir.mkdir(parents=True)
    name = "pronunciation-aabbccddeeff00112233.mp3"
    (audio_dir / name).write_bytes(b"mp3")

    response = client.get(f"/api/audio/{name}")

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.content == b"mp3"
    assert client.get("/api/audio/not-generated.mp3").status_code == 404
    assert client.get("/api/audio/%2E%2E%2Fsecret").status_code == 404


def test_app_starts_without_a_built_page(settings: Settings, tmp_path: Path):
    app = create_app(settings.model_copy(update={"static_dir": tmp_path / "never-built"}))
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/").status_code == 404


def test_missing_languages_config_stops_the_startup(tmp_path: Path):
    app = create_app(Settings(_env_file=None, languages_config=tmp_path / "absent.toml"))
    with pytest.raises(LanguagesConfigError), TestClient(app):
        pass  # pragma: no cover


def test_unexpected_voice_provisioning_failure_never_breaks_shutdown(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    caplog: pytest.LogCaptureFixture,
):
    async def fail_voice_provisioning(*_args, **_kwargs):
        raise RuntimeError("unexpected provisioning fault")

    monkeypatch.setattr("echo_words.api.prepare_configured_voices", fail_voice_provisioning)

    with TestClient(create_app(settings)) as live_client:
        assert live_client.get("/api/health").status_code == 200

    assert "Piper voice provisioning failed unexpectedly" in caplog.text


@pytest.mark.anyio
async def test_sse_endpoint_frames_events_keeps_alive_and_cleans_up_subscribers(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
):
    monkeypatch.setattr("echo_words.api.SSE_KEEP_ALIVE_SECONDS", 0.001)
    hub = EventHub()
    app = create_app(settings)
    route = next(route for route in app.routes if getattr(route, "path", None) == "/api/events")
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(events=hub)))
    response = await route.endpoint(request)

    assert response.media_type == "text/event-stream"
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"

    stream = response.body_iterator
    assert await anext(stream) == ": keep-alive\n\n"
    assert hub.subscriber_count == 1
    await hub.publish("update", {"entry_id": "one", "text": "слово"})
    assert await anext(stream) == ('event: update\ndata: {"entry_id":"one","text":"слово"}\n\n')

    await stream.aclose()
    assert hub.subscriber_count == 0
