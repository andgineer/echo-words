"""End-to-end bench for the planned full articles, complete text chips and four cards.

The bench calls the real free pool. It checks the two future prompts as a flow:

* a text article covers every source word exactly once with chips, while keeping
  combinations whole;
* selected combination and function-word chips are sent back with their context;
* bare and context vocabulary answers retain morphology, usage, origin and
  examples in the PWA article;
* their payload can produce one note with four non-empty card fronts;
* every meaning can become a sense chip.

Raw answers are append-only so scoring can be changed without buying them again.

Run:
    uv run python experiments/one_note_bench.py run --resume
    uv run python experiments/one_note_bench.py report
"""

import argparse
import asyncio
import hashlib
import json
import os
import re
import statistics
import sys
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from backend_bench import (  # noqa: E402
    LANGS,
    Pacer,
    answer_language,
    drain,
    load_keys,
    log,
    parse_json_object,
    split_answer,
    word_hint,
)
from bench_items import SENTENCES  # noqa: E402
from llmbroker import AsyncBroker  # noqa: E402
from plan_trace import text_prompt, vocab_prompt  # noqa: E402


TARGET = "ru"
PROMPT_DIR = Path(__file__).parent / "prompts"
_WORD = re.compile(r"[^\W\d_]+(?:[-'’][^\W\d_]+)*", re.UNICODE)
_ELLIPSIS = re.compile(r"\s*(?:…|\.\.\.)\s*")
_ORIGIN = re.compile(r"происход|этимолог|заимств|восход|исконн|образован", re.IGNORECASE)
_USAGE = re.compile(r"употреб|использ|сочетан|сочетаем", re.IGNORECASE)
_MORPHOLOGY = re.compile(
    r"<table>|форм|спряж|склон|множествен|причаст|презенс|претерит|прошедш",
    re.IGNORECASE,
)
_ALLOWED_TAGS = {"b", "i", "table", "tr", "td"}


EN_TEXT = [
    (
        "I gave up after ten minutes.",
        (("give up",),),
        "combination",
    ),
    (
        "The book is on the table.",
        (),
        "function",
    ),
    (
        "The children are playing in the garden.",
        (),
        "plain",
    ),
    (
        "He is looking forward to the trip.",
        (("look forward to",),),
        "combination",
    ),
    (
        "Although it was raining, we went outside.",
        (),
        "punctuation",
    ),
]

BARE_CASES = [
    ("bare-en-bank", "en", "bank", False, False),
    ("bare-en-reluctant", "en", "reluctant", False, False),
    ("bare-en-give-up", "en", "give up", True, True),
    ("bare-de-bank", "de", "Bank", True, False),
    ("bare-de-verantwortung", "de", "Verantwortung", True, False),
    ("bare-de-rad", "de", "Rad fahren", True, True),
    ("bare-sr-grad", "sr", "град", True, False),
    ("bare-sr-umoran", "sr", "уморан", True, False),
    ("bare-sr-voditi", "sr", "водити рачуна", True, True),
]

# One combination and one standalone function word per source language.
CLICK_CASES = [
    ("click-en-combination", "text-en-0", "gave"),
    ("click-en-function", "text-en-1", "on"),
    ("click-de-combination", "text-de-0", "steht"),
    ("click-de-function", "text-de-0", "Er"),
    ("click-sr-combination", "text-sr-0", "вратио"),
    ("click-sr-function", "text-sr-0", "Он"),
]

