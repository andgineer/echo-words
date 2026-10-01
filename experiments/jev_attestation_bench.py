"""Frozen exploratory attestation tier, using the production-flow pool harness.

Run `uv run python experiments/jev_attestation_bench.py prepare --out ...`, then
`run --out ...` (always resumes), then `report --out ...`. Both arms spend live
API quota. Production prompts and routing are not changed by this experiment.
"""

import argparse
import asyncio
import hashlib
import json
import math
import os
import random
import statistics
import subprocess
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

import httpx
import one_note_bench as bench
from backend_bench import load_keys
from bench_items import ITEMS
from llmbroker import AsyncBroker

MODEL = "jev-1.13.0"
ENDPOINT = "https://api.typesafe.ai/v1/systemone"
PRICE_PER_MILLION = 0.042
ATTESTATION_EVIDENCE = {
    "tablewards": "https://kaikki.org/dictionary/English/meaning/t/ta/tablewards.html",
    "Fahrradsuppe": "https://radler-rast.com/radler-rast-kaffee",
    "bookshelfy": "https://westernliving.ca/shopping/accessories/editors-picks-organizing-accessories-home/",
}
INSTRUCTIONS = (
    "Is the exact wording actually used by speakers of the specified source language? "
    "Rarity is no objection: wording real speakers use in any register, field, dialect "
    "or period is used, however uncommon. Wording that is merely well formed — a "
    "compound, derivation or coinage nobody actually says — is not used, however "
    "natural it looks."
)


def fixtures() -> list[dict]:
    cases = {}

    def add(case_id, lang, word, group, expected):
        cases.setdefault((lang, word), {
            "id": case_id, "lang": lang, "word": word, "group": group,
            "expected_used": expected,
            "attested_used": True if expected or word in ATTESTATION_EVIDENCE else None,
            "reference": f"https://en.wiktionary.org/wiki/{quote(word)}" if expected else "",
            "adjudication_source": ATTESTATION_EVIDENCE.get(word, ""),
            "label_basis": "Existing repository fixture; constructed and typo slices are policy challenges.",
        })

    for case in bench.ATTESTED_CASES:
        add(case.shot_id, case.lang, case.submitted,
            "real" if case.attested else "constructed", case.attested)
    for case in bench.TYPO_CASES:
        add(case.shot_id, case.lang, case.submitted, "typo", False)
        add(f"corrected-{case.shot_id}", case.lang, case.suggestion, "real", True)
    for lang, items in ITEMS.items():
        for word, shape in items:
            if shape == "rare":
                add(f"rare-{lang}-{word}", lang, word, "real", True)
    result = list(cases.values())
    random.Random(20260930).shuffle(result)
    return result


def jev_request(case: dict) -> dict:
    return {
        "model": MODEL,
        "state": {"source_language": bench.LANGUAGES[case["lang"]].name,
                  "wording": case["word"]},
        "questions": {"used": {"type": "noul", "instructions": INSTRUCTIONS}},
    }


