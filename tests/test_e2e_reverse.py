"""A word typed in the target language, driven through a real browser.

What the reader is left looking at while the reverse lookup runs, once it has found
its word, when the tab's language refuses a word that may be the target's, and when
no model answers — each held at a gate, so the provisional state is asserted and not
raced.
"""

import json
import re
from pathlib import Path

import pytest
from e2e_app import Gate, answer, live_app
from fakes import FakeDirectClient, FakeHandle
from playwright.sync_api import Page, expect

from echo_words.config import Settings
from echo_words.language_catalog import BY_CODE

pytestmark = pytest.mark.e2e

RAIL = '[role="tablist"][aria-label="Analysed words"] [role="tab"]'
REFUSED = '{"used": false, "where": ""}'
VOUCHED = '{"used": true, "where": "everyday"}'
TABLE = ("table", "The book is on the table.")
DESK = ("desk", "She works at her desk.")
GRAD = ("grad", "Ovo je lep grad.")


def reverse_words(*equivalents: tuple[str, str], read_as: str) -> str:
    return json.dumps(
        {
            "verdict": "word",
            "read_as": read_as,
            "equivalents": [
                {"word": word, "example": sentence, "form": word} for word, sentence in equivalents
            ],
        },
        ensure_ascii=False,
    )


def article(text: str, word: str, sentence: str = "", **fields: str) -> str:
    """The tab's answer about a word: for one met in a sentence, with what the prompt
    asks about that sentence; for typed input, with the language it names."""
    payload = json.loads(answer("", word).split("===CARD===", 1)[1])
    if sentence:
        payload.update(context_sense=0, context_translation="Перевод.", context_surface=word)
    payload.update(fields)
    return f"{text}===CARD==={json.dumps(payload, ensure_ascii=False)}"


def type_word(page: Page, word: str) -> None:
    page.locator("#word").fill(word)
    page.get_by_role("button", name="Analyse").click()


def in_russian(page: Page) -> None:
    page.add_init_script("localStorage.setItem('echo-words.locale', 'ru')")


