"""Input typed without "!": does the learner mean a reverse lookup?

Every reading fixture is asked of the free pool with the production reading prompt and
the attestation the app asks beside it of a single word, and of Jev as one yes/no
question. The app reverses a single word only when the reading says target with no
source wording named and the attestation finds it unused in the tab's language, and
more than one word on the reading alone. `run` always
resumes; `report` writes the review packet. The pool arm spends pool quota, the Jev arm
Jev's own money.

    uv run python experiments/reading_bench.py run --out experiments/.bench-reading
    uv run python experiments/reading_bench.py report --out experiments/.bench-reading
"""

import argparse
import asyncio
import json
import os
import time
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import httpx
import one_note_bench as bench
from llmbroker import AsyncBroker
from reverse_items import READING_CASES

MODEL = "jev-1.13.0"
ENDPOINT = "https://api.typesafe.ai/v1/systemone"
PRICE_PER_MILLION = 0.042
THRESHOLDS = (0.5, 0.9)
QUESTION = {
    "target": {
        "type": "noul",
        "instructions": (
            "A learner_language speaker learning box_language typed `typed` into the box for "
            "box_language wording; to look up learner_language wording they put \"!\" before "
            "it, and this input has none. Is `typed` plainly learner_language wording typed "
            "here by mistake, one that cannot reasonably be read as box_language, as any form "
            "of box_language wording, or as a misspelling of it? Wording box_language also "
            "uses, or that the two languages share, is not."
        ),
    },
}


def jev_request(shot: bench.Shot) -> dict:
    return {
        "model": MODEL,
        "questions": QUESTION,
        "state": {
            "box_language": bench.LANGUAGES[shot.lang].name,
            "learner_language": bench.READING_BY_ID[shot.shot_id].target,
            "typed": shot.source,
        },
    }


def attestation_shots() -> list[bench.Shot]:
    # Production asks the judgement of a single typed word only.
    return [
        bench.Shot(f"attestation-{shot.shot_id}", "attestation", shot.lang, shot.source)
        for shot in bench.reading_shots()
        if len(bench.split_words(shot.source)) == 1
    ]


def pool_answers(out: Path) -> dict[str, bench.Shot]:
    jobs = {shot.shot_id: shot for shot in (*bench.reading_shots(), *attestation_shots())}
    return bench._select_canonical(bench.read_attempts(out / "pool"), jobs)


def reverses(pool: dict[str, bench.Shot], shot_id: str) -> bool | None:
    """Whether the app would reverse: the reading and the attestation agree, or None unasked."""
    reading = pool.get(shot_id)
    if reading is None or not reading.metrics.get("reading"):
        return None
    says_target = reading.metrics.get("reading") == "target"
    if len(bench.split_words(reading.source)) > 1:
        return says_target
    attestation = pool.get(f"attestation-{shot_id}")
    if attestation is None or not bench.complete(attestation):
        return None
    named = str(reading.payload.get("as_source") or "").strip()
    return says_target and not named and bench.judgement_refused(attestation)


def jev_answers(out: Path) -> dict[str, dict]:
    path = out / "jev.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    return {row["id"]: row for row in rows if row.get("probability") is not None}


async def ask_jev(out: Path) -> None:
    key = bench.load_keys().get("TYPESAFE_API_KEY", "")
    if not key:
        raise ValueError("TYPESAFE_API_KEY is absent")
    done = jev_answers(out)
    async with httpx.AsyncClient(headers={"Authorization": f"Bearer {key}"}, timeout=30) as client:
        for shot in bench.reading_shots():
            if shot.shot_id in done:
                continue
            started = time.monotonic()
            row: dict = {"id": shot.shot_id, "probability": None, "error": None}
            try:
                response = await client.post(ENDPOINT, json=jev_request(shot))
                response.raise_for_status()
                body = response.json()
                row.update(probability=float(body["answers"]["target"]["noul"]), usage=body.get("usage"))
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                # Exception messages can contain request material; only the class is evidence.
                row["error"] = type(exc).__name__
            row["seconds"] = time.monotonic() - started
            with (out / "jev.jsonl").open("a") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            if row["error"]:
                raise RuntimeError(f"Jev failed on {shot.shot_id}; inspect and resume")
            await asyncio.sleep(0.5)