def fingerprint(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def prepare(out: Path) -> dict:
    cases = fixtures()
    design = {
        "tier": "attestation-44-v1", "cases": cases, "threshold": 0.5,
        "abstention_band": [0.1, 0.9], "pace_seconds": 5, "pool_wait_seconds": 60,
        "pool_fastest_of": bench.POOL_FASTEST_OF,
        "requests": {
            case["id"]: {
                "jev": jev_request(case),
                "pool": bench.build_attestation_prompt(bench.LANGUAGES[case["lang"]], case["word"]),
            } for case in cases
        },
    }
    path = out / "manifest.json"
    if path.exists():
        old = json.loads(path.read_text())
        if old["fingerprint"] != fingerprint(design):
            raise ValueError("Frozen design changed; do not mix or silently restart experiments")
        return old
    manifest = {
        "design": design, "fingerprint": fingerprint(design),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    out.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return manifest


def read_rows(out: Path) -> list[dict]:
    path = out / "results.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def selected_rows(rows: list[dict], digest: str) -> dict:
    selected = {}
    for row in rows:
        if row["fingerprint"] != digest:
            raise ValueError("Results belong to a different frozen design")
        key = (row["id"], row["arm"])
        if key not in selected or selected[key]["used"] is None:
            selected[key] = row
    return selected


async def ask_jev(client: httpx.AsyncClient, request: dict) -> dict:
    started = time.monotonic()
    result = {"used": None, "probability": None, "model": MODEL, "error": None}
    try:
        response = await client.post(ENDPOINT, json=request)
        result["status"] = response.status_code
        response.raise_for_status()
        body = response.json()
        result["raw"] = body
        result["model"] = body.get("model")
        value = body["answers"]["used"]["noul"]
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("Invalid Noul")
        result.update(used=value >= 0.5, probability=value)
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        # Exception messages can contain request material; only the class is evidence.
        result["error"] = type(exc).__name__
    result["seconds"] = time.monotonic() - started
    return result


async def ask_pool(broker: AsyncBroker, case: dict, out: Path) -> dict:
    shot = bench.Shot(case["id"], "attestation", case["lang"], case["word"])
    args = SimpleNamespace(concurrency=1, pace=0, paid="", wait=60)
    started = time.monotonic()
    await bench.run_batch(args, out / "pool", broker, [shot])
    verdict = bench.parse_attestation(shot.text) if not shot.error else None
    return {
        "used": verdict.used if verdict else None, "model": shot.answered_by,
        "probability": None, "seconds": time.monotonic() - started,
        "raw": asdict(shot), "error": shot.error,
    }


async def run(out: Path) -> None:
    manifest = prepare(out)
    digest = manifest["fingerprint"]
    selected = selected_rows(read_rows(out), digest)
    keys = load_keys()
    key = keys.get("TYPESAFE_API_KEY", "")
    if not key:
        raise ValueError("TYPESAFE_API_KEY is absent")
    os.environ.update(keys)
    broker = AsyncBroker(home=out / "pool" / "llmbroker")
    misses = 0
    try:
        async with httpx.AsyncClient(
            headers={"Authorization": f"Bearer {key}"}, timeout=30,
        ) as client:
            for index, case in enumerate(manifest["design"]["cases"]):
                arms = ("pool", "jev") if index % 2 else ("jev", "pool")
                called = False
                for arm in arms:
                    previous = selected.get((case["id"], arm))
                    if previous and previous["used"] is not None:
                        continue
                    called = True
                    if arm == "jev":
                        row = await ask_jev(client, manifest["design"]["requests"][case["id"]][arm])
                    else:
                        row = await ask_pool(broker, case, out)
                        misses = misses + 1 if row["used"] is None else 0
                    row.update(id=case["id"], arm=arm, fingerprint=digest,
                               recorded_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
                    with (out / "results.jsonl").open("a") as target:
                        target.write(json.dumps(row, ensure_ascii=False) + "\n")
                    print(f"{index + 1}/{len(manifest['design']['cases'])} {arm} "
                          f"{case['word']}: {row['used']} {row['seconds']:.3f}s", flush=True)
                    if misses >= 2 or (arm == "jev" and row["used"] is None):
                        raise RuntimeError("Availability interrupted; inspect saved answers and resume")
                if called:
                    await asyncio.sleep(manifest["design"]["pace_seconds"])
    finally:
        await broker.aclose()


def summarize(cases: list[dict], selected: dict, arm: str) -> dict:
    pairs = [(case, selected.get((case["id"], arm))) for case in cases]
    usable = [(case, row) for case, row in pairs if row and row["used"] is not None]
    times = sorted(row["seconds"] for _, row in usable)
    summary = {
        "attempted_cases": sum(row is not None for _, row in pairs),
        "usable": len(usable), "expected": len(cases),
        "models": dict(Counter(row["model"] for _, row in usable)),
        "median_seconds": statistics.median(times) if times else None,
        "p90_seconds": times[math.ceil(len(times) * .9) - 1] if times else None,
        "groups": {},
    }
    verified = [(case, row) for case, row in usable if case["attested_used"] is True]
    summary["verified_attested"] = {
        "expected": sum(case["attested_used"] is True for case in cases),
        "usable": len(verified), "rejected": sum(not row["used"] for _, row in verified),
    }
    for group in ("real", "constructed", "typo"):
        rows = [(case, row) for case, row in usable if case["group"] == group]
        summary["groups"][group] = {
            "usable": len(rows), "expected": sum(case["group"] == group for case in cases),
            "approved": sum(row["used"] for _, row in rows),
            "legacy_label_disagreements": sum(row["used"] != case["expected_used"] for case, row in rows),
        }
    if arm == "jev":
        retained = [(case, row) for case, row in usable
                    if row["probability"] <= .1 or row["probability"] >= .9]
        summary["exploratory_abstention"] = {
            "retained": len(retained), "abstained": len(usable) - len(retained),
            "verified_attested_retained": sum(case["attested_used"] is True for case, _ in retained),
            "verified_attested_rejected": sum(case["attested_used"] is True and not row["used"]
                                               for case, row in retained),
            "legacy_label_disagreements": sum(row["used"] != case["expected_used"] for case, row in retained),
        }
    return summary


def report(out: Path) -> dict:
    manifest = prepare(out)
    cases = manifest["design"]["cases"]
    rows = read_rows(out)
    selected = selected_rows(rows, manifest["fingerprint"])
    summary = {
        "fingerprint": manifest["fingerprint"], "semantic_review_required": True,
        "availability_complete": all(
            (case["id"], arm) in selected and selected[(case["id"], arm)]["used"] is not None
            for case in cases for arm in ("pool", "jev")
        ),
        "arms": {arm: summarize(cases, selected, arm) for arm in ("pool", "jev")},
        "languages": {lang: {arm: summarize([c for c in cases if c["lang"] == lang], selected, arm)
                              for arm in ("pool", "jev")} for lang in ("en", "de", "sr")},
        "attempts": dict(Counter(row["arm"] for row in rows)),
        "jev_input_tokens": sum(row.get("raw", {}).get("usage", {}).get("input_tokens", 0)
                                for row in rows if row["arm"] == "jev"),
        "pool_marginal_usd": 0,
    }
    summary["jev_estimated_usd"] = summary["jev_input_tokens"] * PRICE_PER_MILLION / 1_000_000
    paired = [(selected[(case["id"], "pool")], selected[(case["id"], "jev")])
              for case in cases if all((case["id"], arm) in selected
                                       and selected[(case["id"], arm)]["used"] is not None
                                       for arm in ("pool", "jev"))]
    summary["paired_latency"] = {
        "pairs": len(paired),
        "median_pool_over_jev": statistics.median(pool["seconds"] / jev["seconds"]
                                                  for pool, jev in paired) if paired else None,
        "jev_faster_pairs": sum(jev["seconds"] < pool["seconds"] for pool, jev in paired),
    }
    packet = {
        "manifest": manifest, "summary": summary,
        "items": [{**case, "answers": {arm: selected.get((case["id"], arm))
                                        for arm in ("pool", "jev")}} for case in cases],
        "all_attempts": rows,
    }
    for name, value in (("summary.json", summary), ("review-packet-attestation.json", packet)):
        (out / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run", "report"))
    parser.add_argument("--out", type=Path, default=Path("experiments/.bench-jev-20260930"))
    args = parser.parse_args()
    if args.action == "run":
        asyncio.run(run(args.out))
    elif args.action == "report":
        print(json.dumps(report(args.out), indent=2))
    else:
        manifest = prepare(args.out)
        print(f"Frozen {len(manifest['design']['cases'])} cases: {manifest['fingerprint']}")


if __name__ == "__main__":
    main()
