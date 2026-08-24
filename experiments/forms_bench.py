"""Forms-table arm — can the answer show how a word inflects, and be right?

A conjugation table is the one part of the answer the reader cannot check: it is
asked for precisely because the forms are not known. That makes a hallucinated
participle worse than a missing one, so the two are counted apart:

    missing   a required form absent from the table. Visible: the reader sees a
              short table and can ask for more.
    TRAP      an invented form present in the table — ``bekommte``, ``childs``,
              ``човеци``. Silent, authoritative, and wrong.

The negative control matters as much: on a word with no paradigm worth showing
(``sehr``, ``very``, ``веома``) the table must be absent entirely, or it is
decoration rather than signal.

The pool's one documented weakness is morphology (spec/decision-llm-backend.md),
and this feature is morphology end to end — which is the whole reason for the arm.

Run:
    uv run --no-project --python 3.12 --with "llmbroker>=1.5.2" \\
        python experiments/forms_bench.py run --variant f0 f1
    uv run --no-project --python 3.12 --with "llmbroker>=1.5.2" \\
        python experiments/forms_bench.py paid --variant f1 --alias gpt-fast
    uv run --no-project --python 3.12 --with "llmbroker>=1.5.2" \\
        python experiments/forms_bench.py report
"""

import argparse
import asyncio
import json
import re
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import forms_prompts  # noqa: E402
from backend_bench import (  # noqa: E402
    LANGS,
    TARGETS,
    Pacer,
    drain,
    load_keys,
    load_template,
    log,
    parse_json_object,
    resolve_paid,
    split_answer,
    validate_card,
)
from forms_items import CLASSES, FORMS_HINTS, items  # noqa: E402

EXPECTED = {
    (lang, word): (required, traps)
    for klass in CLASSES
    for lang in CLASSES[klass]
    for word, required, traps in CLASSES[klass][lang]
}
from llmbroker import AsyncBroker  # noqa: E402
from llmbroker.direct import AsyncDirectClient  # noqa: E402

TABLE_TAGS = {"b", "i", "table", "tr", "td", "br"}
_TABLE = re.compile(r"<table>(.*?)</table>", re.DOTALL | re.IGNORECASE)
_TAG = re.compile(r"</?([A-Za-z][A-Za-z0-9]*)([^>]*)>")
# Part-of-speech names in the target language: what the answer must stop saying.
POS_WORDS = re.compile(
    r"\b(наречие|существительное|прилагательное|глагол|предлог|союз|местоимение"
    r"|частица|междометие|числительное|сущ\.|прил\.|гл\.|нареч\.)",
    re.IGNORECASE,
)


def table_text(analysis: str) -> str:
    return " ".join(m.group(1) for m in _TABLE.finditer(analysis))


def present(needle: str, haystack: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", haystack, re.IGNORECASE) is not None


def tag_problems(analysis: str) -> list[str]:
    """Only the small tag set, and never an attribute — the sanitizer allows none."""
    problems = []
    seen = {m.group(1).lower() for m in _TAG.finditer(analysis)}
    if seen - TABLE_TAGS:
        problems.append(f"tags {sorted(seen - TABLE_TAGS)}")
    if any(m.group(2).strip() for m in _TAG.finditer(analysis)):
        problems.append("tag carries attributes")
    if re.search(r"\*\*|^#{1,6} |^\s*\|.*\|", analysis, re.MULTILINE):
        problems.append("markdown")
    return problems


@dataclass
class Shot:
    variant: str
    klass: str
    lang: str
    word: str
    required: list
    traps: list
    model: str = "pool"
    answered_by: str | None = None
    t_first: float | None = None
    t_total: float | None = None
    error: str | None = None
    text: str = ""
    metrics: dict = field(default_factory=dict)


def score(shot: Shot) -> Shot:
    if not shot.text:
        return shot
    analysis, payload = split_answer(shot.text)
    card, parse_error = parse_json_object(payload)
    inside = table_text(analysis)
    found = [f for f in shot.required if present(f, inside)]
    tripped = [t for t in shot.traps if present(t, inside)]
    shot.metrics = {
        "table": bool(inside.strip()),
        "required_total": len(shot.required),
        "required_found": len(found),
        "complete": bool(shot.required) and len(found) == len(shot.required),
        "missing": [f for f in shot.required if f not in found],
        "traps_hit": tripped,
        "pos_named": bool(POS_WORDS.search(analysis)),
        "rows": inside.lower().count("<tr>"),
        "tag_problems": tag_problems(analysis),
        "card_ok": bool(card) and not validate_card(card),
        "card_problems": validate_card(card) if card else [parse_error],
        "chars": len(analysis),
    }
    return shot


def out_path(out: Path) -> Path:
    return out / "forms.jsonl"


def append(path: Path, shot: Shot) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(shot), ensure_ascii=False) + "\n")


