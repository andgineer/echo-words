"""The Piper voices this app pins, downloads and is therefore able to offer."""

from dataclasses import dataclass

_VOICE_BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"


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


def installable_piper_voices(code: str) -> tuple[str, ...]:
    """The Piper voices this app can put on the server for a language.

    A voice only ever arrives through the pinned downloads above, so a language absent
    from them has no Piper at all, whatever Piper's own catalogue lists for its locale.
    """
    return tuple(sorted(name for name in PIPER_VOICES if name.split("_", 1)[0] == code))
