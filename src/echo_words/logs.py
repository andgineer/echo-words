"""The service log: the app's own records, on the stream the journal collects."""

import logging
import sys

PACKAGE_LOGGER = "echo_words"
_HANDLER_NAME = "echo-words"
_FORMAT = "%(levelname)s %(name)s: %(message)s"


def configure_logging(level: int = logging.INFO) -> None:
    """Send this package's records to stdout, leaving every other logger alone."""
    # uvicorn configures only its own loggers, so the root one keeps the WARNING level
    # and the empty handler list it starts with: without this the app's own info
    # records are dropped before anything can collect them.
    package = logging.getLogger(PACKAGE_LOGGER)
    package.setLevel(level)
    if any(handler.get_name() == _HANDLER_NAME for handler in package.handlers):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.set_name(_HANDLER_NAME)
    handler.setFormatter(logging.Formatter(_FORMAT))
    package.addHandler(handler)
