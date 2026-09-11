"""Rebuild the PWA and capture the README and docs screenshots from stable demo data."""

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
from playwright.sync_api import Browser, Locator, Page, ViewportSize, expect, sync_playwright

REPO = Path(__file__).resolve().parents[1]
SCREENSHOTS = REPO / "docs" / "common" / "images" / "screenshots"
VIEWPORT: ViewportSize = {"width": 390, "height": 640}
PAGE_MARGIN = 16

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
        {
            "label": "Sehnsucht",
            "reason": "for home",
            "context": "Die Sehnsucht nach der Heimat wurde immer stärker.",
        },
    ],
    "segment_kind": "senses",
    "carded_sense": 0,
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

SERBIAN_ENTRY = {
    "entry_id": "cyrillic-demo",
    "word": "инат",
    "lang": "sr",
    "language": "Српски",
    "lookup_only": False,
    "status": "done",
    "shape": "unit",
    "text": (
        "<b>spite</b> (colloquial); <b>defiance</b> (neutral)\n\n"
        "Noun, masculine; plural <i>инати</i>. Stubborn contrariness: doing something "
        "precisely because someone is against it, even at one's own cost. Most often in "
        "<i>из ината</i> “out of spite” and <i>терати инат</i> “to be contrary.”\n\n"
        "<b>Origin.</b> From Turkish <i>inat</i> “obstinacy,” itself from Arabic "
        "<i>ʿinād</i>.\n\n"
        "<b>Examples</b>\n"
        "<i>Урадио је то из ината.</i> — He did it out of spite.\n"
        "<i>Престани да тераш инат.</i> — Stop being so contrary."
    ),
    "audio_url": "/demo.wav",
    "segments": [
        {"label": "инат", "reason": "out of spite", "context": "Урадио је то из ината."},
        {"label": "инат", "reason": "in defiance", "context": "Живео је дуго, свима у инат."},
        {"label": "инат", "reason": "stubbornness", "context": "Престани да тераш инат."},
    ],
    "segment_kind": "senses",
    "carded_sense": 0,
    "card_status": "added",
    "card_kinds": [
        "Recognition",
        "Recall",
        "ContextRecognition",
        "ContextProduction",
    ],
    "detail_available": True,
}

# The PWA keeps its history on the device, and reads this localStorage copy when
# IndexedDB holds none.
SEED_HISTORY = """entries => {
    const now = Date.now();
    localStorage.setItem("echo-words.cache.v1:history", JSON.stringify(
        { key: "history", data: entries, fetchedAt: now, attemptedAt: now, updatedAt: now },
    ));
}"""


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


@app.get("/api/stats")
async def stats():
    return {
        "languages": {
            "en": {
                "name": "English",
                "today": 3,
                "last_7_days": 18,
                "all_time": 412,
                "lookup_only": 1,
            },
            "de": {
                "name": "Deutsch",
                "today": 5,
                "last_7_days": 31,
                "all_time": 687,
                "lookup_only": 2,
            },
            "sr": {
                "name": "Српски",
                "today": 2,
                "last_7_days": 9,
                "all_time": 143,
                "lookup_only": 0,
            },
        },
        "session_counters_since": "startup",
    }


def language_status(name: str, deck: str, model: str, at: str) -> dict[str, object]:
    return {
        "name": name,
        "deck": deck,
        "paid_alias": "gpt-fast",
        "paid_available_today": True,
        "paid_refusal": None,
        "last_call": {"model": model, "paid": False, "ok": True, "at": at, "error": None},
    }


@app.get("/api/status")
async def status():
    return {
        "pool": {
            "available": True,
            "providers_usable": 4,
            "providers_total": 4,
            "degraded": False,
            "missing_keys": [],
            "direct_missing_keys": [],
        },
        "paid_calls": {"today": 1, "daily_cap": 100},
        "languages": {
            "en": language_status(
                "English", "EchoWords: English", "groq-gpt-oss-120b", "2026-09-11T09:41:00Z"
            ),
            "de": language_status(
                "Deutsch",
                "EchoWords: German",
                "google-gemini-3.5-flash-lite",
                "2026-09-11T14:52:00Z",
            ),
            "sr": language_status(
                "Српски",
                "EchoWords: Serbian",
                "google-gemini-3.5-flash-lite",
                "2026-09-11T14:37:00Z",
            ),
        },
        "anki": {
            "last_result": "ok",
            "last_sync_at": "2026-09-11T15:05:00Z",
            "unsynced_changes": False,
            "full_sync_required": False,
            "error": None,
        },
    }


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


# The e2e suite imports this module, and a missing build must fail that one test
# rather than the collection of the whole suite.
app.mount(
    "/",
    StaticFiles(directory=REPO / "_static", html=True, check_dir=False),
    name="static",
)


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


def settled_card(page: Page) -> Locator:
    """The card slides in on every switch; a shot taken mid-slide is off-centre and faded."""
    card = page.locator(".deck")
    expect(card).to_have_css("transform", "matrix(1, 0, 0, 1, 0, 0)")
    expect(card).to_have_css("opacity", "1")
    return card


def shot_down_to(page: Page, card: Locator, path: Path) -> None:
    """A page shorter than the screen is cut under its card, not padded with empty ground."""
    box = card.bounding_box()
    if box is None:
        raise RuntimeError(f"nothing on the page to photograph for {path.name}")
    page.screenshot(
        path=path,
        animations="disabled",
        full_page=True,
        clip={
            "x": 0,
            "y": 0,
            "width": VIEWPORT["width"],
            "height": box["y"] + box["height"] + PAGE_MARGIN,
        },
    )


def capture(browser: Browser, url: str, out: Path) -> None:
    context = browser.new_context(
        viewport=VIEWPORT,
        device_scale_factor=2,
        color_scheme="dark",
        locale="en-US",
        timezone_id="UTC",
    )
    try:
        page = context.new_page()
        page.goto(url)
        page.evaluate(SEED_HISTORY, [WORD_ENTRY, TEXT_ENTRY, SERBIAN_ENTRY])
        page.reload(wait_until="networkidle")
        page.get_by_role("tab", name="Deutsch", exact=True).click()
        page.get_by_placeholder("a word or a phrase").fill("sich verlassen auf")
        settled_card(page)
        page.screenshot(path=out / "add-word.png", animations="disabled")

        page.get_by_placeholder("a word or a phrase").fill("")
        page.get_by_role("tab", name="Sehnsucht", exact=True).click()
        settled_card(page).screenshot(path=out / "card-added.png", animations="disabled")

        page.get_by_role("tab", name=SENTENCE, exact=True).click()
        settled_card(page).screenshot(path=out / "sentence.png", animations="disabled")

        page.get_by_role("tab", name="Српски", exact=True).click()
        settled_card(page).screenshot(path=out / "cyrillic-card.png", animations="disabled")

        for view, name in (("Stats", "stats.png"), ("Status", "status.png")):
            page.get_by_role("tab", name=view, exact=True).click()
            card = page.locator(".app-main > .card")
            expect(card.get_by_role("heading", name=view, exact=True)).to_be_visible()
            shot_down_to(page, card, out / name)
    finally:
        context.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="capture the already-built _static bundle",
    )
    if not parser.parse_args().skip_build:
        subprocess.run(
            [sys.executable, "-m", "invoke", "build-static"],
            cwd=REPO,
            check=True,
        )
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    with live_server() as url, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        capture(browser, url, SCREENSHOTS)
        browser.close()


if __name__ == "__main__":
    main()
