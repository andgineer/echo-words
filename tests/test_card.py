import json

import pytest

from echo_words.card import (
    CardParseError,
    Example,
    ParsedText,
    ParsedUnit,
    parse_answer_payload,
)


def example(word="bank"):
    return {
        "text": f"The {word} opens.",
        "translation": "Перевод.",
        "highlighted": f"The <b>{word}</b> opens.",
        "gapped": "The ___ opens.",
    }


def meaning(label="", **changes):
    value = {"label": label, "translations": ["банк"], "examples": [example()]}
    value.update(changes)
    return value


def payload(**changes):
    value = {
        "kind": "unit",
        "word": "bank",
        "word_relation": "same",
        "suggestion": "",
        "meanings": [meaning()],
        "segments": [],
    }
    value.update(changes)
    return json.dumps(value)


def test_a_unit_uses_the_validated_returned_dictionary_headword(languages):
    parsed = parse_answer_payload(
        payload(
            word="give up",
            word_relation="morphology",
            meanings=[meaning(examples=[example("gave up")])],
        ),
        "gave up",
        languages["en"],
        unit_intent=True,
    )

    assert isinstance(parsed, ParsedUnit)
    assert parsed.note.word == "give up"
    assert parsed.note.meaning.examples[0] == Example(
        "The gave up opens.",
        "Перевод.",
        "The <b>gave up</b> opens.",
        "The ___ opens.",
    )


def test_unit_and_text_branches_cannot_mix(languages):
    with pytest.raises(CardParseError, match="text answer contains unit fields"):
        parse_answer_payload(
            json.dumps({"kind": "text", "combinations": [], "word": "bank"}),
            "The bank opens.",
            languages["en"],
        )
    with pytest.raises(CardParseError, match="unit answer contains text combinations"):
        parse_answer_payload(
            payload(combinations=[{"surface": "bank opens"}]),
            "bank",
            languages["en"],
        )


def test_explicit_unit_intent_refuses_a_text_verdict(languages):
    with pytest.raises(CardParseError, match="unit-intent"):
        parse_answer_payload(
            json.dumps({"kind": "text", "combinations": []}),
            "Rad fahren",
            languages["de"],
            unit_intent=True,
        )


def test_singular_keys_and_singletons_are_normalized(languages):
    parsed = parse_answer_payload(
        payload(
            meanings=[
                {
                    "label": "",
                    "translation": "банк",
                    "examples": example(),
                },
            ],
        ),
        "bank",
        languages["en"],
    )

    assert isinstance(parsed, ParsedUnit)
    assert parsed.note.meaning.translations == ["банк"]
    assert len(parsed.note.meaning.examples) == 1


def test_bad_meanings_are_dropped_and_context_sense_is_remapped(languages):
    parsed = parse_answer_payload(
        payload(
            meanings=[
                meaning("учреждение"),
                meaning("сломано", translations=[]),
                meaning("берег", translations=["берег"]),
            ],
            context_sense=2,
        ),
        "bank",
        languages["en"],
    )

    assert isinstance(parsed, ParsedUnit)
    assert [item.label for item in parsed.note.meanings] == ["учреждение", "берег"]
    assert parsed.note.sense == 1


def test_an_empty_singleton_label_survives_after_a_malformed_sibling_is_dropped(
    languages,
):
    parsed = parse_answer_payload(
        payload(
            meanings=[
                meaning("broken", translations=[]),
                meaning("", translations=["банк"]),
            ],
            context_sense=1,
        ),
        "bank",
        languages["en"],
    )

    assert isinstance(parsed, ParsedUnit)
    assert [item.label for item in parsed.note.meanings] == [""]
    assert parsed.note.sense == 0


def test_a_dropped_or_unusable_context_sense_falls_back_to_the_first(languages):
    parsed = parse_answer_payload(
        payload(
            meanings=[meaning("first"), meaning("bad", examples=[])],
            context_sense=1,
        ),
        "bank",
        languages["en"],
    )

    assert isinstance(parsed, ParsedUnit)
    assert parsed.note.sense == 0


def test_an_answer_with_no_usable_meaning_fails(languages):
    with pytest.raises(CardParseError, match="no usable meaning"):
        parse_answer_payload(
            payload(meanings=[meaning(translations=[]), meaning(examples=[])]),
            "bank",
            languages["en"],
        )


