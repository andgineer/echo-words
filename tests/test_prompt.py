import json
import logging

from echo_words.card import ParsedText, ParsedUnit
from echo_words.prompt import (
    MAX_COMPLETE_ANSWER_CHARS,
    PAYLOAD_LOG_LIMIT,
    build_extended_prompt,
    build_prompt,
    extract_answer,
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
    assert "mark those selected tokens and no others" in prompt
    assert "do not expand the selection to neighbouring context" in prompt


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