EXPECTED_SURFACE_GROUPS = {
    "text-de-0": (("steht", "auf"),),
    "text-de-1": (("freue", "mich", "auf"),),
    "text-de-2": (("sagt", "ab"),),
    "text-de-3": (("nehmen", "unter", "die", "Lupe"),),
    "text-de-4": (("habe", "die", "Nase", "voll"),),
    "text-de-5": (("fällt", "aus"),),
    "text-de-6": (("kommt", "in", "Frage"),),
    "text-de-7": (("zieht", "um"),),
    "text-de-9": (("uns", "auf", "beschränken"),),
    "text-sr-0": (("се", "вратио"),),
    "text-sr-1": (("се", "јавио"),),
    "text-sr-2": (("se", "oblači"),),
    "text-sr-3": (("се", "изненадио"),),
    "text-sr-4": (("ми", "се", "иде"),),
    "text-sr-5": (("bojim", "se"),),
    "text-sr-6": (("Nadam", "se"),),
    "text-sr-7": (("se", "igraju"),),
    "text-sr-8": (("mi", "se", "čini"), ("u", "redu")),
    "text-en-0": (("gave", "up"),),
    "text-en-3": (("looking", "forward", "to"),),
}

EXPECTED_LOOKUPS = {
    "text-de-0": ("aufstehen",),
    "text-de-1": ("sich freuen auf",),
    "text-de-2": ("absagen",),
    "text-de-3": ("unter die Lupe nehmen",),
    "text-de-4": ("die Nase voll haben von",),
    "text-de-5": ("ausfallen",),
    "text-de-6": ("überhaupt nicht in Frage kommen",),
    "text-de-7": ("umziehen",),
    "text-de-9": ("sich beschränken auf",),
    "text-sr-0": ("вратити се",),
    "text-sr-1": ("јавити се",),
    "text-sr-2": ("oblačiti se",),
    "text-sr-3": ("изненадити се",),
    "text-sr-4": ("иде ми се",),
    "text-sr-5": ("bojati se",),
    "text-sr-6": ("nadati se",),
    "text-sr-7": ("igrati se",),
    "text-sr-8": ("činiti se", "u redu"),
    "text-en-0": ("give up",),
    "text-en-3": ("look forward to",),
}

# These texts contain no multi-word lexical lookup target. They catch the more
# expensive direction of error: turning ordinary grammar into one chip.
NO_COMBINATION_SHOTS = {
    "text-de-8",
    "text-de-10",
    "text-en-1",
    "text-en-2",
    "text-en-4",
    "text-sr-9",
}

FUNCTION_WORDS = {
    "en": {"i", "the", "is", "on", "after", "he", "to", "it", "was", "we", "in"},
    "de": {"er", "ich", "sie", "wir", "den", "jeden", "um", "sich", "auf", "das", "ist"},
    "sr": {"он", "се", "ми", "она", "ne", "da", "na", "је", "u", "није"},
}


@dataclass
class Shot:
    shot_id: str
    kind: str
    lang: str
    source: str
    context: str = ""
    expected_groups: list[list[str]] = field(default_factory=list)
    expects_morphology: bool = False
    expression: bool = False
    prompt_hash: str = ""
    answered_by: str | None = None
    t_first: float | None = None
    t_total: float | None = None
    error: str | None = None
    text: str = ""
    payload: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)


def normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", str(value)).casefold().split()).strip(
        " .,;:!?…",
    )


def tokens(value: str) -> list[str]:
    return [normalize(token) for token in _WORD.findall(value)]


def prompt_fingerprint(kind: str) -> str:
    name = "one-note-text.txt" if kind == "text" else "one-note-vocab.txt"
    return hashlib.sha256((PROMPT_DIR / name).read_bytes()).hexdigest()[:12]


def text_shots() -> list[Shot]:
    rows: list[Shot] = []
    for lang, fixtures in SENTENCES.items():
        for index, (source, expected, _fixture_kind) in enumerate(fixtures):
            rows.append(
                Shot(
                    f"text-{lang}-{index}",
                    "text",
                    lang,
                    source,
                    expected_groups=[list(group) for group in expected],
                    prompt_hash=prompt_fingerprint("text"),
                ),
            )
    for index, (source, expected, _fixture_kind) in enumerate(EN_TEXT):
        rows.append(
            Shot(
                f"text-en-{index}",
                "text",
                "en",
                source,
                expected_groups=[list(group) for group in expected],
                prompt_hash=prompt_fingerprint("text"),
            ),
        )
    return rows