def test_invalid_examples_do_not_spend_the_two_retained_example_slots(languages):
    valid = example()
    parsed = parse_answer_payload(
        payload(
            meanings=[
                meaning(
                    examples=[
                        {"text": "broken"},
                        {"translation": "broken"},
                        valid,
                    ],
                ),
            ],
        ),
        "bank",
        languages["en"],
    )

    assert isinstance(parsed, ParsedUnit)
    assert parsed.note.meaning.examples == [
        Example(
            valid["text"],
            valid["translation"],
            valid["highlighted"],
            valid["gapped"],
        ),
    ]


def test_no_sense_count_ceiling_rejects_a_bounded_answer(languages):
    meanings = [meaning(f"sense {index}") for index in range(9)]
    parsed = parse_answer_payload(payload(meanings=meanings), "bank", languages["en"])

    assert isinstance(parsed, ParsedUnit)
    assert len(parsed.note.meanings) == 9


def test_markup_leaking_into_the_plain_example_is_unwrapped(languages):
    marked = example()
    marked["text"] = "The <b>bank</b> opens."

    parsed = parse_answer_payload(
        payload(meanings=[meaning(examples=[marked])]),
        "bank",
        languages["en"],
    )

    assert isinstance(parsed, ParsedUnit)
    assert parsed.note.meaning.examples[0].text == "The bank opens."
    assert parsed.note.meaning.examples[0].gapped == "The ___ opens."


@pytest.mark.parametrize(
    "changes",
    [
        {"highlighted": ""},
        {"highlighted": 4},
        {"highlighted": "The bank opens."},
    ],
)
def test_an_unmarked_or_unprintable_highlight_sinks_its_example(languages, changes):
    broken = example()
    broken.update(changes)
    with pytest.raises(CardParseError, match="no usable meaning"):
        parse_answer_payload(
            payload(meanings=[meaning(examples=[broken])]),
            "bank",
            languages["en"],
        )


@pytest.mark.parametrize("gapped", ["", 4, "The ___ closes.", "The <b>___</b> opens."])
def test_the_blanked_form_is_derived_and_a_returned_one_is_ignored(languages, gapped):
    supplied = example()
    supplied["gapped"] = gapped

    parsed = parse_answer_payload(
        payload(meanings=[meaning(examples=[supplied])]),
        "bank",
        languages["en"],
    )

    assert isinstance(parsed, ParsedUnit)
    assert parsed.note.meaning.examples[0].gapped == "The ___ opens."


def test_the_plain_sentence_comes_from_the_highlight_not_from_a_returned_field(languages):
    varied = example()
    varied["highlighted"] = "Yesterday, the <b>bank</b> opened!"
    varied["text"] = "Something else entirely."

    parsed = parse_answer_payload(
        payload(meanings=[meaning(examples=[varied])]),
        "bank",
        languages["en"],
    )

    assert isinstance(parsed, ParsedUnit)
    assert parsed.note.meaning.examples[0].text == "Yesterday, the bank opened!"
    assert parsed.note.meaning.examples[0].gapped == "Yesterday, the ___ opened!"


def test_selected_context_example_must_equal_the_supplied_context(languages):
    with pytest.raises(CardParseError, match="must equal the supplied context"):
        parse_answer_payload(
            payload(context_sense=0),
            "bank",
            languages["en"],
            unit_intent=True,
            context="We sat on the bank.",
        )


def test_context_forms_are_built_from_the_exact_selected_surface(languages):
    context = "We sat on the bank."
    contextual = example()
    contextual.update(highlighted="<b>We sat</b> on the <b>bank</b>.")

    parsed = parse_answer_payload(
        payload(meanings=[meaning(examples=[contextual])], context_sense=0),
        "bank",
        languages["en"],
        unit_intent=True,
        context=context,
    )

    assert isinstance(parsed, ParsedUnit)
    assert parsed.note.meaning.examples[0] == Example(
        context,
        "Перевод.",
        "We sat on the <b>bank</b>.",
        "We sat on the ___.",
    )


