import json
import logging

import pytest

from echo_words.card import ParsedText, ParsedUnit
from echo_words.prompt import (
    MAX_COMPLETE_ANSWER_CHARS,
    MAX_DETAIL_CHARS,
    MAX_EQUIVALENTS,
    PAYLOAD_LOG_LIMIT,
    Equivalent,
    ReverseAnswer,
    Verdict,
    build_extended_prompt,
    build_prompt,
    build_reading_prompt,
    build_reverse_prompt,
    extract_answer,
    parse_attestation,
    parse_reading,
    parse_reverse,
    reverse_example_issue,
)


def unit_json():
    return json.dumps(
        {
            "kind": "unit",
            "word": "bank",
            "word_relation": "same",
            "suggestion": "",
            "meanings": [
                {
                    "label": "",
                    "translations": ["банк"],
                    "examples": [
                        {
                            "text": "The bank opens.",
                            "translation": "Банк открыт.",
                            "highlighted": "The <b>bank</b> opens.",
                            "gapped": "The ___ opens.",
                        },
                    ],
                },
            ],
            "segments": [],
        },
    )


def test_the_submit_box_prompt_carries_both_neutral_branches(languages):
    prompt = build_prompt(languages["sr"], "Он се вратио.", "Russian")

    assert '"kind": "unit"' in prompt
    assert '"kind": "text"' in prompt
    assert "Српски" in prompt
    assert "WRITE YOUR ENTIRE ANSWER IN Russian" in prompt
    assert "for nouns give gender and plural" in prompt
    assert "do not impose a numerical limit" in prompt
    assert "at most five" not in prompt


def test_a_selected_unit_is_asked_with_the_unit_contract_alone(languages):
    """The branch is settled by the tap, so nothing about text can apply to the
    answer. Carrying it anyway asks a fast model to hold a contract it cannot use."""
    prompt = build_prompt(
        languages["de"],
        "Rad fahren",
        "Russian",
        context="Er fährt jeden Tag Rad.",
        unit_intent=True,
    )

    assert '"kind": "unit"' in prompt
    assert '"kind": "text"' not in prompt
    assert "combinations" not in prompt
    assert "First decide whether the submission" not in prompt
    assert "context_sense" in prompt


def test_the_open_branch_decision_stays_where_the_branch_is_unknown(languages):
    open_prompt = build_prompt(languages["de"], "Rad fahren", "Russian")

    assert "First decide whether the submission" in open_prompt
    assert "context_sense" not in open_prompt


def test_the_selected_unit_prompt_is_the_shorter_one(languages):
    """Half of what the merged prompt spends on a chip tap cannot apply to it."""
    open_prompt = build_prompt(languages["de"], "Rad fahren", "Russian")
    unit_prompt = build_prompt(languages["de"], "Rad fahren", "Russian", unit_intent=True)

    assert len(unit_prompt) < len(open_prompt) * 0.7


def test_open_verdict_defaults_contextual_finite_clauses_to_text(languages):
    prompt = build_prompt(
        languages["en"],
        "A colleague finally made up her mind after lunch.",
        "Russian",
    )

    assert "Anything\nthat reports a particular situation is text" in prompt
    assert "even when a fixed expression fills\nmost of it" in prompt
    assert "return that expression separately in combinations" in prompt
    assert "If uncertain, choose text" in prompt
    assert "whose whole wording is the reusable lookup target" in prompt


def test_text_combinations_preserve_separate_exact_source_units(languages):
    prompt = build_prompt(
        languages["sr"],
        "Sve mi se čini da nešto nije u redu.",
        "Russian",
    )

    assert "put every clear multi-word lookup target in\ncombinations" in prompt
    assert "Keep distinct non-overlapping units\nseparate" in prompt
    assert "label and surface are the same unit twice" in prompt
    assert "copied token for token out of the submitted\ntext" in prompt
    assert "in the same spelling, script and capitalization" in prompt
    assert "So label may read `aufstehen`\nwhile surface reads `steht ... auf`" in prompt
    assert "Include every fixed piece —\nreflexive particle" in prompt
    assert "in\nthe form it takes in this sentence" in prompt
    assert "leave out negation and the current\nsubject, object or complement" in prompt
    assert "the backend\ngives every source word its own chip anyway" in prompt
    assert "never\ntranslate, transliterate, correct or lemmatise it" in prompt


