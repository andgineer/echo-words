"""M0 backend spike — which LLM backend each source language needs.

Measures the two backend kinds echo-words ships (spec/implementation-plan.md,
"M0 — LLM backend spike"): the free llmbroker pool and the paid direct client,
over a fixed item set per source language, with the production prompt.

Outside the package and outside CI: it deliberately calls real models, and the
paid phase spends real money.

Phases:
    pool   route through ``AsyncBroker.stream`` — the shipped llmbroker path;
           records which pooled model actually answered
    free   each free-tier model on its own, to get per-model numbers the pool
           hides behind its routing
    paid   each paid alias through ``broker.direct(alias)`` — the shipped api path
    judge  LLM-judge pre-filter over recorded runs (never the final word)
    report aggregate everything recorded so far
    review emit a markdown file for the human pass

Keys are read from ``.deploy/.env`` (falling back to the real environment), and
llmbroker keeps its state under the output directory, not in the user's cache.

Run:
    uv run --no-project --python 3.12 --with "llmbroker>=1.5.1" \\
        python experiments/backend_bench.py pool --lang en de sr
    uv run --no-project --python 3.12 --with "llmbroker>=1.5.1" \\
        python experiments/backend_bench.py free --lang sr --limit 20
    uv run --no-project --python 3.12 --with "llmbroker>=1.5.1" \\
        python experiments/backend_bench.py paid --alias sonnet flash --lang sr
    uv run --no-project --python 3.12 --with "llmbroker>=1.5.1" \\
        python experiments/backend_bench.py judge --judge gpt
    uv run --no-project --python 3.12 --with "llmbroker>=1.5.1" \\
        python experiments/backend_bench.py report
"""

import argparse
import asyncio
import functools
import json
import os
import re
import statistics
import sys
import time
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import llmbroker  # noqa: E402
from bench_items import ITEMS  # noqa: E402
from llmbroker import AsyncBroker  # noqa: E402
from llmbroker.direct import AsyncDirectClient  # noqa: E402
from llmbroker.standalone.secrets import parse_env_file  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
PLAN = REPO / "spec" / "implementation-plan.md"
ENV_FILE = REPO / ".deploy" / ".env"
PRESETS = Path(llmbroker.__file__).parent / "presets"

CARD_DELIM = "===CARD==="
MAX_ANALYSIS = 3500
MAX_MEANINGS = 3
ALLOWED_TAGS = {"b", "i"}
TARGET_LANG = "русский"
# The functional description's whole-answer budget; past it the answer is late, not lost.
SLOW_ANSWER = 30.0
# IPA extensions, the stress/length marks, the strays outside that block, and the
# tone diacritics a Serbian transcription is written with — [kôsa] is IPA too.
IPA_CHARS = "[ɐ-ʯˈˌːŋæœøðθâêîôûȁȃȅȇȉȋȍȏȕȗǎěǐǒǔ̀-̑]"

# Display names and prompt hints exactly as the shipped languages.toml carries them
# (spec/implementation-plan.md, "Languages configuration").
LANGS = {
    "en": ("English", ""),
    "de": ("Deutsch", ""),
    "sr": (
        "Српски",
        "для существительных указывай род и множественное число, для глаголов — вид",
    ),
}


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


@functools.cache
def load_template() -> str:
    """The production prompt, read from the plan's own block — the spike must compare
    backends, not prompts, and prompt.py itself only lands in M2."""
    plan = PLAN.read_text(encoding="utf-8")
    block = re.search(r"^```text\n(.*?)^```\n", plan, re.DOTALL | re.MULTILINE)
    if block is None:
        raise RuntimeError(f"prompt template block not found in {PLAN}")
    return block.group(1)


def build_prompt(word: str, lang: str) -> str:
    source_lang, hints = LANGS[lang]
    return (
        load_template()
        .replace("{source_lang}", source_lang)
        .replace("{target_lang}", TARGET_LANG)
        .replace("{source_hints}", hints)
        .replace("{word}", word)
    )


