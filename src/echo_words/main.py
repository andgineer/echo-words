"""The ``echo-words`` command: a launcher for the web app."""

from pathlib import Path

import rich_click as click
import uvicorn

from echo_words import __version__
from echo_words.anki import AnkiError, rebuild_note_type
from echo_words.config import Settings, settings

click.rich_click.USE_MARKDOWN = True


@click.group(invoke_without_command=True)
@click.version_option(version=__version__, prog_name="echo-words")
@click.option("--reload", is_flag=True, help="Restart the server when the sources change.")
@click.pass_context
def echo_words(ctx: click.Context, reload: bool) -> None:
    """
    Serve the echo-words web app on `ECHOWORDS_HOST:ECHOWORDS_PORT`.
    """
    if ctx.invoked_subcommand is not None:
        return
    click.echo(f"echo-words on http://{settings.host}:{settings.port}")
    uvicorn.run("echo_words.api:app", host=settings.host, port=settings.port, reload=reload)


@echo_words.command(name="rebuild-note-type")
@click.option("--yes", is_flag=True, help="Delete. Without it nothing is removed.")
@click.option(
    "--env-file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Read settings from this file, as the service reads its own.",
)
def rebuild_note_type_command(yes: bool, env_file: Path | None) -> None:
    """
    Delete the EchoWords note type and every note of it, then upload to AnkiWeb.

    The next card added recreates it with the current fields and templates, and
    every Anki app is asked to download the uploaded collection once.
    Stop the service first: the collection must not be open elsewhere.
    """
    # Parsed here rather than sourced by the caller's shell: a password may hold
    # anything, and the AnkiWeb credentials must not travel through a command line.
    active = Settings(_env_file=env_file) if env_file is not None else settings
    try:
        click.echo(rebuild_note_type(active, confirmed=yes))
    except AnkiError as exc:
        # A rebuild that found nothing must not read as a rebuild that worked.
        raise click.ClickException(str(exc)) from exc


if __name__ == "__main__":  # pragma: no cover
    echo_words()  # pylint: disable=no-value-for-parameter
