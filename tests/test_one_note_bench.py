import json
from dataclasses import replace

import one_note_bench as bench

from echo_words.prompt import VERDICT_PREFIX


def _shot(shot_id: str, *, expected_kind: str = "text") -> bench.Shot:
    return bench.Shot(
        shot_id=shot_id,
        kind="verdict",
        lang="en",
        source="I have no idea",
        expected_kind=expected_kind,
    )


def _outcome(shot: bench.Shot, actual_kind: str | None) -> str:
    if actual_kind is None:
        shot.text = ""
    elif actual_kind == "text":
        shot.text = 'translation===CARD==={"kind":"text","combinations":[]}'
    else:
        payload = {
            "kind": "unit",
            "word": "have no idea",
            "word_relation": "morphology",
            "suggestion": "",
            "meanings": [
                {
                    "label": "",
                    "translations": ["не иметь понятия"],
                    "examples": [
                        {
                            "text": "I have no idea.",
                            "translation": "Я понятия не имею.",
                            "highlighted": "I <b>have</b> <b>no</b> <b>idea</b>.",
                            "gapped": "I ___ ___ ___.",
                        },
                    ],
                },
            ],
            "segments": [],
        }
        shot.text = "<b>have no idea</b>\nне иметь понятия\n===CARD===\n" + json.dumps(
            payload,
            ensure_ascii=False,
        )
    return str(bench.score(shot).metrics["verdict_outcome"])


def _text_answer() -> str:
    return 'translation===CARD==={"kind":"text","combinations":[]}'


def _unit_answer(source: str) -> str:
    payload = {
        "kind": "unit",
        "word": source,
        "word_relation": "morphology",
        "suggestion": "",
        "meanings": [
            {
                "label": "",
                "translations": ["перевод"],
                "examples": [
                    {
                        "text": f"Example with {source}.",
                        "translation": "Пример.",
                        "highlighted": f"Example with <b>{source}</b>.",
                        "gapped": "Example with ___.",
                    },
                ],
            },
        ],
        "segments": [],
    }
    return "analysis===CARD===" + json.dumps(payload, ensure_ascii=False)


def test_tolerant_verdict_outcomes_do_not_turn_gray_boundaries_into_hard_errors():
    assert _outcome(_shot("verdict:clauses:en:1"), "text") == "correct"
    assert _outcome(_shot("verdict:fragments:en:1"), "unit") == "acceptable"
    assert _outcome(_shot("verdict:clauses:de:2"), "unit") == "ambiguous"
    # Registered by the shape of the utterance, not by what an answer extracted.
    assert _outcome(_shot("verdict:clauses:de:0"), "unit") == "ambiguous"
    # A clause carrying its own subject and time is not that shape.
    assert _outcome(_shot("verdict:clauses:de:4"), "unit") == "hard_error"
    assert _outcome(_shot("verdict:fragments:en:2"), "unit") == "hard_error"
    assert _outcome(_shot("verdict:sentences-split:de:0"), "unit") == "hard_error"
    assert _outcome(_shot("verdict:units:de:0", expected_kind="unit"), "text") == "hard_error"
    assert _outcome(_shot("verdict:clauses:en:1"), None) == "unusable"


def test_pada_kisa_is_scored_as_the_expected_unit():
    payload = {
        "kind": "unit",
        "word": "Пада киша",
        "word_relation": "same",
        "suggestion": "",
        "meanings": [
            {
                "label": "",
                "translations": ["идёт дождь"],
                "examples": [
                    {
                        "text": "Пада киша данас.",
                        "translation": "Сегодня идёт дождь.",
                        "highlighted": "<b>Пада</b> <b>киша</b> данас.",
                        "gapped": "___ ___ данас.",
                    },
                ],
            },
        ],
        "segments": [],
    }
    shot = bench.Shot(
        shot_id="verdict:clauses:sr:0",
        kind="verdict",
        lang="sr",
        source="Пада киша",
        expected_kind="text",
        text="<b>Пада киша</b>\nидёт дождь\n===CARD===\n" + json.dumps(payload, ensure_ascii=False),
    )

    scored = bench.score(shot)

    assert scored.expected_kind == "unit"
    assert scored.metrics["actual_kind"] == "unit"
    assert scored.metrics["verdict_outcome"] == "correct"


def test_append_only_answers_retain_the_first_terminal_prompt_attempt(tmp_path):
    out = tmp_path / "bench"
    canonical = next(
        shot for shot in bench.verdict_shots() if shot.shot_id == "verdict:clauses:en:0"
    )
    old = replace(canonical)
    old.prompt_hash = "archived"
    old.text = _text_answer()
    old.answered_by = "old-provider"
    bench.append(out, old)

    current = replace(canonical)
    current.prompt_hash = bench.prompt_fingerprint(current)
    current.text = _text_answer()
    current.answered_by = "first-current-provider"
    bench.append(out, current)

    retry = replace(canonical)
    retry.prompt_hash = current.prompt_hash
    retry.text = current.text
    retry.answered_by = "latest-current-provider"
    bench.append(out, retry)

    attempts = bench.read_attempts(out)
    arms = bench.read_arms(out, attempts)
    production = bench.read(out, attempts)

    assert len(attempts) == 3
    assert [len(arm) for arm in arms] == [1, 1]
    assert arms[0][old.shot_id].answered_by == "old-provider"
    assert arms[1][current.shot_id].answered_by == "first-current-provider"
    assert production[current.shot_id].answered_by == "first-current-provider"


