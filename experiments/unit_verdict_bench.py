"""Gate the merged prompt's unit verdict against real pooled LLM answers.

The gate was registered before the first run:

* zero non-units may be flagged as units;
* zero articles may contradict their JSON verdict;
* zero analyse-text answers may contain ``context_sense``;
* at least 95% of true units must either be carded directly or be recoverable
  as the first chip;
* every fixture must have a parseable verdict before a variant can pass.

The first condition is deliberately absolute: that error automatically writes a
clause to Anki. A false negative costs one tap, so its path has a separate floor
matching the previously measured 28-of-29 recovery rate without pretending the
two directions cost the same.

Outside the package and CI: ``run`` calls the real llmbroker free pool. Answers
are append-only JSONL so scoring and gate changes can be replayed without another
call.

Run:
    uv run python experiments/unit_verdict_bench.py run --variant v1 --suite gate
    uv run python experiments/unit_verdict_bench.py report --variant v1
"""

import argparse
import asyncio
import json
import re
import statistics
import sys
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import unit_verdict_prompts  # noqa: E402
from backend_bench import (  # noqa: E402
    LANGS,
    TARGETS,
    Pacer,
    drain,
    load_keys,
    log,
    parse_json_object,
    split_answer,
)
from bench_items import SENTENCES  # noqa: E402
from extract_items import CLAUSES, CONTROLS, FRAGMENTS, INFLECTED, UNITS  # noqa: E402
from llmbroker import AsyncBroker  # noqa: E402


DANGEROUS_MAX = 0
ARTICLE_MISMATCH_MAX = 0
CONTEXT_LEAK_MAX = 0
UNIT_PATH_MIN = 0.95
CARD_DELIMITER = "===CARD==="
_BOLD_START = re.compile(r"^<b>[^<]+</b>")


@dataclass(frozen=True)
class Fixture:
    fixture_id: str
    klass: str
    lang: str
    text: str
    expected_unit: bool
    accepted: tuple[str, ...]


@dataclass
class Shot:
    variant: str
    fixture_id: str
    klass: str
    lang: str
    word: str
    expected_unit: bool
    accepted: list[str]
    prompt_hash: str
    answered_by: str | None = None
    t_first: float | None = None
    t_total: float | None = None
    error: str | None = None
    text: str = ""
    metrics: dict = field(default_factory=dict)


def normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", str(value)).casefold().split()).strip(
        " .,;:!?…",
    )


def _fixture_rows() -> list[Fixture]:
    fixtures: list[Fixture] = []
    sources = (
        ("units", UNITS, True),
        ("inflected", INFLECTED, True),
        ("controls", CONTROLS, True),
        ("fragments", FRAGMENTS, False),
        ("clauses", CLAUSES, False),
    )
    for klass, source, expected in sources:
        for lang, rows in source.items():
            for index, (text, accepted) in enumerate(rows):
                fixtures.append(
                    Fixture(f"{klass}:{lang}:{index}", klass, lang, text, expected, accepted),
                )
    for lang, rows in SENTENCES.items():
        for index, (text, expected, kind) in enumerate(rows):
            accepted = tuple(value for group in expected for value in group)
            fixtures.append(
                Fixture(f"sentences-{kind}:{lang}:{index}", f"sentences-{kind}", lang, text, False, accepted),
            )
    return fixtures


FIXTURES = _fixture_rows()
CHARACTERISTIC_IDS = {
    "units:de:0",  # Rad fahren
    "inflected:de:0",  # fährt Rad
    "fragments:de:0",  # ist allein im Restaurant
    "clauses:de:1",  # Es regnet
    "sentences-split:de:0",  # Er steht ... auf.
    "sentences-split:sr:0",  # Он се ... вратио ...
}
REGRESSION_IDS = CHARACTERISTIC_IDS | {
    "units:sr:9",  # на крају крајева
    "inflected:de:2",  # steht zur Verfügung
    "inflected:sr:0",  # возим бицикл
    "inflected:sr:1",  # донео одлуку
    "inflected:sr:6",  # ide pešice
    "fragments:de:7",  # völlig durcheinander gebracht
    "fragments:de:9",  # wirkt ziemlich verschlossen
}


def selected_fixtures(suite: str, langs: list[str], limit: int) -> list[Fixture]:
    picked = [fixture for fixture in FIXTURES if fixture.lang in langs]
    if suite == "characteristic":
        picked = [fixture for fixture in picked if fixture.fixture_id in CHARACTERISTIC_IDS]
    elif suite == "regression":
        picked = [fixture for fixture in picked if fixture.fixture_id in REGRESSION_IDS]
    if limit:
        by_class: dict[str, list[Fixture]] = {}
        for fixture in picked:
            by_class.setdefault(fixture.klass, []).append(fixture)
        picked = [fixture for group in by_class.values() for fixture in group[:limit]]
    return picked


