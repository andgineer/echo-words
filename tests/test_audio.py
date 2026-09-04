import asyncio
import hashlib
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from echo_words import audio
from echo_words.languages import Language

pytestmark = pytest.mark.anyio


def mock_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_dictionary_recording_prefers_the_configured_english_accent(
    languages,
    settings,
    monkeypatch,
):
    requested = []

    def handler(request):
        requested.append(str(request.url))
        if "/entries/en/word" in request.url.path:
            return httpx.Response(
                200,
                json=[
                    {
                        "phonetics": [
                            {"audio": "https://cdn.example/word-uk.mp3"},
                            {"audio": "https://cdn.example/word-us.mp3"},
                        ],
                    },
                ],
            )
        return httpx.Response(200, content=b"dictionary mp3")

    piper = AsyncMock(side_effect=AssertionError("Piper must not run after a hit"))
    edge = AsyncMock(side_effect=AssertionError("edge must not run after a hit"))
    monkeypatch.setattr(audio, "_piper_audio", piper)
    monkeypatch.setattr(audio, "_edge_audio", edge)
    async with mock_client(handler) as client:
        result = await audio.fetch_pronunciation(
            "word",
            languages["en"],
            settings=settings,
            client=client,
        )

    assert result is not None
    assert result.read_bytes() == b"dictionary mp3"
    assert requested[-1] == "https://cdn.example/word-us.mp3"
    piper.assert_not_awaited()
    edge.assert_not_awaited()


async def test_dictionary_miss_and_http_error_fall_through_to_piper(
    languages,
    settings,
    monkeypatch,
):
    async def fake_piper(_word, _lang, output, _settings):
        output.write_bytes(b"piper")
        return True

    monkeypatch.setattr(audio, "_piper_audio", fake_piper)
    monkeypatch.setattr(
        audio,
        "_edge_audio",
        AsyncMock(side_effect=AssertionError("edge must not run after Piper")),
    )
    for status in (404, 503):
        word = f"word-{status}"

        def handler(_request, response_status=status):
            return httpx.Response(response_status, json=[])

        async with mock_client(handler) as client:
            result = await audio.fetch_pronunciation(
                word,
                languages["en"],
                settings=settings,
                client=client,
            )
        assert result is not None
        assert result.read_bytes() == b"piper"


async def test_fake_piper_synthesizes_wav_and_encodes_mp3(
    languages,
    settings,
    monkeypatch,
):
    voice_name = languages["en"].tts_voice
    assert voice_name is not None
    models = settings.data_dir / "models"
    models.mkdir(parents=True)
    (models / f"{voice_name}.onnx").write_bytes(b"model")
    (models / f"{voice_name}.onnx.json").write_text("{}")

    class FakeVoice:
        @classmethod
        def load(cls, _model, *, config_path):
            assert config_path.endswith(".onnx.json")
            return cls()

        def synthesize_wav(self, _word, wav_file):
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(22050)
            wav_file.writeframes(b"\x00\x00" * 2205)

    monkeypatch.setitem(sys.modules, "piper", SimpleNamespace(PiperVoice=FakeVoice))
    monkeypatch.setattr(
        audio,
        "_edge_audio",
        AsyncMock(side_effect=AssertionError("edge must not run after Piper")),
    )
    language = replace(languages["en"], dict_api=None)
    async with mock_client(lambda _request: httpx.Response(500)) as client:
        result = await audio.fetch_pronunciation(
            "word",
            language,
            settings=settings,
            client=client,
        )

    assert result is not None
    assert result.read_bytes()
    assert not result.read_bytes().startswith(b"RIFF")