def test_separated_context_surface_is_marked_in_source_order(languages):
    context = "Er steht jeden Morgen um sechs auf."
    contextual = {
        "text": context,
        "translation": "Он встаёт каждое утро в шесть.",
        "highlighted": f"<b>{context}</b>",
        "gapped": "___",
    }

    parsed = parse_answer_payload(
        payload(
            word="aufstehen",
            word_relation="morphology",
            meanings=[meaning(examples=[contextual])],
            context_sense=0,
        ),
        "steht auf",
        languages["de"],
        unit_intent=True,
        context=context,
    )

    assert isinstance(parsed, ParsedUnit)
    assert parsed.note.meaning.examples[0].highlighted == (
        "Er <b>steht</b> jeden Morgen um sechs <b>auf</b>."
    )
    assert parsed.note.meaning.examples[0].gapped == "Er ___ jeden Morgen um sechs ___."


def test_invalid_returned_headword_fails_instead_of_using_the_submission(languages):
    with pytest.raises(CardParseError, match="dictionary headword"):
        parse_answer_payload(payload(word="bank!"), "banked", languages["en"])


def test_a_correct_spelling_suggestion_retains_the_submitted_word(languages):
    parsed = parse_answer_payload(
        payload(word="recieve", word_relation="typo", suggestion="receive"),
        "  recieve  ",
        languages["en"],
    )

    assert isinstance(parsed, ParsedUnit)
    assert parsed.note.word == "recieve"
    assert parsed.word_relation == "typo"
    assert parsed.suggestion == "receive"


def test_a_corrected_headword_is_kept_so_the_note_is_one_word_throughout(languages):
    """The meanings, examples and gap under this headword describe the corrected
    word, so the note carries that word too — and the reader is told it did."""
    parsed = parse_answer_payload(
        payload(word="receive", word_relation="typo", suggestion=""),
        "recieve",
        languages["en"],
    )

    assert isinstance(parsed, ParsedUnit)
    assert parsed.note.word == "receive"
    assert parsed.word_relation == "typo"
    # Naming "receive" as the suggestion would offer the reader the word already carded.
    assert parsed.suggestion is None


@pytest.mark.parametrize(
    ("word", "suggestion", "expected_suggestion"),
    [
        ("receive", "receive", None),
        ("receiving", "receive", "receive"),
        ("receive", "", None),
    ],
)
def test_the_analysed_headword_is_the_one_carded(
    languages,
    word,
    suggestion,
    expected_suggestion,
):
    """However the answer names the correction, the note is built from the word the
    answer described — never from a spelling nothing under the heading is about."""
    parsed = parse_answer_payload(
        payload(word=word, word_relation="typo", suggestion=suggestion),
        "recieve",
        languages["en"],
    )

    assert isinstance(parsed, ParsedUnit)
    assert parsed.note.word == word
    assert parsed.word_relation == "typo"
    assert parsed.suggestion == expected_suggestion


def test_a_same_relation_contradicted_by_the_word_is_not_read_as_a_correction(languages):
    """The answer analysed another spelling while calling it the same word, and that
    contradiction says nothing about the learner's spelling. Reading it as a correction
    would call a dictionary form for an inflected submission a typo — which is what the
    submissions of a learner mostly are — so the card is made and no accusation with it.
    """
    parsed = parse_answer_payload(
        payload(word="можда", word_relation="same", suggestion=""),
        "мозда",
        languages["sr"],
    )

    assert isinstance(parsed, ParsedUnit)
    assert parsed.note.word == "можда"
    assert parsed.word_relation == "morphology"
    assert parsed.suggestion is None


def test_a_headword_differing_from_the_submission_only_in_case_stays_the_same_word(
    languages,
):
    parsed = parse_answer_payload(
        payload(word="он", word_relation="same", suggestion=""),
        "Он",
        languages["sr"],
    )

    assert isinstance(parsed, ParsedUnit)
    assert parsed.note.word == "он"
    assert parsed.word_relation == "same"
    assert parsed.suggestion is None


def test_a_headword_transliterated_into_the_other_serbian_script_is_not_a_typo(languages):
    parsed = parse_answer_payload(
        payload(word="можда", word_relation="same", suggestion=""),
        "možda",
        languages["sr"],
    )

    assert isinstance(parsed, ParsedUnit)
    assert parsed.word_relation == "same"
    assert parsed.suggestion is None


