import logging
import re

from echo_words.prompt import (
    PAYLOAD_LOG_LIMIT,
    build_extended_prompt,
    build_prompt,
    build_text_prompt,
    extract_card,
    extract_segments,
)


def test_prompt_carries_the_language_word_target_context_and_hints(languages):
    prompt = build_prompt(
        languages["sr"],
        "глава",
        "Russian",
        context="прва глава књиге",
    )
    assert "Српски" in prompt
    assert "глава" in prompt
    assert "WRITE YOUR ENTIRE ANSWER IN Russian" in prompt
    assert "прва глава књиге" in prompt
    assert "for nouns give gender and plural" in prompt
    assert "===CARD===" in prompt
    assert "label is a\n1-3 word tag in Russian" in prompt
    assert "pos is that\nsense's part of speech as one short abbreviation in Russian" in prompt
    assert "text is a\nsentence in Српски, translation is its rendering in Russian" in prompt
    assert "(colloquial, formal, slang, vulgar\n   and so on)" in prompt
    assert "If there is no typo, suggestion is an\nempty string." in prompt
    assert "with no punctuation used for emphasis\nanywhere?" in prompt


def test_card_is_extracted_after_the_hidden_delimiter(languages):
    raw = """<b>recieve</b>\n===CARD===
{"word":"recieve","suggestion":"receive","meanings":[{"label":"","pos":"гл.",
"translations":["получать"],"examples":[
{"text":"I recieve it.","translation":"Я получаю это."}]}]}"""
    parsed = extract_card(raw, "recieve", languages["en"])
    assert parsed is not None
    note, suggestion = parsed
    assert note.word == "recieve"
    assert suggestion == "receive"


def test_missing_delimiter_has_no_card(languages):
    assert extract_card('{"word":"word"}', "word", languages["en"]) is None


def test_malformed_json_after_the_delimiter_has_no_card(languages):
    assert extract_card("analysis===CARD==={broken", "word", languages["en"]) is None


def test_a_rejected_card_block_is_logged_with_its_reason_and_its_payload(languages, caplog):
    raw = 'analysis===CARD==={"word":"word","meanings":[{"label":"","translations":[]}]}'
    with caplog.at_level(logging.WARNING, logger="echo_words.prompt"):
        assert extract_card(raw, "word", languages["en"]) is None
    logged = caplog.text
    assert "en/'word'" in logged
    assert "translations must be a non-empty list" in logged
    assert '"meanings"' in logged


def test_a_missing_card_block_is_logged_as_such(languages, caplog):
    with caplog.at_level(logging.WARNING, logger="echo_words.prompt"):
        assert extract_card("analysis with no payload", "word", languages["en"]) is None
    assert "never wrote the delimiter" in caplog.text


def test_a_logged_payload_is_clipped_and_says_how_long_it_was(languages, caplog):
    payload = '{"word":"word","junk":"' + "x" * (PAYLOAD_LOG_LIMIT * 2)
    with caplog.at_level(logging.WARNING, logger="echo_words.prompt"):
        assert extract_card(f"analysis===CARD==={payload}", "word", languages["en"]) is None
    assert f"({len(payload)} chars)" in caplog.text
    assert "x" * (PAYLOAD_LOG_LIMIT + 1) not in caplog.text


def test_a_rejected_segments_block_is_logged_with_its_payload(languages, caplog):
    with caplog.at_level(logging.WARNING, logger="echo_words.prompt"):
        assert extract_segments('prose===CARD==={"segments":{}}', languages["de"]) is None
    assert "unusable segments block for de" in caplog.text
    assert '"segments"' in caplog.text


def test_extended_prompt_carries_context_but_has_no_card_contract(languages):
    prompt = build_extended_prompt(
        languages["en"],
        "bucket",
        "Russian",
        context="kick the bucket",
    )
    assert "lexicographer" in prompt
    assert "kick the bucket" in prompt
    assert "EVERY sense" in prompt
    assert "No JSON and no delimiters" in prompt
    assert "===CARD===" not in prompt


def test_the_text_prompt_carries_the_language_text_target_and_hints(languages):
    prompt = build_text_prompt(languages["sr"], "Он се синоћ вратио кући.", "Russian")
    assert "Српски" in prompt
    assert "Он се синоћ вратио кући." in prompt
    assert "WRITE YOUR ENTIRE ANSWER IN Russian" in prompt
    assert "for nouns give gender and plural" in prompt
    assert "why — one short line in Russian" in prompt
    assert '{"segments": [{"label": "...", "surface": "...", "why": "..."}]}' in prompt
    assert not re.search(r"\{[a-z_]+\}", prompt)


def test_the_text_prompt_asks_for_no_card_and_no_transcription(languages):
    prompt = build_text_prompt(languages["de"], "Er steht jeden Morgen um sechs auf.", "Russian")
    assert "===CARD===" in prompt
    assert '"meanings"' not in prompt
    assert "Give no phonetic transcription." in prompt


def test_segments_are_extracted_after_the_hidden_delimiter(languages):
    raw = (
        "Он вернулся домой.\n===CARD===\n"
        '{"segments":[{"label":"вратити се","surface":"се … вратио","why":"Повратни глагол."}]}'
    )
    segments = extract_segments(raw, languages["sr"])
    assert segments is not None
    assert segments[0].label == "вратити се"


def test_a_text_with_no_delimiter_has_no_segments_but_an_empty_list_is_an_answer(languages):
    assert extract_segments("just prose", languages["de"]) is None
    assert extract_segments("prose===CARD==={broken", languages["de"]) is None
    assert extract_segments('prose===CARD==={"segments":[]}', languages["de"]) == []