async def test_piper_import_and_inference_failures_fall_through_to_edge(
    languages,
    settings,
    monkeypatch,
):
    voice_name = languages["en"].tts_voice
    assert voice_name is not None
    models = settings.data_dir / "models"
    models.mkdir(parents=True)
    (models / f"{voice_name}.onnx").write_bytes(b"model")
    (models / f"{voice_name}.onnx.json").write_text("{}")
    language = replace(languages["en"], dict_api=None)

    async def fake_edge(_word, _lang, output, _settings):
        output.write_bytes(b"edge")
        return True

    monkeypatch.setattr(audio, "_edge_audio", fake_edge)

    def fail_inference(*_args, **_kwargs):
        raise RuntimeError("inference failed")

    for piper_module in (
        None,
        SimpleNamespace(
            PiperVoice=SimpleNamespace(
                load=lambda *_args, **_kwargs: SimpleNamespace(
                    synthesize_wav=fail_inference,
                ),
            ),
        ),
    ):
        monkeypatch.setitem(sys.modules, "piper", piper_module)
        word = "import" if piper_module is None else "inference"
        async with mock_client(lambda _request: httpx.Response(500)) as client:
            result = await audio.fetch_pronunciation(
                word,
                language,
                settings=settings,
                client=client,
            )
        assert result is not None
        assert result.read_bytes() == b"edge"


async def test_edge_language_and_phrase_skip_earlier_chain_steps(
    languages,
    settings,
    monkeypatch,
):
    dictionary = AsyncMock(side_effect=AssertionError("dictionary must be skipped"))
    piper = AsyncMock(side_effect=AssertionError("Piper must be skipped"))

    async def fake_edge(_word, _lang, output, _settings):
        output.write_bytes(b"edge")
        return True

    monkeypatch.setattr(audio, "_dictionary_audio", dictionary)
    monkeypatch.setattr(audio, "_piper_audio", piper)
    monkeypatch.setattr(audio, "_edge_audio", fake_edge)
    async with mock_client(lambda _request: httpx.Response(500)) as client:
        serbian = await audio.fetch_pronunciation(
            "реч",
            languages["sr"],
            settings=settings,
            client=client,
        )
        phrase = await audio.fetch_pronunciation(
            "two words",
            replace(languages["en"], tts="edge"),
            settings=settings,
            client=client,
        )

    assert serbian is not None and serbian.read_bytes() == b"edge"
    assert phrase is not None and phrase.read_bytes() == b"edge"
    dictionary.assert_not_awaited()
    piper.assert_not_awaited()


async def test_edge_tts_uses_language_voice_and_returns_none_on_failure(
    languages,
    settings,
    monkeypatch,
):
    calls = []

    class FakeCommunicate:
        def __init__(self, word, voice):
            calls.append((word, voice))

        async def save(self, path):
            if calls[-1][0] == "провал":
                raise RuntimeError("offline")
            Path(path).write_bytes(b"edge mp3")

    monkeypatch.setattr(audio.edge_tts, "Communicate", FakeCommunicate)
    async with mock_client(lambda _request: httpx.Response(500)) as client:
        success = await audio.fetch_pronunciation(
            "успех",
            languages["sr"],
            settings=settings,
            client=client,
        )
        failure = await audio.fetch_pronunciation(
            "провал",
            languages["sr"],
            settings=settings,
            client=client,
        )

    assert success is not None and success.read_bytes() == b"edge mp3"
    assert failure is None
    assert calls == [
        ("успех", "sr-RS-SophieNeural"),
        ("провал", "sr-RS-SophieNeural"),
    ]


async def test_a_language_with_no_voice_of_its_own_is_silent_rather_than_english(
    settings,
    monkeypatch,
):
    """The default voice speaks English. Lending it to a language that has no voice
    would card the word read as if it were English, which is worse than no recording."""
    calls = []

    class FakeCommunicate:
        def __init__(self, word, voice):
            calls.append((word, voice))

        async def save(self, path):
            Path(path).write_bytes(b"edge mp3")

    monkeypatch.setattr(audio.edge_tts, "Communicate", FakeCommunicate)
    bulgarian = Language(code="bg", name="Български", deck="d", script="cyrillic")
    async with mock_client(lambda _request: httpx.Response(500)) as client:
        silent = await audio.fetch_pronunciation(
            "здравей",
            bulgarian,
            settings=settings,
            client=client,
        )
        english = await audio.fetch_pronunciation(
            "hello",
            Language(code="en", name="English", deck="d", script="latin"),
            settings=settings,
            client=client,
        )

    assert silent is None
    # The accent's default voice is still the one English itself falls back on.
    assert english is not None
    assert calls == [("hello", settings.edge_tts_voice)]