async def run(out: Path) -> None:
    os.environ.update(bench.load_keys())
    args = SimpleNamespace(concurrency=1, pace=2.0, wait=180.0, paid="")
    broker = AsyncBroker(home=out / "llmbroker")
    try:
        todo = bench.pending([*bench.reading_shots(), *attestation_shots()], pool_answers(out), True)
        await bench.run_batch(args, out / "pool", broker, todo)
    finally:
        await broker.aclose()
    await ask_jev(out)


def _counts(expected: dict[str, str], reversed_: dict[str, bool]) -> dict:
    asked = [sid for sid in expected if sid in reversed_]
    return {
        "answered": len(asked),
        "reversed_own_wording": sorted(sid for sid in asked if expected[sid] == "not" and reversed_[sid]),
        "own_wording": sum(expected[sid] == "not" for sid in asked),
        "reversed_russian": sum(expected[sid] == "target" and reversed_[sid] for sid in asked),
        "russian": sum(expected[sid] == "target" for sid in asked),
        "missed_russian": sorted(sid for sid in asked if expected[sid] == "target" and not reversed_[sid]),
        "open_cases_reversed": sorted(sid for sid in asked if expected[sid] == "either" and reversed_[sid]),
    }


def report(out: Path) -> dict:
    cases = {bench.reading_id(case): case for case in READING_CASES}
    expected = {sid: case.expected for sid, case in cases.items()}
    pool = pool_answers(out)
    jev = jev_answers(out)
    pool_readings = {sid: pool[sid].metrics.get("reading") for sid in cases if sid in pool}
    agreed = {sid: decision for sid in cases if (decision := reverses(pool, sid)) is not None}
    summary = {
        "semantic_review_required": True,
        "pool": {
            **_counts(expected, {sid: r == "target" for sid, r in pool_readings.items() if r}),
            "unreadable": sorted(sid for sid, r in pool_readings.items() if not r),
            "models": dict(Counter(pool[sid].answered_by or "none" for sid in pool_readings)),
            "errors": sorted(sid for sid in pool_readings if pool[sid].error),
        },
        "reading_and_attestation": _counts(expected, agreed),
        "jev": {
            str(threshold): _counts(expected, {sid: row["probability"] >= threshold for sid, row in jev.items()})
            for threshold in THRESHOLDS
        },
        "jev_estimated_usd": sum((row.get("usage") or {}).get("input_tokens", 0) for row in jev.values())
        * PRICE_PER_MILLION / 1_000_000,
    }
    items = [
        {
            "id": sid,
            "tab": bench.LANGUAGES[case.lang].name,
            "target": case.target,
            "typed": case.word,
            "expected": case.expected,
            "note": case.note,
            "pool": {
                "reading": pool_readings.get(sid),
                "answered_by": pool[sid].answered_by if sid in pool else None,
                "text": pool[sid].text if sid in pool else None,
            },
            "attestation": pool[f"attestation-{sid}"].text if f"attestation-{sid}" in pool else None,
            "app_reverses": agreed.get(sid),
            "jev_probability": jev[sid]["probability"] if sid in jev else None,
        }
        for sid, case in cases.items()
    ]
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    (out / "review-packet-reading.json").write_text(
        json.dumps({"summary": summary, "items": items}, indent=2, ensure_ascii=False) + "\n",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "report"))
    parser.add_argument("--out", type=Path, default=Path("experiments/.bench-reading"))
    args = parser.parse_args()
    if args.action == "run":
        asyncio.run(run(args.out))
    else:
        print(json.dumps(report(args.out), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