def test_unit_article_still_requires_forms_usage_origin_and_examples(languages):
    prompt = build_prompt(languages["de"], "Bank", "Russian", unit_intent=True)
    for section in ("Forms only when useful", "Usage:", "Origin only where", "examples"):
        assert section in prompt


def test_origin_is_asked_for_only_where_it_is_known(languages):
    """Required of every word, it is supplied for every word — including the ones that
    have none, where what arrives is a confident story assembled from the parts."""
    prompt = build_prompt(languages["de"], "Lupe", "Russian", unit_intent=True)

    assert "Origin only where you know it" in prompt
    assert "Origin: always include it" not in prompt
    assert "leave it out" in prompt


def test_unit_examples_target_only_the_lexical_surface(languages):
    prompt = build_prompt(
        languages["de"],
        "steht auf",
        "Russian",
        context="Er steht jeden Morgen um sechs auf.",
        unit_intent=True,
    )

    assert "<b> tags around all and\nonly the unit" in prompt
    assert "Never mark a subject, object,\nauxiliary or argument" in prompt
    assert "at least one unmarked source-language word" in prompt
    # The context sentence is not among the examples any more, so nothing is said about
    # marking it: the backend marks its own sentence and asks the answer for the two
    # things only it can give.
    assert '"context_sense"' in prompt
    assert '"context_translation"' in prompt
    assert "Do not copy the context sentence into the examples" in prompt


def test_the_deeper_article_is_asked_to_stay_readable(languages):
    """Asked for "every sense, in depth" and given no bound, it came back as a
    dissertation on a phone screen. The reader opened it for one word."""
    prompt = build_extended_prompt(languages["de"], "Tafel", "Russian")

    assert "not a monograph" in prompt
    assert str(MAX_DETAIL_CHARS) in prompt
    assert "One example per sense" in prompt
    assert "Cover every sense" not in prompt
    assert "origin and its\nroute in depth" not in prompt


def test_the_prompt_asks_for_the_spelling_relation_in_one_rule(languages):
    prompt = build_prompt(languages["en"], "recieve", "Russian", unit_intent=True)

    assert '"word_relation": "<same, morphology or typo>"' in prompt
    assert "word_relation is typo when the submission is misspelled" in prompt
    assert "suggestion is empty otherwise: it is only ever a correction" in prompt
    # The near-spelling search cost a paragraph in the most expensive position in the
    # prompt and reached the reader once in 201 answers.
    assert "also_common" not in prompt
    assert "markedly commoner" not in prompt
    # The heading and the card carry the same wording; the correction is named in
    # suggestion, and the interface tells the reader what became of their spelling.
    assert "head a suspected misspelling with the correction" in prompt


def test_contiguous_unit_uses_one_bold_span(languages):
    prompt = build_prompt(languages["en"], "give up", "Russian", unit_intent=True)

    assert "Mark a contiguous unit with one span" in prompt
    assert "separated or reflexive pieces with\none span each" in prompt


def test_answer_extraction_returns_the_discriminated_branch(languages):
    unit = extract_answer(f"article===CARD==={unit_json()}", "bank", languages["en"])
    text = extract_answer(
        'translation===CARD==={"kind":"text","combinations":[]}',
        "The bank opens.",
        languages["en"],
    )

    assert isinstance(unit, ParsedUnit)
    assert isinstance(text, ParsedText)


def test_rejected_payload_is_logged_bounded(languages, caplog):
    payload = '{"kind":"unit","junk":"' + "x" * (PAYLOAD_LOG_LIMIT * 2)
    with caplog.at_level(logging.WARNING, logger="echo_words.prompt"):
        assert extract_answer(f"article===CARD==={payload}", "word", languages["en"]) is None
    assert f"({len(payload)} chars)" in caplog.text


def test_a_rejected_payload_is_logged_beside_the_context_it_was_asked_about(
    languages,
    caplog,
):
    """Most rejections are the answer and the context disagreeing, and a copy that
    missed the sentence by one word is indistinguishable from an invented one unless
    the sentence is there to compare it against."""
    payload = '{"kind":"unit","word":"Treppe","meanings":[]}'
    with caplog.at_level(logging.WARNING, logger="echo_words.prompt"):
        assert (
            extract_answer(
                f"article===CARD==={payload}",
                "Treppe",
                languages["de"],
                context="Wir nehmen die Treppe.",
            )
            is None
        )
    assert "in context 'Wir nehmen die Treppe.'" in caplog.text


