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
