import asyncio
import hashlib
import logging
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


COMMONS = "https://upload.wikimedia.org/wikipedia/commons/transcoded"


async def test_a_commons_recording_is_used_before_the_local_voice(
    languages,
    settings,
    monkeypatch,
):
    piper = AsyncMock(side_effect=AssertionError("Piper must not run after a hit"))
    edge = AsyncMock(side_effect=AssertionError("edge must not run after a hit"))
    monkeypatch.setattr(audio, "_piper_audio", piper)
    monkeypatch.setattr(audio, "_edge_audio", edge)

    async with mock_client(lambda _request: httpx.Response(200, content=b"commons mp3")) as client:
        result = await audio.fetch_pronunciation(
            "word",
            languages["en"],
            settings=settings,
            client=client,
        )

    assert result is not None
    assert result.read_bytes() == b"commons mp3"
    piper.assert_not_awaited()
    edge.assert_not_awaited()


async def test_the_commons_url_is_derived_from_the_file_name_md5(
    languages,
    settings,
    monkeypatch,
):
    """Commons files a recording under two directories taken from the md5 of its name,
    so the recording is reached without asking an API where it is."""
    requested = []

    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(200, content=b"commons mp3")

    monkeypatch.setattr(
        audio,
        "_piper_audio",
        AsyncMock(side_effect=AssertionError("Piper must not run after a hit")),
    )
    async with mock_client(handler) as client:
        await audio.fetch_pronunciation(
            "schneiden",
            languages["de"],
            settings=settings,
            client=client,
        )

    assert requested == [f"{COMMONS}/4/4c/De-schneiden.ogg/De-schneiden.ogg.mp3"]


@pytest.mark.parametrize(
    ("code", "prefix", "word", "directories", "escaped"),
    [
        ("ru", "Ru", "дом", "1/16", "Ru-%D0%B4%D0%BE%D0%BC.ogg"),
        ("pt", "Pt-br", "água", "6/6d", "Pt-br-%C3%A1gua.ogg"),
    ],
)
async def test_the_commons_directories_hash_the_name_before_it_is_escaped(
    languages,
    settings,
    monkeypatch,
    code,
    prefix,
    word,
    escaped,
    directories,
):
    """Commons hashes the file name itself, never its percent-encoded spelling.
    Digesting the escaped name sends every accented and Cyrillic word to a path
    that answers 404, which the chain cannot tell from a word Commons lacks."""
    requested = []

    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(200, content=b"commons mp3")

    monkeypatch.setattr(
        audio,
        "_piper_audio",
        AsyncMock(side_effect=AssertionError("Piper must not run after a hit")),
    )
    language = replace(languages["de"], code=code, recordings=prefix)
    async with mock_client(handler) as client:
        await audio.fetch_pronunciation(word, language, settings=settings, client=client)

    assert requested == [f"{COMMONS}/{directories}/{escaped}/{escaped}.mp3"]


