"""The ``echo-words`` command: a launcher for the web app."""

import rich_click as click
import uvicorn

from echo_words import __version__
from echo_words.anki import AnkiError, rebuild_note_type
from echo_words.config import settings

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
def rebuild_note_type_command(yes: bool) -> None:
    """
    Delete the EchoWords note type and every note of it.

    The next card added recreates it with the current fields and templates.
    Stop the service first: the collection must not be open elsewhere.
    """
    try:
        click.echo(rebuild_note_type(settings, confirmed=yes))
    except AnkiError as exc:
        # A rebuild that found nothing must not read as a rebuild that worked.
        raise click.ClickException(str(exc)) from exc


if __name__ == "__main__":  # pragma: no cover
    echo_words()  # pylint: disable=no-value-for-parameter