def test_current_selection_rejects_stale_fixture_metadata_and_prompt_hash(tmp_path):
    out = tmp_path / "bench"
    canonical = next(
        shot for shot in bench.verdict_shots() if shot.shot_id == "verdict:clauses:en:0"
    )

    stale_source = replace(canonical, source=canonical.source + " now")
    stale_source.prompt_hash = bench.prompt_fingerprint(stale_source)
    stale_source.text = _text_answer()
    stale_source.answered_by = "provider"
    bench.append(out, stale_source)

    stale_expected = replace(canonical, expected_kind="unit")
    stale_expected.prompt_hash = bench.prompt_fingerprint(canonical)
    stale_expected.text = _text_answer()
    stale_expected.answered_by = "provider"
    bench.append(out, stale_expected)

    stale_hash = replace(canonical, prompt_hash="stale-hash")
    stale_hash.text = _text_answer()
    stale_hash.answered_by = "provider"
    bench.append(out, stale_hash)

    assert canonical.shot_id not in bench.read(out)


def _passing_quality_counts() -> dict[str, int]:
    return {
        "usable_initial": bench.MIN_USABLE_INITIAL,
        "usable_verdicts": 100,
        "hard_verdict_errors": 10,
        "text_branch": bench.MIN_TEXT_BRANCH,
        "bare_cardable": bench.MIN_BARE_CARDABLE,
        "registered_units": bench.REGISTERED_UNITS,
        "cardable_units": bench.MIN_CARDABLE_UNITS,
        "click_success": bench.MIN_CLICK_SUCCESS,
        "expression_success": bench.MIN_EXPRESSION_SUCCESS,
        "typo_success": 3,
        "typo_carded_misspelling": 0,
        "neighbour_success": 4,
        "neighbour_false_offers": 0,
        "attested_kept": 3,
        "unused_refused": 3,
    }


def test_the_cardable_unit_floor_sits_at_the_bottom_of_its_measured_spread():
    """Measured 13 to 17 of 21 across six full runs that answered every text shot.
    A floor inside that spread reddens on the draw; at its bottom the gate still holds
    the count to something a collapse would break."""
    assert bench.CARDABLE_UNITS_SPREAD[0] == bench.MIN_CARDABLE_UNITS
    counts = _passing_quality_counts()
    counts["cardable_units"] = bench.MIN_CARDABLE_UNITS
    assert bench.quality_gates(counts, "full")["registered units cardable"] is True
    counts["cardable_units"] = bench.MIN_CARDABLE_UNITS - 1
    assert bench.quality_gates(counts, "full")["registered units cardable"] is False


def test_a_chip_the_learner_would_card_wrong_is_not_a_unit_recovered():
    """An expanded or partial boundary carries a surface the reader would card as the
    entry, so the gate counts only exact chips and registered alternatives."""
    counts = _passing_quality_counts()
    counts["registered_units"] = bench.REGISTERED_UNITS
    counts["cardable_units"] = bench.MIN_CARDABLE_UNITS - 1
    assert bench.quality_gates(counts, "full")["registered units cardable"] is False


def test_quality_thresholds_pass_at_the_boundaries():
    assert all(bench.quality_gates(_passing_quality_counts(), "full").values())


def test_quality_thresholds_fail_immediately_below_each_minimum():
    keys = (
        "usable_initial",
        "text_branch",
        "bare_cardable",
        "cardable_units",
        "click_success",
        "expression_success",
        "attested_kept",
        "unused_refused",
    )
    for key in keys:
        counts = _passing_quality_counts()
        counts[key] -= 1
        assert not all(bench.quality_gates(counts, "full").values())

    counts = _passing_quality_counts()
    counts["hard_verdict_errors"] = 11
    assert not bench.quality_gates(counts, "full")["obvious hard verdict errors"]


def test_a_word_list_carded_as_a_unit_is_the_failure_and_a_refusal_is_not():
    """There is no unit to extract from two unrelated words, so the text branch and a
    refusal are both right — production reads a refused multi-word submission as text.
    Only a dictionary entry made out of the pair loses the reader anything."""
    carded = next(row for row in bench.wordlist_shots() if row.shot_id == "wordlist-de-ampel-links")
    carded.text = (
        "translation===CARD==="
        '{"kind":"unit","word":"Ampel links","word_relation":"same","suggestion":"",'
        '"meanings":[{"label":"","translations":["светофор слева"],"examples":['
        '{"text":"Die Ampel links.","translation":"x","highlighted":"Die <b>Ampel links</b>.",'
        '"gapped":"Die ___."}]}],"segments":[]}'
    )
    scored = bench.score(carded)
    assert scored.metrics["wordlist_carded"] is True
    assert scored.metrics["wordlist_chips"] == 0

    refused = next(
        row for row in bench.wordlist_shots() if row.shot_id == "wordlist-de-ampel-links"
    )
    refused.text = f'{VERDICT_PREFIX} {{"used": false, "where": ""}}\n'
    scored = bench.score(refused)
    assert scored.metrics["wordlist_carded"] is False
    # The reader still gets a chip for each submitted word.
    assert scored.metrics["wordlist_chips"] == 2


def test_only_a_card_under_the_mistyped_spelling_fails_the_typo_arm():
    """The reader is harmed by exactly one outcome: a card headed by the spelling they
    mistyped. An entry that silently heads itself with the correction hands over the
    right card, and a withheld one hands over none — both are safe."""
    counts = _passing_quality_counts()
    counts["typo_success"] = 0
    assert bench.quality_gates(counts, "full")["a misspelling is never carded"] is True
    counts["typo_carded_misspelling"] = 1
    assert bench.quality_gates(counts, "full")["a misspelling is never carded"] is False


