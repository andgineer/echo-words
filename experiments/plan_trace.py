"""Run characteristic post-plan flows through real draft prompts and print traces.

This is a model of the fallback selected by Step 0: the shipped surface router
stays, while the vocabulary and text prompts receive the future one-note/four-card
contracts. It calls the real free pool and stores raw answers in a gitignored
JSONL file.
"""

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from backend_bench import LANGS, TARGETS, drain, load_keys, log, parse_json_object, split_answer  # noqa: E402
from echo_words.languages import plain_text, plain_unit  # noqa: E402
from echo_words.shape import classify, word_count  # noqa: E402
from llmbroker import AsyncBroker  # noqa: E402


PROMPTS = Path(__file__).parent / "prompts"


@dataclass
class Trace:
    trace_id: str
    source: str
    lang: str
    shape: str
    context: str = ""
    trigger: str = "submit box"
    prompt_kind: str = ""
    answered_by: str | None = None
    t_first: float | None = None
    t_total: float | None = None
    error: str | None = None
    text: str = ""
    payload: dict = field(default_factory=dict)


def vocab_prompt(source: str, lang: str, target: str, context: str = "") -> str:
    template = (PROMPTS / "one-note-vocab.txt").read_text(encoding="utf-8")
    if context:
        request = f'Unit to card: "{source}"\nContext: "{context}"'
        context_field = ', "context_sense": <zero-based index of the context sense>'
        context_rule = (
            "context_sense is required because context was supplied. It is the zero-based "
            "index into meanings of the sense used in that context."
        )
    else:
        request = f'Input from the submit box: "{source}"'
        context_field = ""
        context_rule = "No context was supplied. Do not include context_sense."
    source_lang, hints = LANGS[lang]
    return template.format(
        source_lang=source_lang,
        target_lang=TARGETS[target][0],
        source_hints=hints,
        request=request,
        context_field=context_field,
        context_rule=context_rule,
    )


def text_prompt(source: str, lang: str, target: str) -> str:
    source_lang, hints = LANGS[lang]
    return (PROMPTS / "one-note-text.txt").read_text(encoding="utf-8").format(
        source_lang=source_lang,
        target_lang=TARGETS[target][0],
        source_hints=hints,
        text=source,
    )


def routed(trace_id: str, source: str, lang: str) -> Trace:
    shape = classify(source)
    normalized = plain_text(source) if shape == "text" else plain_unit(source)
    return Trace(trace_id, normalized, lang, shape, prompt_kind=shape)


def clicked(trace_id: str, source: str, lang: str, context: str) -> Trace:
    return Trace(
        trace_id,
        plain_unit(source),
        lang,
        "unit",
        context=plain_text(context),
        trigger=f"chip {source!r}",
        prompt_kind="unit",
    )


def build_prompt(trace: Trace, target: str) -> str:
    if trace.shape == "text":
        return text_prompt(trace.source, trace.lang, target)
    return vocab_prompt(trace.source, trace.lang, target, trace.context)


def output_path(out: Path) -> Path:
    return out / "trace.jsonl"


def append(out: Path, trace: Trace) -> None:
    path = output_path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(trace), ensure_ascii=False) + "\n")


def read(out: Path) -> dict[str, Trace]:
    path = output_path(out)
    if not path.exists():
        return {}
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            trace = Trace(**json.loads(line))
            rows[trace.trace_id] = trace
    return rows


async def call(broker: AsyncBroker, trace: Trace, target: str, out: Path, wait: float) -> Trace:
    handle = broker.stream(
        build_prompt(trace, target),
        operation=f"plan-trace-{trace.lang}",
        wait=wait,
    )
    try:
        await drain(handle, trace)
        trace.answered_by = handle.llm_name
    except Exception as exc:  # noqa: BLE001 - a provider failure belongs in the trace
        trace.error = f"{type(exc).__name__}: {exc}"
        trace.answered_by = handle.llm_name
    finally:
        await handle.aclose()
    _analysis, payload = split_answer(trace.text)
    parsed, _error = parse_json_object(payload)
    trace.payload = parsed or {}
    append(out, trace)
    log(f"{trace.trace_id}: {trace.source!r} -> {trace.answered_by or '?'} {trace.t_total}s {trace.error or ''}")
    return trace


def segments(trace: Trace) -> list[dict]:
    value = trace.payload.get("segments")
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def meanings(trace: Trace) -> list[dict]:
    value = trace.payload.get("meanings")
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def choose_segment(trace: Trace, label: str) -> dict:
    return next(
        (item for item in segments(trace) if str(item.get("label", "")).casefold() == label.casefold()),
        {"label": label, "context": trace.source},
    )


def choose_bank_sense(trace: Trace) -> dict:
    bank_meanings = meanings(trace)
    return next(
        (
            meaning
            for meaning in bank_meanings
            if "берег" in " ".join(map(str, meaning.get("translations", []))).casefold()
        ),
        bank_meanings[-1] if bank_meanings else {},
    )


