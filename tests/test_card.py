import json

import pytest

from echo_words.card import (
    MAX_CANDIDATES,
    CardParseError,
    Example,
    Meaning,
    Note,
    parse_card_payload,
)
from echo_words.languages import MAX_CONTEXT_LENGTH


def _note(payload_text, word, language):
    return parse_card_payload(payload_text, word, language).note


def payload(**changes) -> str:
    value = {
        "word": "bank",
        "suggestion": "",
        "meanings": [
            {
                "label": "",
                "translations": ["банк", "банковское учреждение"],
                "examples": [
                    {
                        "text": "The bank opens at nine.",
                        "translation": "Банк открывается в девять.",
                    },
                ],
            },
        ],
    }
    value.update(changes)
    return json.dumps(value)


def test_valid_single_meaning_payload_uses_the_canonical_input_word(languages):
    parsed = parse_card_payload(payload(word="untrusted"), "bank", languages["en"])
    note, suggestion = parsed.note, parsed.suggestion
    assert note == Note(
        word="bank",
        meanings=[
            Meaning(
                label="",
                translations=["банк", "банковское учреждение"],
                examples=[
                    Example(
                        text="The bank opens at nine.",
                        translation="Банк открывается в девять.",
                    ),
                ],
            ),
        ],
    )
    assert suggestion is None


@pytest.mark.parametrize("count", [2, 3])
def test_valid_multi_meaning_payload_keeps_each_labeled_meaning(languages, count):
    meanings = [
        {
            "label": f"значение {index}",
            "pos": "сущ.",
            "translations": [f"перевод {index}"],
            "examples": [
                {"text": f"Bank example {index}.", "translation": f"Пример {index}."},
            ],
        }
        for index in range(count)
    ]
    note = parse_card_payload(payload(meanings=meanings), "bank", languages["en"]).note
    assert [meaning.label for meaning in note.meanings] == [
        f"значение {index}" for index in range(count)
    ]


def test_payload_with_trailing_garbage_uses_the_first_json_object(languages):
    note = _note(
        f"{payload()} trailing model commentary",
        "bank",
        languages["en"],
    )
    assert note.word == "bank"


@pytest.mark.parametrize(
    "broken",
    [
        "not JSON",
        payload(meanings=[]),
        payload(
            meanings=[
                {
                    "label": "",
                    "translations": [],
                    "examples": [
                        {"text": "The bank is open.", "translation": "Банк открыт."},
                    ],
                },
            ],
        ),
        payload(
            meanings=[
                {
                    "label": "",
                    "translations": ["банк"],
                    "examples": [],
                },
            ],
        ),
        payload(
            meanings=[
                {
                    "label": "",
                    "translations": ["банк"],
                    "examples": [
                        {"text": f"Bank example {index}.", "translation": f"Пример {index}."}
                        for index in range(3)
                    ],
                },
            ],
        ),
        payload(
            meanings=[
                {
                    "label": str(index),
                    "translations": ["перевод"],
                    "examples": [
                        {"text": "Bank example.", "translation": "Пример."},
                    ],
                }
                for index in range(4)
            ],
        ),
        payload(
            meanings=[
                {
                    "translations": ["перевод"],
                    "examples": [{"text": "Bank example.", "translation": "Пример."}],
                },
            ],
        ),
        payload(word=""),
        payload(word=" \t"),
    ],
    ids=[
        "malformed-json",
        "empty-meanings",
        "empty-translations",
        "empty-examples",
        "three-examples",
        "four-meanings",
        "missing-label",
        "empty-echoed-word",
        "whitespace-echoed-word",
    ],
)
def test_invalid_payload_is_rejected(languages, broken):
    with pytest.raises(CardParseError):
        parse_card_payload(broken, "bank", languages["en"])


def test_a_broken_payload_carries_what_the_json_decoder_objected_to(languages):
    # The free pool's own failure: escaping stops halfway through a \uXXXX sequence.
    with pytest.raises(CardParseError, match=r"Invalid \\uXXXX escape"):
        parse_card_payload('{"word": "bank", "pos": "\\u04гл."}', "bank", languages["en"])


@pytest.mark.parametrize("label", ["", " \t"])
def test_multi_meaning_payload_requires_non_empty_labels(languages, label):
    meanings = [
        {
            "label": label,
            "translations": ["банк"],
            "examples": [{"text": "The bank is open.", "translation": "Банк открыт."}],
        },
        {
            "label": "берег",
            "translations": ["берег"],
            "examples": [{"text": "Sit on the bank.", "translation": "Сядь на берегу."}],
        },
    ]

    with pytest.raises(CardParseError):
        parse_card_payload(payload(meanings=meanings), "bank", languages["en"])