async def test_a_word_commons_does_not_have_falls_through_to_the_voice(
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

    async with mock_client(lambda _request: httpx.Response(404)) as client:
        result = await audio.fetch_pronunciation(
            "blorptium",
            languages["de"],
            settings=settings,
            client=client,
        )

    assert result is not None
    assert result.read_bytes() == b"piper"


async def test_a_throttled_commons_leaves_the_word_to_the_voice(
    languages,
    settings,
    monkeypatch,
):
    """A throttle is not retried inside the deadline the answer waits on: the voice
    speaks the word instead, and its recording is what the cache keeps."""
    requested = []

    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(429)

    async def fake_piper(_word, _lang, output, _settings):
        output.write_bytes(b"piper")
        return True

    monkeypatch.setattr(audio, "_piper_audio", fake_piper)
    async with mock_client(handler) as client:
        result = await audio.fetch_pronunciation(
            "Haus",
            languages["de"],
            settings=settings,
            client=client,
        )

    assert result is not None
    assert result.read_bytes() == b"piper"
    assert len(requested) == 1


def _mp3_with_rate(path, rate, *, id3=False):
    version, index = (3, {44100: 0, 48000: 1, 32000: 2}.get(rate, 0)), 0
    if rate in (22050, 24000, 16000):
        version = (2, {22050: 0, 24000: 1, 16000: 2}[rate])
    header = bytes(
        [
            0xFF,
            0xE0 | (version[0] << 3) | 0x02,
            0x90 | (version[1] << 2),
            0x00,
        ],
    )
    tag = b"ID3\x04\x00\x00\x00\x00\x00\x05" + b"\x00" * 5 if id3 else b""
    path.write_bytes(tag + header + b"\x00" * 64)
    return path


@pytest.mark.parametrize(
    ("rate", "human"),
    [(44100, True), (48000, True), (32000, True), (24000, False), (22050, False)],
)
def test_a_recording_is_told_from_a_synthesized_one_by_its_rate(tmp_path, rate, human):
    """The engines synthesize at their own fixed rates and a Commons transcode carries
    the source's, so a word the throttle cost a recording can be found again."""
    assert audio.is_human_recording(_mp3_with_rate(tmp_path / f"{rate}.mp3", rate)) is human


def test_an_id3_tag_does_not_hide_the_rate(tmp_path):
    """Commons' own transcodes carry one, so reading the first frame naively finds none."""
    tagged = _mp3_with_rate(tmp_path / "tagged.mp3", 44100, id3=True)

    assert audio.is_human_recording(tagged) is True


def test_an_unreadable_file_is_not_taken_for_a_recording(tmp_path):
    empty = tmp_path / "empty.mp3"
    empty.write_bytes(b"")

    assert audio.is_human_recording(empty) is False


async def test_a_refreshed_fetch_asks_again_for_a_word_the_voice_already_spoke(
    languages,
    settings,
    monkeypatch,
):
    """The voice writes at the cache path, so a throttled word is answered from disk for
    ever unless the cache is discarded first."""
    requested = []

    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(200, content=b"commons mp3")

    monkeypatch.setattr(
        audio,
        "_piper_audio",
        AsyncMock(side_effect=AssertionError("Piper must not run after a hit")),
    )
    cached = audio._audio_path("Haus", languages["de"], settings)
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_bytes(b"piper")

    async with mock_client(handler) as client:
        kept = await audio.fetch_pronunciation(
            "Haus",
            languages["de"],
            settings=settings,
            client=client,
        )
        assert kept is not None
        assert kept.read_bytes() == b"piper"
        assert requested == []

        refreshed = await audio.fetch_pronunciation(
            "Haus",
            languages["de"],
            settings=settings,
            client=client,
            refresh=True,
        )

    assert refreshed is not None
    assert refreshed.read_bytes() == b"commons mp3"
    assert len(requested) == 1


@pytest.mark.parametrize("extension", ["oga", "wav"])
async def test_a_recording_filed_under_another_extension_is_still_found(
    languages,
    settings,
    monkeypatch,
    extension,
):
    """A word uploaded as .oga or .wav is published under that name and nowhere else,
    so asking only for the .ogg counts a recording Commons holds as an absence."""
    requested = []

    def handler(request):
        url = str(request.url)
        requested.append(url)
        if f".{extension}/" in url:
            return httpx.Response(200, content=b"commons mp3")
        return httpx.Response(404)

    monkeypatch.setattr(
        audio,
        "_piper_audio",
        AsyncMock(side_effect=AssertionError("Piper must not run after a hit")),
    )
    async with mock_client(handler) as client:
        result = await audio.fetch_pronunciation(
            "casa",
            replace(languages["de"], code="pt", recordings="Pt-br"),
            settings=settings,
            client=client,
        )

    assert result is not None
    assert result.read_bytes() == b"commons mp3"
    assert [url.split("/")[-1] for url in requested[:1]] == ["Pt-br-casa.ogg.mp3"]
    assert any(f".{extension}/" in url for url in requested)


async def test_the_other_names_are_asked_only_when_the_ogg_misses(
    languages,
    settings,
    monkeypatch,
):
    """The words that answer first time are the common case, and they must not pay a
    round trip for a coverage gap they do not have."""
    requested = []

    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(200, content=b"commons mp3")

    monkeypatch.setattr(
        audio,
        "_piper_audio",
        AsyncMock(side_effect=AssertionError("Piper must not run after a hit")),
    )
    async with mock_client(handler) as client:
        await audio.fetch_pronunciation("Haus", languages["de"], settings=settings, client=client)

    assert requested == [f"{COMMONS}/7/7e/De-Haus.ogg/De-Haus.ogg.mp3"]


async def test_a_word_under_none_of_the_names_falls_through_to_the_voice(
    languages,
    settings,
    monkeypatch,
    caplog,
):
    requested = []

    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(404)

    async def fake_piper(_word, _lang, output, _settings):
        output.write_bytes(b"piper")
        return True

    monkeypatch.setattr(audio, "_piper_audio", fake_piper)
    caplog.set_level(logging.INFO, logger="echo_words")
    async with mock_client(handler) as client:
        result = await audio.fetch_pronunciation(
            "blorptium",
            languages["de"],
            settings=settings,
            client=client,
        )

    assert result is not None
    assert result.read_bytes() == b"piper"
    assert len(requested) == 3
    miss = [record for record in caplog.records if "no Commons recording" in record.message]
    assert len(miss) == 1
    assert miss[0].levelno == logging.INFO
    assert "ogg HTTP 404, oga HTTP 404, wav HTTP 404" in miss[0].getMessage()


@pytest.mark.parametrize(
    ("status", "level"),
    [
        (404, logging.INFO),
        (429, logging.WARNING),
        (503, logging.WARNING),
    ],
)
async def test_only_an_unexpected_commons_answer_is_worth_a_warning(
    languages,
    settings,
    monkeypatch,
    caplog,
    status,
    level,
):
    """Commons has no recording of a good share of the ordinary words of several
    configured languages, so warning on that would warn in normal operation and stop
    telling the operator anything about the throttles and outages the log is kept for."""

    async def fake_piper(_word, _lang, output, _settings):
        output.write_bytes(b"piper")
        return True

    monkeypatch.setattr(audio, "_piper_audio", fake_piper)
    with caplog.at_level(logging.INFO, logger=audio.logger.name):
        async with mock_client(lambda _request: httpx.Response(status)) as client:
            await audio.fetch_pronunciation(
                "Haus",
                languages["de"],
                settings=settings,
                client=client,
            )

    missed = [record for record in caplog.records if "no Commons recording" in record.getMessage()]
    assert [record.levelno for record in missed] == [level]
    assert [str(status) in record.getMessage() for record in missed] == [True]


async def test_a_commons_that_never_answers_leaves_the_word_to_the_voice(
    languages,
    settings,
    monkeypatch,
):
    """Spending the step's deadline is not a failure of the answer: a connection that
    never completes falls through as quietly as a word Commons does not have, and
    leaves the cache to whichever step does speak the word."""

    def handler(_request):
        raise httpx.ConnectTimeout("Commons did not answer")

    async def fake_piper(_word, _lang, output, _settings):
        output.write_bytes(b"piper")
        return True

    monkeypatch.setattr(audio, "_piper_audio", fake_piper)
    monkeypatch.setattr(
        audio,
        "_edge_audio",
        AsyncMock(side_effect=AssertionError("edge must not run after Piper")),
    )

    async with mock_client(handler) as client:
        result = await audio.fetch_pronunciation(
            "Haus",
            languages["de"],
            settings=settings,
            client=client,
        )

    assert result is not None
    assert result.read_bytes() == b"piper"
    assert list((settings.data_dir / "audio").glob("pronunciation-*.mp3")) == [result]


async def test_the_recording_step_spends_only_its_own_short_deadline(
    languages,
    settings,
    monkeypatch,
):
    """The whole point of the step is that it answers inside the deadline the answer
    waits on, so it is given seconds rather than the budget a background download has."""
    timeouts = []

    def handler(request):
        timeouts.append(request.extensions["timeout"])
        return httpx.Response(200, content=b"commons mp3")

    monkeypatch.setattr(
        audio,
        "_piper_audio",
        AsyncMock(side_effect=AssertionError("Piper must not run after a hit")),
    )
    async with mock_client(handler) as client:
        await audio.fetch_pronunciation("Haus", languages["de"], settings=settings, client=client)

    assert timeouts == [dict.fromkeys(("connect", "read", "write", "pool"), 3)]


async def test_a_voice_download_keeps_the_longer_budget_of_its_own(
    languages,
    settings,
    monkeypatch,
):
    """A voice is megabytes fetched in the background at startup, and nothing waits on
    it, so the recording step's few seconds must not be imposed on it."""
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
    timeouts = []

    def handler(request):
        timeouts.append(request.extensions["timeout"])
        return httpx.Response(200, content=contents[str(request.url)])

    async with mock_client(handler) as client:
        await audio.prepare_configured_voices(
            [replace(languages["en"], tts_voice="configured")],
            settings,
            client=client,
        )

    assert timeouts == [dict.fromkeys(("connect", "read", "write", "pool"), 10)] * 2


async def test_commons_is_not_asked_for_a_phrase(languages, settings, monkeypatch):
    """A headword carded with its article is not one word, and the recording of the
    bare noun would speak a text the card does not show."""
    requested = []

    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(200, content=b"commons mp3")

    async def fake_piper(_word, _lang, output, _settings):
        output.write_bytes(b"piper")
        return True

    monkeypatch.setattr(audio, "_piper_audio", fake_piper)
    async with mock_client(handler) as client:
        result = await audio.fetch_pronunciation(
            "die Zwiebel",
            languages["de"],
            settings=settings,
            client=client,
        )

    assert result is not None and result.read_bytes() == b"piper"
    assert requested == []


async def test_a_commons_request_names_the_app(languages, settings, monkeypatch):
    """Wikimedia's policy refuses a generic client agent, and httpx's default is one."""
    agents = []

    def handler(request):
        agents.append(request.headers.get("user-agent"))
        return httpx.Response(200, content=b"commons mp3")

    monkeypatch.setattr(
        audio,
        "_piper_audio",
        AsyncMock(side_effect=AssertionError("Piper must not run after a hit")),
    )
    async with mock_client(handler) as client:
        await audio.fetch_pronunciation("Haus", languages["de"], settings=settings, client=client)

    assert agents == [audio._USER_AGENT]
    assert agents[0].startswith("echo-words/")
    assert "github.com/andgineer/echo-words" in agents[0]


async def test_a_language_without_recordings_never_asks_commons(
    languages,
    settings,
    monkeypatch,
):
    requested = []

    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(200, content=b"commons mp3")

    async def fake_piper(_word, _lang, output, _settings):
        output.write_bytes(b"piper")
        return True

    monkeypatch.setattr(audio, "_piper_audio", fake_piper)
    async with mock_client(handler) as client:
        result = await audio.fetch_pronunciation(
            "Haus",
            replace(languages["de"], recordings=None),
            settings=settings,
            client=client,
        )

    assert result is not None and result.read_bytes() == b"piper"
    assert requested == []


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
    language = replace(languages["en"], recordings=None)
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
    language = replace(languages["en"], recordings=None)

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
    commons = AsyncMock(side_effect=AssertionError("Commons must be skipped"))
    piper = AsyncMock(side_effect=AssertionError("Piper must be skipped"))

    async def fake_edge(_word, _lang, output, _settings):
        output.write_bytes(b"edge")
        return True

    monkeypatch.setattr(audio, "_commons_recording", commons)
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
    commons.assert_not_awaited()
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
            replace(languages["en"], tts="edge", recordings=None),
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
    language = replace(languages["en"], recordings=None)
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
        def load(cls, _model, *, config_path=None):
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
    language = replace(languages["en"], recordings=None)

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
    language = replace(languages["en"], recordings=None)
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


def test_only_the_two_most_recent_voices_stay_loaded(tmp_path, monkeypatch):
    loaded = []

    def fake_load(model, *, config_path):
        loaded.append(model)
        return SimpleNamespace(model=model)

    monkeypatch.setitem(
        sys.modules,
        "piper",
        SimpleNamespace(PiperVoice=SimpleNamespace(load=fake_load)),
    )
    models = [tmp_path / f"voice{index}.onnx" for index in range(3)]

    for model in models:
        audio._load_voice(model, model.with_suffix(".json"))

    assert list(audio._VOICES) == models[1:]
    assert loaded == [str(model) for model in models]


def test_a_voice_spoken_again_outlives_the_one_loaded_after_it(tmp_path, monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "piper",
        SimpleNamespace(
            PiperVoice=SimpleNamespace(load=lambda model, *, config_path: SimpleNamespace()),
        ),
    )
    first, second, third = (tmp_path / f"voice{index}.onnx" for index in range(3))

    audio._load_voice(first, first.with_suffix(".json"))
    audio._load_voice(second, second.with_suffix(".json"))
    audio._load_voice(first, first.with_suffix(".json"))
    audio._load_voice(third, third.with_suffix(".json"))

    assert list(audio._VOICES) == [first, third]


async def test_voice_preparation_loads_no_more_voices_than_the_cache_holds(
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
    monkeypatch.setattr(
        audio,
        "PIPER_VOICES",
        {"first": files, "second": files, "third": files},
    )
    loaded = []

    def fake_load(model, *, config_path):
        loaded.append(model)
        return SimpleNamespace()

    monkeypatch.setitem(
        sys.modules,
        "piper",
        SimpleNamespace(PiperVoice=SimpleNamespace(load=fake_load)),
    )
    configured = [
        replace(languages["en"], code=name, tts_voice=name) for name in ("first", "second", "third")
    ]

    async with mock_client(
        lambda request: httpx.Response(200, content=contents[str(request.url)])
    ) as client:
        await audio.prepare_configured_voices(configured, settings, client=client)

    models = settings.data_dir / "models"
    assert loaded == [str(models / "first.onnx"), str(models / "second.onnx")]
    assert (models / "third.onnx").is_file()
