"""Serbian typed in Cyrillic, asked as typed and transliterated into Latin.

Every Serbian fixture of the full tier that carries a Cyrillic letter, and the four
Russian words the Serbian tab meets, is asked twice in a row, once as typed and once in
Latin letters, alternating which goes first, so one pool at one moment answers both. The
second judgements those answers happen to need follow. Both arms spend live pool quota.

    uv run python experiments/serbian_input_bench.py run --out experiments/.bench-sr-input
    uv run python experiments/serbian_input_bench.py report --out experiments/.bench-sr-input

`run` always resumes, and stops after three answerless calls in a row: an exhausted pool.
"""

import argparse
import asyncio
import json
import os
import re
import unicodedata
from collections import Counter
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import one_note_bench as bench
from llmbroker import AsyncBroker
from reverse_items import OFFER_WORDS

from echo_words.languages import _SERBIAN_LATIN

ARMS = ("typed", "latin")
_CYRILLIC = re.compile("[Ѐ-ӿ]")
_LATIN = re.compile(r"[a-zčćđšž]", re.IGNORECASE)
_TAG = re.compile(r"<[^>]*>")


def serbian_latin(text: str) -> str:
    """Serbian Cyrillic in Latin letters with its capitals kept; every other character as is."""
    normalized = unicodedata.normalize("NFC", text)
    written = []
    for index, char in enumerate(normalized):
        latin = _SERBIAN_LATIN.get(char.casefold())
        if latin is None or char.islower():
            written.append(latin or char)
        elif len(latin) > 1 and _in_capitals(normalized, index):
            written.append(latin.upper())
        else:
            written.append(latin.capitalize())
    return "".join(written)


def _in_capitals(text: str, index: int) -> bool:
    # Љ is Lj at the head of a word and LJ inside one written all in capitals.
    after = text[index + 1 : index + 2]
    before = text[index - 1 : index] if index else ""
    return after.isupper() if after.isalpha() else before.isupper()


def typed_jobs() -> list[bench.Shot]:
    serbian = [
        shot
        for shot in bench.initial_jobs_for_tier("full")
        if shot.lang == "sr" and _CYRILLIC.search(shot.source + shot.context)
    ]
    return [*serbian, *bench.offer_shots()]


def jobs(arm: str) -> list[bench.Shot]:
    typed = typed_jobs()
    if arm == "typed":
        return typed
    return [
        replace(shot, source=serbian_latin(shot.source), context=serbian_latin(shot.context))
        for shot in typed
    ]


def answers(out: Path, arm: str, wanted: list[bench.Shot]) -> dict[str, bench.Shot]:
    return bench._select_canonical(bench.read_attempts(out / arm), {s.shot_id: s for s in wanted})


def second_judgements(out: Path, arm: str) -> list[bench.Shot]:
    rows = answers(out, arm, jobs(arm))
    return [*bench.correction_shots(rows), *bench.offer_correction_shots(rows)]


async def ask_in_pairs(args, out: Path, broker: AsyncBroker, wanted: dict[str, list]) -> None:
    todo = {
        arm: {s.shot_id: s for s in bench.pending(wanted[arm], answers(out, arm, wanted[arm]), True)}
        for arm in ARMS
    }
    order = list(dict.fromkeys(shot.shot_id for arm in ARMS for shot in wanted[arm]))
    silent = 0
    for index, shot_id in enumerate(order):
        for arm in ARMS if index % 2 == 0 else ARMS[::-1]:
            shot = todo[arm].get(shot_id)
            if shot is None:
                continue
            await bench.run_batch(args, out / arm, broker, [shot])
            silent = silent + 1 if shot.error or not shot.text else 0
            if silent >= 3:
                raise RuntimeError("three answerless calls in a row: the pool is exhausted; resume later")


async def run(out: Path) -> None:
    bench.assert_no_prompt_drift()
    os.environ.update(bench.load_keys())
    args = SimpleNamespace(concurrency=1, pace=2.0, wait=180.0, paid="")
    broker = AsyncBroker(home=out / "llmbroker")
    try:
        await ask_in_pairs(args, out, broker, {arm: jobs(arm) for arm in ARMS})
        await ask_in_pairs(args, out, broker, {arm: second_judgements(out, arm) for arm in ARMS})
    finally:
        await broker.aclose()


def _scripts(texts: list[str]) -> dict[str, int]:
    texts = [_TAG.sub("", text) for text in texts]
    counted = Counter(
        "mixed" if _CYRILLIC.search(text) and _LATIN.search(text)
        else "cyrillic" if _CYRILLIC.search(text)
        else "latin"
        for text in texts
        if text
    )
    return dict(counted)