def test_a_target_word_is_translated_first_and_then_becomes_the_entry_for_its_word(
    page: Page,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cyrillic on the English tab is nothing English could be, so it is looked up in
    reverse with no shortcut. While that call runs the page says what it is doing; once
    it lands the entry is the one for «table», headed by what was typed."""
    gate = Gate()
    handles = [
        FakeHandle([reverse_words(TABLE, DESK, read_as="стол")], hold=gate.wait),
        FakeHandle([article("<b>table</b> — стол", "table", TABLE[1])]),
    ]
    with live_app(settings, monkeypatch, handles=handles) as app:
        page.goto(app.url)
        expect(page.locator("#word")).to_have_attribute("placeholder", "Russian or English")
        type_word(page, "стол")

        expect(page.locator(".working.pending")).to_have_text("Translating «стол» into English…")
        expect(page.locator(".entry-title")).to_have_text("стол")

        gate.open()

        expect(page.locator(".entry-title")).to_have_text("стол → table")
        expect(page.locator(RAIL)).to_have_text(["table"])
        expect(page.locator(".entry-text")).to_contain_text("table — стол")
        expect(page.locator(".segment-label")).to_have_text(["desk"])
        expect(page.locator(".delete-card")).to_be_visible()
        assert 'Wording: "стол"' in app.broker.stream_calls[0]["prompt"]


def test_a_word_the_tab_refuses_is_offered_the_target_reading_with_one_tap(
    page: Page,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Serbian and Russian share Cyrillic, so «город» on the Serbian tab is answered as
    Serbian first. When the judgement refuses it, the page offers the Russian reading,
    and the tap sends the same word with its shortcut."""
    in_russian(page)
    handles = [
        FakeHandle(
            [article("<b>город</b>", "город", submission="город", submission_language="sr")]
        ),
        FakeHandle([reverse_words(GRAD, read_as="город")]),
        FakeHandle([article("<b>grad</b> — город", "grad", GRAD[1])]),
    ]
    with live_app(
        settings,
        monkeypatch,
        handles=handles,
        attestations=[REFUSED, VOUCHED],
    ) as app:
        page.goto(app.url)
        page.get_by_test_id("lang-sr").click()
        expect(page.locator("#word")).to_have_attribute("placeholder", "Текст или !русский текст")
        page.locator("#word").fill("город")
        page.get_by_role("button", name="Разобрать").click()

        offer = page.locator(".reverse-offer")
        expect(offer).to_have_text("Искать как русское слово")
        expect(page.locator(".entry-text")).to_have_count(0)

        with page.expect_request("**/api/words") as sent:
            offer.click()

        assert sent.value.post_data_json["word"] == "!город"
        expect(page.locator(".entry-title")).to_have_text("город → grad")
        expect(page.locator(".entry-text")).to_contain_text("grad — город")
        expect(page.locator(".chips .chip")).to_have_text(["grad", "город"])


def test_a_lookup_no_model_answers_says_so_and_its_retry_keeps_the_shortcut(
    page: Page,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without its `!` the retried word would be read as Serbian, which is the one
    reading the reader has already said it is not."""
    handles = [
        FakeHandle(["neither model"]),
        FakeHandle([reverse_words(GRAD, read_as="город")]),
        FakeHandle([article("<b>grad</b> — город", "grad", GRAD[1])]),
    ]
    with live_app(
        settings,
        monkeypatch,
        handles=handles,
        client=FakeDirectClient(["wrote a lookup"]),
    ) as app:
        page.goto(app.url)
        page.get_by_test_id("lang-sr").click()
        type_word(page, "!город")

        expect(page.locator(".error-text")).to_have_text("Could not get the analysis.")
        expect(page.locator(".entry-title")).to_have_text("город")
        # The paid model was asked without the reader being asked: nothing was on the page.
        assert len(app.broker.direct_calls) == 1

        with page.expect_request("**/api/words") as sent:
            page.locator(".entry-error .retry").click()

        assert sent.value.post_data_json["word"] == "!город"
        expect(page.locator(".entry-title")).to_have_text("город → grad")


def test_input_typed_on_the_wrong_tab_takes_the_reader_to_its_own_tab(
    page: Page,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """German typed on the English tab is answered by the English tab's rules first,
    because nothing but that answer says what language it is in. The entry then moves
    to the German tab, and the reader looking at it goes there with it."""
    gate = Gate()
    typed_on_english = article(
        "<b>the English tab's answer</b>",
        "Haus",
        submission="Haus",
        submission_language="de",
    )
    handles = [
        FakeHandle([typed_on_english], hold=gate.wait),
        FakeHandle([article("<b>Haus</b> — дом", "Haus")]),
    ]
    with live_app(settings, monkeypatch, handles=handles) as app:
        page.goto(app.url)
        type_word(page, "Haus")
        expect(page.get_by_test_id("lang-en")).to_have_class(re.compile(r"\bactive\b"))
        expect(page.locator(".entry-text")).to_contain_text("the English tab's answer")

        gate.open()

        expect(page.get_by_test_id("lang-de")).to_have_class(re.compile(r"\bactive\b"))
        expect(page.locator(".entry-text")).to_contain_text("Haus — дом")
        expect(page.locator(".entry-text")).not_to_contain_text("the English tab's answer")
        expect(page.locator(".chips .chip")).to_have_text(["Haus"])
        expect(page.locator(".delete-card")).to_be_visible()

        # Nothing of it is left behind on the tab it was typed on.
        page.get_by_test_id("lang-en").click()
        expect(page.locator(".chips .chip")).to_have_count(0)


def test_input_in_a_language_no_tab_teaches_is_headed_as_a_translation(
    page: Page,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nobody here is learning French, so the answer stays as written under a heading
    that says what it is: no card, and no refusal for a word English rightly lacks."""
    french = article(
        "<b>chaussure</b> — ботинок",
        "chaussure",
        submission="chaussure",
        submission_language="fr",
    )
    with live_app(
        settings,
        monkeypatch,
        handles=[FakeHandle([french])],
        attestation=REFUSED,
    ) as app:
        page.goto(app.url)
        type_word(page, "chaussure")

        expect(page.locator(".notice-text")).to_have_text("Translated from French")
        expect(page.locator(".entry-text")).to_contain_text("chaussure — ботинок")
        expect(page.locator(".delete-card")).to_have_count(0)
        expect(page.locator(".segment-label")).to_have_count(0)
        expect(page.locator(".reverse-offer")).to_have_count(0)


def _directory_tabs(path: Path) -> list[str]:
    """Tabs for the languages whose names are the longest the hint can be asked to
    carry, in either interface language, and the three whose names do not decline."""
    longest_russian = sorted(BY_CODE.values(), key=lambda entry: -len(entry.russian))[:4]
    longest_english = sorted(BY_CODE.values(), key=lambda entry: -len(entry.english))[:4]
    chosen = {entry.code: entry for entry in (*longest_russian, *longest_english)}
    for code in ("en", "de", "sr", "af", "eo", "sw"):
        chosen[code] = BY_CODE[code]
    path.write_text(
        "".join(
            f'[languages.{entry.code}]\nname = "{entry.name}"\n'
            f'deck = "{entry.deck}"\nscript = "{entry.script}"\n\n'
            for entry in chosen.values()
        ),
        encoding="utf-8",
    )
    return list(chosen)


FITS = """
(input) => {
  const style = getComputedStyle(input);
  const room =
    input.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
  const pen = document.createElement("canvas").getContext("2d");
  pen.font = `${style.fontStyle} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
  return { room, width: pen.measureText(input.placeholder).width, hint: input.placeholder };
}
"""


@pytest.mark.parametrize("interface", ["ru", "en"])
def test_the_input_hint_fits_a_phone_for_the_longest_language_names(
    each_engine_page: Page,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    interface: str,
) -> None:
    """The hint is the only instruction the field has, and a clipped one loses the
    shortcut or the second language. Measured in the field's own font at 360 px."""
    page = each_engine_page
    page.set_viewport_size({"width": 360, "height": 740})
    page.add_init_script(f"localStorage.setItem('echo-words.locale', '{interface}')")
    tabs = _directory_tabs(tmp_path / "many.toml")
    wide = settings.model_copy(update={"languages_config": tmp_path / "many.toml"})
    with live_app(wide, monkeypatch) as app:
        page.goto(app.url)
        field = page.locator("#word")
        expect(field).not_to_have_attribute("placeholder", "")
        measured = []
        for code in tabs:
            page.get_by_test_id(f"lang-{code}").click()
            measured.append(field.evaluate(FITS))

    assert len({item["hint"] for item in measured}) > len(tabs) // 2
    clipped = [item for item in measured if item["width"] > item["room"]]
    assert clipped == []
