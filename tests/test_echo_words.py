from click.testing import CliRunner

from echo_words import __version__
from echo_words.main import echo_words


def test_version():
    assert __version__


def test_version_option():
    runner = CliRunner()
    result = runner.invoke(echo_words, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_the_command_serves_the_app_on_the_configured_address(monkeypatch):
    calls = []
    monkeypatch.setattr("uvicorn.run", lambda *args, **kwargs: calls.append((args, kwargs)))
    monkeypatch.setattr("echo_words.main.settings.host", "10.0.0.5")
    monkeypatch.setattr("echo_words.main.settings.port", 9999)

    result = CliRunner().invoke(echo_words, [])

    assert result.exit_code == 0
    assert calls == [
        (("echo_words.api:app",), {"host": "10.0.0.5", "port": 9999, "reload": False}),
    ]
