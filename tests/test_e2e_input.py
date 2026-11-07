"""Clipboard insertion must preserve word boundaries before input sanitization."""

import pytest
from e2e_app import answer, live_app
from fakes import FakeHandle
from playwright.sync_api import Page, expect

from echo_words.config import Settings

pytestmark = pytest.mark.e2e


@pytest.mark.parametrize(
    ("initial", "start", "end", "pasted", "expected", "caret"),
    [
        ("", 0, 0, "one\ntwo", "one two", 7),
        ("", 0, 0, "one\rtwo", "one two", 7),
        ("", 0, 0, "one\r\ntwo", "one two", 7),
        ("", 0, 0, "\r\none\n\ntwo\r", " one  two ", 10),
        ("before OLD after", 7, 10, "one\ntwo", "before one two after", 14),
        ("beforeafter", 6, 6, " one\ntwo ", "before one two after", 15),
    ],
)
def test_multiline_paste_keeps_boundaries_selection_and_submitted_value(
    each_engine_page: Page,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    initial: str,
    start: int,
    end: int,
    pasted: str,
    expected: str,
    caret: int,
) -> None:
    page = each_engine_page
    with live_app(settings, monkeypatch, handles=[FakeHandle([answer("answer")])]) as app:
        page.goto(app.url)
        field = page.locator("#word")
        field.fill(initial)
        field.evaluate("(el, range) => el.setSelectionRange(...range)", [start, end])
        prevented = field.evaluate(
            """(el, text) => {
                const clipboard = new DataTransfer();
                clipboard.setData('text/plain', text);
                const event = new ClipboardEvent('paste', {
                    clipboardData: clipboard, bubbles: true, cancelable: true,
                });
                el.dispatchEvent(event);
                return event.defaultPrevented;
            }""",
            pasted,
        )

        assert prevented
        expect(field).to_have_value(expected)
        assert field.evaluate("el => [el.selectionStart, el.selectionEnd]") == [caret, caret]
        with page.expect_response(
            lambda response: (
                response.url.endswith("/api/words") and response.request.method == "POST"
            )
        ) as submitted:
            page.get_by_role("button", name="Analyse").click()
        assert submitted.value.request.post_data_json["word"] == expected.strip()
        expect(field).to_have_value("")


@pytest.mark.parametrize("pasted", ["one\ntwo", "one two"])
def test_native_clipboard_paste_replaces_selection_and_keeps_typing_position(
    each_engine_page: Page,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    pasted: str,
) -> None:
    page = each_engine_page
    with live_app(settings, monkeypatch) as app:
        page.goto(app.url)
        # Copy through a real textarea so both engines supply their native clipboard.
        page.evaluate("document.body.appendChild(document.createElement('textarea'))")
        source = page.locator("textarea")
        source.fill(pasted)
        source.select_text()
        page.keyboard.press("ControlOrMeta+c")
        field = page.locator("#word")
        field.fill("before OLD after")
        field.evaluate("el => el.setSelectionRange(7, 10)")

        page.keyboard.press("ControlOrMeta+v")

        expect(field).to_have_value("before one two after")
        page.keyboard.type(" next")
        expect(field).to_have_value("before one two next after")


@pytest.mark.parametrize("pasted", ["one\ntwo", "one two"])
def test_native_paste_undo_restores_selection_and_submitted_value(
    each_engine_page: Page,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    pasted: str,
) -> None:
    page = each_engine_page
    with live_app(settings, monkeypatch, handles=[FakeHandle([answer("answer")])]) as app:
        page.goto(app.url)
        page.evaluate("document.body.appendChild(document.createElement('textarea'))")
        source = page.locator("textarea")
        source.fill(pasted)
        source.select_text()
        page.keyboard.press("ControlOrMeta+c")
        field = page.locator("#word")
        # Playwright fill and paste share an Undo group in WebKit; seed without one.
        field.evaluate(
            """el => {
                el.value = 'before OLD after';
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.focus();
                el.setSelectionRange(7, 10);
            }""",
        )
        page.keyboard.press("ControlOrMeta+v")
        expect(field).to_have_value("before one two after")
        assert field.evaluate("el => [el.selectionStart, el.selectionEnd]") == [14, 14]

        page.keyboard.press("ControlOrMeta+z")

        expect(field).to_have_value("before OLD after")
        assert field.evaluate("el => [el.selectionStart, el.selectionEnd]") == [7, 10]
        with page.expect_response(
            lambda response: (
                response.url.endswith("/api/words") and response.request.method == "POST"
            )
        ) as submitted:
            page.get_by_role("button", name="Analyse").click()
        assert submitted.value.request.post_data_json["word"] == "before OLD after"
        expect(field).to_have_value("")