async def test_a_cyrillic_locale_voice_is_never_handed_latin(
    languages,
    settings,
    monkeypatch,
):
    calls = []

    class FakeCommunicate:
        def __init__(self, word, voice):
            calls.append((word, voice))

        async def save(self, path):
            Path(path).write_bytes(b"edge mp3")

    monkeypatch.setattr(audio.edge_tts, "Communicate", FakeCommunicate)
    async with mock_client(lambda _request: httpx.Response(500)) as client:
        for word in ("haljina", "хаљина", "džemper", "Njiva", "kuća đak žena šest"):
            assert await audio.fetch_pronunciation(
                word,
                languages["sr"],
                settings=settings,
                client=client,
            )
        assert await audio.fetch_pronunciation(
            "wardrobe",
            replace(languages["en"], tts="edge", dict_api=None),
            settings=settings,
            client=client,
        )

    assert calls == [
        ("хаљина", "sr-RS-SophieNeural"),
        ("хаљина", "sr-RS-SophieNeural"),
        ("џемпер", "sr-RS-SophieNeural"),
        ("Њива", "sr-RS-SophieNeural"),
        ("кућа ђак жена шест", "sr-RS-SophieNeural"),
        ("wardrobe", "en-US-AriaNeural"),
    ]


async def test_a_voice_is_loaded_once_and_reused_for_every_later_word(
    languages,
    settings,
    monkeypatch,
):
    """Loading a voice costs seconds and synthesizing with a loaded one costs a
    fraction of a second: paying the load per word puts audio outside its deadline."""
    voice_name = languages["en"].tts_voice
    assert voice_name is not None
    models = settings.data_dir / "models"
    models.mkdir(parents=True)
    (models / f"{voice_name}.onnx").write_bytes(b"model")
    (models / f"{voice_name}.onnx.json").write_text("{}")
    loads = []

    class FakeVoice:
        @classmethod
        def load(cls, model, *, config_path):
            loads.append((model, config_path))
            return cls()

        def synthesize_wav(self, _word, wav_file):
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(22050)
            wav_file.writeframes(b"\x00\x00" * 2205)

    monkeypatch.setitem(sys.modules, "piper", SimpleNamespace(PiperVoice=FakeVoice))
    language = replace(languages["en"], dict_api=None)
    async with mock_client(lambda _request: httpx.Response(500)) as client:
        for word in ("first", "second"):
            result = await audio.fetch_pronunciation(
                word,
                language,
                settings=settings,
                client=client,
            )
            assert result is not None and result.read_bytes()

    assert len(loads) == 1


async def test_one_shared_voice_synthesizes_one_word_at_a_time(
    languages,
    settings,
    monkeypatch,
):
    """Three audio roles resolve concurrently through one cached voice, and espeak-ng
    underneath it keeps process-global state."""
    voice_name = languages["en"].tts_voice
    assert voice_name is not None
    models = settings.data_dir / "models"
    models.mkdir(parents=True)
    (models / f"{voice_name}.onnx").write_bytes(b"model")
    (models / f"{voice_name}.onnx.json").write_text("{}")
    active = []
    counting = threading.Lock()
    overlapped = threading.Event()

    class FakeVoice:
        @classmethod
        def load(cls, _model, *, config_path=None):  # noqa: ARG003 - matches Piper's signature.
            return cls()

        def synthesize_wav(self, word, wav_file):
            with counting:
                active.append(word)
                if len(active) > 1:
                    overlapped.set()
            time.sleep(0.02)
            with counting:
                active.remove(word)
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(22050)
            wav_file.writeframes(b"\x00\x00" * 2205)

    monkeypatch.setitem(sys.modules, "piper", SimpleNamespace(PiperVoice=FakeVoice))
    language = replace(languages["en"], dict_api=None)

    async with mock_client(lambda _request: httpx.Response(500)) as client:
        results = await asyncio.gather(
            *(
                audio.fetch_pronunciation(word, language, settings=settings, client=client)
                for word in ("first", "second", "third")
            ),
        )

    assert all(result is not None for result in results)
    assert not overlapped.is_set()