def test_an_entry_headed_by_the_mistyped_spelling_is_flagged():
    shot = next(row for row in bench.typo_shots() if row.shot_id == "typo-de-vieleicht")
    shot.text = (
        "translation===CARD==="
        '{"kind":"unit","word":"vieleicht","word_relation":"same","suggestion":"",'
        '"meanings":[{"label":"","translations":["может быть"],"examples":['
        '{"text":"Vieleicht kommt er.","translation":"x",'
        '"highlighted":"<b>Vieleicht</b> kommt er.","gapped":"___ kommt er."}]}],'
        '"segments":[]}'
    )

    scored = bench.score(shot)

    assert scored.metrics["typo_heads_submission"] is True
    assert scored.metrics["typo_word_exact"] is False


def test_a_silently_corrected_spelling_is_a_safe_outcome():
    """`podrska` came back headed `podrška` with relation `same`: the reader gets the
    right card and is simply not told they mistyped. Safe, and not a gate failure."""
    shot = next(row for row in bench.typo_shots() if row.shot_id == "typo-sr-podrska")
    shot.text = (
        "translation===CARD==="
        '{"kind":"unit","word":"podrška","word_relation":"same","suggestion":"",'
        '"meanings":[{"label":"","translations":["поддержка"],"examples":['
        '{"text":"Hvala na podršci.","translation":"x",'
        '"highlighted":"Hvala na <b>podršci</b>.","gapped":"Hvala na ___."}]}],'
        '"segments":[]}'
    )

    scored = bench.score(shot)

    assert scored.metrics["typo_heads_submission"] is False
    assert scored.metrics["typo_word_exact"] is True
    # It never named the misspelling, which is a manners diagnostic and gates nothing.
    assert scored.metrics["typo_success"] is False


def test_tier_manifests_have_frozen_non_overlapping_counts():
    assert len(bench.SMOKE_CANONICAL_IDS) == 30
    assert len(bench.HISTORICAL_HARD_IDS) == 38
    assert len(bench.CONFIRMATION_ANCHOR_IDS) == 8
    assert len(bench.canonical_ids_for_tier("confirmation")) == 81
    assert len(bench.canonical_ids_for_tier("full")) == 157
    assert len(bench.initial_jobs_for_tier("smoke")) + len(bench.CLICK_IDS) == 55
    assert len(bench.initial_jobs_for_tier("confirmation")) + len(bench.CLICK_IDS) == 125
    assert len(bench.initial_jobs_for_tier("full")) + len(bench.CLICK_IDS) == 216
    # A word list is measured on the full tier only, at three calls.
    assert len(bench.wordlist_ids_for_tier("full")) == 3
    assert bench.wordlist_ids_for_tier("confirmation") == frozenset()
    assert len(bench.attested_ids_for_tier("smoke")) == 5
    assert len(bench.attested_ids_for_tier("confirmation")) == 10
    assert len(bench.attested_ids_for_tier("full")) == 16
    # Every attested fixture is judged twice, as production judges it.
    assert len(bench.attestation_ids_for_tier("full")) == 22
    # The ordinary-word class is measured on the full tier and gates nothing there.
    assert len(bench.ORDINARY_ATTESTED_IDS) == 6
    assert not bench.ORDINARY_ATTESTED_IDS & bench.attested_ids_for_tier("confirmation")
    assert all(bench.ATTESTED_BY_ID[i].attested for i in bench.ORDINARY_ATTESTED_IDS)
    assert all(
        "Do not write an article" in bench.prompt_for(shot) for shot in bench.attestation_shots()
    )
    assert not bench.ATTESTED_IDS & bench.TYPO_IDS
    # Both classes are represented at every tier, or the arm measures only one error.
    assert {bench.ATTESTED_BY_ID[i].attested for i in bench.SMOKE_ATTESTED_IDS} == {True, False}
    assert "verdict:clauses:sr:0" in bench.HISTORICAL_HARD_IDS
    assert "verdict:fragments:en:1" in bench.CONFIRMATION_ANCHOR_IDS


def test_registered_typo_inputs_are_valid_unit_intent_cases():
    rows = bench.typo_shots()

    assert [row.source for row in rows] == [
        "recieve",
        "Strase",
        "мозда",
        "definately",
        "vieleicht",
        "podrska",
    ]
    assert all("kind must be unit" in bench.prompt_for(row) for row in rows)


def test_typo_success_requires_the_corrected_word_on_the_card():
    job = bench.typo_shots()[0]
    payload = json.loads(_unit_answer(job.expected_suggestion).split("===CARD===", 1)[1])
    payload["word_relation"] = "typo"
    payload["suggestion"] = ""

    scored = bench.score(
        replace(job, text="analysis===CARD===" + json.dumps(payload)),
    )

    assert scored.metrics["typo_success"] is True


def _neighbour_answer(shot, *, relation, suggestion):
    payload = json.loads(_unit_answer(shot.source).split("===CARD===", 1)[1])
    payload["word_relation"] = relation
    payload["suggestion"] = suggestion
    return "analysis===CARD===" + json.dumps(payload)


def test_a_likelier_near_neighbour_is_offered_beside_the_learners_own_card():
    """The submission is a real word, so its article and its card are the learner's.
    The commoner word it may have been meant for is advice standing beside them."""
    job = next(shot for shot in bench.neighbour_shots() if shot.shot_id == "neighbour-en-causal")

    offered = bench.score(
        replace(job, text=_neighbour_answer(job, relation="same", suggestion="casual")),
    )

    assert offered.metrics["neighbour_offered"] is True
    assert offered.metrics["neighbour_kept_submission"] is True
    assert offered.metrics["neighbour_success"] is True
    assert offered.metrics["neighbour_false_offer"] is False


