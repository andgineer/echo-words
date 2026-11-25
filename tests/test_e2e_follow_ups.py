"""Questions asked under an entry, driven through a real browser.

What only the running app can show: that a reply keeps to the entry that asked while
the reader is on another card, what the model is given at the pool's door, that a
reply a reload interrupted comes back cut off in its place and one retry fills that
place once, and that an entry the server has forgotten can still be asked about.
"""

import re
import time
from urllib.parse import urlsplit

import pytest
from e2e_app import WORD, Gate, answer, live_app, submit
from fakes import FakeDirectClient, FakeHandle
from playwright.sync_api import Page, expect

from echo_words.config import Settings

pytestmark = pytest.mark.e2e

ARTICLE = "<b>Schlüssel</b> — ключ"
SECOND = "Schloss"
DEEPER = "<b>Nur im Artikel</b>: der Generalschlüssel öffnet jedes Schloss."
TUTOR = "=== THE LEARNER'S QUESTION NOW ==="
RAIL = '[role="tablist"][aria-label="Analysed words"] [role="tab"]'
ANSWER_FINISHED = "(entry) => entry.status === 'done'"
REPLY_FINISHED = "(entry) => (entry.follow_ups ?? []).some((turn) => turn.state === 'done')"


def _questions(app) -> list[str]:
    return [call["prompt"] for call in app.broker.stream_calls if TUTOR in call["prompt"]]


def _section(prompt: str, name: str) -> str | None:
    found = re.search(
        rf"=== {re.escape(name)} ===\n(.*?)\n=== END OF {re.escape(name)} ===", prompt, re.DOTALL
    )
    return found.group(1) if found else None


def _asked(app, count: int) -> list[str]:
    deadline = time.monotonic() + 10
    while len(_questions(app)) < count:
        if time.monotonic() > deadline:
            raise TimeoutError("the question never reached the pool")
        time.sleep(0.05)
    return _questions(app)


def _ask(page: Page, question: str) -> None:
    page.locator(".ask-field").fill(question)
    page.locator(".ask-field").press("Enter")


def _open(page: Page, word: str) -> None:
    page.locator(RAIL, has_text=word).click()
    expect(page.locator(".entry-title")).to_have_text(word)