async def run(args, out: Path) -> None:
    import os

    os.environ.update(load_keys())
    broker = AsyncBroker(home=out / "llmbroker")
    try:
        if args.flow == "expression":
            initial = [routed("expression-rad-fixed", "Rad fahren", "de")]
        else:
            initial = [
                routed("word-bank", "bank", "en"),
                routed("expression-rad", "Rad fahren", "de"),
                routed("sentence-aufstehen", "Er steht jeden Morgen um sechs auf.", "de"),
                routed("short-clause-cuvam", "чувам се.", "sr"),
            ]
        results = {}
        for trace in initial:
            results[trace.trace_id] = await call(broker, trace, args.target, out, args.wait)

        if args.flow == "expression":
            fahren = choose_segment(results["expression-rad-fixed"], "fahren")
            await call(
                broker,
                clicked(
                    "click-fahren-fixed",
                    str(fahren.get("label", "fahren")),
                    "de",
                    str(fahren.get("context", "Ich möchte heute Rad fahren.")),
                ),
                args.target,
                out,
                args.wait,
            )
            return
        auf = choose_segment(results["sentence-aufstehen"], "aufstehen")
        fahren = choose_segment(results["expression-rad"], "fahren")
        river = choose_bank_sense(results["word-bank"])
        examples = river.get("examples") if isinstance(river.get("examples"), list) else []
        river_context = str(examples[0].get("text", "")) if examples and isinstance(examples[0], dict) else "They sat on the bank of the river."
        followups = [
            clicked(
                "click-aufstehen",
                str(auf.get("label", "aufstehen")),
                "de",
                str(auf.get("context", results["sentence-aufstehen"].source)),
            ),
            clicked("click-fahren", str(fahren.get("label", "fahren")), "de", str(fahren.get("context", "Rad fahren"))),
            clicked("click-bank-river", "bank", "en", river_context),
        ]
        for trace in followups:
            await call(broker, trace, args.target, out, args.wait)
    finally:
        await broker.aclose()


def selected_meaning(trace: Trace) -> tuple[int, dict]:
    listed = meanings(trace)
    raw_index = trace.payload.get("context_sense", 0)
    index = raw_index if isinstance(raw_index, int) and not isinstance(raw_index, bool) else 0
    if not 0 <= index < len(listed):
        index = 0
    return index, listed[index] if listed else {}


def chip_summary(trace: Trace) -> list[dict]:
    if trace.shape == "text" or (not trace.context and word_count(trace.source) > 1 and segments(trace)):
        return [
            {
                "label": item.get("label", ""),
                "reason": item.get("why", ""),
                "context": item.get("context", trace.source),
            }
            for item in segments(trace)
        ]
    return [
        {
            "label": trace.payload.get("word", trace.source),
            "reason": ", ".join(map(str, meaning.get("translations", []))),
            "context": str((meaning.get("examples") or [{}])[0].get("text", "")),
        }
        for meaning in meanings(trace)
    ]


def show(out: Path) -> None:
    for trace in read(out).values():
        analysis, _payload = split_answer(trace.text)
        print(f"\n=== {trace.trace_id} ===")
        print(f"Поступил текст: {trace.source!r} ({trace.trigger})")
        print(f"Роутер/запрос: {trace.shape} -> {trace.prompt_kind} prompt")
        print(f"LLM ({trace.answered_by}) вернула:\n{analysis}")
        if trace.shape == "text":
            print("Anki: карточек нет")
        else:
            index, meaning = selected_meaning(trace)
            translations = ", ".join(map(str, meaning.get("translations", [])))
            label = str(meaning.get("label", ""))
            examples = meaning.get("examples") if isinstance(meaning.get("examples"), list) else []
            example = examples[0] if examples and isinstance(examples[0], dict) else {}
            word = trace.payload.get("word", trace.source)
            suffix = f" ({label})" if len(meanings(trace)) > 1 and label else ""
            print(f"Anki: одна note, sense #{index}, 4 карточки")
            print(f"  1. {word}{suffix} -> {translations}")
            print(f"  2. {translations}{suffix} -> {word}")
            print(f"  3. {example.get('highlighted', '')} -> {translations}; {word}")
            print(f"  4. {translations}; {example.get('gapped', '')} -> {word}")
        print("Чипы на фронт:")
        for chip in chip_summary(trace):
            print(f"  {chip['label']} — {chip['reason']} [context: {chip['context']}]")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["run", "show"])
    parser.add_argument("--target", choices=sorted(TARGETS), default="ru")
    parser.add_argument("--flow", choices=["all", "expression"], default="all")
    parser.add_argument("--wait", type=float, default=75.0)
    parser.add_argument("--out", default=str(Path(__file__).parent / ".bench-plan-trace"))
    args = parser.parse_args()
    out = Path(args.out)
    asyncio.run(run(args, out)) if args.action == "run" else show(out)


if __name__ == "__main__":
    main()