def load_keys() -> dict[str, str]:
    values = dict(os.environ)
    if ENV_FILE.exists():
        for key, value in parse_env_file(ENV_FILE.read_text(encoding="utf-8")).items():
            if value.strip() and not values.get(key, "").strip():
                values[key] = value
    return values


def free_models() -> list[dict]:
    preset = tomllib.loads((PRESETS / "freetier.toml").read_text(encoding="utf-8"))
    return preset["llms"]


def paid_catalog() -> dict:
    return tomllib.loads((PRESETS / "paid-catalog.toml").read_text(encoding="utf-8"))


def paid_models() -> dict[str, dict]:
    return {
        model["alias"]: {**model, "base_url": p["base_url"], "api_key_ref": p["api_key_ref"]}
        for p in paid_catalog()["provider"]
        for model in p["models"]
    }


def resolve_paid(name: str) -> dict:
    """A catalog alias, or ``provider:model-id`` for a model the catalog does not
    carry — the catalog is curated, and a survey is exactly where an uncurated
    model has to be reachable."""
    catalog = paid_models()
    if name in catalog:
        return catalog[name]
    provider_id, _, model_id = name.partition(":")
    for provider in paid_catalog()["provider"]:
        if provider["id"] == provider_id and model_id:
            return {
                "model": model_id,
                "base_url": provider["base_url"],
                "api_key_ref": provider["api_key_ref"],
            }
    known = sorted(catalog) + [p["id"] + ":<model-id>" for p in paid_catalog()["provider"]]
    raise SystemExit(f"unknown paid model {name!r} — expected one of {known}")


# ----------------------------------------------------------------------------
# Scoring: everything that can be checked without an opinion
# ----------------------------------------------------------------------------


def split_answer(text: str) -> tuple[str, str]:
    analysis, _, payload = text.partition(CARD_DELIM)
    return analysis.strip(), payload.strip()


def parse_json_object(payload: str) -> tuple[dict | None, str]:
    if not payload:
        return None, "no ===CARD=== payload"
    body = re.sub(r"^```(?:json)?|```$", "", payload.strip(), flags=re.MULTILINE).strip()
    start, end = body.find("{"), body.rfind("}")
    if start < 0 or end <= start:
        return None, "no JSON object after the delimiter"
    try:
        card = json.loads(body[start : end + 1])
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON: {exc.msg}"
    return (card, "") if isinstance(card, dict) else (None, "JSON is not an object")


def validate_meaning(index: int, meaning: object) -> list[str]:
    if not isinstance(meaning, dict):
        return [f"meaning {index} is not an object"]
    problems = []
    translations = meaning.get("translations")
    if not isinstance(translations, list) or not translations:
        problems.append(f"meaning {index}: translations missing or empty")
    examples = meaning.get("examples")
    if not isinstance(examples, list) or not examples:
        return [*problems, f"meaning {index}: examples missing or empty"]
    for j, example in enumerate(examples):
        if not isinstance(example, dict) or not example.get("text"):
            problems.append(f"meaning {index} example {j}: no text")
        elif not example.get("translation"):
            problems.append(f"meaning {index} example {j}: no translation")
    return problems


def validate_card(card: dict) -> list[str]:
    """The M2 card.py contract, applied here so the spike measures what will ship."""
    meanings = card.get("meanings")
    if not isinstance(meanings, list) or not meanings:
        return ["meanings missing or empty"]
    problems = []
    if len(meanings) > MAX_MEANINGS:
        problems.append(f"{len(meanings)} meanings (max {MAX_MEANINGS})")
    for i, meaning in enumerate(meanings):
        problems += validate_meaning(i, meaning)
    if not isinstance(card.get("word"), str) or not card["word"].strip():
        problems.append("word missing")
    if "suggestion" in card and not isinstance(card["suggestion"], str):
        problems.append("suggestion is not a string")
    return problems