def test_morphology_can_change_the_headword_without_a_spelling_suggestion(languages):
    parsed = parse_answer_payload(
        payload(word="receive", word_relation="morphology", suggestion=""),
        "received",
        languages["en"],
    )

    assert isinstance(parsed, ParsedUnit)
    assert parsed.note.word == "receive"
    assert parsed.word_relation == "morphology"
    assert parsed.suggestion is None


def test_a_commoner_near_spelling_is_offered_beside_the_submitted_word(languages):
    parsed = parse_answer_payload(
        payload(word="causal", word_relation="same", suggestion="", also_common="casual"),
        "causal",
        languages["en"],
    )

    assert isinstance(parsed, ParsedUnit)
    assert parsed.note.word == "causal"
    assert parsed.word_relation == "same"
    assert parsed.suggestion == "casual"


def test_a_declared_correction_outranks_a_commoner_near_spelling(languages):
    parsed = parse_answer_payload(
        payload(
            word="receive",
            word_relation="typo",
            suggestion="receive",
            also_common="relieve",
        ),
        "recieve",
        languages["en"],
    )

    assert isinstance(parsed, ParsedUnit)
    assert parsed.word_relation == "typo"
    # The correction is the headword here, so nothing is offered beside it — and what
    # is dropped must not be replaced by the weaker advice.
    assert parsed.suggestion is None


@pytest.mark.parametrize("also_common", ["", "  ", "causal", "not a word!", 7, None])
def test_an_unusable_commoner_near_spelling_offers_nothing(languages, also_common):
    parsed = parse_answer_payload(
        payload(word="causal", word_relation="same", suggestion="", also_common=also_common),
        "causal",
        languages["en"],
    )

    assert isinstance(parsed, ParsedUnit)
    assert parsed.suggestion is None


@pytest.mark.parametrize("word_relation", [None, "", "correction", 4])
def test_an_unusable_relation_label_falls_back_to_the_spellings(languages, word_relation):
    parsed = parse_answer_payload(
        payload(word_relation=word_relation),
        "bank",
        languages["en"],
    )

    assert isinstance(parsed, ParsedUnit)
    assert parsed.word_relation == "same"
    assert parsed.suggestion is None


@pytest.mark.parametrize(
    ("word_relation", "word", "suggestion", "expected"),
    [
        ("same", "banks", "", ("morphology", "banks", None)),
        # An answer that analysed the submitted spelling and names another one is not
        # calling it a misspelling: the suggestion stands as advice beside the card.
        ("same", "bank", "banks", ("same", "bank", "banks")),
        ("morphology", "bank", "banks", ("same", "bank", "banks")),
        ("typo", "bank", "", ("same", "bank", None)),
        ("typo", "banks", "bank", ("typo", "banks", None)),
        ("morphology", "banks", "", ("morphology", "banks", None)),
    ],
)
def test_inconsistent_word_and_suggestion_combinations_are_reconciled(
    languages,
    word_relation,
    word,
    suggestion,
    expected,
):
    parsed = parse_answer_payload(
        payload(word_relation=word_relation, word=word, suggestion=suggestion),
        "bank",
        languages["en"],
    )

    assert isinstance(parsed, ParsedUnit)
    assert (parsed.word_relation, parsed.note.word, parsed.suggestion) == expected


def test_generated_example_marks_every_submitted_token_that_occurs_verbatim(languages):
    incomplete = {
        "text": "Es macht Spaß, Rad zu fahren.",
        "translation": "Ездить на велосипеде весело.",
        "highlighted": "Es macht Spaß, <b>Rad zu</b> fahren.",
        "gapped": "Es macht Spaß, ___ fahren.",
    }

    with pytest.raises(CardParseError, match="no usable meaning"):
        parse_answer_payload(
            payload(
                word="Rad fahren",
                meanings=[meaning(examples=[incomplete])],
            ),
            "Rad fahren",
            languages["de"],
        )


def test_generated_example_token_check_does_not_assume_matching_morphology(languages):
    inflected = {
        "text": "Ich fahre jeden Tag Rad.",
        "translation": "Я каждый день езжу на велосипеде.",
        "highlighted": "Ich <b>fahre</b> jeden Tag <b>Rad</b>.",
        "gapped": "Ich ___ jeden Tag ___.",
    }

    parsed = parse_answer_payload(
        payload(word="Rad fahren", meanings=[meaning(examples=[inflected])]),
        "Rad fahren",
        languages["de"],
    )

    assert isinstance(parsed, ParsedUnit)