def test_a_neighbour_carded_instead_of_offered_is_not_a_success():
    """Calling it a misspelling replaces the learner's word instead of advising on it,
    and `_kept_the_misspelling` then cards nothing at all."""
    job = next(shot for shot in bench.neighbour_shots() if shot.shot_id == "neighbour-en-causal")

    as_typo = bench.score(
        replace(job, text=_neighbour_answer(job, relation="typo", suggestion="casual")),
    )

    assert as_typo.metrics["neighbour_kept_submission"] is False
    assert as_typo.metrics["neighbour_success"] is False


def test_a_neighbour_invented_for_an_ordinary_word_fails_a_zero_tolerance_gate():
    """A needless replace offer costs the learner more than a missed one: it appears
    beside a card they spelled correctly, on the common path rather than the rare one."""
    job = next(shot for shot in bench.neighbour_shots() if shot.shot_id == "neighbour-en-kitchen")

    invented = bench.score(
        replace(job, text=_neighbour_answer(job, relation="same", suggestion="chicken")),
    )
    counts = _passing_quality_counts()
    counts["neighbour_false_offers"] = 1

    assert invented.metrics["neighbour_false_offer"] is True
    assert invented.metrics["neighbour_success"] is False
    assert (
        bench.quality_gates(counts, "full")["no near neighbour is invented for an ordinary word"]
        is False
    )


def test_a_refused_coinage_is_a_complete_answer_and_is_not_re_asked_on_resume():
    """A refusal is the outcome the unused fixtures expect, not a missing branch.
    Judging it by the branch keys re-asks all six every resume, and `_select_canonical`
    then keeps the last draw where every other kind keeps the first."""
    job = next(shot for shot in bench.attested_shots() if shot.shot_id.startswith("unused-"))
    refusal = '===USED=== {"used": false, "where": ""}\n'
    refused = bench.score(replace(job, prompt_hash=bench.prompt_fingerprint(job), text=refusal))

    assert bench.attested_refused(refused) is True
    assert bench.complete(refused) is True
    assert bench.pending([job], {job.shot_id: refused}, resume=True) == []


def test_an_uncorrected_misspelling_on_the_card_is_a_zero_tolerance_failure():
    """The card must carry the attested spelling: a note headed by the misspelling
    teaches the misspelling, whatever the answer called the relation."""
    job = bench.typo_shots()[3]
    payload = json.loads(_unit_answer(job.source).split("===CARD===", 1)[1])
    payload["word_relation"] = "typo"
    payload["suggestion"] = job.expected_suggestion
    uncorrected = "analysis===CARD===" + json.dumps(payload)

    scored = bench.score(replace(job, text=uncorrected))

    assert scored.metrics["payload_valid"] is True
    assert scored.metrics["typo_word_exact"] is False
    assert not bench.deterministic_gates(
        [scored],
        [],
        "full",
    )["accepted typos card the corrected spelling"]


def test_the_declared_relation_is_reported_but_no_longer_a_contract():
    """The card is bound to the wording, not to the label the answer chose for it: the
    entry names the word it is about without calling the difference a misspelling, so a
    relation of morphology over the corrected spelling harms nothing."""
    job = bench.typo_shots()[0]
    payload = json.loads(_unit_answer(job.expected_suggestion).split("===CARD===", 1)[1])
    payload["word_relation"] = "morphology"
    scored = bench.score(
        replace(job, text="analysis===CARD===" + json.dumps(payload)),
    )

    assert scored.metrics["typo_relation_exact"] is False
    assert scored.metrics["typo_word_exact"] is True
    assert bench.deterministic_gates([scored], [], "full")[
        "accepted typos card the corrected spelling"
    ]


def test_a_misspelling_the_standalone_judgement_refuses_cards_nothing_to_hold():
    """Production makes no card there at all, so the contract about what a card carries
    has nothing to hold. Counting it as a violation would red the gate for the outcome
    the judgement exists to produce."""
    job = bench.typo_shots()[4]
    payload = json.loads(_unit_answer(job.source).split("===CARD===", 1)[1])
    payload["word_relation"] = "same"
    kept = bench.score(replace(job, text="analysis===CARD===" + json.dumps(payload)))
    refusal = bench.score(
        replace(
            next(
                shot
                for shot in bench.attestation_shots()
                if shot.shot_id == bench.attestation_id(job.shot_id)
            ),
            text='{"used": false, "where": ""}',
        ),
    )

    assert kept.metrics["typo_word_exact"] is False
    assert bench.deterministic_gates([kept, refusal], [], "full")[
        "accepted typos card the corrected spelling"
    ]


def test_resume_retries_availability_and_parse_misses_for_verdicts():
    job = next(shot for shot in bench.verdict_shots() if shot.shot_id == "verdict:clauses:en:0")
    unavailable = replace(job, prompt_hash=bench.prompt_fingerprint(job))
    unavailable.metrics = {
        "answered": False,
        "payload_valid": False,
        "actual_kind": None,
    }

    assert bench.pending([job], {job.shot_id: unavailable}, resume=True) == [job]

    invalid_json = bench.score(
        replace(
            job,
            prompt_hash=bench.prompt_fingerprint(job),
            text="analysis===CARD==={",
        ),
    )

    assert bench.pending([job], {job.shot_id: invalid_json}, resume=True) == [job]


