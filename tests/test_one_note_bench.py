import json
from dataclasses import replace

import one_note_bench as bench


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
    assert _outcome(_shot("verdict:clauses:de:0"), "unit") == "hard_error"
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
        "registered_units": bench.MIN_REGISTERED_UNITS,
        "click_success": bench.MIN_CLICK_SUCCESS,
        "expression_success": bench.MIN_EXPRESSION_SUCCESS,
        "typo_success": 5,
        "confirmed_attempted": 6,
        "confirmed_cardable": 4,
        "confirmed_success": 0,
    }


def test_quality_thresholds_pass_at_the_boundaries():
    assert all(bench.quality_gates(_passing_quality_counts(), "full").values())


def test_quality_thresholds_fail_immediately_below_each_minimum():
    keys = (
        "usable_initial",
        "text_branch",
        "bare_cardable",
        "registered_units",
        "click_success",
        "expression_success",
        "typo_success",
        "confirmed_cardable",
    )
    for key in keys:
        counts = _passing_quality_counts()
        counts[key] -= 1
        assert not all(bench.quality_gates(counts, "full").values())

    counts = _passing_quality_counts()
    counts["hard_verdict_errors"] = 11
    assert not bench.quality_gates(counts, "full")["obvious hard verdict errors"]


def test_tier_manifests_have_frozen_non_overlapping_counts():
    assert len(bench.SMOKE_CANONICAL_IDS) == 30
    assert len(bench.HISTORICAL_HARD_IDS) == 38
    assert len(bench.CONFIRMATION_ANCHOR_IDS) == 8
    assert len(bench.canonical_ids_for_tier("confirmation")) == 81
    assert len(bench.canonical_ids_for_tier("full")) == 157
    assert len(bench.initial_jobs_for_tier("smoke")) + len(bench.CLICK_IDS) == 42
    assert len(bench.initial_jobs_for_tier("confirmation")) + len(bench.CLICK_IDS) == 99
    assert len(bench.initial_jobs_for_tier("full")) + len(bench.CLICK_IDS) == 175
    assert len(bench.confirmed_ids_for_tier("smoke")) == 3
    assert len(bench.confirmed_ids_for_tier("full")) == 6
    assert not bench.CONFIRMED_IDS & bench.TYPO_IDS
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


def test_typo_success_requires_original_word_and_exact_suggestion():
    job = bench.typo_shots()[0]
    payload = json.loads(_unit_answer(job.source).split("===CARD===", 1)[1])
    payload["word_relation"] = "typo"
    payload["suggestion"] = job.expected_suggestion

    scored = bench.score(
        replace(job, text="analysis===CARD===" + json.dumps(payload)),
    )

    assert scored.metrics["typo_success"] is True


def test_accepted_silent_typo_correction_is_a_zero_tolerance_failure():
    job = bench.typo_shots()[3]
    payload = json.loads(_unit_answer(job.expected_suggestion).split("===CARD===", 1)[1])
    payload["word_relation"] = "morphology"
    corrected = "analysis===CARD===" + json.dumps(payload)

    scored = bench.score(replace(job, text=corrected))

    assert scored.metrics["payload_valid"] is True
    assert scored.metrics["typo_word_exact"] is False
    assert not bench.deterministic_gates(
        [scored],
        [],
        "full",
    )["accepted typos retain the submitted spelling"]


def test_registered_typo_cannot_pass_by_declaring_morphology():
    job = bench.typo_shots()[0]
    payload = json.loads(_unit_answer(job.source).split("===CARD===", 1)[1])
    payload["word_relation"] = "morphology"
    scored = bench.score(
        replace(job, text="analysis===CARD===" + json.dumps(payload)),
    )

    assert scored.metrics["payload_valid"] is True
    assert scored.metrics["typo_relation_exact"] is False
    assert not bench.deterministic_gates(
        [scored],
        [],
        "full",
    )["accepted registered typos declare typo relation"]


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


def test_review_packet_lists_typo_click_and_raw_evidence():
    typo = bench.typo_shots()[0]
    payload = json.loads(_unit_answer(typo.source).split("===CARD===", 1)[1])
    payload["word_relation"] = "typo"
    payload["suggestion"] = typo.expected_suggestion
    typo = bench.score(
        replace(typo, text="analysis===CARD===" + json.dumps(payload)),
    )

    packet = bench.review_packet("smoke", [typo], {typo.shot_id: typo})

    assert packet["screen"] == "AUTOMATED SCREEN"
    assert packet["prompt_status"] == "unmeasured"
    assert packet["semantic_review_required"] is True
    typo_item = next(item for item in packet["items"] if item["fixture_id"] == typo.shot_id)
    assert typo_item["categories"] == ["typo"]
    assert typo_item["expected"]["word_relation"] == "typo"
    assert typo_item["actual"]["word_relation"] == "typo"
    assert typo_item["expected"]["suggestion"] == "receive"
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
    shot = bench.Shot(
        "text-de-9",
        "text",
        "de",
        "Wir müssen uns auf das Wesentliche beschränken.",
        expected_groups=[
            ["sich auf etwas beschränken", "sich beschränken auf", "beschränken auf"],
        ],
        expected_kind="text",
    )
    shot.text = (
        "translation===CARD==="
        '{"kind":"text","combinations":['
        '{"label":"sich auf etwas beschränken","surface":"auf … beschränken",'
        '"why":"verb"}]}'
    )

    scored = bench.score(shot)

    assert scored.metrics["registered_units_found"] == 1
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


def test_a_dropped_clitic_still_counts_while_its_word_keeps_a_chip():
    shot = next(row for row in bench.text_shots() if row.shot_id == "text-de-1")
    shot.text = (
        "translation===CARD==="
        '{"kind":"text","combinations":['
        '{"label":"sich freuen auf","surface":"freue ... auf","why":"Verb"}]}'
    )

    scored = bench.score(shot)

    assert scored.metrics["registered_units_found"] == 1
    assert scored.metrics["registered_unit_matches"][0]["match"] == "partial boundary"
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
