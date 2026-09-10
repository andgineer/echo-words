"""One real server and one real browser: the app end to end, with the LLM faked.

The browser loads the built PWA from a uvicorn running the real application, so the
event stream, the pipeline, the Anki store and the rendering are all the shipped ones.
Only the LLM boundary is a fake, because a failure worth a regression test — a lost
race, a budget miss, a refused judgement — is one no provider can be asked for.
"""

import asyncio
import contextlib
import json
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
import uvicorn
from fakes import FakeBroker
from playwright.sync_api import Page

from echo_words.api import create_app
from echo_words.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[1]
BUILT_PWA = REPO_ROOT / "_static"
STARTUP_TIMEOUT_SECONDS = 20.0
GATE_TIMEOUT_SECONDS = 20.0


class Gate:
    """A point in a faked answer that the test opens by hand, so what the browser is
    asserted to be showing is held there rather than raced against a clock."""

    def __init__(self) -> None:
        self._opened = threading.Event()

    async def wait(self) -> None:
        loop = asyncio.get_running_loop()
        if not await loop.run_in_executor(None, self._opened.wait, GATE_TIMEOUT_SECONDS):
            raise TimeoutError("the test never opened the gate this answer waits on")

    def open(self) -> None:
        self._opened.set()


@dataclass
class LiveApp:
    """The running app: where the browser reaches it, and the fake it answers from."""

    url: str
    broker: FakeBroker
    settings: Settings


def _no_lookups(monkeypatch: pytest.MonkeyPatch, audio: object = None) -> None:
    """Silence the two boundaries an answer touches on its way to the page. Both reach
    the network, and neither is what any of these tests is about — except where a test
    is about the recording itself and hands one in."""

    async def no_audio(*_args: object, **_kwargs: object) -> None:
        return None

    class NoReference:
        async def documents(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def usage(self, *_args: object, **_kwargs: object) -> None:
            return None

    monkeypatch.setattr("echo_words.api.fetch_pronunciation", audio or no_audio)
    monkeypatch.setattr("echo_words.api.Wiktionary", NoReference)
    monkeypatch.setattr("echo_words.api.Wikipedia", NoReference)


def _wired_broker(script: dict, box: list[FakeBroker]) -> type[FakeBroker]:
    class ScriptedBroker(FakeBroker):
        def __init__(self, home=None, direct=()) -> None:
            super().__init__(home=home, direct=direct, **script)
            box.append(self)

    return ScriptedBroker


@contextlib.contextmanager
def live_app(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    *,
    static_build: Path = BUILT_PWA,
    audio: object = None,
    **script: object,
) -> Iterator[LiveApp]:
    """Serve the real app on a loopback port until the block ends."""
    if not (BUILT_PWA / "index.html").exists():
        pytest.fail(f"{BUILT_PWA}/index.html is missing — run `uv run inv build-static`")
    box: list[FakeBroker] = []
    monkeypatch.setattr("llmbroker.AsyncBroker", _wired_broker(script, box))
    _no_lookups(monkeypatch, audio)
    served = Settings(**{**settings.model_dump(), "static_dir": static_build})
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(served),
            host="127.0.0.1",
            port=0,
            log_level="warning",
            # The browser holds the event stream open for as long as its page lives, and
            # a graceful shutdown would wait for it: the page outlives this block.
            timeout_graceful_shutdown=1,
        ),
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = threading.Event()
        for _ in range(int(STARTUP_TIMEOUT_SECONDS * 20)):
            if server.started:
                break
            deadline.wait(0.05)
        else:
            raise TimeoutError("the app under test never finished starting")
        port = server.servers[0].sockets[0].getsockname()[1]
        yield LiveApp(url=f"http://127.0.0.1:{port}", broker=box[0], settings=served)
    finally:
        server.should_exit = True
        thread.join(timeout=STARTUP_TIMEOUT_SECONDS)


WORD = "Schlüssel"


def answer(article: str, word: str = WORD, relation: str = "same") -> str:
    """One pool answer in the shape the prompt asks for: an article, then its card."""
    card = {
        "kind": "unit",
        "word": word,
        "word_relation": relation,
        "suggestion": word if relation == "typo" else "",
        "meanings": [
            {
                "label": "",
                "translations": ["ключ"],
                "examples": [
                    {
                        "text": f"Use {word} now.",
                        "translation": "Перевод.",
                        "highlighted": f"Use <b>{word}</b> now.",
                        "gapped": "Use ___ now.",
                    },
                ],
            },
        ],
        "segments": [],
    }
    return f"{article}===CARD==={json.dumps(card, ensure_ascii=False)}"


def unreadable(article: str, word: str = WORD) -> str:
    """An answer whose article reads well and whose payload the parser refuses. The
    shape is production's commonest: a meaning left with no usable example, which
    empties the meaning, which empties the answer."""
    payload = json.loads(answer("", word).split("===CARD===", 1)[1])
    payload["meanings"][0]["examples"] = []
    return f"{article}===CARD==={json.dumps(payload, ensure_ascii=False)}"


def submit(page: Page, url: str, word: str = WORD) -> None:
    page.goto(url)
    page.get_by_placeholder("a word or a phrase").fill(word)
    page.get_by_role("button", name="Analyse").click()
