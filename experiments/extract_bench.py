"""Unit-extraction arm — should a multi-word input be carded whole, and by whom?

The question the routing decision left open. A multi-word input reaches the
vocabulary prompt and is carded verbatim, which is right for ``Rad fahren`` and
wrong for ``ist allein im Restaurant``. This measures whether the model can tell
the two apart well enough to be trusted with the deck.

The two error directions are not symmetric, so they are counted separately:

    split     a lexical unit taken apart — ``fahren`` carded out of ``Rad
              fahren``. Expensive: the card looks correct, so nothing catches it
              and the deck quietly rots.
    missed    a fragment whose focus was not found. Cheap: it is exactly what
              ships today, and a candidate list recovers it in one tap.

So the arm reports ``split`` on the unit class as the gate, and focus accuracy
on the fragment class as the payoff. ``v3`` additionally returns a ranked
candidate list, which makes one run score both designs at once: the top
candidate is what would be added automatically, and the whole list is what a
tap would choose from.

Outside the package and outside CI: it calls real models. The free pool only,
so it spends time rather than money.

Run:
    uv run --no-project --python 3.12 --with "llmbroker>=1.5.2" \\
        python experiments/extract_bench.py run --variant v0 v1 v2 v3
    uv run --no-project --python 3.12 --with "llmbroker>=1.5.2" \\
        python experiments/extract_bench.py report
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

import extract_prompts  # noqa: E402
from backend_bench import (  # noqa: E402
    LANGS,
    resolve_paid,
    TARGETS,
    Pacer,
    answer_language,
    drain,
    html_violations,
    load_keys,
    load_template,
    log,
    parse_json_object,
    split_answer,
    validate_card,
    word_hint,
)
from extract_items import CLASSES, items  # noqa: E402
from llmbroker import AsyncBroker  # noqa: E402
from llmbroker.direct import AsyncDirectClient  # noqa: E402

MAX_CANDIDATES = 3
_WORDS = re.compile(r"[^\W\d_]+", re.UNICODE)
PROMPT_SOURCE = Path(__file__).resolve().parent.parent / "src" / "echo_words" / "prompt.py"


def text_template() -> str:
    """The shipped running-text prompt, read as text — same reason as load_template."""
    source = PROMPT_SOURCE.read_text(encoding="utf-8")
    block = re.search(r'^_TEXT_PROMPT = """(.*?)"""$', source, re.DOTALL | re.MULTILINE)
    if block is None:
        raise RuntimeError(f"running-text template not found in {PROMPT_SOURCE}")
    return block.group(1)


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", str(text)).casefold().split()).strip(" .,;:!?…")


def tokens(text: str) -> list[str]:
    return _WORDS.findall(normalize(text))


def covers_input(surface: str, source: str) -> bool:
    """Whether the unit occupies the whole input — the test the card decision reads.

    A sequence comparison, not a set one: a dropped clitic is exactly the
    difference between an inflected unit and a use of one, and ``вратио се`` out
    of ``вратио се кући`` must not count as the whole thing.
    """
    return bool(surface) and tokens(surface) == tokens(source)


def is_split(label: str, source: str) -> bool:
    """The expensive error, detected structurally rather than against the fixture:
    the answer is a proper part of the input, every word of it already there.

    Structural because it must not depend on my list of accepted answers being
    complete. It over-reports by design — dropping the article from ``eine
    Entscheidung treffen`` trips it too — so every hit is printed for the human
    pass instead of being counted as settled.
    """
    label_words, source_words = tokens(label), tokens(source)
    if not label_words or len(label_words) >= len(source_words):
        return False
    return set(label_words) <= set(source_words)


@dataclass
class Shot:
    variant: str
    klass: str
    lang: str
    word: str
    accepted: list
    traps: list = field(default_factory=list)
    model: str = "pool"
    answered_by: str | None = None
    t_first: float | None = None
    t_total: float | None = None
    error: str | None = None
    text: str = ""
    metrics: dict = field(default_factory=dict)


def segment_labels(card: dict | None) -> list[str]:
    raw = (card or {}).get("segments")
    if not isinstance(raw, list):
        return []
    return [
        str(s["label"]).strip()
        for s in raw
        if isinstance(s, dict) and str(s.get("label", "")).strip()
    ]


def score(shot: Shot) -> Shot:
    if not shot.text:
        return shot
    text_mode = shot.variant in extract_prompts.TEXT_VARIANTS
    analysis, payload = split_answer(shot.text)
    card, parse_error = parse_json_object(payload)
    accepted = {normalize(a) for a in shot.accepted}
    traps = {normalize(t) for t in shot.traps}
    if text_mode:
        # A running-text answer offers a chip row; its first chip is what a card
        # would be built from, so it stands where the card's word field stands.
        candidates = segment_labels(card)
        label = candidates[0] if candidates else ""
        problems = [parse_error] if card is None else ([] if candidates else ["no segments"])
        surface = ""
    else:
        problems = validate_card(card) if card else [parse_error]
        label = str((card or {}).get("word", "")).strip()
        surface = str((card or {}).get("surface", "")).strip()
        raw_candidates = (card or {}).get("candidates")
        candidates = (
            [str(c).strip() for c in raw_candidates if str(c).strip()]
            if isinstance(raw_candidates, list)
            else []
        )
    shot.metrics = {
        "label": label,
        "hit": normalize(label) in accepted,
        # The prefix or the reflexive particle went missing and left a real word
        # of the language behind, so nothing downstream can notice the loss.
        "stripped": normalize(label) in traps,
        "stripped_any": any(normalize(c) in traps for c in candidates),
        "split": is_split(label, shot.word),
        "echoed": normalize(label) == normalize(shot.word),
        "surface": surface,
        "surface_present": bool(surface),
        # What the shipped rule would do with this answer: the whole input
        # occupied by the unit means the input is that unit and becomes a note.
        "cards_whole": covers_input(surface, shot.word),
        "label_valid": bool(label) and word_hint(label, shot.lang) is None,
        "candidates": candidates,
        "too_many_candidates": len(candidates) > MAX_CANDIDATES,
        "hit_any": any(normalize(c) in accepted for c in candidates),
        "first_is_word": bool(candidates) and normalize(candidates[0]) == normalize(label),
        "card_ok": bool(card) and not problems,
        "card_problems": problems,
        "format_problems": html_violations(analysis),
        "analysis_chars": len(analysis),
        "answer_lang": answer_language(analysis),
    }
    return shot


def out_path(out: Path) -> Path:
    return out / "extract.jsonl"


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
        if line.strip():
            # Re-score on read: the metrics move as the harness learns, the answers do not.
            shots.append(score(Shot(**json.loads(line))))
    return shots


def jobs(args) -> list[tuple[str, str, str, str, list, list]]:
    """(variant, klass, lang, text, accepted, traps) for everything the filters admit."""
    picked = []
    for variant in args.variant:
        for klass in args.klass:
            for lang in args.lang:
                for text, accepted, traps in items(klass, lang)[: args.limit or None]:
                    picked.append((variant, klass, lang, text, list(accepted), list(traps)))
    return picked


def build_prompt(variant: str, word: str, lang: str, target: str) -> str:
    source_lang, hints = LANGS[lang]
    if variant in extract_prompts.TEXT_VARIANTS:
        rendered = extract_prompts.build_text(text_template(), variant)
    else:
        rendered = extract_prompts.build(load_template("vocab"), variant)
    return rendered.format(
        source_lang=source_lang,
        target_lang=TARGETS[target][0],
        source_hints=hints,
        context_note="",
        word=word,
    )


async def run(args, out: Path) -> None:
    import os

    os.environ.update(load_keys())
    broker = AsyncBroker(home=out / "llmbroker")
    path = out_path(out)
    gate = asyncio.Semaphore(args.concurrency)
    pacer = Pacer(args.pace)

    async def one(  # noqa: PLR0913 - one call carries its whole identity
        variant: str, klass: str, lang: str, word: str, accepted: list, traps: list,
    ) -> None:
        shot = Shot(
            variant=variant, klass=klass, lang=lang, word=word,
            accepted=accepted, traps=traps,
        )
        await pacer.wait()
        async with gate:
            handle = broker.stream(
                build_prompt(variant, word, lang, args.target),
                operation=f"extract-{variant}-{lang}",
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
        got = shot.metrics.get("label", "")
        log(f"{variant} {klass:9} {lang} {word!r} -> {got!r} {shot.t_total}s {shot.error or ''}")

    try:
        await asyncio.gather(*(one(*job) for job in jobs(args)))
    finally:
        await broker.aclose()


async def run_paid(args, out: Path) -> None:
    """The same items through metered models, one client each.

    The pool routes on its own availability, so it hands different variants to
    different models and a variant-to-variant difference cannot be told from a
    model-to-model one. Pinning the model is the only way to read the numbers.
    """
    keys = load_keys()
    specs = {name: resolve_paid(name) for name in args.alias}
    targets = [(n, s) for n, s in specs.items() if keys.get(s["api_key_ref"], "").strip()]
    missing = [n for n in specs if n not in dict(targets)]
    if missing:
        log(f"skipped (no key): {missing}")
    log(f"paid models: {[n for n, _ in targets]}")
    path = out_path(out)
    gate = asyncio.Semaphore(args.concurrency)
    pacer = Pacer(args.pace)

    async def one(  # noqa: PLR0913 - one metered call carries its whole identity
        alias: str, spec: dict, variant: str, klass: str, lang: str,
        word: str, accepted: list, traps: list,
    ) -> None:
        shot = Shot(
            variant=variant, klass=klass, lang=lang, word=word,
            accepted=accepted, traps=traps, model=alias, answered_by=alias,
        )
        await pacer.wait()
        client = AsyncDirectClient(
            base_url=spec["base_url"],
            model=spec["model"],
            api_key=keys.get(spec["api_key_ref"], ""),
            timeout=args.wait,
        )
        prompt = build_prompt(variant, word, lang, args.target)
        async with gate:
            for attempt in range(args.retries + 1):
                try:
                    await drain(client.stream(prompt, timeout=args.wait), shot)
                except Exception as exc:  # noqa: BLE001 - a dead model is a result, not a crash
                    shot.error = f"{type(exc).__name__}: {exc}"
                if not shot.error or "RateLimit" not in shot.error:
                    break
                await asyncio.sleep(args.backoff * (attempt + 1))
        await client.aclose()
        score(shot)
        append(path, shot)
        got = shot.metrics.get("label", "")
        log(f"{alias} {variant} {klass:9} {lang} {word!r} -> {got!r} {shot.t_total}s {shot.error or ''}")

    await asyncio.gather(
        *(one(alias, spec, *job) for alias, spec in targets for job in jobs(args))
    )


def pct(part: int, whole: int) -> str:
    return f"{part / whole:.0%}" if whole else "  -"


def report(out: Path) -> None:
    shots = [s for s in read_shots(out) if s.metrics]
    if not shots:
        raise SystemExit(f"nothing recorded in {out_path(out)}")
    combos = sorted({(s.variant, s.model) for s in shots})
    print(f"{len(shots)} answers over {', '.join(sorted({s.variant for s in shots}))}\n")
    header = f"{'class':10} {'variant':8} {'model':16} {'n':>3} {'hit@1':>6} {'hit@any':>8} {'STRIP':>6} "
    print(header + f"{'SPLIT':>6} {'echoed':>7} {'whole':>6} {'surf':>5} {'valid':>6} {'card':>5} {'p50 s':>6}")
    for klass in ("units", "inflected", "morphology", "fragments", "clauses", "controls"):
        rows = [s for s in shots if s.klass == klass]
        if not rows:
            continue
        for variant, model in combos:
            group = [s for s in rows if s.variant == variant and s.model == model]
            if not group:
                continue
            n = len(group)
            m = [s.metrics for s in group]
            times = [s.t_total for s in group if s.t_total]
            has_candidates = (
                variant in extract_prompts.WITH_CANDIDATES
                or variant in extract_prompts.TEXT_VARIANTS
            )
            any_hit = pct(sum(1 for x in m if x["hit"] or x["hit_any"]), n) if has_candidates else "  -"
            print(
                f"{klass:10} {variant:8} {model:16} {n:>3} "
                f"{pct(sum(x['hit'] for x in m), n):>6} "
                f"{any_hit:>8} {pct(sum(x['stripped'] for x in m), n):>6} "
                f"{pct(sum(x['split'] for x in m), n):>6} "
                f"{pct(sum(x['echoed'] for x in m), n):>7} "
                f"{pct(sum(x.get('cards_whole') for x in m), n):>6} "
                f"{pct(sum(x.get('surface_present') for x in m), n):>5} "
                f"{pct(sum(x['label_valid'] for x in m), n):>6} "
                f"{pct(sum(x['card_ok'] for x in m), n):>5} "
                f"{statistics.median(times) if times else 0:>6.1f}"
            )
        print()

    stripped = [s for s in shots if s.metrics.get("stripped") or s.metrics.get("stripped_any")]
    print("--- prefix or reflexive particle lost ---")
    for shot in sorted(stripped, key=lambda s: (s.variant, s.lang)):
        where = "carded" if shot.metrics["stripped"] else "in candidates"
        print(
            f"  {shot.variant} {shot.model} {shot.lang} {shot.word!r} -> "
            f"{shot.metrics['candidates'] or shot.metrics['label']!r}  ({where}, trap {shot.traps})"
        )
    if not stripped:
        print("  none")

    print("\n--- units flagged as split: the human pass decides which are real ---")
    flagged = [s for s in shots if s.klass == "units" and s.metrics["split"]]
    for shot in sorted(flagged, key=lambda s: (s.variant, s.lang)):
        print(f"  {shot.variant} {shot.lang} {shot.word!r} -> {shot.metrics['label']!r}")
    if not flagged:
        print("  none")

    print("\n--- fragments whose focus was missed ---")
    for shot in sorted(
        (s for s in shots if s.klass == "fragments" and not s.metrics["hit"]),
        key=lambda s: (s.variant, s.lang),
    ):
        cands = shot.metrics["candidates"]
        tail = f"  candidates={cands}" if cands else ""
        print(
            f"  {shot.variant} {shot.lang} {shot.word!r} -> {shot.metrics['label']!r} "
            f"(wanted {shot.accepted}){tail}"
        )

    print("\n--- the card decision: whole input carded, or its unit offered ---")
    for klass, want in (("units", True), ("inflected", True), ("fragments", False)):
        wrong = [
            s
            for s in shots
            if s.klass == klass and s.metrics.get("surface_present") and s.metrics["cards_whole"] is not want
        ]
        verb = "offered instead of carded" if want else "CARDED WHOLE instead of offered"
        print(f"  {klass}: {len(wrong)} {verb}")
        for shot in sorted(wrong, key=lambda s: (s.variant, s.lang)):
            print(
                f"    {shot.variant} {shot.lang} {shot.word!r} -> word={shot.metrics['label']!r} "
                f"surface={shot.metrics['surface']!r}"
            )
    missing = [s for s in shots if s.metrics and not s.metrics.get("surface_present") and s.metrics.get("card_ok")]
    print(f"  no surface field at all: {len(missing)}")
    for shot in missing[:10]:
        print(f"    {shot.variant} {shot.lang} {shot.word!r}")

    broken = [s for s in shots if s.error or not s.metrics["card_ok"]]
    print(f"\n--- unusable answers: {len(broken)} ---")
    for shot in broken[:20]:
        why = shot.error or "; ".join(shot.metrics["card_problems"])
        print(f"  {shot.variant} {shot.lang} {shot.word!r}: {why}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["run", "paid", "report", "prompts"])
    parser.add_argument("--alias", nargs="+", default=["gpt-fast"], help="paid: catalog aliases")
    parser.add_argument("--retries", type=int, default=2, help="paid: retries on a rate limit")
    parser.add_argument("--backoff", type=float, default=20.0)
    parser.add_argument(
        "--variant",
        nargs="+",
        default=sorted(extract_prompts.VARIANTS),
        choices=sorted(extract_prompts.VARIANTS) + sorted(extract_prompts.TEXT_VARIANTS),
    )
    parser.add_argument("--klass", nargs="+", default=list(CLASSES), choices=list(CLASSES))
    parser.add_argument("--lang", nargs="+", default=["en", "de", "sr"], choices=list(LANGS))
    parser.add_argument("--limit", type=int, default=0, help="first N items per class per language")
    parser.add_argument("--target", default="ru", choices=list(TARGETS))
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--pace", type=float, default=2.0, help="seconds between call starts")
    parser.add_argument("--wait", type=float, default=45.0, help="whole-call budget, seconds")
    parser.add_argument("--out", default=str(Path(__file__).parent / ".bench"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.phase == "report":
        report(out)
    elif args.phase == "prompts":
        for variant in args.variant:
            rendered = build_prompt(variant, "ist allein im Restaurant", "de", args.target)
            family = extract_prompts.VARIANTS | extract_prompts.TEXT_VARIANTS
            print(f"===== {variant}: {family[variant][0]} =====")
            print(rendered)
    else:
        started = time.monotonic()
        asyncio.run((run_paid if args.phase == "paid" else run)(args, out))
        log(f"run done in {time.monotonic() - started:.0f}s -> {out_path(out)}")


if __name__ == "__main__":
    main()