@pytest.mark.parametrize("suggestion", [None, "", "BANK"])
def test_absent_empty_or_same_suggestion_does_not_affect_the_note(languages, suggestion):
    value = json.loads(payload())
    if suggestion is None:
        value.pop("suggestion")
    else:
        value["suggestion"] = suggestion
    parsed = parse_card_payload(json.dumps(value), "bank", languages["en"])
    note, parsed_suggestion = parsed.note, parsed.suggestion
    assert note.word == "bank"
    assert parsed_suggestion is None


def test_valid_different_suggestion_is_returned_alongside_the_note(languages):
    parsed = parse_card_payload(
        payload(suggestion="receive"),
        "recieve",
        languages["en"],
    )
    note, suggestion = parsed.note, parsed.suggestion
    assert note.word == "recieve"
    assert suggestion == "receive"


def test_suggestion_that_fails_the_language_gate_is_dropped_but_the_note_parses(languages):
    parsed = parse_card_payload(
        payload(suggestion="получать"),
        "recieve",
        languages["en"],
    )
    note, suggestion = parsed.note, parsed.suggestion
    assert note.word == "recieve"
    assert suggestion is None


def test_analysed_unit_is_the_models_headword_when_it_passes_the_word_rule(languages):
    parsed = parse_card_payload(payload(word="allein"), "ist allein im Restaurant", languages["de"])
    assert parsed.analysed == "allein"
    assert parsed.note.word == "ist allein im Restaurant"
    assert not parsed.input_is_unit


def test_input_is_the_unit_when_the_model_echoes_it(languages):
    parsed = parse_card_payload(payload(word="Rad  fahren"), "Rad fahren", languages["de"])
    assert parsed.input_is_unit


def test_a_single_word_is_its_own_unit_even_under_a_dictionary_headword(languages):
    # An inflected word is answered under the form a dictionary lists, which is
    # the same unit, not a unit found inside a longer input.
    parsed = parse_card_payload(payload(word="одржавати"), "одржава", languages["sr"])
    assert parsed.analysed == "одржавати"
    assert parsed.input_is_unit


@pytest.mark.parametrize("headword", ["bank!", "банк", "a" * 60])
def test_headword_that_fails_the_word_rule_falls_back_to_the_input(languages, headword):
    # It would be one tap from the front of a note, so it is held to the rule a
    # typed word is held to; failing it means the answer is about the input after all.
    parsed = parse_card_payload(payload(word=headword), "bank", languages["en"])
    assert parsed.analysed == "bank"
    assert parsed.input_is_unit


def test_candidates_are_held_to_the_rule_typed_input_is_held_to(languages):
    parsed = parse_card_payload(
        payload(word="allein", candidates=["allein", "Restaurant!", "", "einsam", 7, "allein"]),
        "ist allein im Restaurant",
        languages["de"],
    )
    # "allein" is the analysed unit and never repeated; the rest are dropped or kept
    # exactly as validate_word would decide for a typed word.
    assert parsed.candidates == ["einsam"]


def test_candidates_are_capped(languages):
    parsed = parse_card_payload(
        payload(word="allein", candidates=["a", "b", "c", "d", "e"]),
        "ist allein im Restaurant",
        languages["de"],
    )
    assert len(parsed.candidates) == MAX_CANDIDATES


def test_absent_or_broken_candidates_are_an_empty_list(languages):
    for value in (None, "nope", 5, {}):
        parsed = parse_card_payload(payload(candidates=value), "bank", languages["en"])
        assert parsed.candidates == []


def two_meanings() -> list[dict]:
    return [
        {
            "label": "учреждение",
            "translations": ["банк"],
            "examples": [{"text": "The bank is open.", "translation": "Банк открыт."}],
        },
        {
            "label": "берег",
            "translations": ["берег"],
            "examples": [{"text": "Sit on the bank.", "translation": "Сядь на берегу."}],
        },
    ]


def test_a_payload_without_cards_asks_for_nothing_beyond_the_two(languages):
    parsed = parse_card_payload(payload(), "bank", languages["en"])

    assert parsed.context_sense is None
    assert parsed.context_prompt == ""
    assert parsed.split_recall is False


def test_the_card_requests_are_read_off_the_payload(languages):
    parsed = parse_card_payload(
        payload(
            meanings=two_meanings(),
            cards=[
                {"kind": "context", "sense": 1},
                {"kind": "context_production", "prompt": "Мы сидели  на\nберегу."},
                {"kind": "split_recall"},
            ],
        ),
        "bank",
        languages["en"],
    )

    assert parsed.context_sense == 1
    assert parsed.context_prompt == "Мы сидели на берегу."
    assert parsed.split_recall is True