def html_violations(analysis: str) -> list[str]:
    problems = []
    tags = {t.lower() for t in re.findall(r"</?([A-Za-z][A-Za-z0-9]*)", analysis)}
    if tags - ALLOWED_TAGS:
        problems.append(f"tags {sorted(tags - ALLOWED_TAGS)}")
    if re.search(r"\*\*|^#{1,6} |^\s*\|.*\|", analysis, re.MULTILINE):
        problems.append("markdown")
    return problems


def json_has_tags(card: dict) -> bool:
    return "<" in json.dumps(card, ensure_ascii=False)


def cyrillic_share(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if "Ѐ" <= c <= "ӿ") / len(letters)


def score_run(word: str, text: str) -> dict:
    analysis, payload = split_answer(text)
    card, error = parse_json_object(payload)
    problems = validate_card(card) if card else [error]
    ipa = bool(re.search(rf"[/\[][^/\[\]]{{0,40}}{IPA_CHARS}[^/\[\]]{{0,40}}[/\]]", analysis))
    return {
        "chars": len(text),
        "analysis_chars": len(analysis),
        "delimiter": CARD_DELIM in text,
        "card_ok": bool(card) and not problems,
        "card_problems": problems,
        "meanings": len(card.get("meanings", [])) if card else 0,
        "over_length": len(analysis) > MAX_ANALYSIS,
        "format_problems": html_violations(analysis),
        "tags_in_json": bool(card) and json_has_tags(card),
        "word_echoed": bool(card) and str(card.get("word", "")).strip() == word,
        "suggestion": (card or {}).get("suggestion", ""),
        "ipa": ipa,
        "target_lang_share": round(cyrillic_share(analysis), 3),
    }


# ----------------------------------------------------------------------------
# Running
# ----------------------------------------------------------------------------


class Pacer:
    """Space out call starts. Without it the harness sends a burst no real user
    produces, trips every free-tier rate limit, and measures the failover tail
    instead of the primary model."""

    def __init__(self, gap: float) -> None:
        self._gap = gap
        self._lock = asyncio.Lock()
        self._next = 0.0

    async def wait(self) -> None:
        if not self._gap:
            return
        async with self._lock:
            now = time.monotonic()
            delay = max(0.0, self._next - now)
            self._next = max(now, self._next) + self._gap
        await asyncio.sleep(delay)


@dataclass
class Run:
    phase: str
    lang: str
    word: str
    shape: str
    model: str
    answered_by: str | None = None
    t_first: float | None = None
    t_total: float | None = None
    error: str | None = None
    text: str = ""
    metrics: dict = field(default_factory=dict)
    judge: dict = field(default_factory=dict)


async def drain(stream, run: Run) -> None:
    run.t_first = run.t_total = None
    run.error = None
    run.text = ""
    started = time.monotonic()
    chunks: list[str] = []
    try:
        async for delta in stream:
            if run.t_first is None:
                run.t_first = round(time.monotonic() - started, 3)
            chunks.append(delta)
    finally:
        # A stream that died past the first delta still says something about the model.
        run.t_total = round(time.monotonic() - started, 3)
        run.text = "".join(chunks)


def finish(run: Run) -> Run:
    if run.text:
        run.metrics = score_run(run.word, run.text)
    return run


def out_path(out: Path, phase: str) -> Path:
    return out / f"{phase}.jsonl"


def append(path: Path, run: Run) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(run), ensure_ascii=False) + "\n")


def read_runs(out: Path, phases: list[str]) -> list[Run]:
    runs = []
    for phase in phases:
        path = out_path(out, phase)
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            run = Run(**json.loads(line))
            # Re-score on read: the metrics move as the harness learns, the text does not.
            runs.append(finish(run))
    return runs