async def test_voice_preparation_loads_what_it_installed(
    languages,
    settings,
    monkeypatch,
):
    """The first word after a restart must not pay the load inside its own deadline."""
    contents = {"https://voices/model": b"model", "https://voices/config": b"config"}
    files = audio.PiperVoiceFiles(
        model=audio.VoiceFile(
            ".onnx",
            "https://voices/model",
            hashlib.sha256(contents["https://voices/model"]).hexdigest(),
        ),
        config=audio.VoiceFile(
            ".onnx.json",
            "https://voices/config",
            hashlib.sha256(contents["https://voices/config"]).hexdigest(),
        ),
    )
    monkeypatch.setattr(audio, "PIPER_VOICES", {"configured": files})
    loaded = []

    def fake_load(model, *, config_path):
        loaded.append((model, config_path))
        return SimpleNamespace()

    monkeypatch.setitem(
        sys.modules,
        "piper",
        SimpleNamespace(PiperVoice=SimpleNamespace(load=fake_load)),
    )
    configured = replace(languages["en"], tts_voice="configured")

    def handler(request):
        return httpx.Response(200, content=contents[str(request.url)])

    async with mock_client(handler) as client:
        await audio.prepare_configured_voices(
            [configured, languages["sr"]],
            settings,
            client=client,
        )

    models = settings.data_dir / "models"
    assert loaded == [(str(models / "configured.onnx"), str(models / "configured.onnx.json"))]


async def test_a_voice_that_cannot_be_installed_is_never_loaded(
    languages,
    settings,
    monkeypatch,
):
    monkeypatch.setattr(
        audio,
        "_install_voice_file",
        AsyncMock(side_effect=RuntimeError("download failed")),
    )
    monkeypatch.setattr(
        audio,
        "_load_voice",
        lambda *_args: pytest.fail("a voice with no files on disk cannot be loaded"),
    )

    async with mock_client(lambda _request: httpx.Response(500)) as client:
        await audio.prepare_configured_voices([languages["en"]], settings, client=client)


async def test_voice_preparation_fetches_only_configured_piper_files(
    languages,
    settings,
    monkeypatch,
):
    contents = {"https://voices/model": b"model", "https://voices/config": b"config"}
    files = audio.PiperVoiceFiles(
        model=audio.VoiceFile(
            ".onnx",
            "https://voices/model",
            hashlib.sha256(contents["https://voices/model"]).hexdigest(),
        ),
        config=audio.VoiceFile(
            ".onnx.json",
            "https://voices/config",
            hashlib.sha256(contents["https://voices/config"]).hexdigest(),
        ),
    )
    monkeypatch.setattr(audio, "PIPER_VOICES", {"configured": files})
    configured = replace(languages["en"], tts_voice="configured")
    requested = []

    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(200, content=contents[str(request.url)])

    async with mock_client(handler) as client:
        await audio.prepare_configured_voices(
            [configured, languages["sr"]],
            settings,
            client=client,
        )

    assert requested == ["https://voices/model", "https://voices/config"]
    assert (settings.data_dir / "models" / "configured.onnx").read_bytes() == b"model"
    assert (settings.data_dir / "models" / "configured.onnx.json").read_bytes() == b"config"


