from click.testing import CliRunner

from echo_words import __version__
from echo_words.config import Settings
from echo_words.main import echo_words


def test_version():
    assert __version__


def test_version_option():
    runner = CliRunner()
    result = runner.invoke(echo_words, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_the_rebuild_subcommand_deletes_nothing_unless_yes_is_passed(monkeypatch):
    confirmations = []

    def record(_settings, *, confirmed):
        confirmations.append(confirmed)
        return "what it would delete"

    monkeypatch.setattr("echo_words.main.rebuild_note_type", record)

    dry = CliRunner().invoke(echo_words, ["rebuild-note-type"])
    assert dry.exit_code == 0
    assert "what it would delete" in dry.output
    assert confirmations == [False]

    assert CliRunner().invoke(echo_words, ["rebuild-note-type", "--yes"]).exit_code == 0
    assert confirmations == [False, True]


def test_a_rebuild_with_no_collection_there_fails_instead_of_reporting_success(
    monkeypatch,
    tmp_path,
):
    """Exit 0 on a collection it never found reads as a rebuild that worked, and the
    operator restarts a service whose every add still fails."""
    monkeypatch.setattr(
        "echo_words.main.settings",
        Settings(_env_file=None, data_dir=tmp_path, anki_sync=False),
    )

    result = CliRunner().invoke(echo_words, ["rebuild-note-type", "--yes"])

    assert result.exit_code != 0
    assert "no collection at" in result.output


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