def test_oversized_complete_answer_is_rejected_before_payload_parsing(
    languages,
    monkeypatch,
):
    def should_not_parse(*_args, **_kwargs):
        raise AssertionError("oversized answers must stop before JSON decoding")

    monkeypatch.setattr("echo_words.prompt.parse_answer_payload", should_not_parse)
    raw = "x" * (MAX_COMPLETE_ANSWER_CHARS + 1)

    assert extract_answer(raw, "bank", languages["en"]) is None


def test_extended_prompt_has_no_compact_contract(languages):
    prompt = build_extended_prompt(languages["en"], "bank", "Russian", context="the bank")
    assert "lexicographer" in prompt
    assert "the bank" in prompt
    assert "===CARD===" not in prompt


def _reverse(*equivalents: dict, verdict: str = "word", read_as: str = "стул") -> str:
    return json.dumps(
        {"verdict": verdict, "read_as": read_as, "equivalents": list(equivalents)},
        ensure_ascii=False,
    )


def _equivalent(word: str, example: str, form: str) -> dict:
    return {"word": word, "example": example, "form": form}


def test_the_reverse_prompt_names_both_languages_and_asks_for_the_form(languages):
    prompt = build_reverse_prompt(languages["de"], "стул", "Russian")

    assert '"стул"' in prompt
    assert "from Russian into Deutsch" in prompt
    assert '"form"' in prompt
    assert "commonest" in prompt
    assert '"not_a_word"' in prompt
    assert '"sentence"' in prompt


def test_a_string_value_missing_its_opening_quote_is_still_read(languages):
    raw = (
        '{"verdict": "word", "read_as": "мир", "equivalents": [{"word": "mir", '
        '"example": Potpisali su mirovni sporazum i nastupio je mir.", "form": "mir"}]}'
    )

    answer = parse_reverse(raw, languages["sr"], "Russian")

    assert answer == ReverseAnswer(
        "word",
        "мир",
        (Equivalent("mir", "Potpisali su mirovni sporazum i nastupio je mir."),),
    )


def test_a_bare_literal_is_not_taken_for_a_missing_quote():
    # Repairing the note must leave the literal before it alone.
    assert parse_attestation('{"used": true, "note": rare but attested"}') == Verdict(True)


def test_the_reading_question_names_both_languages_and_a_second_alphabet(languages):
    serbian = build_reading_prompt(languages["sr"], "собака", "Russian")
    german = build_reading_prompt(languages["de"], "собака", "Russian")

    assert '"собака"' in serbian
    assert "into the box for Српски" in serbian
    assert "in either of its alphabets" in serbian
    assert "alphabets" not in german


@pytest.mark.parametrize(
    ("raw", "reading"),
    [
        ('{"why": "plain Russian", "reading": "target"}', "target"),
        ('{"why": "Serbian dog", "reading": "source"}', "source"),
        ('Sure: {"reading": "typo"}', "typo"),
        ('{"reading": "russian"}', None),
        ('{"why": "no verdict"}', None),
        ("not json", None),
    ],
)
def test_only_a_known_reading_is_read(raw, reading):
    assert parse_reading(raw) == reading


def test_a_reverse_answer_carries_its_equivalents_and_the_reading(languages):
    raw = _reverse(
        _equivalent("Stuhl", "Die Stühle stehen im Garten.", "Stühle"),
        _equivalent("Hocker", "Er sitzt auf einem Hocker.", "Hocker"),
        read_as="стул",
    )

    answer = parse_reverse("```json\n" + raw + "\n```", languages["de"], "Russian")

    # The inflected example is kept: the card marks the word by the form it is spelled in.
    assert answer == ReverseAnswer(
        "word",
        "стул",
        (
            Equivalent("Stuhl", "Die Stühle stehen im Garten."),
            Equivalent("Hocker", "Er sitzt auf einem Hocker."),
        ),
    )


@pytest.mark.parametrize("verdict", ["not_a_word", "sentence"])
def test_a_reverse_refusal_carries_no_equivalents(languages, verdict):
    raw = _reverse(_equivalent("Stuhl", "Der Stuhl ist neu.", "Stuhl"), verdict=verdict)

    assert parse_reverse(raw, languages["de"], "Russian") == ReverseAnswer(verdict, "", ())