def test_adjacent_bold_target_spans_are_normalized_for_one_blank(languages):
    split = example("give up")
    split["highlighted"] = "The <b>give</b> <b>up</b> opens."
    split["gapped"] = "The ___ opens."

    parsed = parse_answer_payload(
        payload(word="give up", meanings=[meaning(examples=[split])]),
        "give up",
        languages["en"],
    )

    assert isinstance(parsed, ParsedUnit)
    assert parsed.note.meaning.examples[0].highlighted == "The <b>give up</b> opens."


def test_adjacent_bold_normalization_does_not_allow_a_whole_sentence(languages):
    split = example()
    split["highlighted"] = "<b>The</b> <b>bank</b> <b>opens</b>."
    split["gapped"] = "___."

    with pytest.raises(CardParseError, match="no usable meaning"):
        parse_answer_payload(
            payload(meanings=[meaning(examples=[split])]),
            "bank",
            languages["en"],
        )


def test_markup_other_than_the_unit_mark_makes_the_example_unusable(languages):
    varied = example()
    varied["highlighted"] = "<script>x</script>The <b>bank</b> opens."

    with pytest.raises(CardParseError, match="no usable meaning"):
        parse_answer_payload(
            payload(meanings=[meaning(examples=[varied])]),
            "bank",
            languages["en"],
        )


@pytest.mark.parametrize(
    "highlighted",
    [
        "<b>The bank opens.</b>",
        "<b>The</b> <b>bank</b> <b>opens</b>.",
    ],
)
def test_a_highlight_covering_the_whole_sentence_is_rejected(languages, highlighted):
    broken = example()
    broken.update(highlighted=highlighted)

    with pytest.raises(CardParseError, match="no usable meaning"):
        parse_answer_payload(
            payload(meanings=[meaning(examples=[broken])]),
            "bank",
            languages["en"],
        )


def test_text_answer_is_structurally_distinct(languages):
    parsed = parse_answer_payload(
        json.dumps({"kind": "text", "combinations": []}),
        "The bank opens.",
        languages["en"],
    )
    assert isinstance(parsed, ParsedText)
    assert [segment.label for segment in parsed.segments] == ["The", "bank", "opens"]


def test_a_bare_string_value_is_requoted(languages):
    broken = payload().replace('"word_relation": "same"', '"word_relation": same')

    parsed = parse_answer_payload(broken, "bank", languages["en"])

    assert isinstance(parsed, ParsedUnit)
    assert parsed.word_relation == "same"


def test_a_full_stop_between_two_items_is_read_as_a_comma(languages):
    broken = payload().replace('], "segments"', ']. "segments"')

    parsed = parse_answer_payload(broken, "bank", languages["en"])

    assert isinstance(parsed, ParsedUnit)
    assert parsed.note.word == "bank"


def test_a_backslash_escaping_nothing_is_dropped(languages):
    value = json.loads(payload(meanings=[meaning(translations=["прекратить"])]))
    broken = json.dumps(value, ensure_ascii=False).replace(
        '"прекратить"',
        r'"\прекратить"',
    )

    parsed = parse_answer_payload(broken, "bank", languages["en"])

    assert isinstance(parsed, ParsedUnit)
    assert parsed.note.meaning.translations == ["прекратить"]


def test_a_payload_no_repair_can_decode_still_fails(languages):
    with pytest.raises(CardParseError, match="not valid JSON"):
        parse_answer_payload('{"kind": "unit", "word"', "bank", languages["en"])


def test_a_repair_which_does_not_apply_cannot_corrupt_the_one_which_does(languages):
    value = json.loads(payload(meanings=[meaning(translations=["прекратить"])]))
    value["meanings"][0]["examples"][0]["translation"] = "значит: остановить"
    broken = json.dumps(value, ensure_ascii=False).replace(
        '"прекратить"',
        r'"\прекратить"',
    )

    parsed = parse_answer_payload(broken, "bank", languages["en"])

    assert isinstance(parsed, ParsedUnit)
    assert parsed.note.meaning.translations == ["прекратить"]
    assert parsed.note.meaning.examples[0].translation == "значит: остановить"


