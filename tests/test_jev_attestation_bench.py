import asyncio
import json

import httpx
import jev_attestation_bench as bench
import pytest


def test_fixtures_are_complete_unique_and_do_not_send_labels():
    cases = bench.fixtures()
    assert len(cases) == 44
    assert len({(case["lang"], case["word"]) for case in cases}) == 44
    assert sum(case["group"] == "real" for case in cases) == 32
    assert sum(case["group"] == "constructed" for case in cases) == 6
    assert sum(case["group"] == "typo" for case in cases) == 6
    assert cases == bench.fixtures()
    assert sum(case["attested_used"] is True for case in cases) == 35
    assert all(case["attested_used"] is None for case in cases if case["group"] == "typo")
    for case in cases:
        request = bench.jev_request(case)
        assert set(request["state"]) == {"source_language", "wording"}
        assert "expected_used" not in json.dumps(request)


def test_manifest_rejects_prompt_drift(tmp_path, monkeypatch):
    monkeypatch.setattr(bench.subprocess, "check_output", lambda *a, **k: "test-commit\n")
    first = bench.prepare(tmp_path)
    assert bench.prepare(tmp_path) == first
    monkeypatch.setattr(bench, "INSTRUCTIONS", "different question")
    with pytest.raises(ValueError, match="Frozen design changed"):
        bench.prepare(tmp_path)


def test_resume_keeps_first_usable_and_rejects_other_experiments():
    rows = [
        {"id": "a", "arm": "jev", "fingerprint": "same", "used": None},
        {"id": "a", "arm": "jev", "fingerprint": "same", "used": False},
        {"id": "a", "arm": "jev", "fingerprint": "same", "used": True},
    ]
    assert bench.selected_rows(rows, "same")[("a", "jev")]["used"] is False
    with pytest.raises(ValueError, match="different frozen design"):
        bench.selected_rows(rows, "other")


@pytest.mark.parametrize(
    "probability, expected",
    [(0, False), (0.49, False), (0.5, True), (1, True), (True, None), (1.1, None), ("0.9", None)],
)
def test_jev_transport_validates_probabilities(probability, expected):
    async def check():
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "model": bench.MODEL,
                    "answers": {"used": {"noul": probability}},
                },
            )
        )
        async with httpx.AsyncClient(transport=transport) as client:
            return await bench.ask_jev(client, {})

    result = asyncio.run(check())
    assert result["used"] is expected
    assert (result["error"] is None) == (expected is not None)


def test_jev_failure_does_not_persist_response_secrets():
    async def check():
        transport = httpx.MockTransport(lambda request: httpx.Response(401, text="secret"))
        async with httpx.AsyncClient(transport=transport) as client:
            return await bench.ask_jev(client, {})

    result = asyncio.run(check())
    assert result["used"] is None
    assert result["status"] == 401
    assert "secret" not in json.dumps(result)


def test_pool_uses_existing_harness_and_retains_raw_answer(tmp_path, monkeypatch):
    async def fake_batch(args, out, broker, shots):
        assert args.paid == ""
        assert out == tmp_path / "pool"
        assert len(shots) == 1
        shots[0].text = '{"used": false, "where": ""}'
        shots[0].answered_by = "fake-pool"

    monkeypatch.setattr(bench.bench, "run_batch", fake_batch)
    result = asyncio.run(bench.ask_pool(None, bench.fixtures()[0], tmp_path))
    assert result["used"] is False
    assert result["model"] == "fake-pool"
    assert result["raw"]["text"] == '{"used": false, "where": ""}'


def test_report_separates_missing_answers_challenges_and_cost(tmp_path, monkeypatch):
    monkeypatch.setattr(bench.subprocess, "check_output", lambda *a, **k: "test-commit\n")
    manifest = bench.prepare(tmp_path)
    case = next(c for c in bench.fixtures() if c["group"] == "constructed")
    row = {
        "id": case["id"],
        "arm": "jev",
        "fingerprint": manifest["fingerprint"],
        "used": True,
        "probability": 0.99,
        "seconds": 0.2,
        "model": bench.MODEL,
        "raw": {"usage": {"input_tokens": 1000}},
    }
    (tmp_path / "results.jsonl").write_text(json.dumps(row) + "\n")
    report = bench.report(tmp_path)
    assert report["availability_complete"] is False
    assert report["semantic_review_required"] is True
    assert report["jev_estimated_usd"] == pytest.approx(0.000042)
    assert report["arms"]["jev"]["groups"]["constructed"]["legacy_label_disagreements"] == 1
    assert report["arms"]["jev"]["groups"]["real"]["usable"] == 0
    assert report["arms"]["jev"]["exploratory_abstention"]["legacy_label_disagreements"] == 1
    packet = json.loads((tmp_path / "review-packet-attestation.json").read_text())
    assert len(packet["items"]) == 44


def test_completed_measurement_resumes_without_buying_answers_again(tmp_path, monkeypatch):
    monkeypatch.setattr(bench.subprocess, "check_output", lambda *a, **k: "test-commit\n")
    monkeypatch.setattr(bench, "load_keys", lambda: {"TYPESAFE_API_KEY": "test-only-key"})
    monkeypatch.setattr(bench.os, "environ", {})
    calls = []

    class FakeBroker:
        def __init__(self, **kwargs):
            pass

        async def aclose(self):
            pass

    async def no_sleep(seconds):
        pass

    async def fake_jev(client, request):
        calls.append("jev")
        return {
            "used": True,
            "probability": 0.9,
            "model": bench.MODEL,
            "seconds": 0.25,
            "raw": {"usage": {"input_tokens": 100}},
        }

    async def fake_pool(broker, case, out):
        calls.append("pool")
        return {"used": True, "model": "fake-pool", "seconds": 1.0}

    monkeypatch.setattr(bench, "AsyncBroker", FakeBroker)
    monkeypatch.setattr(bench, "ask_jev", fake_jev)
    monkeypatch.setattr(bench, "ask_pool", fake_pool)
    monkeypatch.setattr(bench.asyncio, "sleep", no_sleep)
    asyncio.run(bench.run(tmp_path))
    before = (tmp_path / "results.jsonl").read_bytes()
    assert len(calls) == 88
    asyncio.run(bench.run(tmp_path))
    assert len(calls) == 88
    assert (tmp_path / "results.jsonl").read_bytes() == before
    report = bench.report(tmp_path)
    assert report["availability_complete"] is True
    assert report["paired_latency"] == {
        "pairs": 44,
        "median_pool_over_jev": 4.0,
        "jev_faster_pairs": 44,
    }
    assert report["jev_input_tokens"] == 4400