def test_resume_does_not_replace_a_usable_wrong_branch_with_a_lucky_retry():
    job = next(shot for shot in bench.text_shots() if shot.shot_id == "text-en-0")
    wrong_branch = bench.score(
        replace(
            job,
            prompt_hash=bench.prompt_fingerprint(job),
            text=_unit_answer("give up"),
        ),
    )

    assert wrong_branch.metrics["actual_kind"] == "unit"
    assert wrong_branch.metrics["semantic_payload_valid"] is True
    assert bench.pending([job], {job.shot_id: wrong_branch}, resume=True) == []


def test_explicit_unit_text_branch_is_terminal_and_fails_bare_and_click_quality():
    bare_job = next(shot for shot in bench.bare_shots() if shot.shot_id == "bare-en-bank")
    click_job = bench.Shot(
        "click-en-function",
        "context",
        "en",
        "on",
        context="The book is on the table.",
        expected_kind="unit",
        selected_segment_kind="standalone",
    )

    for job in (bare_job, click_job):
        wrong_branch = bench.score(
            replace(
                job,
                prompt_hash=bench.prompt_fingerprint(job),
                text=_text_answer(),
            ),
        )

        assert wrong_branch.metrics["payload_valid"] is False
        assert wrong_branch.metrics["semantic_payload_valid"] is True
        assert wrong_branch.metrics["unit_intent_wrong_branch"] is True
        assert wrong_branch.metrics["actual_kind"] == "text"
        assert bench.complete(wrong_branch)
        assert bench.pending([job], {job.shot_id: wrong_branch}, resume=True) == []

    bare_wrong = bench.score(replace(bare_job, text=_text_answer()))
    click_wrong = bench.score(replace(click_job, text=_text_answer()))
    counts = bench.quality_counts([bare_wrong], [click_wrong])

    assert counts["usable_initial"] == 1
    assert counts["bare_cardable"] == 0
    assert counts["click_success"] == 0


def test_later_lucky_attempt_cannot_wash_away_explicit_unit_wrong_branch(tmp_path):
    out = tmp_path / "bench"
    job = next(shot for shot in bench.bare_shots() if shot.shot_id == "bare-en-bank")
    prompt_hash = bench.prompt_fingerprint(job)
    wrong_branch = replace(
        job,
        prompt_hash=prompt_hash,
        answered_by="semantic-wrong-branch",
        text=_text_answer(),
    )
    lucky_retry = replace(
        job,
        prompt_hash=prompt_hash,
        answered_by="lucky-retry",
        text=_unit_answer("bank"),
    )
    bench.append(out, wrong_branch)
    bench.append(out, lucky_retry)

    attempts = bench.read_attempts(out)
    current = bench.read(out, attempts)
    arms = bench.read_arms(out, attempts)
    selected = current[job.shot_id]

    assert selected.answered_by == "semantic-wrong-branch"
    assert selected.metrics["actual_kind"] == "text"
    assert selected.metrics["payload_valid"] is False
    assert selected.metrics["unit_intent_wrong_branch"] is True
    assert arms[0][job.shot_id].answered_by == "semantic-wrong-branch"
    assert bench.pending([job], current, resume=True) == []


def test_deterministic_contracts_ignore_rejected_context_selector_payloads():
    job = next(shot for shot in bench.bare_shots() if shot.shot_id == "bare-en-bank")
    payload = json.loads(_unit_answer("bank").split("===CARD===", 1)[1])
    payload["context_sense"] = 0
    accepted = bench.score(
        replace(job, text="analysis===CARD===" + json.dumps(payload)),
    )
    rejected_payload = {**payload, "meanings": []}
    rejected = bench.score(
        replace(job, text="analysis===CARD===" + json.dumps(rejected_payload)),
    )

    assert accepted.metrics["payload_valid"] is True
    assert accepted.metrics["context_sense_leak"] is True
    assert rejected.metrics["payload_valid"] is False
    assert rejected.metrics["context_sense_leak"] is True
    assert not bench.deterministic_gates(
        [accepted],
        [],
        "full",
    )["no context selector leaks into context-free answers"]
    rejected_gates = bench.deterministic_gates([rejected], [], "full")
    assert rejected_gates["no context selector leaks into context-free answers"]
    assert rejected_gates["accepted payloads contain one branch"]
    assert rejected_gates["accepted payloads are bounded and sanitized"]


def test_markup_that_changes_a_sentence_is_rejected_before_the_safety_gate():
    job = next(shot for shot in bench.bare_shots() if shot.shot_id == "bare-en-bank")
    payload = json.loads(_unit_answer("bank").split("===CARD===", 1)[1])
    payload["meanings"][0]["examples"][0]["highlighted"] = 'Example with <img src="x"><b>bank</b>.'
    scored = bench.score(
        replace(
            job,
            text=(
                '<section onclick="x">analysis & detail</section>===CARD===' + json.dumps(payload)
            ),
        ),
    )

    assert scored.metrics["payload_valid"] is False
    assert scored.metrics["format_ok"] is False
    assert scored.metrics["raw_sentence_forms_exact"] is False
    assert bench.deterministic_gates(
        [scored],
        [],
        "full",
    )["accepted payloads are bounded and sanitized"]


def test_whole_sentence_highlighting_is_exposed_even_when_parser_rejects_it():
    job = next(shot for shot in bench.bare_shots() if shot.shot_id == "bare-en-bank")
    payload = json.loads(_unit_answer("bank").split("===CARD===", 1)[1])
    example = payload["meanings"][0]["examples"][0]
    example["highlighted"] = "<b>Example with bank.</b>"
    example["gapped"] = "___"

    scored = bench.score(
        replace(job, text="analysis===CARD===" + json.dumps(payload)),
    )

    assert scored.metrics["payload_valid"] is False
    assert scored.metrics["raw_sentence_issues"][0]["issue"] == "whole sentence is the unit"


