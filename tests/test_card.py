import json

import pytest

from echo_words.card import CardParseError, Example, Meaning, Note, parse_card_payload


def payload(**changes) -> str:
    value = {
        "word": "bank",
        "suggestion": "",
        "meanings": [
            {
                "label": "",
                "pos": "сущ.",
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
    note, suggestion = parse_card_payload(payload(word="untrusted"), "bank", languages["en"])
    assert note == Note(
        word="bank",
        meanings=[
            Meaning(
                label="",
                pos="сущ.",
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
    note, _suggestion = parse_card_payload(payload(meanings=meanings), "bank", languages["en"])
    assert [meaning.label for meaning in note.meanings] == [
        f"значение {index}" for index in range(count)
    ]


def test_payload_with_trailing_garbage_uses_the_first_json_object(languages):
    note, _suggestion = parse_card_payload(
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
                    "pos": "сущ.",
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
                    "pos": "сущ.",
                    "translations": ["банк"],
                    "examples": [],
                },
            ],
        ),
        payload(
            meanings=[
                {
                    "label": "",
                    "pos": "сущ.",
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
                    "pos": "сущ.",
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


def test_missing_pos_is_tolerated_as_an_empty_string(languages):
    meanings = [
        {
            "label": "",
            "translations": ["банк"],
            "examples": [{"text": "The bank is open.", "translation": "Банк открыт."}],
        },
    ]
    note, _suggestion = parse_card_payload(payload(meanings=meanings), "bank", languages["en"])
    assert note.meanings[0].pos == ""


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
    note, parsed_suggestion = parse_card_payload(json.dumps(value), "bank", languages["en"])
    assert note.word == "bank"
    assert parsed_suggestion is None


def test_valid_different_suggestion_is_returned_alongside_the_note(languages):
    note, suggestion = parse_card_payload(
        payload(suggestion="receive"),
        "recieve",
        languages["en"],
    )
    assert note.word == "recieve"
    assert suggestion == "receive"


def test_suggestion_that_fails_the_language_gate_is_dropped_but_the_note_parses(languages):
    note, suggestion = parse_card_payload(
        payload(suggestion="получать"),
        "recieve",
        languages["en"],
    )
    assert note.word == "recieve"
    assert suggestion is None
