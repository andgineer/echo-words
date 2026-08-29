"""Resilient pronunciation lookup and text-to-speech generation."""

import asyncio
import hashlib
import io
import logging
import os
import re
import tempfile
import threading
import wave
from collections.abc import Iterable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any
from urllib.parse import quote

import edge_tts
import httpx
import lameenc  # pyrefly: ignore[missing-import] - compiled extension has no type metadata.

from echo_words.config import Settings
from echo_words.config import settings as default_settings
from echo_words.languages import Language

HTTP_TIMEOUT_SECONDS = 10
_DICTIONARY_URL = "https://api.dictionaryapi.dev/api/v2/entries/{lang}/{word}"
_VOICE_BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"
_AUDIO_NAME_PATTERN = re.compile(r"pronunciation-[0-9a-f]{20}\.mp3")

# Loading a voice costs seconds and around 110 MB, synthesizing with a loaded one
# costs a fraction of a second, so every configured voice is kept for the process's
# life and the service's memory limits are sized for all of them at once. One lock
# per voice, because a shared voice is used from several synthesis threads at once.
_VOICES: dict[Path, Any] = {}
_VOICE_LOCKS: dict[Path, threading.Lock] = {}
_VOICES_LOCK = threading.Lock()

_SERBIAN_DIGRAPHS = (
    ("dž", "џ"),
    ("Dž", "Џ"),
    ("DŽ", "Џ"),
    ("lj", "љ"),
    ("Lj", "Љ"),
    ("LJ", "Љ"),
    ("nj", "њ"),
    ("Nj", "Њ"),
    ("NJ", "Њ"),
)
_SERBIAN_LETTERS = str.maketrans(
    "abcčćdđefghijklmnoprsštuvzžABCČĆDĐEFGHIJKLMNOPRSŠTUVZŽ",
    "абцчћдђефгхијклмнопрсштувзжАБЦЧЋДЂЕФГХИЈКЛМНОПРСШТУВЗЖ",
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VoiceFile:
    suffix: str
    url: str
    sha256: str


@dataclass(frozen=True)
class PiperVoiceFiles:
    model: VoiceFile
    config: VoiceFile


PIPER_VOICES = {
    "en_US-lessac-medium": PiperVoiceFiles(
        model=VoiceFile(
            ".onnx",
            f"{_VOICE_BASE_URL}/en/en_US/lessac/medium/en_US-lessac-medium.onnx",
            "5efe09e69902187827af646e1a6e9d269dee769f9877d17b16b1b46eeaaf019f",
        ),
        config=VoiceFile(
            ".onnx.json",
            f"{_VOICE_BASE_URL}/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json",
            "efe19c417bed055f2d69908248c6ba650fa135bc868b0e6abb3da181dab690a0",
        ),
    ),
    "de_DE-thorsten-medium": PiperVoiceFiles(
        model=VoiceFile(
            ".onnx",
            f"{_VOICE_BASE_URL}/de/de_DE/thorsten/medium/de_DE-thorsten-medium.onnx",
            "7e64762d8e5118bb578f2eea6207e1a35a8e0c30595010b666f983fc87bb7819",
        ),
        config=VoiceFile(
            ".onnx.json",
            f"{_VOICE_BASE_URL}/de/de_DE/thorsten/medium/de_DE-thorsten-medium.onnx.json",
            "974adee790533adb273a1ac88f49027d2a1b8f0f2cf4905954a4791e79264e85",
        ),
    ),
}


async def fetch_pronunciation(
    word: str,
    lang: Language,
    *,
    settings: Settings = default_settings,
    client: httpx.AsyncClient | None = None,
) -> Path | None:
    """Return one cached mp3, falling through dictionary, Piper, then edge-tts."""
    try:
        output = _audio_path(word, lang, settings)
        if output.is_file():
            return output
        output.parent.mkdir(parents=True, exist_ok=True)
    except Exception as exc:  # noqa: BLE001 - a cache failure must not fail the answer.
        logger.warning("audio cache is unavailable for %s/%r: %s", lang.code, word, exc)
        return None

    if (
        lang.dict_api
        and len(word.split()) == 1
        and await _try_dictionary_audio(word, lang, output, client)
    ):
        return output

    if lang.tts != "edge":
        try:
            if await _piper_audio(word, lang, output, settings):
                return output
        except Exception as exc:  # noqa: BLE001 - every audio boundary degrades.
            logger.warning("Piper audio failed for %s/%r: %s", lang.code, word, exc)

    try:
        await _edge_audio(word, lang, output, settings)
        return output
    except Exception as exc:  # noqa: BLE001 - audio must never fail the answer.
        logger.warning("edge-tts audio failed for %s/%r: %s", lang.code, word, exc)
        return None


async def prepare_configured_voices(
    languages: Iterable[Language],
    settings: Settings,
    *,
    client: httpx.AsyncClient | None = None,
) -> None:
    """Download and load only configured Piper voices, retrying failures next startup."""
    owned_client: httpx.AsyncClient | None = None
    try:
        voices = {
            language.tts_voice
            for language in languages
            if language.tts == "piper" and language.tts_voice
        }
        if not voices:
            return
        settings.data_dir.joinpath("models").mkdir(parents=True, exist_ok=True)
        if client is None:
            owned_client = httpx.AsyncClient(follow_redirects=True)
            client = owned_client
        for voice_name in sorted(voices):
            await _prepare_voice(voice_name, settings, client)
    except Exception as exc:  # noqa: BLE001 - provisioning must never break app startup.
        logger.warning("could not prepare Piper voices: %s", exc)
    finally:
        if owned_client is not None:
            try:
                await owned_client.aclose()
            except Exception as exc:  # noqa: BLE001 - provisioning remains best-effort.
                logger.warning("could not close Piper download client: %s", exc)


async def _prepare_voice(
    voice_name: str,
    settings: Settings,
    client: httpx.AsyncClient,
) -> None:
    files = PIPER_VOICES.get(voice_name)
    if files is None:
        logger.warning("no pinned Piper download is known for %s", voice_name)
        return
    for voice_file in (files.model, files.config):
        try:
            await _install_voice_file(voice_name, voice_file, settings, client)
        except Exception as exc:  # noqa: BLE001 - retry on the next startup.
            logger.warning("could not prepare Piper voice %s: %s", voice_name, exc)
            return
    await _preload_voice(voice_name, files, settings)


async def _preload_voice(voice_name: str, files: PiperVoiceFiles, settings: Settings) -> None:
    """Pay the load at startup instead of inside the deadline of the first word."""
    models = settings.data_dir / "models"
    try:
        await asyncio.to_thread(
            _load_voice,
            models / f"{voice_name}{files.model.suffix}",
            models / f"{voice_name}{files.config.suffix}",
        )
    except Exception as exc:  # noqa: BLE001 - a failed load only costs the first word.
        logger.warning("could not load Piper voice %s: %s", voice_name, exc)


def is_audio_filename(name: str) -> bool:
    """Return whether a URL component can be one of this module's generated names."""
    return _AUDIO_NAME_PATTERN.fullmatch(name) is not None


async def _try_dictionary_audio(
    word: str,
    lang: Language,
    output: Path,
    client: httpx.AsyncClient | None,
) -> bool:
    dictionary_client = client
    owns_client = dictionary_client is None
    try:
        if dictionary_client is None:
            dictionary_client = httpx.AsyncClient(follow_redirects=True)
        return await _dictionary_audio(word, lang, output, dictionary_client)
    except Exception as exc:  # noqa: BLE001 - every dictionary boundary degrades.
        logger.warning("dictionary audio failed for %s/%r: %s", lang.code, word, exc)
        return False
    finally:
        if owns_client and dictionary_client is not None:
            try:
                await dictionary_client.aclose()
            except Exception as exc:  # noqa: BLE001 - closing must not fail the answer.
                logger.warning("dictionary client close failed: %s", exc)


async def _dictionary_audio(
    word: str,
    lang: Language,
    output: Path,
    client: httpx.AsyncClient,
) -> bool:
    url = _DICTIONARY_URL.format(
        lang=quote(lang.dict_api or "", safe=""),
        word=quote(word, safe=""),
    )
    response = await client.get(url, timeout=HTTP_TIMEOUT_SECONDS)
    if response.status_code == httpx.codes.NOT_FOUND:
        return False
    response.raise_for_status()
    audio_urls = [
        phonetic.get("audio")
        for entry in response.json()
        if isinstance(entry, dict)
        for phonetic in entry.get("phonetics", [])
        if isinstance(phonetic, dict) and phonetic.get("audio")
    ]
    if not audio_urls:
        return False
    preferred = next(
        (candidate for candidate in audio_urls if f"-{lang.accent}" in candidate.lower()),
        audio_urls[0],
    )
    if preferred.startswith("//"):
        preferred = f"https:{preferred}"
    recording = await client.get(preferred, timeout=HTTP_TIMEOUT_SECONDS)
    recording.raise_for_status()
    _raise_if_cancelling()
    _write_atomic(output, recording.content)
    return True


async def _piper_audio(
    word: str,
    lang: Language,
    output: Path,
    settings: Settings,
) -> bool:
    if not lang.tts_voice:
        return False
    model = settings.data_dir / "models" / f"{lang.tts_voice}.onnx"
    config = settings.data_dir / "models" / f"{lang.tts_voice}.onnx.json"
    if not model.is_file() or not config.is_file():
        logger.warning("Piper voice %s is not ready", lang.tts_voice)
        return False
    mp3 = await asyncio.to_thread(_synthesize_piper, word, model, config)
    _raise_if_cancelling()
    _write_atomic(output, mp3)
    return True


def _voice_lock(model: Path) -> threading.Lock:
    with _VOICES_LOCK:
        return _VOICE_LOCKS.setdefault(model, threading.Lock())


def _load_voice(model: Path, config: Path) -> Any:
    with _voice_lock(model):
        return _cached_voice(model, config)


def _cached_voice(model: Path, config: Path) -> Any:
    """Load once and keep it. Callers hold this voice's lock."""
    # Piper is deliberately lazy: a broken native install must degrade to edge-tts.
    from piper import PiperVoice  # noqa: PLC0415 - sanctioned native dependency boundary.

    voice = _VOICES.get(model)
    if voice is None:
        voice = PiperVoice.load(str(model), config_path=str(config))
        _VOICES[model] = voice
    return voice


def _synthesize_piper(word: str, model: Path, config: Path) -> bytes:
    wav_buffer = io.BytesIO()
    # One voice now serves every thread, and espeak-ng's phonemization underneath it
    # keeps process-global state, so one word at a time goes through a given voice.
    with _voice_lock(model):
        voice = _cached_voice(model, config)
        with wave.open(wav_buffer, "wb") as wav_file:
            voice.synthesize_wav(word, wav_file)
    wav_buffer.seek(0)
    with wave.open(wav_buffer, "rb") as wav_file:
        encoder = lameenc.Encoder()
        encoder.set_bit_rate(64)
        encoder.set_in_sample_rate(wav_file.getframerate())
        encoder.set_channels(wav_file.getnchannels())
        encoder.set_quality(2)
        pcm = wav_file.readframes(wav_file.getnframes())
        return encoder.encode(pcm) + encoder.flush()


async def _edge_audio(word: str, lang: Language, output: Path, settings: Settings) -> None:
    voice = lang.edge_tts_voice or settings.edge_tts_voice
    temporary = _temporary_path(output)
    try:
        await edge_tts.Communicate(_speech_text(word, voice), voice).save(str(temporary))
        _raise_if_cancelling()
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)