def stratified(items: list[tuple[str, str]], limit: int) -> list[tuple[str, str]]:
    """A subset that keeps every shape represented — the item list is grouped by shape,
    so a plain head slice would benchmark only common and rare words."""
    if not limit or limit >= len(items):
        return items
    by_shape: dict[str, list[tuple[str, str]]] = {}
    for item in items:
        by_shape.setdefault(item[1], []).append(item)
    picked: list[tuple[str, str]] = []
    while len(picked) < limit:
        for bucket in by_shape.values():
            if bucket and len(picked) < limit:
                picked.append(bucket.pop(0))
    return [item for item in items if item in picked]


def selected(args) -> list[tuple[str, str, str]]:
    jobs = []
    for lang in args.lang:
        for word, shape in stratified(ITEMS[lang], args.limit):
            jobs.append((lang, word, shape))
    return jobs


async def run_pool(args, out: Path) -> None:
    os.environ.update(load_keys())
    broker = AsyncBroker(home=out / "llmbroker")
    phase = args.tag or "pool"
    path = out_path(out, phase)
    gate = asyncio.Semaphore(args.concurrency)
    pacer = Pacer(args.pace)

    async def one(lang: str, word: str, shape: str) -> None:
        run = Run(phase=phase, lang=lang, word=word, shape=shape, model="pool")
        await pacer.wait()
        async with gate:
            handle = broker.stream(
                build_prompt(word, lang),
                operation=f"vocab-{lang}",
                wait=args.wait,
            )
            try:
                await drain(handle, run)
                run.answered_by = handle.llm_name
            except Exception as exc:  # noqa: BLE001 - a dead model is a result, not a crash
                run.error = f"{type(exc).__name__}: {exc}"
                run.answered_by = handle.llm_name
            finally:
                await handle.aclose()
        append(path, finish(run))
        log(f"pool {lang} {word!r} -> {run.answered_by} {run.t_total}s {run.error or ''}")

    try:
        await asyncio.gather(*(one(*job) for job in selected(args)))
    finally:
        await broker.aclose()


async def stream_direct(client: AsyncDirectClient, run: Run, timeout: float) -> None:
    try:
        await drain(client.stream(build_prompt(run.word, run.lang), timeout=timeout), run)
    except Exception as exc:  # noqa: BLE001 - a dead model is a result, not a crash
        run.error = f"{type(exc).__name__}: {exc}"


async def run_direct(args, out: Path, phase: str, targets: list[tuple[str, dict]]) -> None:
    """One client per model, every selected item through it — used by `free` and `paid`."""
    keys = load_keys()
    phase = args.tag or phase
    path = out_path(out, phase)
    gate = asyncio.Semaphore(args.concurrency)
    pacer = Pacer(args.pace)

    async def one(name: str, spec: dict, lang: str, word: str, shape: str) -> None:
        run = Run(phase=phase, lang=lang, word=word, shape=shape, model=name, answered_by=name)
        await pacer.wait()
        client = AsyncDirectClient(
            base_url=spec["base_url"],
            model=spec["model"],
            api_key=keys.get(spec["api_key_ref"], ""),
            timeout=args.wait,
        )
        async with gate:
            for attempt in range(args.retries + 1):
                await stream_direct(client, run, args.wait)
                if not run.error or "RateLimit" not in run.error:
                    break
                await asyncio.sleep(args.backoff * (attempt + 1))
        await client.aclose()
        append(path, finish(run))
        log(f"{phase} {name} {lang} {word!r} {run.t_total}s {run.error or ''}")

    jobs = [(name, spec, *job) for name, spec in targets for job in selected(args)]
    await asyncio.gather(*(one(*job) for job in jobs))


async def run_free(args, out: Path) -> None:
    keys = load_keys()
    targets = [
        (m["name"], m)
        for m in free_models()
        if keys.get(m["api_key_ref"], "").strip()
        and (not args.model or m["name"] in args.model)
    ]
    log(f"free models: {[name for name, _ in targets]}")
    await run_direct(args, out, "free", targets)


