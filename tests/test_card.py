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