async def test_voice_preparation_follows_hugging_face_resolve_redirects(
    languages,
    settings,
    monkeypatch,
):
    model = b"redirected model"
    config = b"redirected config"
    files = audio.PiperVoiceFiles(
        model=audio.VoiceFile(
            ".onnx",
            "https://huggingface.co/voice.onnx",
            hashlib.sha256(model).hexdigest(),
        ),
        config=audio.VoiceFile(
            ".onnx.json",
            "https://huggingface.co/voice.onnx.json",
            hashlib.sha256(config).hexdigest(),
        ),
    )
    monkeypatch.setattr(audio, "PIPER_VOICES", {"configured": files})
    configured = replace(languages["en"], tts_voice="configured")
    requested = []

    def handler(request):
        requested.append(str(request.url))
        if request.url.host == "huggingface.co":
            return httpx.Response(
                302,
                headers={"Location": f"https://cdn.example{request.url.path}"},
            )
        content = config if request.url.path.endswith(".json") else model
        return httpx.Response(200, content=content)

    # Deliberately leave the client's default follow_redirects=False. Provisioning
    # must opt in for each Hugging Face /resolve request itself.
    async with mock_client(handler) as client:
        await audio.prepare_configured_voices([configured], settings, client=client)

    assert requested == [
        "https://huggingface.co/voice.onnx",
        "https://cdn.example/voice.onnx",
        "https://huggingface.co/voice.onnx.json",
        "https://cdn.example/voice.onnx.json",
    ]
    assert (settings.data_dir / "models" / "configured.onnx").read_bytes() == model
    assert (settings.data_dir / "models" / "configured.onnx.json").read_bytes() == config


async def test_bad_voice_checksum_never_installs_the_temporary_file(
    languages,
    settings,
    monkeypatch,
):
    files = audio.PiperVoiceFiles(
        model=audio.VoiceFile(".onnx", "https://voices/bad", "0" * 64),
        config=audio.VoiceFile(".onnx.json", "https://voices/config", "0" * 64),
    )
    monkeypatch.setattr(audio, "PIPER_VOICES", {"configured": files})
    configured = replace(languages["en"], tts_voice="configured")
    async with mock_client(lambda _request: httpx.Response(200, content=b"wrong")) as client:
        await audio.prepare_configured_voices([configured], settings, client=client)

    models = settings.data_dir / "models"
    assert not (models / "configured.onnx").exists()
    assert list(models.iterdir()) == []


async def test_voice_preparation_degrades_when_the_model_directory_cannot_be_created(
    languages,
    settings,
    tmp_path,
    caplog,
):
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("file")
    broken_settings = settings.model_copy(update={"data_dir": blocked})

    await audio.prepare_configured_voices(languages.values(), broken_settings)

    assert "could not prepare Piper voices" in caplog.text


async def test_voice_preparation_degrades_when_the_http_client_cannot_be_created(
    languages,
    settings,
    monkeypatch,
    caplog,
):
    def fail_client(**_kwargs):
        raise RuntimeError("client setup failed")

    monkeypatch.setattr(audio.httpx, "AsyncClient", fail_client)

    await audio.prepare_configured_voices(languages.values(), settings)

    assert "could not prepare Piper voices: client setup failed" in caplog.text


async def test_cancelled_piper_inference_cannot_publish_late_audio(
    languages,
    settings,
    monkeypatch,
):
    voice_name = languages["en"].tts_voice
    assert voice_name is not None
    models = settings.data_dir / "models"
    models.mkdir(parents=True)
    (models / f"{voice_name}.onnx").write_bytes(b"model")
    (models / f"{voice_name}.onnx.json").write_text("{}")
    language = replace(languages["en"], dict_api=None)
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def slow_synthesis(_word, _model, _config):
        started.set()
        release.wait(timeout=1)
        finished.set()
        return b"late mp3"

    monkeypatch.setattr(audio, "_synthesize_piper", slow_synthesis)
    task = asyncio.create_task(
        audio.fetch_pronunciation("late", language, settings=settings),
    )
    try:
        assert await asyncio.to_thread(started.wait, 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        release.set()

    assert await asyncio.to_thread(finished.wait, 1)
    assert list((settings.data_dir / "audio").glob("pronunciation-*.mp3")) == []
