"""Typed input: does the answer name the language it is really written in?

Every language fixture is asked of the free pool with the production prompt for typed
input, which carries the language line; `run` always resumes, `report` writes the review
packet. The rest of the answer is measured by the ordinary tiers of one_note_bench.py,
which ask every typed fixture with the same line.

    uv run python experiments/language_bench.py run --out experiments/.bench-language-a
    uv run python experiments/language_bench.py report --out experiments/.bench-language-a
"""

import argparse
import asyncio
import json
import os
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import one_note_bench as bench
from language_items import LANGUAGE_CASES
from llmbroker import AsyncBroker


def answers(out: Path) -> dict[str, bench.Shot]:
    jobs = {shot.shot_id: shot for shot in bench.language_shots()}
    return bench._select_canonical(bench.read_attempts(out), jobs)


async def run(out: Path) -> None:
    bench.assert_no_prompt_drift()
    os.environ.update(bench.load_keys())
    args = SimpleNamespace(concurrency=1, pace=2.0, wait=180.0, paid="")
    broker = AsyncBroker(home=out / "llmbroker")
    try:
        await bench.run_batch(args, out, broker, bench.pending(bench.language_shots(), answers(out), True))
    finally:
        await broker.aclose()


def report(out: Path) -> dict:
    rows = answers(out)
    cases = {bench.language_id(case): case for case in LANGUAGE_CASES}
    named = {sid: rows[sid].metrics.get("submission_language") for sid in cases if sid in rows and bench.complete(rows[sid])}

    def ids(expected: str | None = None, *, other: bool = False) -> list[str]:
        return [
            sid
            for sid in named
            if (cases[sid].expected not in {"source", "target", "either"} if other else cases[sid].expected == expected)
        ]

    source, target, other = ids("source"), ids("target"), ids(other=True)
    summary = {
        "semantic_review_required": True,
        "answered": len(named),
        "unanswered": sorted(sid for sid in cases if sid not in named),
        "models": dict(Counter(rows[sid].answered_by or "none" for sid in named)),
        "tab_language_named_another": sorted(f"{sid}: {named[sid]}" for sid in source if named[sid] != "source"),
        "tab_language": len(source),
        "learner_language_caught": sum(named[sid] == "target" for sid in target),
        "learner_language": len(target),
        "learner_language_missed": sorted(f"{sid}: {named[sid]}" for sid in target if named[sid] != "target"),
        "other_language_named_right": sum(named[sid] == cases[sid].expected for sid in other),
        "other_language": len(other),
        "other_language_wrong": sorted(
            f"{sid}: {named[sid]} (expected {cases[sid].expected})" for sid in other if named[sid] != cases[sid].expected
        ),
        "open_cases": sorted(f"{sid}: {named[sid]}" for sid in ids("either")),
    }
    items = [
        {
            "id": sid,
            "tab": bench.LANGUAGES[case.lang].name,
            "target": case.target,
            "typed": case.text,
            "expected": case.expected,
            "note": case.note,
            "named": rows[sid].metrics.get("named") if sid in rows else None,
            "read_as": named.get(sid),
            "answered_by": rows[sid].answered_by if sid in rows else None,
            "answer": rows[sid].text if sid in rows else None,
        }
        for sid, case in cases.items()
    ]
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    (out / "review-packet-language.json").write_text(
        json.dumps({"summary": summary, "items": items}, indent=2, ensure_ascii=False) + "\n",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "report"))
    parser.add_argument("--out", type=Path, default=Path("experiments/.bench-language-a"))
    args = parser.parse_args()
    if args.action == "run":
        asyncio.run(run(args.out))
    else:
        print(json.dumps(report(args.out), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