def build_prompt(variant: str, fixture: Fixture, target: str) -> str:
    source_lang, hints = LANGS[fixture.lang]
    request = f'analyse this text. Submitted text: "{fixture.text}"'
    return unit_verdict_prompts.build(variant).format(
        source_lang=source_lang,
        target_lang=TARGETS[target][0],
        source_hints=hints,
        request=request,
    )


def _segment_labels(payload: dict | None) -> list[str]:
    raw = (payload or {}).get("segments")
    if not isinstance(raw, list):
        return []
    return [
        str(segment.get("label", "")).strip()
        for segment in raw
        if isinstance(segment, dict) and str(segment.get("label", "")).strip()
    ]


def score(shot: Shot) -> Shot:
    analysis, raw_payload = split_answer(shot.text)
    payload, parse_error = parse_json_object(raw_payload)
    verdict = (payload or {}).get("unit")
    verdict_valid = isinstance(verdict, bool)
    labels = _segment_labels(payload)
    accepted = {normalize(value) for value in shot.accepted}
    recovered_first = bool(labels) and normalize(labels[0]) in accepted
    article_unit = bool(_BOLD_START.match(analysis.strip()))
    shot.metrics = {
        "answered": bool(shot.text) and not shot.error,
        "delimiter": CARD_DELIMITER in shot.text,
        "parse_error": parse_error,
        "verdict": verdict if verdict_valid else None,
        "verdict_valid": verdict_valid,
        "dangerous": not shot.expected_unit and verdict is True,
        "false_negative": shot.expected_unit and verdict is False,
        "segments": labels,
        "recovered_first": recovered_first,
        "unit_path": verdict is True or (verdict is False and recovered_first),
        "article_unit": article_unit,
        "article_matches": verdict_valid and article_unit is verdict,
        "context_sense_leak": bool(payload) and "context_sense" in payload,
        "word": str((payload or {}).get("word", "")).strip(),
        "meanings": len((payload or {}).get("meanings", []))
        if isinstance((payload or {}).get("meanings"), list)
        else -1,
    }
    return shot


def output_path(out: Path) -> Path:
    return out / "verdict.jsonl"


def append(path: Path, shot: Shot) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(shot), ensure_ascii=False) + "\n")


def read_shots(out: Path) -> list[Shot]:
    path = output_path(out)
    if not path.exists():
        return []
    latest: dict[tuple[str, str], Shot] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            shot = score(Shot(**json.loads(line)))
            latest[(shot.variant, shot.fixture_id)] = shot
    return list(latest.values())


async def run(args, out: Path) -> None:
    import os

    os.environ.update(load_keys())
    recorded = read_shots(out)
    completed = {
        (shot.variant, shot.fixture_id)
        for shot in recorded
        if shot.metrics.get("verdict_valid") and shot.prompt_hash == unit_verdict_prompts.fingerprint(shot.variant)
    }
    fixtures = selected_fixtures(args.suite, args.lang, args.limit)
    jobs = [
        (variant, fixture)
        for variant in args.variant
        for fixture in fixtures
        if not args.resume or (variant, fixture.fixture_id) not in completed
    ]
    log(f"{len(jobs)} calls ({len(fixtures)} fixtures x {len(args.variant)} variants)")
    broker = AsyncBroker(home=out / "llmbroker")
    gate = asyncio.Semaphore(args.concurrency)
    pacer = Pacer(args.pace)

    async def one(variant: str, fixture: Fixture) -> None:
        shot = Shot(
            variant=variant,
            fixture_id=fixture.fixture_id,
            klass=fixture.klass,
            lang=fixture.lang,
            word=fixture.text,
            expected_unit=fixture.expected_unit,
            accepted=list(fixture.accepted),
            prompt_hash=unit_verdict_prompts.fingerprint(variant),
        )
        await pacer.wait()
        async with gate:
            handle = broker.stream(
                build_prompt(variant, fixture, args.target),
                operation=f"unit-verdict-{variant}-{fixture.lang}",
                wait=args.wait,
            )
            try:
                await drain(handle, shot)
                shot.answered_by = handle.llm_name
            except Exception as exc:  # noqa: BLE001 - provider failure is benchmark data
                shot.error = f"{type(exc).__name__}: {exc}"
                shot.answered_by = handle.llm_name
            finally:
                await handle.aclose()
        score(shot)
        append(output_path(out), shot)
        verdict = shot.metrics.get("verdict")
        log(
            f"{variant} {fixture.klass:16} {fixture.lang} {fixture.text!r} -> "
            f"{verdict!r} by {shot.answered_by or '?'} in {shot.t_total}s {shot.error or ''}",
        )

    try:
        await asyncio.gather(*(one(*job) for job in jobs))
    finally:
        await broker.aclose()


