"""Rebuild the PWA and capture the three README screenshots from stable demo data."""

import argparse
import asyncio
import contextlib
import io
import subprocess
import sys
import threading
import wave
from collections.abc import Iterator
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[1]
SCREENSHOTS = REPO / "docs" / "common" / "images" / "screenshots"

WORD_ENTRY = {
    "entry_id": "word-demo",
    "word": "Sehnsucht",
    "lang": "de",
    "language": "Deutsch",
    "lookup_only": False,
    "status": "done",
    "shape": "unit",
    "text": (
        "<b>longing</b> (neutral); <b>yearning</b> (literary)\n\n"
        "A deep, often melancholic longing for a person, place, or state of being "
        "that is absent. Usually used with <i>nach</i> + dative.\n\n"
        "<b>Origin.</b> A German compound of <i>sehnen</i> “to long for” and "
        "<i>Sucht</i> “addiction, intense craving.”\n\n"
        "<b>Examples</b>\n"
        "<i>Ich habe große Sehnsucht nach dir.</i> — I miss you so much.\n"
        "<i>Sie spürte Sehnsucht nach Freiheit.</i> — She yearned for freedom."
    ),
    "audio_url": "/demo.wav",
    "segments": [
        {
            "label": "Sehnsucht",
            "reason": "for a person",
            "context": "Ich habe große Sehnsucht nach dir.",
        },
        {
            "label": "Sehnsucht",
            "reason": "for freedom",
            "context": "Sie spürte Sehnsucht nach Freiheit.",
        },
    ],
    "segment_kind": "senses",
    "card_status": "added",
    "card_kinds": [
        "Recognition",
        "Recall",
        "ContextRecognition",
        "ContextProduction",
    ],
    "detail_available": True,
}

SENTENCE = "Ich traf ihn gestern, weil er mir das Buch zurückgeben wollte."
TEXT_ENTRY = {
    "entry_id": "text-demo",
    "word": SENTENCE,
    "lang": "de",
    "language": "Deutsch",
    "lookup_only": False,
    "status": "done",
    "shape": "text",
    "text": (
        "<b>I met him yesterday because he wanted to give me the book back.</b>\n\n"
        "<b>What is hard here</b>\n"
        "<i>weil</i> sends the finite verb to the end of its clause, which is why "
        "<i>wollte</i> comes last.\n\n"
        "<i>zurückgeben</i> is separable, but beside the modal <i>wollen</i> it stays "
        "as one infinitive.\n\n"
        "<i>mir</i> is dative: it marks the person receiving the book without a "
        "separate preposition."
    ),
    "audio_url": "/demo.wav",
    "segments": [
        {"label": "zurückgeben", "reason": "separable verb", "context": SENTENCE},
        {"label": "weil", "reason": "word order", "context": SENTENCE},
        {"label": "traf", "reason": "", "context": SENTENCE},
        {"label": "gestern", "reason": "", "context": SENTENCE},
        {"label": "wollte", "reason": "", "context": SENTENCE},
        {"label": "Buch", "reason": "", "context": SENTENCE},
    ],
    "segment_kind": "text",
    "card_status": None,
    "card_kinds": [],
    "detail_available": False,
}


def silent_wav() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8_000)
        audio.writeframes(b"\x00\x00" * 8_000 * 2)
    return buffer.getvalue()


app = FastAPI()


@app.get("/api/languages")
async def languages():
    return [
        {"code": "en", "name": "English"},
        {"code": "de", "name": "Deutsch"},
        {"code": "sr", "name": "Српски"},
    ]


@app.get("/api/words/recent")
async def recent():
    return [WORD_ENTRY, TEXT_ENTRY]


@app.get("/api/events")
async def events():
    async def stream():
        while True:
            yield ": keep-alive\n\n"
            await asyncio.sleep(10)

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/demo.wav")
async def audio():
    return Response(silent_wav(), media_type="audio/wav")


app.mount("/", StaticFiles(directory=REPO / "_static", html=True), name="static")


@contextlib.contextmanager
def live_server() -> Iterator[str]:
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        threading.Event().wait(0.05)
    else:
        raise RuntimeError("the screenshot server did not start")
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def capture(*, build: bool = True) -> None:
    if build:
        subprocess.run(
            [sys.executable, "-m", "invoke", "build-static"],
            cwd=REPO,
            check=True,
        )
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    with live_server() as url, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 390, "height": 640},
            device_scale_factor=2,
            color_scheme="dark",
            locale="en-US",
        )
        page = context.new_page()
        page.goto(url, wait_until="networkidle")
        page.get_by_role("tab", name="Deutsch", exact=True).click()
        page.get_by_placeholder("a word or a phrase").fill("sich verlassen auf")
        page.screenshot(path=SCREENSHOTS / "add-word.png")

        page.get_by_placeholder("a word or a phrase").fill("")
        page.get_by_role("tab", name="Sehnsucht", exact=True).click()
        page.locator(".deck").screenshot(path=SCREENSHOTS / "card-added.png")

        page.get_by_role("tab", name=SENTENCE, exact=True).click()
        page.locator(".deck").screenshot(path=SCREENSHOTS / "sentence.png")
        browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="capture the already-built _static bundle",
    )
    capture(build=not parser.parse_args().skip_build)