def test_unmarked_exact_bare_unit_token_is_exposed_even_when_parser_rejects_it():
    job = next(shot for shot in bench.bare_shots() if shot.shot_id == "bare-de-rad")
    payload = json.loads(_unit_answer("Rad fahren").split("===CARD===", 1)[1])
    payload["word_relation"] = "same"
    example = payload["meanings"][0]["examples"][0]
    example.update(
        text="Ich gehe in den Park, um Rad zu fahren.",
        highlighted="Ich gehe in den Park, um <b>Rad zu</b> fahren.",
        gapped="Ich gehe in den Park, um ___ fahren.",
    )

    scored = bench.score(
        replace(job, text="analysis===CARD===" + json.dumps(payload)),
    )

    assert scored.metrics["payload_valid"] is False
    assert scored.metrics["raw_sentence_issues"][0]["issue"] == (
        "submitted token occurs outside target"
    )


def test_forms_table_terms_reads_tables_and_not_the_prose_around_them():
    named = (
        "<b>Kübel</b> ведро<table><tr><td>der Kübel</td><td>именительный падеж</td></tr></table>"
    )
    phrases = (
        "<b>Kübel</b> ведро"
        "<table><tr><td>zwei Kübel Wasser</td><td>два ведра воды</td></tr></table>"
    )
    # The same word outside a table is ordinary usage prose and not a violation.
    prose = "<b>Kübel</b> ведро, существительное мужского рода в обиходной речи"

    assert bench.forms_table_terms(named) == ["именительный падеж"]
    assert bench.forms_table_terms(phrases) == []
    assert bench.forms_table_terms(prose) == []


def test_review_packet_shows_a_forms_table_that_names_a_grammatical_category():
    shot = bench.bare_shots()[0]
    article = (
        f"<b>{shot.source}</b> перевод"
        "<table><tr><td>формы</td><td>прошедшее время</td></tr></table>"
    )
    payload = _unit_answer(shot.source).split("===CARD===", 1)[1]
    scored = bench.score(replace(shot, text=f"{article}===CARD==={payload}"))

    assert scored.metrics["has_forms_table"] is True
    assert scored.metrics["forms_table_terms"] == ["прошедшее время"]

    packet = bench.review_packet("smoke", [scored], {scored.shot_id: scored})
    item = next(one for one in packet["items"] if one["fixture_id"] == scored.shot_id)

    assert "forms_table_terms" in item["categories"]
    assert item["actual"]["forms_table_terms"] == ["прошедшее время"]


def test_review_packet_carries_the_screen_counts_the_reviewer_reads_past():
    typo = bench.typo_shots()[0]
    screen = {"counts": {"tables_naming_terms": 3}, "quality_thresholds": {"gate": True}}

    packet = bench.review_packet("smoke", [typo], {typo.shot_id: typo}, screen)

    assert packet["screen"] == screen


def test_review_packet_lists_typo_click_and_raw_evidence():
    typo = bench.typo_shots()[0]
    payload = json.loads(_unit_answer(typo.source).split("===CARD===", 1)[1])
    payload["word_relation"] = "typo"
    payload["suggestion"] = typo.expected_suggestion
    typo = bench.score(
        replace(typo, text="analysis===CARD===" + json.dumps(payload)),
    )

    packet = bench.review_packet("smoke", [typo], {typo.shot_id: typo})

    assert packet["screen"] == {}
    assert packet["prompt_status"] == "unmeasured"
    assert packet["semantic_review_required"] is True
    typo_item = next(item for item in packet["items"] if item["fixture_id"] == typo.shot_id)
    assert typo_item["categories"] == ["typo"]
    assert typo_item["expected"]["word_relation"] == "typo"
    assert typo_item["actual"]["word_relation"] == "typo"
    # The correction is applied, so the card is expected to carry it and the
    # suggestion to be empty rather than repeating the word already carded.
    assert typo_item["expected"]["word"] == "receive"
    assert typo_item["expected"]["suggestion"] == ""
    assert typo_item["raw_evidence"]["answer"] == typo.text
    assert {item["fixture_id"] for item in packet["items"]} >= bench.CLICK_IDS


def test_complete_current_attempt_packet_is_pending_review_not_accepted():
    typo = bench.typo_shots()[0]
    current = {typo.shot_id: typo}
    current.update(
        {
            case.shot_id: bench.Shot(
                case.shot_id,
                "context",
                "en",
                case.label,
            )
            for case in bench.CLICK_CASES
        },
    )

    packet = bench.review_packet("smoke", [typo], current)

    assert packet["prompt_status"] == "pending_semantic_review"
    assert packet["semantic_review_required"] is True


def test_unavailable_click_sources_remain_failures_in_the_fixed_denominator():
    assert bench.context_shots({}) == []
    assert not bench.click_gate([])["at least five successful click cases"]


def test_click_gate_allows_one_failure_but_each_success_is_fully_structural():
    rows = []
    for shot_id in sorted(bench.CLICK_IDS):
        shot = _shot(shot_id, expected_kind="unit")
        shot.kind = "context"
        shot.metrics = {
            "answered": True,
            "payload_valid": True,
            "actual_kind": "unit",
            "four_cards_ready": True,
            "context_example_exact": True,
            "context_surface_exact": True,
            "click_target_exact": True,
            "click_target_kind_exact": True,
        }
        rows.append(shot)

    assert all(bench.click_gate(rows).values())
    assert all(bench.click_gate(rows[:-1]).values())
    assert not all(bench.click_gate(rows[:-2]).values())
    rows[0].metrics["context_parts_highlighted"] = False
    assert all(bench.click_gate(rows).values())
    rows[0].metrics["context_surface_exact"] = False
    assert all(bench.click_gate(rows).values())
    rows[1].metrics["context_surface_exact"] = False
    assert not all(bench.click_gate(rows).values())


