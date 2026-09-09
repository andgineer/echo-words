"""What a reader's page does when the model fails, driven through a real browser.

Every case here is a failure the pipeline is written to absorb, and each asserts the
one thing a unit test cannot: what is left on the screen afterwards. The LLM is faked
and gated, so the provisional state is held until the assertion about it has run.
"""

import json

import pytest
from anki.collection import Collection
from e2e_app import WORD, Gate, answer, live_app, submit, unreadable
from fakes import FakeDirectClient, FakeHandle, another_answer, lost_the_race
from llmbroker import LLMTimeoutError
from playwright.sync_api import Page, expect

from echo_words.anki import NOTE_TYPE_NAME, AnkiStore, MisconfiguredNoteTypeError, collection_path
from echo_words.config import Settings

pytestmark = pytest.mark.e2e

PROVISIONAL = "<b>the lane that lost</b>"
WINNER = "<b>the whole answer that won</b>"
PAID = "<b>the answer that was paid for</b>"
FIRST = "<b>the first analysis</b>"
SECOND = "<b>the second analysis</b>"
OTHER = "Wanderung"
RAIL = '[role="tablist"][aria-label="Analysed words"] [role="tab"]'


def test_a_lost_race_repaints_the_entry_instead_of_splicing_the_answer_that_won(
    page: Page,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reader is shown one lane's text while every lane runs on. When another lane
    finishes a whole answer first, what was on the page is void: it is dropped and the
    answer that won is written in its place, never appended to it."""
    gate = Gate()
    replaced = lost_the_race(answer(WINNER), winner="the-winner", streamed="the-loser")
    handle = FakeHandle([answer(PROVISIONAL)], error=replaced, hold=gate.wait)
    with live_app(settings, monkeypatch, handles=[handle]) as app:
        submit(page, app.url)
        entry = page.locator(".entry-text")
        expect(entry).to_contain_text("the lane that lost")

        gate.open()

        expect(entry).to_contain_text("the whole answer that won")
        expect(entry).not_to_contain_text("the lane that lost")
        expect(page.locator(".entry-model")).to_have_text("the-winner")


def test_a_payload_no_one_can_read_is_swapped_for_the_pools_next_answer(
    page: Page,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The article on the page is worth reading and its card is not buildable. Before
    that costs a paid call and a second budget of waiting, the same pool call is asked
    for the answer its other lane is holding, and the page is repainted with it."""
    gate = Gate()
    handle = FakeHandle(
        [unreadable(FIRST)],
        hold=gate.wait,
        others=[another_answer(answer(SECOND), llm_name="the-other-lane")],
    )
    with live_app(
        settings,
        monkeypatch,
        handles=[handle],
        client=FakeDirectClient([answer(PAID)]),
    ) as app:
        submit(page, app.url)
        entry = page.locator(".entry-text")
        expect(entry).to_contain_text("the first analysis")

        gate.open()

        expect(entry).to_contain_text("the second analysis")
        expect(entry).not_to_contain_text("the first analysis")
        expect(entry).not_to_contain_text("the answer that was paid for")
        expect(page.locator(".entry-model")).to_have_text("the-other-lane")
        assert app.broker.direct_calls == []


def test_a_budget_miss_drops_the_half_answer_it_showed_for_the_paid_one(
    page: Page,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pool answer that never lands leaves half an article on the page. The paid step
    replaces the page rather than continuing it, so the reader is never shown one
    model's opening welded onto another model's ending."""
    gate = Gate()
    handle = FakeHandle(
        [answer(PROVISIONAL)],
        error=LLMTimeoutError("the pool missed the answer budget"),
        hold=gate.wait,
    )
    with live_app(
        settings,
        monkeypatch,
        handles=[handle],
        client=FakeDirectClient([answer(PAID)]),
    ) as app:
        submit(page, app.url)
        entry = page.locator(".entry-text")
        expect(entry).to_contain_text("the lane that lost")

        gate.open()

        expect(entry).to_contain_text("the answer that was paid for")
        expect(entry).not_to_contain_text("the lane that lost")


def test_a_pool_failure_with_no_paid_step_settles_the_entry_into_a_retryable_error(
    page: Page,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With the paid step switched off there is nothing to replace the answer with, so
    the entry settles into an error offering a retry. The part-written analysis stays
    with it — it was streamed only after the judgement vouched for the wording, and it
    is marked failed rather than passed off as finished. What must not survive is the
    spinner, which would leave a dead entry looking like one still being worked on."""
    gate = Gate()
    handle = FakeHandle(
        [answer(PROVISIONAL)],
        error=LLMTimeoutError("the pool missed the answer budget"),
        hold=gate.wait,
    )
    offline = Settings(**{**settings.model_dump(), "api_model": ""})
    with live_app(offline, monkeypatch, handles=[handle]) as app:
        submit(page, app.url)
        expect(page.locator(".entry-text")).to_contain_text("the lane that lost")

        gate.open()

        expect(page.locator(".entry-error")).to_be_visible()
        expect(page.get_by_role("button", name=f"Send “{WORD}” again")).to_be_visible()
        expect(page.locator(".working.pending")).to_have_count(0)
        expect(page.locator(".entry-card-status")).to_have_count(0)


def test_a_wording_the_judgement_refuses_is_never_shown_however_much_streamed(
    page: Page,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The withhold gate outlives streaming: a complete article about a coinage reaches
    the server and still never reaches the page, because the judgement refused it."""
    handle = FakeHandle([answer("<b>an invented compound</b>", word="Löffelangst")])
    with live_app(
        settings,
        monkeypatch,
        handles=[handle],
        attestation='{"used": false, "where": ""}',
    ) as app:
        submit(page, app.url, "Löffelangst")
        expect(page.locator(".entry-card-status")).to_have_text("🚫 no card")
        expect(page.locator(".entry-notice")).to_contain_text("does not vouch")
        expect(page.locator(".entry-text")).to_have_count(0)


def test_a_second_word_being_analysed_does_not_write_into_the_card_still_open(
    page: Page,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One event stream carries every entry, and the reader may be looking at any of
    them. A second word's deltas belong to a second card, and reaching the open one
    would rewrite a finished analysis into somebody else's."""
    gate = Gate()
    with live_app(
        settings,
        monkeypatch,
        handles=[
            FakeHandle([answer(FIRST)]),
            FakeHandle([answer(SECOND, word=OTHER)], hold=gate.wait),
        ],
    ) as app:
        submit(page, app.url)
        expect(page.locator(".entry-text")).to_contain_text("the first analysis")

        page.get_by_placeholder("a word or a phrase").fill(OTHER)
        page.get_by_role("button", name="Analyse").click()
        expect(page.locator(".entry-text")).to_contain_text("the second analysis")

        page.get_by_role("tab", name=WORD).click()
        expect(page.locator(".entry-text")).to_contain_text("the first analysis")
        expect(page.locator(".entry-text")).not_to_contain_text("the second analysis")

        gate.open()

        expect(page.locator(".entry-text")).to_contain_text("the first analysis")
        expect(page.locator(".entry-text")).not_to_contain_text("the second analysis")
        page.get_by_role("tab", name=OTHER).click()
        expect(page.locator(".entry-text")).to_contain_text("the second analysis")


def test_a_retry_sends_the_word_again_and_leaves_the_failed_entry_reachable(
    page: Page,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The retry beside a failed entry sends the word again rather than reopening the
    entry that failed, so the reader ends on a working card with the failed one still
    in the rail behind it — a failure that vanished would be one nobody could report."""
    offline = Settings(**{**settings.model_dump(), "api_model": ""})
    with live_app(
        offline,
        monkeypatch,
        handles=[
            FakeHandle([answer(PROVISIONAL)], error=LLMTimeoutError("the pool missed it")),
            FakeHandle([answer(FIRST)]),
        ],
    ) as app:
        submit(page, app.url)
        expect(page.locator(".entry-error")).to_be_visible()

        page.get_by_role("button", name=f"Send “{WORD}” again").click()

        expect(page.locator(".entry-text")).to_contain_text("the first analysis")
        expect(page.locator(".entry-error")).to_have_count(0)
        expect(page.locator(RAIL)).to_have_count(2)


def test_a_card_made_for_another_headword_says_so_above_the_analysis(
    page: Page,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An answer may card a headword other than the wording submitted — an article for
    a bare noun, a corrected spelling. The page has to say so, or the reader drills a
    card they never asked for and never sees that they did."""
    carded = "der Schlüssel"
    with live_app(
        settings,
        monkeypatch,
        handles=[FakeHandle([answer(FIRST, word=carded)])],
    ) as app:
        submit(page, app.url)
        expect(page.locator(".entry-notice")).to_contain_text(f"The card is for “{carded}”")
        expect(page.locator(".entry-notice")).to_contain_text(f"not the “{WORD}” you typed")


def test_the_submitted_word_reaches_the_configured_deck_as_one_note(
    page: Page,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole point of the app is the note at the end of it. Every other test stops
    at the page; this one opens the collection the server wrote and looks."""
    with live_app(settings, monkeypatch, handles=[FakeHandle([answer(FIRST)])]) as app:
        submit(page, app.url)
        expect(page.locator(".entry-card-status")).to_contain_text("✅")
        expect(page.locator(".segments")).to_have_count(0)
        page.reload()
        expect(page.locator(".entry-card-status")).to_contain_text("✅")
        expect(page.locator(".segments")).to_have_count(0)
        written = collection_path(app.settings)

    # Opened once the server has closed the collection: pylib allows one holder.
    collection = Collection(str(written))
    try:
        notes = collection.find_notes(f"note:{NOTE_TYPE_NAME}")
        assert len(notes) == 1
        fields = collection.get_note(notes[0]).items()
        assert any(WORD in value for _name, value in fields)
        decks = {collection.decks.name(card.did) for card in collection.get_note(notes[0]).cards()}
        assert decks == {"English::Vocabulary"}
    finally:
        collection.close()


@pytest.mark.parametrize("save_fails", [False, True])
def test_sense_chips_follow_the_save_result_and_survive_reload(
    page: Page,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    save_fails: bool,
) -> None:
    article, payload = answer(FIRST).split("===CARD===")
    card = json.loads(payload)
    card["meanings"].append(
        {
            "label": "music",
            "translations": ["скрипичный ключ"],
            "examples": [
                {
                    "text": f"Read the {WORD} here.",
                    "translation": "Прочитай ключ здесь.",
                    "highlighted": f"Read the <b>{WORD}</b> here.",
                    "gapped": "Read the ___ here.",
                },
            ],
        },
    )

    async def fail_save(*_args, **_kwargs):
        raise MisconfiguredNoteTypeError

    if save_fails:
        monkeypatch.setattr(AnkiStore, "add_note", fail_save)
    gate = Gate()
    handle = FakeHandle([f"{article}===CARD==={json.dumps(card)}"], hold=gate.wait)
    with live_app(settings, monkeypatch, handles=[handle]) as app:
        submit(page, app.url)
        expect(page.locator(".entry-text")).to_contain_text("the first analysis")
        expect(page.locator(".segments")).to_have_count(0)
        gate.open()

        expected_chips = ["ключ", "скрипичный ключ"] if save_fails else ["скрипичный ключ"]
        expect(page.locator(".segment-label")).to_have_text(expected_chips)
        page.reload()
        expect(page.locator(".segment-label")).to_have_text(expected_chips)
