"""The pinned Piper downloads, which are the only voices this app can install."""

from echo_words.voices import PIPER_VOICES, installable_piper_voices


def test_only_a_pinned_download_counts_as_a_piper_voice():
    """A voice reaches the server as one of these downloads or not at all, so a
    language absent from them has no Piper whatever Piper's catalogue lists."""
    assert installable_piper_voices("en") == ("en_US-lessac-medium",)
    assert installable_piper_voices("de") == ("de_DE-thorsten-medium",)
    assert installable_piper_voices("pl") == ()
    assert installable_piper_voices("sr") == ()
    for voice in PIPER_VOICES:
        assert voice in installable_piper_voices(voice.split("_", 1)[0])


def test_every_pinned_voice_carries_both_files_from_the_same_release():
    """A model without its config cannot be loaded, and a config from another release
    would be loaded against the wrong model."""
    for voice, files in PIPER_VOICES.items():
        assert files.model.suffix == ".onnx"
        assert files.config.suffix == ".onnx.json"
        assert files.config.url == f"{files.model.url}.json"
        assert files.model.url.endswith(f"/{voice}.onnx")
        assert len(files.model.sha256) == 64
        assert len(files.config.sha256) == 64