@pytest.mark.parametrize(
    ("example", "form", "issue"),
    [
        ("Er kauft einen Tisch.", "Stuhl", "form"),
        ("Der Stuhl ist " + "sehr " * 100 + "alt.", "Stuhl", "too_long"),
        ("Он купил новый Stuhl.", "Stuhl", "script"),
        ("", "Stuhl", "missing"),
    ],
)
def test_an_example_the_card_could_not_use_leaves_a_bare_chip(languages, example, form, issue):
    raw = _reverse(
        _equivalent("Stuhl", example, form),
        _equivalent("Hocker", "Er sitzt auf einem Hocker.", "Hocker"),
    )

    answer = parse_reverse(raw, languages["de"], "Russian")

    assert reverse_example_issue(example, form, "Stuhl", languages["de"], "Russian") == issue
    assert answer is not None
    assert answer.equivalents[0] == Equivalent("Stuhl", "")
    assert answer.equivalents[1].example == "Er sitzt auf einem Hocker."


def test_the_reverse_prompt_asks_a_two_script_language_for_latin_only(languages):
    serbian = build_reverse_prompt(languages["sr"], "стол", "Russian")
    german = build_reverse_prompt(languages["de"], "стол", "Russian")

    assert "latinica, and never in Cyrillic" in serbian
    assert "Cyrillic" not in german


def test_a_serbian_answer_written_in_cyrillic_is_read_as_written(languages):
    serbian = languages["sr"]
    raw = _reverse(_equivalent("књига", "Читам ову књигу.", "књигу"), read_as="книга")

    assert parse_reverse(raw, serbian, "Russian") == ReverseAnswer(
        "word", "книга", (Equivalent("књига", "Читам ову књигу."),)
    )


def test_a_target_language_sentence_is_no_example_where_the_scripts_are_shared(languages):
    """Serbian writes Cyrillic, so only the letters Russian alone writes give it away."""
    serbian = languages["sr"]
    raw = _reverse(_equivalent("књига", "Я читаю эту книгу.", "книгу"), read_as="книга")

    answer = parse_reverse(raw, serbian, "Russian")

    assert reverse_example_issue("Я читаю эту книгу.", "книгу", "књига", serbian) == "letters"
    assert answer == ReverseAnswer("word", "книга", (Equivalent("књига", ""),))


def test_a_number_is_never_found_inside_a_longer_word(languages):
    serbian = languages["sr"]

    assert reverse_example_issue("Ovo mesto je slobodno.", "sto", "sto", serbian) == "form"
    assert reverse_example_issue("Sto ljudi je došlo.", "sto", "sto", serbian) is None


def test_a_missing_or_wrong_form_falls_back_to_the_word_itself(languages):
    german = languages["de"]

    assert reverse_example_issue("Der Stuhl ist neu.", "", "Stuhl", german) is None
    assert reverse_example_issue("Der Stuhl ist neu.", "Stühle", "Stuhl", german) is None


def test_a_separated_expression_is_found_piece_by_piece(languages):
    german = languages["de"]

    assert (
        reverse_example_issue("Ich stehe um sieben auf.", "stehe … auf", "aufstehen", german)
        is None
    )


def test_an_equivalent_the_source_language_refuses_is_dropped(languages):
    raw = _reverse(
        _equivalent("стул", "Der Stuhl ist neu.", "Stuhl"),
        _equivalent("Stuhl", "Der Stuhl ist neu.", "Stuhl"),
        _equivalent("Stuhl.", "Der Stuhl ist alt.", "Stuhl"),
    )

    answer = parse_reverse(raw, languages["de"], "Russian")

    # The Cyrillic word is no German word, and the trailing stop is punctuation off
    # the edge of a repeat.
    assert answer == ReverseAnswer("word", "стул", (Equivalent("Stuhl", "Der Stuhl ist neu."),))


