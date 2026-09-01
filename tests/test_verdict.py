"""The leading verdict: what is read from it, and what is kept from the reader."""

import pytest

from echo_words.prompt import (
    VERDICT_PREFIX,
    build_attestation_prompt,
    parse_attestation,
    parse_verdict,
    strip_verdict,
)

ARTICLE = "<b>envy</b>\nзависть"


def line(body: str) -> str:
    return f"{VERDICT_PREFIX} {body}\n"


def test_a_well_formed_verdict_is_read():
    assert parse_verdict(line('{"used": true, "where": "everyday"}')).used is True
    assert parse_verdict(line('{"used": false, "where": ""}')).used is False


@pytest.mark.parametrize(
    "body",
    [
        '{"used": "yes"}',
        '{"used": 1}',
        '{"used": null}',
        "{}",
        '{"where": "everyday"}',
        '{"used": true',
        "not json at all}",
        '["used"]',
    ],
)
def test_a_verdict_that_does_not_say_used_is_no_verdict(body):
    """Nothing here may be read as a refusal: an unreadable judgement is an absent
    one, and closing on it would refuse real words."""
    assert parse_verdict(line(body)) is None


def test_an_answer_without_a_verdict_has_none():
    assert parse_verdict(ARTICLE) is None
    assert parse_verdict("") is None


def test_the_verdict_never_reaches_the_reader():
    raw = line('{"used": true, "where": "literary"}') + ARTICLE
    assert strip_verdict(raw) == ARTICLE
    assert VERDICT_PREFIX not in strip_verdict(raw)


@pytest.mark.parametrize("length", range(1, len(VERDICT_PREFIX) + 1))
def test_a_verdict_still_arriving_is_held_back(length):
    """The prefix streams in character by character, and a half-written marker must
    not flash on the page before the judgement it belongs to is readable."""
    assert strip_verdict(VERDICT_PREFIX[:length]) == ""


def test_a_complete_prefix_awaiting_its_json_is_held_back():
    assert strip_verdict(VERDICT_PREFIX + ' {"used": tr') == ""


def test_a_courtesy_word_before_the_marker_does_not_switch_the_judgement_off():
    """The gate is the parsed field, never the model obeying "write nothing else": one
    stray token ahead of the marker must not read as an answer that never judged."""
    raw = f"Sure!\n{line('{"used": false, "where": ""}')}prose"

    assert parse_verdict(raw).used is False
    assert VERDICT_PREFIX not in strip_verdict(raw)


def test_a_brace_inside_the_judgement_does_not_split_the_answer():
    """Reading and hiding the verdict are one scan, so a register named with a brace
    cannot leave the parser calling it absent while the reader sees its tail."""
    raw = line('{"used": false, "where": "slang {of a kind}"}') + ARTICLE

    assert parse_verdict(raw).used is False
    assert strip_verdict(raw) == ARTICLE


def test_a_judgement_written_over_several_lines_never_shows_as_prose():
    """Cutting an unreadable marker at its first line would print the rest of its JSON
    to the reader, one field at a time, and then take it away again."""
    wrapped = f'{VERDICT_PREFIX} {{\n  "used": false,\n  "where": ""\n}}\n{ARTICLE}'

    for length in range(len(VERDICT_PREFIX), len(wrapped) - len(ARTICLE)):
        assert strip_verdict(wrapped[:length]) == ""
    assert parse_verdict(wrapped).used is False
    assert strip_verdict(wrapped) == ARTICLE


def test_a_judgement_that_never_closes_gives_the_article_back():
    """An unreadable judgement is an absent one, and the article under it is still the
    reader's: a marker nobody can parse must not hold the answer back for good. The
    budget it gets first is generous, because expiring early is its own defect."""
    raw = f'{VERDICT_PREFIX} {{"used": true\n{"prose " * 120}'

    assert parse_verdict(raw) is None
    assert strip_verdict(raw).startswith("prose ")


def test_a_marker_at_the_far_edge_of_the_lead_is_still_read():
    """The window covers a marker that starts inside the lead. Half-finding one there
    would switch the judgement off and print the marker as prose."""
    raw = f'{"x" * 195}{VERDICT_PREFIX} {{"used": false, "where": ""}}\n{ARTICLE}'

    assert parse_verdict(raw).used is False
    assert VERDICT_PREFIX not in strip_verdict(raw)


def test_a_marker_far_into_the_article_is_left_alone():
    """Only a leading judgement is one; the same run of characters inside the prose is
    prose, and cutting the article open at it would lose what came before."""
    raw = ARTICLE + " " * 300 + line('{"used": false}')

    assert parse_verdict(raw) is None
    assert strip_verdict(raw) == raw


def test_an_answer_that_merely_starts_with_a_delimiter_is_not_swallowed():
    """Only this marker is withheld. A run of equals signs that diverges from it is
    prose the reader is owed — while a run still matching it is held back above,
    because on a stream it may yet become the marker."""
    assert strip_verdict("=== not a verdict") == "=== not a verdict"
    assert strip_verdict("===USEDX") == "===USEDX"


def test_the_standalone_judgement_reads_a_bare_object():
    """The attestation call answers with JSON and no marker: it has no article to
    separate itself from, which is the whole reason it is asked apart."""
    assert parse_attestation('{"used": false, "where": ""}').used is False
    assert parse_attestation('sure: {"used": true, "where": "everyday"}').used is True
    assert parse_attestation("nothing that parses") is None
    assert parse_attestation('{"used": "yes"}') is None
    assert parse_attestation("") is None


def test_the_standalone_question_asks_for_nothing_but_the_judgement(languages):
    prompt = build_attestation_prompt(languages["de"], "Fahrradsuppe")

    assert "Fahrradsuppe" in prompt
    assert languages["de"].name in prompt
    assert "Do not write an article" in prompt
    # Rarity is not the question, and saying so is what keeps real rare words carded.
    assert "Rarity is no objection" in prompt


def test_a_wordy_judgement_wrapped_over_lines_never_shows_its_json():
    """The bound on an unclosed judgement has to outlast a real one. Expiring mid-object
    prints the rest of its JSON to the reader as prose, one field at a time."""
    opening = f'{VERDICT_PREFIX} {{\n  "where": "{"a" * 220}"'

    assert strip_verdict(opening) == ""

    whole = f'{opening}",\n  "used": false\n}}\n{ARTICLE}'
    assert parse_verdict(whole) is None or parse_verdict(whole).used is False


def test_a_partial_marker_is_held_wherever_a_whole_one_would_be_read():
    """The two scans share one window. Gating the partial one tighter left a band where
    half a marker was shown as prose and then taken away again."""
    for preamble in (0, 100, 195, 199):
        raw = f"{'x' * preamble}{VERDICT_PREFIX[:6]}"
        assert VERDICT_PREFIX[:6] not in strip_verdict(raw), preamble