def _summary(shot: bench.Shot | None) -> dict | None:
    if shot is None:
        return None
    payload = shot.payload or {}
    examples = [
        str(example.get("highlighted") or example.get("text") or "")
        for meaning in payload.get("meanings") or []
        if isinstance(meaning, dict)
        for example in meaning.get("examples") or []
        if isinstance(example, dict)
    ]
    return {
        "answered_by": shot.answered_by,
        "error": shot.error,
        "seconds": shot.t_total,
        "complete": bench.complete(shot),
        "judgement_refused": bench.judgement_refused(shot) if shot.kind in bench.JUDGEMENT_KINDS else None,
        "word": payload.get("word"),
        "word_relation": shot.metrics.get("word_relation"),
        "verdict_correct": shot.metrics.get("verdict_correct"),
        "format_ok": shot.metrics.get("format_ok"),
        "card_fronts": shot.metrics.get("card_fronts"),
        "example_scripts": _scripts(examples),
        "text": shot.text,
    }


def report(out: Path) -> dict:
    typed = typed_jobs()
    rows = {}
    for arm in ARMS:
        wanted = jobs(arm)
        arm_rows = answers(out, arm, wanted)
        corrections = second_judgements(out, arm)
        arm_rows.update(answers(out, arm, corrections))
        rows[arm] = arm_rows
    ids = [shot.shot_id for shot in typed]
    second_ids = sorted({sid for arm in ARMS for sid in rows[arm] if sid not in ids})
    items = [
        {
            "id": shot_id,
            "kind": (rows["typed"].get(shot_id) or rows["latin"].get(shot_id)).kind
            if (rows["typed"].get(shot_id) or rows["latin"].get(shot_id))
            else None,
            "input": {arm: (rows[arm][shot_id].source if shot_id in rows[arm] else None) for arm in ARMS},
            "context": {arm: (rows[arm][shot_id].context if shot_id in rows[arm] else None) for arm in ARMS},
            "answers": {arm: _summary(rows[arm].get(shot_id)) for arm in ARMS},
        }
        for shot_id in [*ids, *second_ids]
    ]
    summary = {
        "semantic_review_required": True,
        "fixtures": len(typed),
        "arms": {
            arm: {
                "answered": sum(1 for sid in ids if sid in rows[arm] and rows[arm][sid].text),
                "complete": sum(1 for sid in ids if sid in rows[arm] and bench.complete(rows[arm][sid])),
                "models": dict(Counter(rows[arm][sid].answered_by for sid in ids if sid in rows[arm])),
                "verdict_correct": sum(
                    bool(rows[arm][sid].metrics.get("verdict_correct"))
                    for sid in ids
                    if sid in rows[arm] and rows[arm][sid].kind == "verdict"
                ),
                "verdicts": sum(1 for sid in ids if sid in rows[arm] and rows[arm][sid].kind == "verdict"),
                "judgements_refused": sorted(
                    rows[arm][sid].source
                    for sid in ids
                    if sid in rows[arm]
                    and rows[arm][sid].kind in bench.JUDGEMENT_KINDS
                    and bench.judgement_refused(rows[arm][sid])
                ),
                "offer_outcomes": {
                    word: bench.offer_outcome(rows[arm], slug) for slug, word in OFFER_WORDS
                },
                "example_scripts": dict(
                    sum(
                        (Counter((_summary(rows[arm][sid]) or {}).get("example_scripts") or {})
                         for sid in ids if sid in rows[arm]),
                        Counter(),
                    ),
                ),
                "second_judgements": len([sid for sid in second_ids if sid in rows[arm]]),
            }
            for arm in ARMS
        },
    }
    packet = {"summary": summary, "items": items}
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    (out / "review-packet-serbian-input.json").write_text(
        json.dumps(packet, indent=2, ensure_ascii=False) + "\n",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "report", "plan"))
    parser.add_argument("--out", type=Path, default=Path("experiments/.bench-sr-input"))
    args = parser.parse_args()
    if args.action == "run":
        asyncio.run(run(args.out))
    elif args.action == "report":
        print(json.dumps(report(args.out), indent=2, ensure_ascii=False))
    else:
        for typed, latin in zip(jobs("typed"), jobs("latin"), strict=True):
            print(f"{typed.shot_id:42} {typed.source!r:40} {latin.source!r}")


if __name__ == "__main__":
    main()