def _serbian_cyrillic(text: str) -> str:
    for latin, cyrillic in _SERBIAN_DIGRAPHS:
        text = text.replace(latin, cyrillic)
    return text.translate(_SERBIAN_LETTERS)


# A voice keyed by the locale whose script it actually pronounces: Microsoft's sr-RS voices
# are Serbian Cyrillic, and given Gaj's Latin they read the word as if it were English.
_CYRILLIC_LOCALE_VOICES = {"sr-RS": _serbian_cyrillic}


def _speech_text(word: str, voice: str) -> str:
    convert = _CYRILLIC_LOCALE_VOICES.get(voice.rsplit("-", 1)[0])
    return convert(word) if convert is not None else word


async def _install_voice_file(
    voice_name: str,
    voice_file: VoiceFile,
    settings: Settings,
    client: httpx.AsyncClient,
) -> None:
    destination = settings.data_dir / "models" / f"{voice_name}{voice_file.suffix}"
    if destination.is_file() and await asyncio.to_thread(_sha256, destination) == voice_file.sha256:
        return
    temporary = _temporary_path(destination)
    digest = hashlib.sha256()
    try:
        logger.info("downloading Piper voice file %s", destination.name)
        async with client.stream(
            "GET",
            voice_file.url,
            timeout=HTTP_TIMEOUT_SECONDS,
            follow_redirects=True,
        ) as response:
            response.raise_for_status()
            with temporary.open("wb") as downloaded:
                async for chunk in response.aiter_bytes():
                    digest.update(chunk)
                    downloaded.write(chunk)
        if digest.hexdigest() != voice_file.sha256:
            raise ValueError(f"checksum mismatch for {destination.name}")
        _raise_if_cancelling()
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _audio_path(word: str, lang: Language, settings: Settings) -> Path:
    digest = hashlib.sha256(f"{lang.code}\0{word}".encode()).hexdigest()[:20]
    return settings.data_dir / "audio" / f"pronunciation-{digest}.mp3"


def _temporary_path(destination: Path) -> Path:
    descriptor, name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    os.close(descriptor)
    return Path(name)


def _write_atomic(destination: Path, content: bytes) -> None:
    temporary = _temporary_path(destination)
    try:
        temporary.write_bytes(content)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(partial(source.read, 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _raise_if_cancelling() -> None:
    task = asyncio.current_task()
    if task is not None and task.cancelling():
        raise asyncio.CancelledError