def read_shots(out: Path) -> list[Shot]:
    path = out_path(out)
    if not path.exists():
        return []
    shots = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        shot = Shot(**json.loads(line))
        expected = EXPECTED.get((shot.lang, shot.word))
        if expected is not None:
            shot.required, shot.traps = list(expected[0]), list(expected[1])
        shots.append(score(shot))
    return shots


def jobs(args) -> list[tuple[str, str, str, str, list, list]]:
    return [
        (variant, klass, lang, word, list(required), list(traps))
        for variant in args.variant
        for klass in args.klass
        for lang in args.lang
        for word, required, traps in items(klass, lang)[: args.limit or None]
    ]


def build_prompt(variant: str, word: str, lang: str, target: str) -> str:
    source_lang, hints = LANGS[lang]
    return forms_prompts.build(load_template("vocab"), variant).format(
        source_lang=source_lang,
        target_lang=TARGETS[target][0],
        source_hints=hints,
        context_note="",
        word=word,
        forms_hint=FORMS_HINTS[lang],
    )


def make_shot(variant, klass, lang, word, required, traps, model="pool"):  # noqa: PLR0913
    return Shot(
        variant=variant, klass=klass, lang=lang, word=word,
        required=required, traps=traps, model=model,
        answered_by=None if model == "pool" else model,
    )


async def run(args, out: Path) -> None:
    import os

    os.environ.update(load_keys())
    broker = AsyncBroker(home=out / "llmbroker")
    path = out_path(out)
    gate = asyncio.Semaphore(args.concurrency)
    pacer = Pacer(args.pace)

    async def one(*job) -> None:
        shot = make_shot(*job)
        await pacer.wait()
        async with gate:
            handle = broker.stream(
                build_prompt(shot.variant, shot.word, shot.lang, args.target),
                operation=f"forms-{shot.variant}-{shot.lang}",
                wait=args.wait,
            )
            try:
                await drain(handle, shot)
                shot.answered_by = handle.llm_name
            except Exception as exc:  # noqa: BLE001 - a dead model is a result, not a crash
                shot.error = f"{type(exc).__name__}: {exc}"
                shot.answered_by = handle.llm_name
            finally:
                await handle.aclose()
        score(shot)
        append(path, shot)
        log(f"{shot.variant} {shot.lang} {shot.word!r} table={shot.metrics.get('table')} "
            f"{shot.metrics.get('required_found')}/{shot.metrics.get('required_total')} "
            f"traps={shot.metrics.get('traps_hit')} {shot.t_total}s {shot.error or ''}")

    try:
        await asyncio.gather(*(one(*job) for job in jobs(args)))
    finally:
        await broker.aclose()


async def run_paid(args, out: Path) -> None:
    keys = load_keys()
    specs = {name: resolve_paid(name) for name in args.alias}
    targets = [(n, s) for n, s in specs.items() if keys.get(s["api_key_ref"], "").strip()]
    log(f"paid models: {[n for n, _ in targets]}")
    path = out_path(out)
    gate = asyncio.Semaphore(args.concurrency)
    pacer = Pacer(args.pace)

    async def one(alias: str, spec: dict, *job) -> None:
        shot = make_shot(*job, model=alias)
        await pacer.wait()
        client = AsyncDirectClient(
            base_url=spec["base_url"], model=spec["model"],
            api_key=keys.get(spec["api_key_ref"], ""), timeout=args.wait,
        )
        prompt = build_prompt(shot.variant, shot.word, shot.lang, args.target)
        async with gate:
            try:
                await drain(client.stream(prompt, timeout=args.wait), shot)
            except Exception as exc:  # noqa: BLE001 - a dead model is a result, not a crash
                shot.error = f"{type(exc).__name__}: {exc}"
        await client.aclose()
        score(shot)
        append(path, shot)
        log(f"{alias} {shot.variant} {shot.lang} {shot.word!r} table={shot.metrics.get('table')} "
            f"{shot.metrics.get('required_found')}/{shot.metrics.get('required_total')} "
            f"traps={shot.metrics.get('traps_hit')} {shot.t_total}s {shot.error or ''}")

    await asyncio.gather(*(one(a, s, *job) for a, s in targets for job in jobs(args)))


