"""The standalone judgement: what it is asked, and what is read back from it."""

from echo_words.prompt import build_attestation_prompt, build_prompt, parse_attestation


def test_the_standalone_judgement_reads_a_bare_object():
    """The attestation call answers with JSON and nothing else: it has no article to
    separate itself from, which is the whole reason it is asked apart."""
    assert parse_attestation('{"used": false, "where": ""}').used is False
    assert parse_attestation('sure: {"used": true, "where": "everyday"}').used is True
    assert parse_attestation("nothing that parses") is None
    assert parse_attestation('{"used": "yes"}') is None
    assert parse_attestation("") is None


def test_an_unreadable_judgement_is_an_absent_one():
    """Nothing here may be read as a refusal: closing on an unreadable answer would
    withhold real words, which is the worse error."""
    for body in ('{"used": 1}', '{"used": null}', "{}", '{"where": "everyday"}', '["used"]'):
        assert parse_attestation(body) is None


def test_the_standalone_question_asks_for_nothing_but_the_judgement(languages):
    prompt = build_attestation_prompt(languages["de"], "Fahrradsuppe")

    assert "Fahrradsuppe" in prompt
    assert languages["de"].name in prompt
    assert "Do not write an article" in prompt
    # Rarity is not the question, and saying so is what keeps real rare words carded.
    assert "Rarity is no objection" in prompt


def test_no_article_prompt_asks_for_a_judgement_of_its_own(languages):
    """The judgement is one call with one job. Asking for it again at the head of an
    article makes every answer open with a JSON line, and the article's own verdict
    withheld one coinage in thirty-eight that this call did not."""
    for kwargs in ({"unit_intent": True}, {}):
        prompt = build_prompt(languages["de"], "Fahrradsuppe", "Russian", **kwargs)

        assert '"used"' not in prompt
        assert "===USED===" not in prompt
        assert "judge the submitted wording" not in prompt