def test_markup_leaking_into_the_plain_example_is_not_reported_as_a_defect():
    shot = bench.Shot("bare-en-bank", "bare", "en", "bank", expected_kind="unit")
    shot.text = (
        "<b>bank</b> article===CARD==="
        '{"kind":"unit","word":"bank","word_relation":"same","suggestion":"",'
        '"meanings":[{"label":"","translations":["банк"],'
        '"examples":[{"text":"The <b>bank</b> opens.","translation":"Банк открывается.",'
        '"highlighted":"The <b>bank</b> opens."}]}],"segments":[]}'
    )

    scored = bench.score(shot)

    assert scored.metrics["raw_sentence_issues"] == []
    assert scored.metrics["payload_valid"] is True


def test_a_german_lookup_label_may_close_up_its_separated_spelling():
    shot = next(row for row in bench.text_shots() if row.shot_id == "text-de-6")
    shot.text = (
        "translation===CARD==="
        '{"kind":"text","combinations":['
        '{"label":"infrage kommen","surface":"kommt ... in Frage","why":"verb"}]}'
    )

    scored = bench.score(shot)

    assert scored.metrics["expected_lookups_found"] == 1


def test_a_click_still_succeeds_when_the_answer_returns_component_segments():
    shot = _shot(sorted(bench.CLICK_IDS)[0], expected_kind="unit")
    shot.kind = "context"
    shot.metrics = {
        "answered": True,
        "payload_valid": True,
        "actual_kind": "unit",
        "four_cards_ready": True,
        "context_example_exact": True,
        "context_surface_exact": True,
        "context_segments_empty": False,
        "click_target_exact": True,
        "click_target_kind_exact": True,
    }

    assert bench.click_success(shot)


def test_a_transliterated_serbian_chip_counts_for_its_registered_unit():
    shot = next(row for row in bench.text_shots() if row.shot_id == "text-sr-7")
    shot.text = (
        "translation===CARD==="
        '{"kind":"text","combinations":['
        '{"label":"играти се","surface":"се играју","why":"повратни глагол"}]}'
    )

    scored = bench.score(shot)

    assert scored.metrics["registered_units_found"] == 1
    assert scored.metrics["expected_lookups_found"] == 1


def test_a_function_click_survives_a_combination_which_swallowed_its_token():
    shot = bench.Shot(
        "text-en-1",
        "text",
        "en",
        "The book is on the table.",
        expected_kind="text",
        text=(
            "translation===CARD==="
            '{"kind":"text","combinations":['
            '{"label":"book on","surface":"book on","why":"optional"}]}'
        ),
    )
    scored = bench.score(shot)
    case = bench.CLICK_BY_ID["click-en-function"]

    selected = bench.find_segment(scored, case)

    assert selected is not None
    segment, segment_kind = selected
    assert (segment.label, segment_kind) == ("on", "standalone")


def test_combination_click_selects_the_exact_grouped_chip_and_kind():
    shot = bench.Shot(
        "text-en-0",
        "text",
        "en",
        "I gave up after ten minutes.",
        expected_kind="text",
        text=(
            "translation===CARD==="
            '{"kind":"text","combinations":['
            '{"label":"give up","surface":"gave up","why":"phrasal verb"}]}'
        ),
    )
    scored = bench.score(shot)
    case = bench.CLICK_BY_ID["click-en-combination"]

    selected = bench.find_segment(scored, case)

    assert selected is not None
    segment, segment_kind = selected
    assert segment.label == "gave up"
    assert segment_kind == "combination"


def test_expression_gate_allows_one_failure_but_requires_exact_parts_and_context():
    rows = []
    for shot_id, lang, source, morphology, expression in bench.BARE_CASES:
        shot = bench.Shot(
            shot_id,
            "bare",
            lang,
            source,
            expects_morphology=morphology,
            expression=expression,
        )
        shot.metrics = {
            "answered": True,
            "payload_valid": True,
            "actual_kind": "unit",
            "four_cards_ready": True,
            "expression_parts": 2 if expression else 0,
            "expression_parts_exact": True,
            "expression_contexts_exact": True,
        }
        rows.append(shot)

    assert all(bench.expression_gate(rows).values())
    expression = next(row for row in rows if row.expression)
    expression.metrics["expression_parts_exact"] = False
    assert all(bench.expression_gate(rows).values())
    second = next(row for row in rows if row.expression and row is not expression)
    second.metrics["expression_contexts_exact"] = False
    assert not all(bench.expression_gate(rows).values())


def test_expression_gate_rejects_an_answer_missing_one_expected_component():
    shot = bench.Shot(
        "bare-en-give-up",
        "bare",
        "en",
        "give up",
        expression=True,
    )
    shot.text = (
        "analysis===CARD==="
        '{"kind":"unit","word":"give up","word_relation":"same",'
        '"suggestion":"","meanings":['
        '{"label":"","translations":["сдаться"],"examples":['
        '{"text":"Do not give up.","translation":"Не сдавайся.",'
        '"highlighted":"Do not <b>give up</b>.","gapped":"Do not ___."}]}],'
        '"segments":[{"surface":"give","why":"verb"}]}'
    )

    scored = bench.score(shot)

    assert scored.metrics["expression_parts"] == 1
    assert scored.metrics["expression_parts_exact"] is False
    assert not all(bench.expression_gate([scored]).values())