def test_an_unknown_kind_is_ignored_rather_than_fatal(languages):
    """Anything can stand where a kind belongs, including a value that cannot be looked
    up in a dict at all — and the analysis is already on screen when this is read."""
    parsed = parse_card_payload(
        payload(
            cards=[
                {"kind": "cloze_deletion"},
                "nonsense",
                7,
                {"kind": ["context"]},
                {"kind": {"context": 0}},
                {"kind": 7},
                {"kind": None},
                {},
                {"kind": "context", "sense": 0},
            ],
        ),
        "bank",
        languages["en"],
    )

    assert parsed.context_sense == 0
    assert parsed.split_recall is False


@pytest.mark.parametrize(
    "item",
    [
        {"kind": "context", "sense": 1},
        {"kind": "context", "sense": -1},
        {"kind": "context", "sense": 9},
        {"kind": "context", "sense": "0"},
        {"kind": "context", "sense": True},
        {"kind": "context", "sense": None},
        {"kind": "context"},
    ],
)
def test_a_sense_that_names_no_meaning_drops_the_context_card(languages, item):
    """The absent index is in here too: defaulting it to the first meaning would back
    the card with a sense the context need not be about, and it would look right."""
    parsed = parse_card_payload(payload(cards=[item]), "bank", languages["en"])

    assert parsed.context_sense is None


def test_a_split_asked_for_on_a_single_meaning_is_dropped(languages):
    parsed = parse_card_payload(
        payload(cards=[{"kind": "split_recall"}]),
        "bank",
        languages["en"],
    )

    assert parsed.split_recall is False


def test_a_duplicate_kind_keeps_the_first(languages):
    parsed = parse_card_payload(
        payload(
            meanings=two_meanings(),
            cards=[
                {"kind": "context", "sense": 1},
                {"kind": "context", "sense": 0},
                {"kind": "context_production", "prompt": "первый"},
                {"kind": "context_production", "prompt": "второй"},
            ],
        ),
        "bank",
        languages["en"],
    )

    assert parsed.context_sense == 1
    assert parsed.context_prompt == "первый"


def test_a_first_request_the_model_spoiled_is_not_rescued_by_a_second(languages):
    parsed = parse_card_payload(
        payload(
            meanings=two_meanings(),
            cards=[{"kind": "context", "sense": 7}, {"kind": "context", "sense": 0}],
        ),
        "bank",
        languages["en"],
    )

    assert parsed.context_sense is None


@pytest.mark.parametrize("cards", [None, "nope", 5, {}, []])
def test_absent_or_broken_cards_ask_for_nothing(languages, cards):
    parsed = parse_card_payload(payload(cards=cards), "bank", languages["en"])

    assert parsed.context_sense is None
    assert parsed.context_prompt == ""
    assert parsed.split_recall is False


@pytest.mark.parametrize("prompt", [None, "", "   ", 7])
def test_a_production_card_without_a_prompt_has_no_front(languages, prompt):
    parsed = parse_card_payload(
        payload(cards=[{"kind": "context_production", "prompt": prompt}]),
        "bank",
        languages["en"],
    )

    assert parsed.context_prompt == ""


def test_a_sense_the_parser_refused_leaves_the_production_card_asked_for(languages):
    """The two context cards are decided separately, and only one needs a sense."""
    parsed = parse_card_payload(
        payload(
            cards=[
                {"kind": "context", "sense": 9},
                {"kind": "context_production", "prompt": "Банк открыт."},
            ],
        ),
        "bank",
        languages["en"],
    )

    assert parsed.context_sense is None
    assert parsed.context_prompt == "Банк открыт."


def test_a_prompt_is_sanitised_like_the_context_it_renders(languages):
    """One rule for free text on a card front, whether the user pasted it or the
    model wrote it: single-spaced, printable, bounded."""
    parsed = parse_card_payload(
        payload(
            cards=[
                {
                    "kind": "context_production",
                    "prompt": "\u0007Банк  открыт\nв\u200bдевять.",
                },
            ],
        ),
        "bank",
        languages["en"],
    )

    assert parsed.context_prompt == "Банк открыт в девять."


def test_a_prompt_is_bounded_like_the_context_it_renders(languages):
    """It goes on a card front and stays there: an answer that returned the whole
    analysis would put a wall of text on every review."""
    parsed = parse_card_payload(
        payload(cards=[{"kind": "context_production", "prompt": "очень длинно. " * 200}]),
        "bank",
        languages["en"],
    )

    assert len(parsed.context_prompt) <= MAX_CONTEXT_LENGTH
    assert parsed.context_prompt.startswith("очень длинно.")