async def run_paid(args, out: Path) -> None:
    keys = load_keys()
    specs = {name: resolve_paid(name) for name in args.alias}
    targets = [(n, s) for n, s in specs.items() if keys.get(s["api_key_ref"], "").strip()]
    if len(targets) < len(specs):
        log(f"skipped (no key): {[n for n, _ in specs.items() if (n, specs[n]) not in targets]}")
    log(f"paid models: {[name for name, _ in targets]}")
    await run_direct(args, out, "paid", targets)


# ----------------------------------------------------------------------------
# LLM judge — a pre-filter for the human pass, never the verdict
# ----------------------------------------------------------------------------

JUDGE_PROMPT = """Ты строгий эксперт-лексикограф, носитель русского языка и языка
{source_lang}. Оцени разбор слова «{word}» ({source_lang}), сделанный для
изучающего язык. Вот разбор:

<РАЗБОР>
{answer}
</РАЗБОР>

Оцени по шкале 1-5 (5 — безупречно, 1 — негодно). Транскрипцию IPA не оценивай
и не упоминай — произношение даёт озвучка, а не она:
- translation: правильность переводов и их порядок по частотности, верность помет
  (разг., книжн., сленг, груб.) и части речи
- etymology: фактическая верность происхождения (заимствование, язык-источник)
- examples: естественность примеров и верность их перевода; употреблено ли слово
  в нужной форме
- morphology: верность грамматических сведений (род, число, вид, управление,
  неправильные формы) для этого языка

Ответь ОДНОЙ строкой JSON без пояснений:
{{"translation": N, "etymology": N, "examples": N, "morphology": N,
 "errors": ["краткое описание каждой фактической ошибки"]}}"""


async def run_judge(args, out: Path) -> None:
    os.environ.update(load_keys())
    runs = [r for r in read_runs(out, args.phases) if r.text and not r.judge]
    runs = [r for r in runs if r.shape in args.shapes]
    if args.sample:
        # Cap per model x language, not overall: a group is what the report compares.
        picked: dict[tuple[str, str, str], list[Run]] = {}
        for run in runs:
            bucket = picked.setdefault((run.phase, run.model, run.lang), [])
            if len(bucket) < args.sample:
                bucket.append(run)
        runs = [r for bucket in picked.values() for r in bucket]
    broker = AsyncBroker(home=out / "llmbroker", direct=[args.judge])
    client = await broker.direct(args.judge)
    gate = asyncio.Semaphore(args.concurrency)
    judged: dict[tuple, dict] = {}

    async def one(run: Run) -> None:
        prompt = JUDGE_PROMPT.format(
            source_lang=LANGS[run.lang][0],
            word=run.word,
            answer=split_answer(run.text)[0],
        )
        async with gate:
            try:
                reply = await client.ask(prompt, timeout=args.wait)
                scores, error = parse_json_object(reply.text)
                verdict = scores or {"error": error}
            except Exception as exc:  # noqa: BLE001 - a judge failure is not a run failure
                verdict = {"error": f"{type(exc).__name__}: {exc}"}
        verdict["judge"] = args.judge
        judged[(run.phase, run.model, run.lang, run.word)] = verdict
        log(f"judge {run.model} {run.lang} {run.word!r} -> {verdict}")

    try:
        await asyncio.gather(*(one(r) for r in runs))
    finally:
        await broker.aclose()

    for phase in args.phases:
        path = out_path(out, phase)
        if not path.exists():
            continue
        rows = read_runs(out, [phase])
        for row in rows:
            row.judge = judged.get((row.phase, row.model, row.lang, row.word), row.judge)
        path.write_text(
            "".join(json.dumps(asdict(r), ensure_ascii=False) + "\n" for r in rows),
            encoding="utf-8",
        )


# ----------------------------------------------------------------------------
# Reporting
# ----------------------------------------------------------------------------