def test_expression_gate_preserves_case_in_the_exact_source_parts():
    shot = bench.Shot(
        "bare-de-rad",
        "bare",
        "de",
        "Rad fahren",
        expression=True,
    )
    shot.text = (
        "analysis===CARD==="
        '{"kind":"unit","word":"Rad fahren","word_relation":"same",'
        '"suggestion":"","meanings":['
        '{"label":"","translations":["ехать на велосипеде"],"examples":['
        '{"text":"Ich fahre gern Rad.","translation":"Я люблю ездить на велосипеде.",'
        '"highlighted":"Ich <b>fahre</b> gern <b>Rad</b>.",'
        '"gapped":"Ich ___ gern ___."}]}],'
        '"segments":[{"surface":"rad","why":"noun"},'
        '{"surface":"fahren","why":"verb"}]}'
    )

    scored = bench.score(shot)

    assert bench.normalize("rad") == bench.normalize("Rad")
    assert scored.metrics["expression_parts_exact"] is False
    assert not all(bench.expression_gate([scored]).values())


def test_an_omitted_fixed_part_costs_the_exact_boundary_but_not_the_unit():
    shot = next(row for row in bench.text_shots() if row.shot_id == "text-de-4")
    shot.text = (
        "translation===CARD==="
        '{"kind":"text","combinations":['
        '{"label":"die Nase voll haben","surface":"die Nase voll","why":"verb"}]}'
    )

    scored = bench.score(shot)

    assert scored.metrics["registered_units_found"] == 1
    assert scored.metrics["registered_units_cardable"] == 0
    assert scored.metrics["registered_unit_matches"][0]["match"] == "partial boundary"
    assert scored.metrics["expected_found"] == 0
    # The label names the entry; only the surface proves the fixed part was found.
    assert scored.metrics["expected_lookups_found"] == 1


def test_registered_unit_gate_has_an_explicit_variable_experiencer_alternative():
    shot = next(row for row in bench.text_shots() if row.shot_id == "text-sr-8")
    shot.text = (
        "translation===CARD==="
        '{"kind":"text","combinations":['
        '{"label":"činiti se","surface":"se ... čini","why":"verb"},'
        '{"label":"u redu","surface":"u redu","why":"phrase"}]}'
    )

    scored = bench.score(shot)

    assert scored.metrics["registered_units_found"] == 2
    assert scored.metrics["registered_unit_matches"][0]["match"] == ("accepted alternative")


def test_semantic_label_alone_does_not_pass_without_a_filled_combination_chip():
    shot = bench.Shot(
        "text-de-9",
        "text",
        "de",
        "Wir müssen uns auf das Wesentliche beschränken.",
        expected_groups=[["sich auf etwas beschränken"]],
        expected_kind="text",
    )
    shot.text = (
        "translation===CARD==="
        '{"kind":"text","combinations":['
        '{"label":"sich auf etwas beschränken","surface":"missing parts",'
        '"why":"verb"}]}'
    )

    scored = bench.score(shot)

    assert scored.metrics["registered_units_found"] == 0


def test_merged_neighbor_chip_counts_once_and_can_still_pass_aggregate_threshold():
    shot = next(row for row in bench.text_shots() if row.shot_id == "text-sr-8")
    shot.text = (
        "translation===CARD==="
        '{"kind":"text","combinations":['
        '{"label":"činiti se u redu","surface":"mi se čini u redu",'
        '"why":"merged useful phrase"}]}'
    )

    scored = bench.score(shot)

    assert scored.metrics["registered_units_found"] == 1
    assert scored.metrics["expected_found"] == 0
    assert scored.metrics["registered_unit_misses"] == ["u redu"]
    assert scored.metrics["registered_merged_neighbor_chips"] == [
        {
            "chip": "mi se čini u redu",
            "contains": ["mi se čini", "u redu"],
        },
    ]

    counts = _passing_quality_counts()
    counts["registered_units"] = 20
    assert all(bench.quality_gates(counts, "full").values())


def test_a_clitic_the_label_names_is_taken_back_into_the_chip():
    shot = next(row for row in bench.text_shots() if row.shot_id == "text-de-1")
    shot.text = (
        "translation===CARD==="
        '{"kind":"text","combinations":['
        '{"label":"sich freuen auf","surface":"freue ... auf","why":"Verb"}]}'
    )

    scored = bench.score(shot)

    assert scored.metrics["registered_units_cardable"] == 1
    assert scored.metrics["registered_unit_matches"][0]["chip"] == "freue mich auf"
    assert scored.metrics["registered_unit_matches"][0]["match"] == "exact"
    assert "mich" not in scored.metrics["missing"]


def test_a_chip_sharing_nothing_with_the_registered_unit_is_still_a_miss():
    shot = next(row for row in bench.text_shots() if row.shot_id == "text-sr-3")
    shot.text = (
        "translation===CARD==="
        '{"kind":"text","combinations":['
        '{"label":"ни најмање","surface":"ни најмање","why":"прилог"}]}'
    )

    scored = bench.score(shot)

    assert scored.metrics["registered_units_found"] == 0
    assert scored.metrics["registered_unit_misses"] == ["се изненадио"]


def test_a_run_on_chip_drifting_by_more_than_one_word_is_a_miss():
    shot = next(row for row in bench.text_shots() if row.shot_id == "text-sr-8")
    shot.text = (
        "translation===CARD==="
        '{"kind":"text","combinations":['
        '{"label":"činiti se","surface":"se čini da nešto nije","why":"глагол"}]}'
    )

    scored = bench.score(shot)

    assert "mi se čini" in scored.metrics["registered_unit_misses"]