def pct(part: int, whole: int) -> str:
    return f"{part / whole:.0%}" if whole else "  -"


def report(out: Path) -> None:
    shots = [s for s in read_shots(out) if s.metrics]
    if not shots:
        raise SystemExit(f"nothing recorded in {out_path(out)}")
    combos = sorted({(s.variant, s.model) for s in shots})
    print(f"{len(shots)} answers\n")
    print(f"{'class':8} {'variant':8} {'model':10} {'n':>3} {'table':>6} {'forms':>7} "
          f"{'complete':>9} {'TRAP':>5} {'pos':>5} {'tags':>5} {'p50 s':>6}")
    for klass in ("forms", "nothing"):
        for variant, model in combos:
            group = [s for s in shots if s.klass == klass and s.variant == variant and s.model == model]
            if not group:
                continue
            n = len(group)
            m = [s.metrics for s in group]
            req = sum(x["required_total"] for x in m)
            times = [s.t_total for s in group if s.t_total]
            print(
                f"{klass:8} {variant:8} {model:10} {n:>3} {pct(sum(x['table'] for x in m), n):>6} "
                f"{pct(sum(x['required_found'] for x in m), req):>7} "
                f"{pct(sum(x['complete'] for x in m), n):>9} "
                f"{sum(len(x['traps_hit']) for x in m):>5} "
                f"{pct(sum(x['pos_named'] for x in m), n):>5} "
                f"{sum(1 for x in m if x['tag_problems']):>5} "
                f"{statistics.median(times) if times else 0:>6.1f}"
            )
        print()

    print("--- invented forms (the expensive failure) ---")
    bad = [s for s in shots if s.metrics["traps_hit"]]
    for s in sorted(bad, key=lambda s: (s.variant, s.model, s.lang)):
        print(f"  {s.variant} {s.model} {s.lang} {s.word!r} -> {s.metrics['traps_hit']}")
    if not bad:
        print("  none")

    print("\n--- a table where there should be none ---")
    noise = [s for s in shots if s.klass == "nothing" and s.metrics["table"]]
    for s in sorted(noise, key=lambda s: (s.variant, s.model)):
        print(f"  {s.variant} {s.model} {s.lang} {s.word!r} ({s.metrics['rows']} rows)")
    if not noise:
        print("  none")

    print("\n--- missing required forms ---")
    for s in sorted(
        (s for s in shots if s.klass == "forms" and s.metrics["missing"]),
        key=lambda s: (s.variant, s.model, s.lang),
    ):
        print(f"  {s.variant} {s.model} {s.lang} {s.word!r} missing {s.metrics['missing']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["run", "paid", "report", "prompts"])
    parser.add_argument("--variant", nargs="+", default=sorted(forms_prompts.VARIANTS))
    parser.add_argument("--klass", nargs="+", default=list(CLASSES), choices=list(CLASSES))
    parser.add_argument("--lang", nargs="+", default=["en", "de", "sr"], choices=list(LANGS))
    parser.add_argument("--alias", nargs="+", default=["gpt-fast"])
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--target", default="ru", choices=list(TARGETS))
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--pace", type=float, default=2.0)
    parser.add_argument("--wait", type=float, default=45.0)
    parser.add_argument("--out", default=str(Path(__file__).parent / ".bench-forms"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.phase == "report":
        report(out)
    elif args.phase == "prompts":
        for variant in args.variant:
            print(f"===== {variant}: {forms_prompts.VARIANTS[variant][0]} =====")
            print(build_prompt(variant, "aufstehen", "de", args.target))
    else:
        started = time.monotonic()
        asyncio.run((run_paid if args.phase == "paid" else run)(args, out))
        log(f"{args.phase} done in {time.monotonic() - started:.0f}s -> {out_path(out)}")


if __name__ == "__main__":
    main()