def bare_shots() -> list[Shot]:
    return [
        Shot(
            shot_id,
            "bare",
            lang,
            source,
            expects_morphology=expects_morphology,
            expression=expression,
            prompt_hash=prompt_fingerprint("bare"),
        )
        for shot_id, lang, source, expects_morphology, expression in BARE_CASES
    ]


def output_path(out: Path) -> Path:
    return out / "answers.jsonl"


def append(out: Path, shot: Shot) -> None:
    path = output_path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(shot), ensure_ascii=False) + "\n")


def read(out: Path) -> dict[str, Shot]:
    path = output_path(out)
    if not path.exists():
        return {}
    rows: dict[str, Shot] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            shot = Shot(**json.loads(line))
            rows[shot.shot_id] = score(shot)
    return rows


def segments(payload: dict) -> list[dict]:
    raw = payload.get("segments")
    return [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []


def combinations(payload: dict) -> list[dict]:
    raw = payload.get("combinations")
    return [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []


def match_surface_words(source: list[str], surface: list[str], claimed: set[int]) -> list[int]:
    matched = []
    for word in surface:
        wanted = normalize(word)
        index = next(
            (
                position
                for position, source_word in enumerate(source)
                if position not in claimed
                and position not in matched
                and normalize(source_word) == wanted
            ),
            None,
        )
        if index is not None:
            matched.append(index)
    return sorted(matched)


def surface_parts(source: list[str], indices: list[int]) -> list[str]:
    groups: list[list[int]] = []
    for index in indices:
        if groups and index == groups[-1][-1] + 1:
            groups[-1].append(index)
        else:
            groups.append([index])
    return [" ".join(source[index] for index in group) for group in groups]


def text_segments(
    payload: dict,
    source: str,
    lang: str,
) -> tuple[list[dict], list[str], list[str]]:
    source_forms = _WORD.findall(unicodedata.normalize("NFC", source))
    claimed: set[int] = set()
    prepared: list[tuple[int, dict]] = []
    invalid: list[str] = []
    invalid_lookups: list[str] = []
    for item in combinations(payload):
        lookup = str(item.get("label", "")).strip()
        if not lookup:
            invalid_lookups.append(lookup)
        elif word_hint(lookup, lang) is not None:
            invalid_lookups.append(lookup)
        raw_surface = str(item.get("surface", "")).strip()
        surface_words = _WORD.findall(unicodedata.normalize("NFC", raw_surface))
        matched = match_surface_words(source_forms, surface_words, claimed)
        if len(matched) < 2:
            invalid.append(raw_surface)
            continue
        claimed.update(matched)
        parts = surface_parts(source_forms, matched)
        prepared.append(
            (
                min(matched),
                {
                    "surface": " … ".join(parts),
                    "label": " ".join(source_forms[index] for index in matched),
                    "context": source,
                    "why": item.get("why", ""),
                },
            ),
        )
    for index, form in enumerate(source_forms):
        if index not in claimed:
            prepared.append(
                (
                    index,
                    {"surface": form, "label": form, "context": source, "why": ""},
                ),
            )
    prepared.sort(key=lambda pair: pair[0])
    return [item for _position, item in prepared], invalid, invalid_lookups


def meanings(payload: dict) -> list[dict]:
    raw = payload.get("meanings")
    if not isinstance(raw, list):
        return []
    normalized = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        value = dict(item)
        translations = value.get("translations", value.get("translation"))
        if isinstance(translations, str):
            translations = [translations]
        value["translations"] = translations
        examples = value.get("examples")
        if isinstance(examples, dict):
            value["examples"] = [examples]
        normalized.append(value)
    return normalized


def find_part(source: list[str], part: list[str], claimed: set[int]) -> list[int]:
    for start in range(len(source) - len(part) + 1):
        indices = list(range(start, start + len(part)))
        if not claimed.intersection(indices) and source[start : start + len(part)] == part:
            return indices
    return []


def coverage(source: str, listed: list[dict], lang: str) -> dict:
    source_words = tokens(source)
    claimed: set[int] = set()
    unmatched: list[str] = []
    first_positions: list[int] = []
    for segment in listed:
        surface = str(segment.get("surface", "")).strip()
        segment_indices: list[int] = []
        pending: list[int] = []
        matched = True
        for chunk in _ELLIPSIS.split(surface):
            part = tokens(chunk)
            found = find_part(source_words, part, claimed | set(pending)) if part else []
            if not found:
                unmatched.append(surface)
                matched = False
                break
            pending.extend(found)
        if matched and pending:
            segment_indices = pending
        if segment_indices:
            claimed.update(segment_indices)
            first_positions.append(min(segment_indices))
    function_indices = {
        index for index, token in enumerate(source_words) if token in FUNCTION_WORDS[lang]
    }
    labels = [str(item.get("label", "")).strip() for item in listed]
    assembled_labels = [
        " ".join(part.strip() for part in _ELLIPSIS.split(str(item.get("surface", ""))) if part.strip())
        for item in listed
    ]
    return {
        "source_words": source_words,
        "words_total": len(source_words),
        "words_covered": len(claimed),
        "coverage": len(claimed) / len(source_words) if source_words else 1.0,
        "missing": [word for index, word in enumerate(source_words) if index not in claimed],
        "unmatched_surfaces": unmatched,
        "source_order": first_positions == sorted(first_positions),
        "function_total": len(function_indices),
        "function_covered": len(function_indices & claimed),
        "contexts_exact": all(item.get("context") == source for item in listed),
        "chip_context_ready": True,
        "labels_valid": all(label and word_hint(label, lang) is None for label in labels),
        "labels_preserve_forms": labels == assembled_labels,
        "labels": labels,
    }


def expected_found(shot_id: str, listed: list[dict]) -> tuple[int, int]:
    expected = EXPECTED_SURFACE_GROUPS.get(shot_id, ())
    returned = [set(tokens(str(item.get("surface", "")))) for item in listed]
    found = sum(
        any(set(normalize(word) for word in group).issubset(item) for item in returned)
        for group in expected
    )
    return found, len(expected)


def expected_lookups_found(shot_id: str, payload: dict) -> tuple[int, int]:
    expected = EXPECTED_LOOKUPS.get(shot_id, ())
    returned = {normalize(item.get("label", "")) for item in combinations(payload)}
    found = sum(normalize(label) in returned for label in expected)
    return found, len(expected)


def format_ok(analysis: str) -> bool:
    tags = {tag.casefold() for tag in re.findall(r"</?([A-Za-z][A-Za-z0-9]*)", analysis)}
    markdown = bool(
        re.search(
            r"\*\*|\*[^*\n]+\*|^#{1,6} |^\s*[-*] |^\s*\d+[.)] ",
            analysis,
            re.MULTILINE,
        ),
    )
    return not (tags - _ALLOWED_TAGS) and not markdown


def example_preserves_text(example: dict) -> bool:
    return (
        isinstance(example.get("text"), str)
        and isinstance(example.get("highlighted"), str)
        and re.sub(r"</?b>", "", example["highlighted"]) == example["text"]
    )


def example_ready(example: dict) -> bool:
    return (
        all(isinstance(example.get(key), str) and example[key].strip() for key in (
            "text",
            "translation",
            "highlighted",
            "gapped",
        ))
        and "<b>" in example["highlighted"]
        and "___" in example["gapped"]
    )


def meaning_ok(value: dict) -> bool:
    translations = value.get("translations")
    examples = value.get("examples")
    if not isinstance(translations, list) or not translations or not isinstance(examples, list) or not examples:
        return False
    for example in examples:
        if not isinstance(example, dict) or not example_ready(example):
            return False
    return True


def vocab_metrics(shot: Shot, analysis: str) -> dict:
    listed = meanings(shot.payload)
    raw_sense = shot.payload.get("context_sense")
    sense_valid = (
        isinstance(raw_sense, int)
        and not isinstance(raw_sense, bool)
        and 0 <= raw_sense < len(listed)
    )
    index = raw_sense if shot.context and sense_valid else 0
    selected = listed[index] if listed and 0 <= index < len(listed) else {}
    examples = selected.get("examples") if isinstance(selected.get("examples"), list) else []
    first = examples[0] if examples and isinstance(examples[0], dict) else {}
    translations = selected.get("translations") if isinstance(selected.get("translations"), list) else []
    word = shot.payload.get("word")
    cards_ready = bool(
        isinstance(word, str)
        and word.strip()
        and translations
        and example_ready(first)
    )
    segment_list = segments(shot.payload)
    expression_context = str(first.get("text", ""))
    bolded = tokens(" ".join(re.findall(r"<b>(.*?)</b>", str(first.get("highlighted", "")))))
    requested_parts = tokens(shot.source)
    return {
        "word_valid": isinstance(word, str) and bool(word.strip()) and word_hint(word, shot.lang) is None,
        "meanings": len(listed),
        "meanings_valid": bool(listed) and all(meaning_ok(meaning) for meaning in listed),
        "four_cards_ready": cards_ready,
        "sense_chips_ready": bool(listed) and all(
            isinstance(meaning.get("examples"), list) and bool(meaning["examples"])
            for meaning in listed
        ),
        "examples_preserve_text": bool(listed)
        and all(
            isinstance(meaning.get("examples"), list)
            and all(
                isinstance(example, dict) and example_preserves_text(example)
                for example in meaning["examples"]
            )
            for meaning in listed
        ),
        "origin": bool(_ORIGIN.search(analysis)),
        "usage": bool(_USAGE.search(analysis)),
        "morphology": bool(_MORPHOLOGY.search(analysis)),
        "morphology_required": shot.expects_morphology,
        "context_sense_valid": sense_valid if shot.context else "context_sense" not in shot.payload,
        "context_example_exact": first.get("text") == shot.context if shot.context else True,
        "context_parts_highlighted": all(part in bolded for part in requested_parts)
        if shot.context
        else True,
        "context_segments_empty": not segment_list if shot.context else True,
        "expression_parts": len(segment_list) if shot.expression and not shot.context else 0,
        "expression_contexts_exact": all(
            item.get("context") == expression_context for item in segment_list
        )
        if shot.expression and segment_list
        else True,
        "card_fronts": [
            f"{word}",
            ", ".join(map(str, translations)),
            str(first.get("highlighted", "")),
            str(first.get("gapped", "")),
        ]
        if cards_ready
        else [],
    }


def score(shot: Shot) -> Shot:
    analysis, raw_payload = split_answer(shot.text)
    payload, parse_error = parse_json_object(raw_payload)
    shot.payload = payload or {}
    common = {
        "answered": bool(shot.text) and not shot.error,
        "parse_error": parse_error,
        "payload_valid": payload is not None,
        "answer_language": answer_language(analysis),
        "format_ok": format_ok(analysis),
        "article_chars": len(analysis),
    }
    if shot.kind == "text":
        raw_combinations = combinations(shot.payload)
        listed, invalid_combinations, invalid_lookups = text_segments(
            shot.payload,
            shot.source,
            shot.lang,
        )
        covered = coverage(shot.source, listed, shot.lang)
        found, total = expected_found(shot.shot_id, listed)
        lookups_found, lookups_total = expected_lookups_found(shot.shot_id, shot.payload)
        shot.metrics = {
            **common,
            **covered,
            "segments": len(listed),
            "expected_found": found,
            "expected_total": total,
            "expected_lookups_found": lookups_found,
            "expected_lookups_total": lookups_total,
            "combination_contract_valid": isinstance(
                shot.payload.get("combinations"),
                list,
            ),
            "combination_fragments_ignored": invalid_combinations,
            "combination_lookup_hints_ignored": invalid_lookups,
            "combination_answer_usable": True,
            "negative_control_clean": not raw_combinations
            if shot.shot_id in NO_COMBINATION_SHOTS
            else True,
            "minimal_segment_contract": all(
                set(item).issubset({"label", "surface", "why"})
                for item in raw_combinations
            ),
            "no_card_fields": "word" not in shot.payload and "meanings" not in shot.payload,
        }
    else:
        shot.metrics = {**common, **vocab_metrics(shot, analysis)}
    return shot


def prompt_for(shot: Shot) -> str:
    return (
        text_prompt(shot.source, shot.lang, TARGET)
        if shot.kind == "text"
        else vocab_prompt(shot.source, shot.lang, TARGET, shot.context)
    )


def find_segment(shot: Shot, selector: str) -> dict | None:
    wanted = normalize(selector)
    for segment in segments(shot.payload):
        if wanted in tokens(str(segment.get("surface", ""))):
            return segment
    return None


def context_shots(recorded: dict[str, Shot]) -> list[Shot]:
    rows = []
    for shot_id, text_id, selector in CLICK_CASES:
        source = recorded.get(text_id)
        if source is not None:
            prepared, _invalid, _invalid_lookups = text_segments(
                source.payload,
                source.source,
                source.lang,
            )
            source.payload = {
                **source.payload,
                "segments": prepared,
            }
        segment = find_segment(source, selector) if source else None
        if source is None or segment is None:
            continue
        rows.append(
            Shot(
                shot_id,
                "context",
                source.lang,
                str(segment.get("label", selector)),
                context=source.source,
                expects_morphology=shot_id.endswith("-combination"),
                prompt_hash=prompt_fingerprint("context"),
            ),
        )
    return rows


async def run_batch(args, out: Path, broker: AsyncBroker, jobs: list[Shot]) -> None:
    gate = asyncio.Semaphore(args.concurrency)
    pacer = Pacer(args.pace)

    async def one(shot: Shot) -> None:
        await pacer.wait()
        async with gate:
            handle = broker.stream(
                prompt_for(shot),
                operation=f"one-note-{shot.kind}-{shot.lang}",
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
        append(out, shot)
        log(
            f"{shot.shot_id}: {shot.source!r} -> {shot.answered_by or '?'} "
            f"{shot.t_total}s {shot.error or ''}",
        )

    await asyncio.gather(*(one(shot) for shot in jobs))


def complete(shot: Shot) -> bool:
    if not shot.metrics.get("payload_valid"):
        return False
    if shot.kind == "text":
        return bool(
            shot.metrics.get("combination_contract_valid")
            and shot.metrics.get("combination_answer_usable")
        )
    return bool(shot.metrics.get("four_cards_ready"))


async def run(args, out: Path) -> None:
    os.environ.update(load_keys())
    broker = AsyncBroker(home=out / "llmbroker")
    try:
        recorded = read(out)
        initial = [*text_shots(), *bare_shots()]
        pending = [
            shot
            for shot in initial
            if not (
                args.resume
                and (old := recorded.get(shot.shot_id)) is not None
                and old.prompt_hash == shot.prompt_hash
                and old.source == shot.source
                and old.context == shot.context
                and complete(old)
            )
        ]
        log(f"initial: {len(pending)} calls")
        await run_batch(args, out, broker, pending)
        recorded = read(out)
        clicks = context_shots(recorded)
        pending_clicks = [
            shot
            for shot in clicks
            if not (
                args.resume
                and (old := recorded.get(shot.shot_id)) is not None
                and old.prompt_hash == shot.prompt_hash
                and old.source == shot.source
                and old.context == shot.context
                and complete(old)
            )
        ]
        log(f"clicks: {len(pending_clicks)} calls")
        await run_batch(args, out, broker, pending_clicks)
    finally:
        await broker.aclose()


async def run_clicks(args, out: Path) -> None:
    os.environ.update(load_keys())
    broker = AsyncBroker(home=out / "llmbroker")
    try:
        recorded = read(out)
        clicks = context_shots(recorded)
        pending = [
            shot
            for shot in clicks
            if not (
                args.resume
                and (old := recorded.get(shot.shot_id)) is not None
                and old.prompt_hash == shot.prompt_hash
                and old.source == shot.source
                and old.context == shot.context
                and complete(old)
            )
        ]
        log(f"clicks: {len(pending)} calls")
        await run_batch(args, out, broker, pending)
    finally:
        await broker.aclose()


def ratio(rows: list[Shot], key: str) -> str:
    passed = sum(bool(row.metrics.get(key)) for row in rows)
    return f"{passed}/{len(rows)} ({passed / len(rows):.0%})" if rows else "-"


def report(out: Path) -> None:
    rows = list(read(out).values())
    if not rows:
        raise SystemExit(f"no answers in {output_path(out)}")
    text_rows = [row for row in rows if row.kind == "text"]
    vocab_rows = [row for row in rows if row.kind in {"bare", "context"}]
    context_rows = [row for row in rows if row.kind == "context"]
    required_morph = [
        row
        for row in vocab_rows
        if row.expects_morphology or row.shot_id.endswith("-combination")
    ]
    print(f"{len(rows)} recorded answers\n")
    print("TEXT → ARTICLE + COMPLETE CHIPS + NO NOTE")
    print(f"  parseable payload             {ratio(text_rows, 'payload_valid')}")
    print(f"  exact 100% word coverage      {sum(r.metrics.get('coverage') == 1 for r in text_rows)}/{len(text_rows)}")
    words_total = sum(int(row.metrics.get("words_total", 0)) for row in text_rows)
    words_covered = sum(int(row.metrics.get("words_covered", 0)) for row in text_rows)
    function_total = sum(int(row.metrics.get("function_total", 0)) for row in text_rows)
    function_covered = sum(int(row.metrics.get("function_covered", 0)) for row in text_rows)
    expected_total = sum(int(row.metrics.get("expected_total", 0)) for row in text_rows)
    expected_found_count = sum(int(row.metrics.get("expected_found", 0)) for row in text_rows)
    lookup_total = sum(int(row.metrics.get("expected_lookups_total", 0)) for row in text_rows)
    lookup_found = sum(int(row.metrics.get("expected_lookups_found", 0)) for row in text_rows)
    print(f"  all words covered             {words_covered}/{words_total} ({words_covered / words_total:.0%})")
    print(f"  function words covered        {function_covered}/{function_total} ({function_covered / function_total:.0%})")
    print(f"  expected lexical units found  {lookup_found}/{lookup_total}")
    print(f"  expected source parts grouped {expected_found_count}/{expected_total}")
    negative_rows = [row for row in text_rows if row.shot_id in NO_COMBINATION_SHOTS]
    print(f"  trap-free texts stayed empty  {ratio(negative_rows, 'negative_control_clean')}")
    print(f"  combination contract valid    {ratio(text_rows, 'combination_contract_valid')}")
    print(f"  combination answers usable    {ratio(text_rows, 'combination_answer_usable')}")
    print(f"  chip context backend-owned    {ratio(text_rows, 'chip_context_ready')}")
    print(f"  labels pass input validation  {ratio(text_rows, 'labels_valid')}")
    print(f"  labels preserve visible forms {ratio(text_rows, 'labels_preserve_forms')}")
    print(f"  no model-made label/context   {ratio(text_rows, 'minimal_segment_contract')}")
    print(f"  chips stay in source order    {ratio(text_rows, 'source_order')}")
    print(f"  answer in target language     {sum(r.metrics.get('answer_language') == TARGET for r in text_rows)}/{len(text_rows)}")
    print(f"  article format clean          {ratio(text_rows, 'format_ok')}")
    print(f"  no card fields                {ratio(text_rows, 'no_card_fields')}\n")

    print("VOCAB/CLICK → FULL ARTICLE + ONE NOTE + FOUR CARDS + SENSE CHIPS")
    print(f"  parseable payload             {ratio(vocab_rows, 'payload_valid')}")
    print(f"  every meaning complete        {ratio(vocab_rows, 'meanings_valid')}")
    print(f"  four card fronts ready        {ratio(vocab_rows, 'four_cards_ready')}")
    print(f"  sense chips ready             {ratio(vocab_rows, 'sense_chips_ready')}")
    print(f"  examples preserve text        {ratio(vocab_rows, 'examples_preserve_text')}")
    print(f"  usage present                 {ratio(vocab_rows, 'usage')}")
    print(f"  origin present                {ratio(vocab_rows, 'origin')}")
    print(f"  required morphology present   {ratio(required_morph, 'morphology')}")
    print(f"  context_sense valid/absent    {ratio(vocab_rows, 'context_sense_valid')}")
    print(f"  clicked context is example 1  {ratio(context_rows, 'context_example_exact')}")
    print(f"  all clicked parts highlighted {ratio(context_rows, 'context_parts_highlighted')}")
    print(f"  context answer has no parts   {ratio(context_rows, 'context_segments_empty')}")
    print(f"  article format clean          {ratio(vocab_rows, 'format_ok')}\n")

    times = [row.t_total for row in rows if row.t_total is not None and not row.error]
    if times:
        print(f"latency p50 {statistics.median(times):.1f}s")
    print("\nFAILURES")
    failure_keys = {
        "text": (
            "payload_valid",
            "combination_contract_valid",
            "combination_answer_usable",
            "negative_control_clean",
            "labels_valid",
            "labels_preserve_forms",
            "minimal_segment_contract",
            "source_order",
            "format_ok",
            "no_card_fields",
        ),
        "vocab": (
            "payload_valid",
            "meanings_valid",
            "four_cards_ready",
            "sense_chips_ready",
            "examples_preserve_text",
            "usage",
            "origin",
            "context_sense_valid",
            "format_ok",
        ),
    }
    for row in sorted(rows, key=lambda value: value.shot_id):
        keys = failure_keys["text" if row.kind == "text" else "vocab"]
        failed = [key for key in keys if not row.metrics.get(key)]
        if row.kind == "text" and row.metrics.get("coverage") != 1:
            failed.append(f"coverage={row.metrics.get('coverage', 0):.0%}")
        if row.kind == "text" and row.metrics.get("expected_found") != row.metrics.get(
            "expected_total",
        ):
            failed.append(
                f"grouped={row.metrics.get('expected_found', 0)}/"
                f"{row.metrics.get('expected_total', 0)}",
            )
        if row.kind == "text" and row.metrics.get("expected_lookups_found") != row.metrics.get(
            "expected_lookups_total",
        ):
            failed.append(
                f"lookups={row.metrics.get('expected_lookups_found', 0)}/"
                f"{row.metrics.get('expected_lookups_total', 0)}",
            )
        if row.expects_morphology and not row.metrics.get("morphology"):
            failed.append("morphology")
        if row.kind == "context" and not row.metrics.get("context_example_exact"):
            failed.append("context_example_exact")
        if row.kind == "context" and not row.metrics.get("context_parts_highlighted"):
            failed.append("context_parts_highlighted")
        if failed:
            print(f"  {row.shot_id} {row.source!r}: {', '.join(failed)}")
            if row.kind == "text" and row.metrics.get("missing"):
                print(f"    missing: {row.metrics['missing']}")
            if row.error:
                print(f"    error: {row.error}")


def show(out: Path, shot_ids: list[str]) -> None:
    rows = read(out)
    picked = shot_ids or sorted(rows)
    for shot_id in picked:
        shot = rows.get(shot_id)
        if shot is None:
            continue
        print(f"\n=== {shot.shot_id} {shot.lang} {shot.source!r} ===")
        print(shot.text)
        print("\nMETRICS", json.dumps(shot.metrics, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["run", "run-clicks", "report", "show"])
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--pace", type=float, default=2.0)
    parser.add_argument("--wait", type=float, default=75.0)
    parser.add_argument("--shot", nargs="+", default=[])
    parser.add_argument("--out", default=str(Path(__file__).parent / ".bench-one-note"))
    args = parser.parse_args()
    out = Path(args.out)
    if args.action == "run":
        asyncio.run(run(args, out))
    elif args.action == "run-clicks":
        asyncio.run(run_clicks(args, out))
    elif args.action == "report":
        report(out)
    else:
        show(out, args.shot)


if __name__ == "__main__":
    main()