# IPA is deliberately absent: pronunciation is delivered as audio, so the
# transcription is not a quality axis this project decides anything on.
JUDGE_KEYS = ("translation", "etymology", "examples", "morphology")


def pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:5.1f}%" if whole else "    - "


def quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def suggested(run: Run) -> bool:
    """The typo contract: a misspelled input must come back with a correction offer."""
    hint = str(run.metrics.get("suggestion", "")).strip()
    return bool(hint) and hint.casefold() != run.word.casefold()


def summarize(runs: list[Run]) -> dict:
    ok = [r for r in runs if not r.error]
    totals = [r.t_total for r in ok if r.t_total]
    firsts = [r.t_first for r in ok if r.t_first]
    judged = [r.judge for r in runs if r.judge and "translation" in r.judge]
    typos = [r for r in ok if r.shape == "typo"]
    summary = {
        "typos": len(typos),
        "typos_caught": sum(1 for r in typos if suggested(r)),
        "slow": sum(1 for t in totals if t > SLOW_ANSWER),
        "n": len(runs),
        "failed": len(runs) - len(ok),
        "card_ok": sum(1 for r in ok if r.metrics.get("card_ok")),
        "format_bad": sum(1 for r in ok if r.metrics.get("format_problems")),
        "over_length": sum(1 for r in ok if r.metrics.get("over_length")),
        "tags_in_json": sum(1 for r in ok if r.metrics.get("tags_in_json")),
        "word_kept": sum(1 for r in ok if r.metrics.get("word_echoed")),
        "ipa": sum(1 for r in ok if r.metrics.get("ipa")),
        "ru": sum(1 for r in ok if r.metrics.get("target_lang_share", 0) > 0.5),  # noqa: PLR2004
        "first_p50": round(statistics.median(firsts), 2) if firsts else 0,
        "total_p50": round(statistics.median(totals), 2) if totals else 0,
        "total_p90": round(quantile(totals, 0.9), 2),
        "judged": len(judged),
    }
    for key in JUDGE_KEYS:
        scores = [j[key] for j in judged if isinstance(j.get(key), (int, float))]
        summary[f"judge_{key}"] = round(statistics.mean(scores), 2) if scores else 0
    return summary


def group(runs: list[Run], by_answerer: bool = False) -> dict[tuple[str, str, str], list[Run]]:
    grouped: dict[tuple[str, str, str], list[Run]] = {}
    for run in runs:
        model = (run.answered_by or "-") if by_answerer else run.model
        grouped.setdefault((run.phase, model, run.lang), []).append(run)
    return grouped


def report(out: Path, phases: list[str], by_answerer: bool = False) -> None:
    runs = read_runs(out, phases)
    if not runs:
        raise SystemExit(f"nothing recorded under {out}")
    header = (
        f"{'phase':6} {'model':30} {'lg':3} {'n':>4} {'fail':>5} {'card':>6} {'fmt':>6} "
        f"{'word':>6} {'IPA':>6} {'ru':>6} {'typo':>6} {'slow':>6} "
        f"{'1st':>6} {'p50':>6} {'p90':>6} " + " ".join(f"{k[:4]:>5}" for k in JUDGE_KEYS)
    )
    print(header)
    print("-" * len(header))
    for (phase, model, lang), rows in sorted(group(runs, by_answerer).items()):
        s = summarize(rows)
        ok = s["n"] - s["failed"]
        print(
            f"{phase:6} {model:30} {lang:3} {s['n']:4} {s['failed']:5} "
            f"{pct(s['card_ok'], ok)} {pct(ok - s['format_bad'], ok)} "
            f"{pct(s['word_kept'], ok)} {pct(s['ipa'], ok)} {pct(s['ru'], ok)} "
            f"{pct(s['typos_caught'], s['typos'])} {pct(s['slow'], ok)} "
            f"{s['first_p50']:6.2f} {s['total_p50']:6.2f} {s['total_p90']:6.2f} "
            + " ".join(f"{s['judge_' + k]:5.2f}" for k in JUDGE_KEYS),
        )
    print("\ncard = valid ===CARD=== payload, fmt = clean HTML/no markdown,")
    print("word = payload echoed the input, ru = answer in the target language,")
    print("typo = misspelling came back with a correction offer (typo items only),")
    print(f"slow = answers over {SLOW_ANSWER:.0f}s, 1st/p50/p90 = seconds to first delta /")
    print("median / p90 whole answer. Judge columns are a 1-5 pre-filter, not the verdict.")