def test_senses_that_all_lack_a_label_are_kept_rather_than_dropped(languages):
    parsed = parse_answer_payload(
        payload(meanings=[meaning(), meaning(translations=["берег"])]),
        "bank",
        languages["en"],
    )

    assert isinstance(parsed, ParsedUnit)
    assert [item.translations for item in parsed.note.meanings] == [["банк"], ["берег"]]


def test_an_unlabelled_sense_is_kept_beside_a_labelled_one_and_still_cards(languages):
    # Measured cost of dropping it: Serbian `клупа` returned "скамейка" unlabelled and
    # "тиски" under `техника`, and the note went out teaching the vise.
    parsed = parse_answer_payload(
        payload(meanings=[meaning(), meaning("о реке", translations=["берег"])]),
        "bank",
        languages["en"],
    )

    assert isinstance(parsed, ParsedUnit)
    assert [item.label for item in parsed.note.meanings] == ["", "о реке"]
    assert parsed.note.meaning.translations == ["банк"]


def test_a_context_copy_missing_its_final_stop_still_cards_our_context(languages):
    context = "We sat on the bank."
    contextual = example()
    contextual.update(highlighted="We sat on the <b>bank</b>")

    parsed = parse_answer_payload(
        payload(meanings=[meaning(examples=[contextual])], context_sense=0),
        "bank",
        languages["en"],
        unit_intent=True,
        context=context,
    )

    assert isinstance(parsed, ParsedUnit)
    assert parsed.note.meaning.examples[0] == Example(
        context,
        "Перевод.",
        "We sat on the <b>bank</b>.",
        "We sat on the ___.",
    )


def test_a_context_copy_carrying_an_extra_word_is_still_rejected(languages):
    contextual = example()
    contextual.update(highlighted="We sat on the <b>bank</b> today.")

    with pytest.raises(CardParseError, match="must equal the supplied context"):
        parse_answer_payload(
            payload(meanings=[meaning(examples=[contextual])], context_sense=0),
            "bank",
            languages["en"],
            unit_intent=True,
            context="We sat on the bank.",
        )


def test_a_word_changed_inside_the_context_is_still_rejected(languages):
    contextual = example()
    contextual.update(highlighted="We sat near the <b>bank</b>.")

    with pytest.raises(CardParseError, match="must equal the supplied context"):
        parse_answer_payload(
            payload(meanings=[meaning(examples=[contextual])], context_sense=0),
            "bank",
            languages["en"],
            unit_intent=True,
            context="We sat on the bank.",
        )


def test_a_target_language_sentence_is_not_a_card_front(languages):
    """The card front must be a sentence in the language being learned. A Russian
    sentence with the English word wedged into it teaches nothing, and the guard that
    only asked for letters counted its Cyrillic as sentence context."""
    russian = example()
    russian.update(highlighted="Мы должны <b>receive</b> письмо до конца недели.")

    with pytest.raises(CardParseError, match="no usable meaning"):
        parse_answer_payload(
            payload(word="receive", meanings=[meaning(examples=[russian])]),
            "recieve",
            languages["en"],
            unit_intent=True,
        )


def test_a_serbian_sentence_survives_the_russian_letters_it_does_not_share(languages):
    serbian = example()
    serbian.update(
        text="Деца се играју напољу цео дан.",
        highlighted="Деца <b>се играју</b> напољу цео дан.",
    )

    parsed = parse_answer_payload(
        payload(word="играти се", meanings=[meaning(examples=[serbian])]),
        "се играју",
        languages["sr"],
        unit_intent=True,
    )

    assert isinstance(parsed, ParsedUnit)
    assert parsed.note.meaning.examples[0].text == "Деца се играју напољу цео дан."


def test_a_russian_sentence_is_rejected_even_where_the_source_shares_its_script(languages):
    russian = example()
    russian.update(highlighted="Он <b>вратио</b> домой поздно вечером.")

    with pytest.raises(CardParseError, match="no usable meaning"):
        parse_answer_payload(
            payload(word="вратити се", meanings=[meaning(examples=[russian])]),
            "вратио",
            languages["sr"],
            unit_intent=True,
        )
