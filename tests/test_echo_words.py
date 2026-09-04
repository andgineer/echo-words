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


def test_the_rebuild_subcommand_reads_the_env_file_the_service_is_given(monkeypatch, tmp_path):
    """systemd hands the service this file, and the rebuild has to land on the same
    collection and the same AnkiWeb account. It is parsed the way systemd parses an
    EnvironmentFile: a shell sourcing it would run what the password contains."""
    data_dir = tmp_path / "service-data"
    env_file = tmp_path / "deploy.env"
    env_file.write_text(
        f"ECHOWORDS_DATA_DIR={data_dir}\n"
        "ECHOWORDS_ANKIWEB_USER=owner@example.com\n"
        'ECHOWORDS_ANKIWEB_PASSWORD=pa"ss$(touch pwned)\n',
    )
    seen = []

    def record(settings, *, confirmed):
        seen.append((settings, confirmed))
        return "what it would delete"

    monkeypatch.setattr("echo_words.main.rebuild_note_type", record)

    result = CliRunner().invoke(echo_words, ["rebuild-note-type", "--env-file", str(env_file)])

    assert result.exit_code == 0
    settings, confirmed = seen[0]
    assert (settings.data_dir, confirmed) == (data_dir, False)
    assert settings.ankiweb_user == "owner@example.com"
    assert settings.ankiweb_password == 'pa"ss$(touch pwned)'
    assert not (tmp_path / "pwned").exists()


def test_the_rebuild_subcommand_refuses_an_env_file_that_is_not_there(tmp_path):
    result = CliRunner().invoke(
        echo_words,
        ["rebuild-note-type", "--env-file", str(tmp_path / "absent.env")],
    )

    assert result.exit_code != 0


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