def test_a_conversation_keeps_to_its_entry_through_a_card_change_a_reload_and_a_retry(
    page: Page,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Asked while the deeper article is still arriving, about a detail only it holds;
    answered while the reader is on another card; cut off by a reload, retried in its
    place; sent with no connection and retried; all of it back after a reload."""
    article_gate = Gate()
    first_gate = Gate()
    second_gate = Gate()
    first_start = "Der Generalschlüssel ist "
    first_reply = f"{first_start}ein Schlüssel für alle Schlösser."
    with live_app(
        settings,
        monkeypatch,
        handles=[
            FakeHandle([answer(ARTICLE)]),
            FakeHandle([answer("<b>Schloss</b> — замок", SECOND)]),
            FakeHandle(
                [first_start, "ein Schlüssel für alle Schlösser."],
                hold=first_gate.wait,
                hold_before=1,
            ),
            FakeHandle(["Teil"], hold=second_gate.wait),
            FakeHandle(["Zum Beispiel: Ich habe den Generalschlüssel verloren."]),
            FakeHandle(["Ja."]),
        ],
        client=FakeDirectClient([DEEPER], hold=article_gate.wait),
    ) as app:
        submit(page, app.url)
        expect(page.locator(".delete-card")).to_be_visible()
        page.locator("#word").fill(SECOND)
        page.get_by_role("button", name="Analyse").click()
        expect(page.locator(".entry-title")).to_have_text(SECOND)
        _open(page, WORD)

        # Asked while the article is still being written: the question waits for it.
        page.locator(".detail").click()
        expect(page.locator(".entry-detail")).to_contain_text("Generalschlüssel")
        _ask(page, "Was ist ein Generalschlüssel?")
        expect(page.locator(".turn-question")).to_have_text("Was ist ein Generalschlüssel?")
        expect(page.locator(".ask-field")).to_have_value("")
        page.wait_for_timeout(200)
        assert _questions(app) == []
        article_gate.open()

        expect(page.locator(".turn-answer")).to_have_text(first_start.strip())
        expect(page.locator(".turn")).to_have_attribute("data-state", "asking")
        [prompt] = _asked(app, 1)
        assert "ключ" in _section(prompt, "The analysis")
        assert _section(prompt, "The full entry") == (
            "Nur im Artikel: der Generalschlüssel öffnet jedes Schloss."
        )
        assert _section(prompt, "EARLIER QUESTIONS") is None
        assert "=== THE LEARNER'S QUESTION NOW ===\nWas ist ein Generalschlüssel?\n" in prompt

        # The reader moves on while the reply is still coming; the rest of its text lands
        # where it was asked, not on the card on screen.
        _open(page, SECOND)
        expect(page.locator(".turn")).to_have_count(0)
        first_gate.open()
        _stored_once(page, REPLY_FINISHED)
        expect(page.locator(".turn")).to_have_count(0)
        expect(page.locator(".entry-title")).to_have_text(SECOND)
        _open(page, WORD)
        expect(page.locator(".turn-answer")).to_have_text(first_reply)
        expect(page.locator(".turn-cut")).to_have_count(0)

        _ask(page, "Gib mir einen Satz damit.")
        expect(page.locator(".turn-answer").nth(1)).to_have_text("Teil")
        second = _asked(app, 2)[1]
        assert _section(second, "EARLIER QUESTIONS") == (
            f"Question 1: Was ist ein Generalschlüssel?\nYour answer 1: {first_reply}"
        )

        # A reload in the middle of the reply leaves it cut off, in its place.
        page.reload()
        second_gate.open()
        _open(page, WORD)
        expect(page.locator(".turn-question")).to_have_text(
            ["Was ist ein Generalschlüssel?", "Gib mir einen Satz damit."],
        )
        expect(page.locator(".turn-cut-note")).to_have_text("The reply was cut off.")

        page.locator(".turn-retry").click()
        expect(page.locator(".turn-answer").nth(1)).to_have_text(
            "Zum Beispiel: Ich habe den Generalschlüssel verloren.",
        )
        expect(page.locator(".turn-question", has_text="Gib mir einen Satz damit.")).to_have_count(
            1
        )
        expect(page.locator(".turn")).to_have_count(2)
        expect(page.locator(".turn-cut")).to_have_count(0)
        retried = _asked(app, 3)[2]
        assert "Teil" not in retried
        assert _section(retried, "EARLIER QUESTIONS") == _section(second, "EARLIER QUESTIONS")

        # Sent with no connection, the question stays for a retry beside it.
        page.context.set_offline(True)
        _ask(page, "Und offline?")
        expect(page.locator(".turn-cut-note")).to_have_text(
            "Not sent — the server could not be reached.",
        )
        page.context.set_offline(False)
        page.locator(".turn-retry").click()
        expect(page.locator(".turn-answer").nth(2)).to_have_text("Ja.")

        page.reload()
        _open(page, WORD)
        expect(page.locator(".turn-question")).to_have_text(
            ["Was ist ein Generalschlüssel?", "Gib mir einen Satz damit.", "Und offline?"],
        )
        expect(page.locator(".turn-answer")).to_have_text(
            [first_reply, "Zum Beispiel: Ich habe den Generalschlüssel verloren.", "Ja."],
        )
        _open(page, SECOND)
        expect(page.locator(".turn")).to_have_count(0)


def _stored_once(page: Page, test: str) -> None:
    deadline = time.monotonic() + 10
    while not page.evaluate(
        f"""async () => {{
          const open = indexedDB.open("echo-words", 1);
          const db = await new Promise((resolve) => {{ open.onsuccess = () => resolve(open.result); }});
          const saved = await new Promise((resolve) => {{
            const read = db.transaction("cache", "readonly").objectStore("cache").get("history");
            read.onsuccess = () => resolve(read.result);
          }});
          return (saved?.data ?? []).some({test});
        }}""",
    ):
        if time.monotonic() > deadline:
            raise TimeoutError("what was awaited never reached the browser's database")
        page.wait_for_timeout(50)


def test_a_word_with_no_deeper_article_is_asked_about_after_the_server_forgot_it(
    page: Page,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A restart empties the server and the page keeps the entry, which is all the
    question needs: the page sends what the reader is looking at."""
    with live_app(settings, monkeypatch, handles=[FakeHandle([answer(ARTICLE)])]) as first:
        submit(page, first.url)
        expect(page.locator(".delete-card")).to_be_visible()
        _stored_once(page, ANSWER_FINISHED)
    port = urlsplit(first.url).port

    with live_app(
        settings,
        monkeypatch,
        port=port,
        handles=[FakeHandle(["Ein Schlüssel öffnet ein Schloss."])],
    ) as second:
        page.reload()
        expect(page.locator(".entry-text")).to_contain_text("ключ")

        _ask(page, "Wozu dient er?")

        expect(page.locator(".turn-answer")).to_have_text("Ein Schlüssel öffnet ein Schloss.")
        [prompt] = _asked(second, 1)
        assert 'The wording the learner submitted: "Schlüssel"' in prompt
        assert "ключ" in _section(prompt, "The analysis")
        assert _section(prompt, "The full entry") is None
        assert "Wozu dient er?" in prompt