def review(out: Path, phases: list[str], lang: str, count: int) -> Path:
    """Emit the answers for the human pass — the rubric's final word."""
    runs = [r for r in read_runs(out, phases) if r.lang == lang and r.text]
    by_word: dict[str, list[Run]] = {}
    for run in runs:
        by_word.setdefault(run.word, []).append(run)
    lines = [f"# Human review — {lang}\n"]
    for word, rows in list(by_word.items())[:count]:
        lines.append(f"\n## {word} ({rows[0].shape})\n")
        for run in rows:
            analysis = split_answer(run.text)[0]
            problems = run.metrics.get("card_problems") or []
            answered = f" ({run.answered_by})" if run.answered_by != run.model else ""
            card = problems or "ok"
            lines.append(f"\n### {run.model}{answered} — {run.t_total}s, card: {card}\n")
            if run.judge:
                scores = {k: run.judge.get(k) for k in JUDGE_KEYS}
                lines.append(f"\njudge {scores}\n")
                for problem in run.judge.get("errors", []):
                    lines.append(f"\n- judge: {problem}\n")
            lines.append(f"\n{analysis}\n")
    path = out / f"review-{lang}.md"
    path.write_text("".join(lines), encoding="utf-8")
    return path


# ----------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["pool", "free", "paid", "judge", "report", "review"])
    parser.add_argument("--lang", nargs="+", default=["en", "de", "sr"], choices=list(LANGS))
    parser.add_argument("--limit", type=int, default=0, help="first N items per language")
    parser.add_argument("--model", nargs="+", default=[], help="free: pool model names")
    parser.add_argument(
        "--alias",
        nargs="+",
        default=["sonnet"],
        help="paid: catalog aliases, or provider:model-id for an uncurated model",
    )
    parser.add_argument("--judge", default="gpt", help="judge: paid alias doing the scoring")
    parser.add_argument("--phases", nargs="+", default=["pool", "free", "paid"])
    parser.add_argument("--sample", type=int, default=0, help="judge: cap the judged runs")
    parser.add_argument("--shapes", nargs="+", default=list({s for _, s in ITEMS["en"]}))
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument(
        "--pace",
        type=float,
        default=0.0,
        help="minimum seconds between call starts — model one person, not a burst",
    )
    parser.add_argument("--tag", default="", help="record under this phase name instead")
    parser.add_argument("--wait", type=float, default=45.0, help="whole-call budget, seconds")
    parser.add_argument("--retries", type=int, default=2, help="retries on a rate limit")
    parser.add_argument("--backoff", type=float, default=20.0)
    parser.add_argument("--count", type=int, default=8, help="review: words to include")
    parser.add_argument(
        "--by-answerer",
        action="store_true",
        help="report: group pool runs by the model that answered, not by the backend",
    )
    parser.add_argument("--out", default=str(Path(__file__).parent / ".bench"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.phase == "report":
        report(out, args.phases, args.by_answerer)
    elif args.phase == "review":
        log(f"wrote {review(out, args.phases, args.lang[0], args.count)}")
    else:
        runner = {"pool": run_pool, "free": run_free, "paid": run_paid, "judge": run_judge}
        started = time.monotonic()
        asyncio.run(runner[args.phase](args, out))
        spent = time.monotonic() - started
        log(f"{args.phase} done in {spent:.0f}s -> {out_path(out, args.phase)}")


if __name__ == "__main__":
    main()