def test_the_equivalents_are_capped(languages):
    words = ["Stuhl", "Hocker", "Sessel", "Sitz", "Bank", "Thron", "Schemel"]
    raw = _reverse(*(_equivalent(word, f"Das ist ein {word}.", word) for word in words))

    answer = parse_reverse(raw, languages["de"], "Russian")

    assert answer is not None
    assert [item.word for item in answer.equivalents] == words[:MAX_EQUIVALENTS]


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "not json",
        '{"verdict": "word", "read_as": "стул", "equivalents": [',
        '["word"]',
        '{"verdict": "maybe", "read_as": "", "equivalents": []}',
        '{"verdict": "word", "read_as": "стул", "equivalents": []}',
        '{"verdict": "word", "read_as": "стул"}',
        '{"verdict": "word", "read_as": "стул", "equivalents": [{"word": "стул"}]}',
        '{"verdict": "word", "read_as": "стул", "equivalents": ["Stuhl"]}',
    ],
)
def test_an_unusable_reverse_answer_is_none(languages, raw):
    assert parse_reverse(raw, languages["de"], "Russian") is None


def test_a_sentence_written_around_another_word_is_no_example_of_it(languages):
    german = languages["de"]
    raw = _reverse(
        _equivalent("Fenster", "Ich öffne das Fenster.", "Fenster"),
        _equivalent("Schiebefenster", "Das Schalterfenster ist zu.", "Schalterfenster"),
    )

    answer = parse_reverse(raw, german, "Russian")

    assert reverse_example_issue(
        "Das Schalterfenster ist zu.", "Schalterfenster", "Schiebefenster", german
    ) == ("unrelated")
    assert answer is not None
    assert answer.equivalents[1] == Equivalent("Schiebefenster", "")


@pytest.mark.parametrize(
    ("code", "example", "form", "word"),
    [
        ("de", "Ich freue mich sehr.", "freue mich", "sich freuen"),
        ("en", "He gave up smoking.", "gave up", "give up"),
        ("sr", "Nadam se da će doći.", "Nadam se", "nadati se"),
        ("sr", "Za stolom je sedeo prijatelj.", "stolom", "sto"),
        ("sr", "Za stolom je sedeo prijatelj.", "stolom", "сто"),
    ],
)
def test_a_form_sharing_a_stem_with_its_word_marks_the_sentence(
    languages, code, example, form, word
):
    assert reverse_example_issue(example, form, word, languages[code]) is None


def test_a_suppletive_form_costs_the_sentence_unless_the_word_itself_is_in_it(languages):
    english = languages["en"]

    assert reverse_example_issue("She went home early.", "went", "go", english) == "unrelated"
    assert reverse_example_issue("Let us go, she went on.", "went", "go", english) is None


@pytest.mark.parametrize(
    ("code", "word", "example", "form", "carded"),
    [
        # A German noun lowered, an English word and a Serbian one in dictionary capitals.
        ("de", "tisch", "Das Buch liegt auf dem Tisch.", "Tisch", "Tisch"),
        ("de", "stuhl", "Die Stühle stehen im Garten.", "Stühle", "Stuhl"),
        ("en", "World", "She travelled around the world.", "world", "world"),
        ("sr", "SVET", "Ceo svet to zna.", "svet", "svet"),
        ("sr", "STO", "Sedeli smo za stolom.", "stolom", "sto"),
        # Opening the sentence hides the case, short of the form as the answer copied it.
        ("en", "Peace", "Peace is essential for happiness.", "peace", "peace"),
        ("sr", "Luk", "Luk sam kupio na pijaci.", "Luk", "Luk"),
        ("sr", "LUK", "Luk sam kupio na pijaci.", "Luk", "luk"),
        ("de", "vielleicht", "Vielleicht klappt es doch.", "Vielleicht", "vielleicht"),
        # Several words are left as written: their pieces need not stand together.
        (
            "de",
            "Hals über Kopf",
            "Er rannte Hals über Kopf davon.",
            "Hals über Kopf",
            "Hals über Kopf",
        ),
    ],
)
def test_a_headword_takes_the_case_its_own_sentence_writes_it_in(
    languages, code, word, example, form, carded
):
    raw = _reverse(_equivalent(word, example, form))

    answer = parse_reverse(raw, languages[code], "Russian")

    assert answer is not None
    assert answer.equivalents[0] == Equivalent(carded, example)


def test_a_bare_chip_in_capitals_is_lowered(languages):
    raw = _reverse(
        _equivalent("Hund", "Der Hund bellt.", "Hund"),
        _equivalent("KÖTER", "", ""),
    )

    answer = parse_reverse(raw, languages["de"], "Russian")

    assert answer is not None
    assert answer.equivalents[1] == Equivalent("köter", "")