def pct(part: int, whole: int) -> str:
    return f"{part / whole:.1%}" if whole else "-"


def report_variant(shots: list[Shot], variant: str, expected_ids: set[str]) -> bool:
    rows = [shot for shot in shots if shot.variant == variant]
    usable = [shot for shot in rows if shot.metrics.get("verdict_valid")]
    nonunits = [shot for shot in usable if not shot.expected_unit]
    units = [shot for shot in usable if shot.expected_unit]
    dangerous = [shot for shot in nonunits if shot.metrics["dangerous"]]
    article_mismatch = [shot for shot in usable if not shot.metrics["article_matches"]]
    leaks = [shot for shot in usable if shot.metrics["context_sense_leak"]]
    unit_path = [shot for shot in units if shot.metrics["unit_path"]]
    missing = expected_ids - {shot.fixture_id for shot in usable}
    path_share = len(unit_path) / len(units) if units else 0.0
    passed = (
        not missing
        and len(dangerous) <= DANGEROUS_MAX
        and len(article_mismatch) <= ARTICLE_MISMATCH_MAX
        and len(leaks) <= CONTEXT_LEAK_MAX
        and path_share >= UNIT_PATH_MIN
    )
    print(f"{variant} — {unit_verdict_prompts.VARIANTS[variant][0]}")
    print(f"  usable verdicts       {len(usable)}/{len(expected_ids)}")
    print(f"  dangerous false units {len(dangerous)}/{len(nonunits)}")
    print(f"  false negatives       {sum(s.metrics['false_negative'] for s in units)}/{len(units)}")
    print(f"  direct-or-first-chip  {len(unit_path)}/{len(units)} ({pct(len(unit_path), len(units))})")
    print(f"  article mismatches    {len(article_mismatch)}/{len(usable)}")
    print(f"  context_sense leaks   {len(leaks)}/{len(usable)}")
    times = [shot.t_total for shot in usable if shot.t_total is not None]
    if times:
        print(f"  latency p50           {statistics.median(times):.1f}s")
    print(f"  GATE                   {'PASS' if passed else 'FAIL'}")
    for heading, failures in (
        ("DANGEROUS", dangerous),
        ("ARTICLE", article_mismatch),
        ("CONTEXT", leaks),
    ):
        for shot in failures:
            print(f"    {heading} {shot.lang} [{shot.klass}] {shot.word!r}")
    for fixture_id in sorted(missing):
        print(f"    MISSING {fixture_id}")
    return passed


def report(args, out: Path) -> None:
    shots = read_shots(out)
    fixtures = selected_fixtures(args.suite, args.lang, args.limit)
    expected_ids = {fixture.fixture_id for fixture in fixtures}
    if not shots:
        raise SystemExit(f"no answers in {output_path(out)}")
    results = [report_variant(shots, variant, expected_ids) for variant in args.variant]
    if not all(results):
        raise SystemExit(1)


def show(args, out: Path) -> None:
    shots = read_shots(out)
    needles = [normalize(value) for value in args.text]
    rows = [
        shot
        for shot in shots
        if shot.variant in args.variant
        and (not needles or any(needle in normalize(shot.word) for needle in needles))
    ]
    for shot in sorted(rows, key=lambda value: (value.variant, value.fixture_id)):
        print(f"\n=== {shot.variant} {shot.lang} [{shot.klass}] {shot.word} ===")
        print(shot.text)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("action", choices=["run", "report", "show"])
    result.add_argument("--variant", nargs="+", default=["v1"], choices=sorted(unit_verdict_prompts.VARIANTS))
    result.add_argument("--suite", choices=["gate", "characteristic", "regression"], default="gate")
    result.add_argument("--lang", nargs="+", choices=sorted(LANGS), default=sorted(LANGS))
    result.add_argument("--limit", type=int, default=0, help="first N fixtures per class")
    result.add_argument("--target", choices=sorted(TARGETS), default="ru")
    result.add_argument("--concurrency", type=int, default=3)
    result.add_argument("--pace", type=float, default=2.0)
    result.add_argument("--wait", type=float, default=45.0)
    result.add_argument("--resume", action="store_true")
    result.add_argument("--text", nargs="+", default=[], help="show: source-text substring")
    result.add_argument("--out", default=str(Path(__file__).parent / ".bench-unit-verdict"))
    return result


def main() -> None:
    args = parser().parse_args()
    out = Path(args.out)
    if args.action == "run":
        asyncio.run(run(args, out))
    elif args.action == "report":
        report(args, out)
    else:
        show(args, out)


if __name__ == "__main__":
    main()
