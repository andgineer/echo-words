"""What the operator finds in the service log."""

import logging
from collections.abc import Iterator

import pytest

from echo_words import audio
from echo_words.api import create_app
from echo_words.config import Settings
from echo_words.logs import PACKAGE_LOGGER, configure_logging


@pytest.fixture
def unconfigured_logging() -> Iterator[logging.Logger]:
    """The logging the server would start with on its own: uvicorn says nothing about
    this package, and the root logger keeps the WARNING level and empty handler list
    every process starts with."""
    package = logging.getLogger(PACKAGE_LOGGER)
    root = logging.getLogger()
    kept = (package.handlers[:], package.level, root.handlers[:], root.level)
    package.handlers = []
    package.setLevel(logging.NOTSET)
    root.handlers = []
    root.setLevel(logging.WARNING)
    yield package
    package.handlers, root.handlers = kept[0], kept[2]
    package.setLevel(kept[1])
    root.setLevel(kept[3])


def test_uvicorn_alone_would_drop_the_apps_info_records(unconfigured_logging: logging.Logger):
    """The reason the app configures anything: a miss from Commons is an info record,
    and under the server's own logging it would never be written anywhere."""
    assert unconfigured_logging.getEffectiveLevel() == logging.WARNING
    assert not audio.logger.isEnabledFor(logging.INFO)


def test_the_apps_info_records_reach_the_log(
    unconfigured_logging: logging.Logger,
    capsys: pytest.CaptureFixture[str],
):
    configure_logging()

    audio.logger.info("no Commons recording for %s/%r: HTTP %s", "de", "Haus", 404)

    assert "no Commons recording for de/'Haus': HTTP 404" in capsys.readouterr().out
    assert unconfigured_logging.handlers


def test_starting_the_app_configures_the_log(
    unconfigured_logging: logging.Logger,
    settings: Settings,
    capsys: pytest.CaptureFixture[str],
):
    """The service is started by handing a server this app, so the app is where its
    logging has to be decided; without it an all-404 Commons is silent."""
    create_app(settings)

    audio.logger.info("no Commons recording for %s/%r: HTTP %s", "de", "Haus", 404)

    assert "no Commons recording" in capsys.readouterr().out


def test_the_log_is_configured_once_however_often_the_app_is_built(
    unconfigured_logging: logging.Logger,
    settings: Settings,
    capsys: pytest.CaptureFixture[str],
):
    configure_logging()
    create_app(settings)

    audio.logger.info("one line")

    assert capsys.readouterr().out.count("one line") == 1


def test_nothing_but_this_package_is_configured(unconfigured_logging: logging.Logger):
    """The server's own loggers are its business: a handler on the root logger would
    duplicate every uvicorn line, which propagates to it."""
    root = logging.getLogger()
    kept = root.handlers[:]

    configure_logging()

    assert root.handlers == kept
    assert root.level == logging.WARNING
