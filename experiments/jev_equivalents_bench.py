"""Jev as a check on the Serbian equivalents the reverse lookup offers.

`extract` collects every distinct Serbian equivalent the recorded reverse runs produced,
one per Russian word and spelling; a fresh reviewer labels them in `labels.json` without
seeing a score; `run` asks Jev two questions about each (always resumes); `report`
compares the scores with the labels. Only `run` spends money, Jev's own: no pool quota.

    uv run python experiments/jev_equivalents_bench.py extract --out experiments/.bench-jev-equivalents
    uv run python experiments/jev_equivalents_bench.py run --out experiments/.bench-jev-equivalents
    uv run python experiments/jev_equivalents_bench.py report --out experiments/.bench-jev-equivalents
"""

import argparse
import asyncio
import json
import math
import time
from pathlib import Path

import httpx
import one_note_bench as bench
from backend_bench import load_keys

from echo_words.languages import fold_for_match
from echo_words.prompt import parse_reverse

MODEL = "jev-1.13.0"
ENDPOINT = "https://api.typesafe.ai/v1/systemone"
PRICE_PER_MILLION = 0.042
RUNS = (
    ".bench-reverse",
    ".bench-reverse-latin-b",
    ".bench-reverse-latin-c",
    ".bench-reverse-latin2-a",
    ".bench-reverse-latin2-b",
    ".bench-reverse-latin2-c",
)
QUESTIONS = {
    "serbian": {
        "type": "noul",
        "instructions": (
            "Is serbian_wording a real word or fixed expression of Serbian as its speakers "
            "actually use it, in any register? Croatian, Bosnian and ijekavian forms count as "
            "Serbian, in either alphabet. A Russian word Serbian does not use, a misspelling, or "
            "a coinage nobody says is not."
        ),
    },
    "equivalent": {
        "type": "noul",
        "instructions": (
            "In the sense example_sentence uses it, does serbian_wording translate "
            "russian_wording, in a meaning russian_wording really has?"
        ),
    },
}


def extract(out: Path) -> list[dict]:
    serbian = bench.LANGUAGES["sr"]
    pairs: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for run in RUNS:
        for line in (Path(__file__).parent / run / "answers.jsonl").read_text().splitlines():
            row = json.loads(line)
            if row["lang"] != "sr" or row["kind"] != bench.REVERSE_KIND or not row["text"]:
                continue
            answer = parse_reverse(row["text"], serbian, bench.TARGET_NAME)
            if answer is None or answer.verdict != "word":
                continue
            for position, equivalent in enumerate(answer.equivalents):
                key = (row["source"], fold_for_match(equivalent.word, serbian))
                if key in seen:
                    continue
                seen.add(key)
                pairs.append(
                    {
                        "id": f"p{len(pairs):03d}",
                        "russian": row["source"],
                        "read_as": answer.read_as,
                        "serbian": equivalent.word,
                        "example": equivalent.example,
                        "first": position == 0,
                        "model": row["answered_by"],
                        "run": run,
                    },
                )
    out.mkdir(parents=True, exist_ok=True)
    (out / "pairs.json").write_text(json.dumps(pairs, ensure_ascii=False, indent=1) + "\n")
    return pairs


def jev_request(pair: dict) -> dict:
    return {
        "model": MODEL,
        "questions": QUESTIONS,
        "state": {
            "russian_wording": pair["russian"],
            "serbian_wording": pair["serbian"],
            "example_sentence": pair["example"],
        },
    }


async def run(out: Path) -> None:
    pairs = json.loads((out / "pairs.json").read_text())
    path = out / "jev.jsonl"
    done = {json.loads(line)["id"] for line in path.read_text().splitlines()} if path.exists() else set()
    key = load_keys().get("TYPESAFE_API_KEY", "")
    if not key:
        raise ValueError("TYPESAFE_API_KEY is absent")
    async with httpx.AsyncClient(headers={"Authorization": f"Bearer {key}"}, timeout=30) as client:
        for pair in pairs:
            if pair["id"] in done:
                continue
            started = time.monotonic()
            row: dict = {"id": pair["id"], "error": None}
            try:
                response = await client.post(ENDPOINT, json=jev_request(pair))
                row["status"] = response.status_code
                response.raise_for_status()
                body = response.json()
                answers = {name: body["answers"][name]["noul"] for name in QUESTIONS}
                if not all(isinstance(v, int | float) and math.isfinite(v) and 0 <= v <= 1 for v in answers.values()):
                    raise ValueError("Invalid Noul")
                row.update(answers=answers, usage=body.get("usage"), model=body.get("model"))
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                # Exception messages can contain request material; only the class is evidence.
                row["error"] = type(exc).__name__
            row["seconds"] = time.monotonic() - started
            with path.open("a") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            if row["error"]:
                raise RuntimeError(f"Jev failed on {pair['id']}; inspect and resume")
            await asyncio.sleep(0.5)


def _split(ids: list[str], dropped, bad) -> dict:
    return {
        "bad": sum(bad(i) for i in ids),
        "bad_dropped": sum(bad(i) and dropped(i) for i in ids),
        "good": sum(not bad(i) for i in ids),
        "good_dropped": sum(not bad(i) and dropped(i) for i in ids),
    }


def report(out: Path, threshold: float) -> dict:
    pairs = {pair["id"]: pair for pair in json.loads((out / "pairs.json").read_text())}
    labels = {label["id"]: label for label in json.loads((out / "labels.json").read_text())}
    scores = {row["id"]: row for row in map(json.loads, (out / "jev.jsonl").read_text().splitlines())}
    ids = [i for i in pairs if i in labels and i in scores and scores[i].get("answers")]

    def dropped(i: str) -> bool:
        return min(scores[i]["answers"].values()) < threshold

    def bad(i: str) -> bool:
        return not labels[i]["keep"]

    seconds = sorted(scores[i]["seconds"] for i in ids)
    tokens = sum((scores[i].get("usage") or {}).get("input_tokens", 0) for i in ids)
    summary = {
        "threshold": threshold,
        "labelled_and_scored": len(ids),
        "all": _split(ids, dropped, bad),
        "first_equivalents": _split([i for i in ids if pairs[i]["first"]], dropped, bad),
        "chips": _split([i for i in ids if not pairs[i]["first"]], dropped, bad),
        "russian_passed_as_serbian": sum(bool(labels[i]["russian"]) for i in ids),
        "median_seconds": seconds[len(seconds) // 2] if seconds else None,
        "input_tokens": tokens,
        "estimated_usd": tokens * PRICE_PER_MILLION / 1_000_000,
        "good_dropped": [
            f"{pairs[i]['russian']} -> {pairs[i]['serbian']}" for i in ids if not bad(i) and dropped(i)
        ],
        "bad_kept": [
            f"{pairs[i]['russian']} -> {pairs[i]['serbian']}" for i in ids if bad(i) and not dropped(i)
        ],
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("extract", "run", "report"))
    parser.add_argument("--out", type=Path, default=Path("experiments/.bench-jev-equivalents"))
    parser.add_argument("--threshold", type=float, default=0.5)
    args = parser.parse_args()
    if args.action == "extract":
        print(f"{len(extract(args.out))} pairs")
    elif args.action == "run":
        asyncio.run(run(args.out))
    else:
        print(json.dumps(report(args.out, args.threshold), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
