"""The ``echo-words`` command: a launcher for the web app."""

import rich_click as click
import uvicorn

from echo_words import __version__
from echo_words.config import settings

click.rich_click.USE_MARKDOWN = True


@click.command()
@click.version_option(version=__version__, prog_name="echo-words")
@click.option("--reload", is_flag=True, help="Restart the server when the sources change.")
def echo_words(reload: bool) -> None:
    """
    Serve the echo-words web app on `ECHOWORDS_HOST:ECHOWORDS_PORT`.
    """
    click.echo(f"echo-words on http://{settings.host}:{settings.port}")
    uvicorn.run("echo_words.api:app", host=settings.host, port=settings.port, reload=reload)


if __name__ == "__main__":  # pragma: no cover
    echo_words()  # pylint: disable=no-value-for-parameter
