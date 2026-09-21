"""Paid-tier screen: which model, at which reasoning effort and service tier, answers
the deeper article and the card fast enough — and what it would cost at production volume.

Each arm is a model reached over llmbroker's own request builder and SSE reader, the
path the direct client takes, with the arm's request parameters added. The chunks are
read here rather than through ``AsyncDirectClient.stream`` because the screen needs what
that stream drops: the usage block, reasoning tokens included, and the service tier the
provider actually granted.

    uv run python experiments/tier_screen.py run --job detail
    uv run python experiments/tier_screen.py run --job card --arm luna-none haiku
    uv run python experiments/tier_screen.py report

Outside CI; it calls real models and spends real money.
"""

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from llmbroker.chat import aiter_chat_chunks, build_chat_request, parse_stream_chunk, provider_error
from llmbroker.http_status import DETAIL_SNIPPET, ERROR_FLOOR

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from echo_words.languages import load_languages  # noqa: E402
from echo_words.prompt import build_extended_prompt, build_prompt, extract_answer  # noqa: E402

TARGET_NAME = "Russian"
LANGUAGES = load_languages(REPO / "languages.example.toml")
OPENAI = ("https://api.openai.com/v1", "OPENAI_API_KEY")
ANTHROPIC = ("https://api.anthropic.com/v1", "ANTHROPIC_API_KEY")

# USD per million tokens: input, output. Priority doubles OpenAI's standard rate.
PRICES = {
    ("gpt-5.6-luna", "default"): (0.20, 1.20),
    ("gpt-5.6-luna", "priority"): (0.40, 2.40),
    ("gpt-5.6-terra", "default"): (2.00, 12.00),
    ("gpt-5.6-terra", "priority"): (4.00, 24.00),
    ("gpt-5.6-sol", "default"): (4.00, 20.00),
    ("gpt-5.6-sol", "priority"): (8.00, 40.00),
    ("claude-haiku-4-5", "default"): (1.00, 5.00),
    ("claude-sonnet-5", "default"): (2.00, 10.00),
    ("claude-opus-5", "default"): (5.00, 25.00),
}

# Calls a month on the production host, read off its journal and service log for
# 2026-08-22..09-21: 462 answered entries, 17 deeper articles asked for.
MONTHLY_CALLS = {"card": 462, "detail": 17}


@dataclass(frozen=True)
class Arm:
    label: str
    endpoint: tuple[str, str]
    model: str
    params: dict = field(default_factory=dict)

    @property
    def tier(self) -> str:
        return "priority" if self.params.get("service_tier") == "priority" else "default"


def _effort(effort: str, *, priority: bool = False) -> dict:
    params: dict[str, object] = {}
    if effort != "default":
        params["reasoning_effort"] = effort
    if priority:
        params["service_tier"] = "priority"
    return params


ARMS = [
    Arm("luna-default", OPENAI, "gpt-5.6-luna"),
    Arm("luna-none", OPENAI, "gpt-5.6-luna", _effort("none")),
    Arm("luna-none-prio", OPENAI, "gpt-5.6-luna", _effort("none", priority=True)),
    Arm("luna-low-prio", OPENAI, "gpt-5.6-luna", _effort("low", priority=True)),
    Arm("terra-none", OPENAI, "gpt-5.6-terra", _effort("none")),
    Arm("terra-none-prio", OPENAI, "gpt-5.6-terra", _effort("none", priority=True)),
    Arm("terra-low-prio", OPENAI, "gpt-5.6-terra", _effort("low", priority=True)),
    Arm("sol-none", OPENAI, "gpt-5.6-sol", _effort("none")),
    Arm("sol-none-prio", OPENAI, "gpt-5.6-sol", _effort("none", priority=True)),
    Arm("sol-low-prio", OPENAI, "gpt-5.6-sol", _effort("low", priority=True)),
    Arm("haiku", ANTHROPIC, "claude-haiku-4-5"),
    Arm("sonnet-default", ANTHROPIC, "claude-sonnet-5"),
    Arm("sonnet-nothink", ANTHROPIC, "claude-sonnet-5", {"thinking": {"type": "disabled"}}),
    Arm("opus-low", ANTHROPIC, "claude-opus-5", {"reasoning_effort": "low"}),
    Arm("opus-nothink", ANTHROPIC, "claude-opus-5", {"thinking": {"type": "disabled"}}),
]
ARMS_BY_LABEL = {arm.label: arm for arm in ARMS}
CARD_ARMS = ["luna-none", "luna-none-prio", "luna-low-prio", "terra-none-prio", "haiku", "sonnet-nothink"]


@dataclass(frozen=True)
class Fixture:
    id: str
    lang: str
    word: str
    context: str = ""
    unit: bool = True


# Deeper-article words: polysemy, false friends, a coinage-adjacent rarity, idioms,
# and Serbian morphology — the places a fuller brief has to be right, not just long.
DETAIL_FIXTURES = [
    Fixture("en-reluctant", "en", "reluctant"),
    Fixture("en-give-up", "en", "give up"),
    Fixture("en-petrichor", "en", "petrichor"),
    Fixture("en-sanguine", "en", "sanguine"),
    Fixture("de-bekommen", "de", "bekommen"),
    Fixture("de-aufheben", "de", "aufheben", "Hebt die Quittung gut auf, falls ihr sie noch braucht."),
    Fixture("de-schadenfreude", "de", "Schadenfreude"),
    Fixture("de-nase-voll", "de", "die Nase voll haben"),
    Fixture("sr-grad", "sr", "град", "Јуче је падао град и уништио воће."),
    Fixture("sr-drzati-rec", "sr", "држати реч"),
    Fixture("sr-ipak", "sr", "ипак"),
    Fixture("sr-klupa", "sr", "клупа"),
]

# Card fixtures: bare units, a selected unit in context, and running text.
CARD_FIXTURES = [
    Fixture("card-en-reluctant", "en", "reluctant"),
    Fixture("card-en-give-up", "en", "give up"),
    Fixture("card-de-bekommen", "de", "bekommen"),
    Fixture("card-de-aufheben", "de", "aufheben", "Hebt die Quittung gut auf, falls ihr sie noch braucht."),
    Fixture("card-sr-klupa", "sr", "клупа"),
    Fixture("card-sr-drzati-rec", "sr", "држати реч"),
    Fixture("card-de-text", "de", "Ich freue mich schon auf das Wochenende.", unit=False),
    Fixture("card-sr-text", "sr", "Deca se igraju napolju ceo dan.", unit=False),
]


def prompt_for(job: str, fixture: Fixture) -> str:
    language = LANGUAGES[fixture.lang]
    if job == "detail":
        return build_extended_prompt(language, fixture.word, TARGET_NAME, context=fixture.context)
    return build_prompt(
        language,
        fixture.word,
        TARGET_NAME,
        context=fixture.context,
        unit_intent=fixture.unit,
    )


async def call(http: httpx.AsyncClient, arm: Arm, prompt: str, timeout: float) -> dict:
    base_url, key_ref = arm.endpoint
    url, headers, body = build_chat_request(
        base_url,
        arm.model,
        os.environ[key_ref],
        [{"role": "user", "content": prompt}],
        stream=True,
        params=arm.params,
    )
    started = time.monotonic()
    first: float | None = None
    text = ""
    usage: dict | None = None
    granted: str | None = None
    try:
        async with http.stream("POST", url, headers=headers, json=body, timeout=timeout) as resp:
            if resp.status_code >= ERROR_FLOOR:
                detail = (await resp.aread()).decode(errors="replace")[:DETAIL_SNIPPET]
                raise provider_error(resp.status_code, detail, resp.headers)
            async for chunk in aiter_chat_chunks(resp, arm.model):
                delta, _ = parse_stream_chunk(chunk, arm.model)
                granted = chunk.get("service_tier") or granted
                if isinstance(chunk.get("usage"), dict):
                    usage = chunk["usage"]
                if delta:
                    if first is None:
                        first = time.monotonic() - started
                    text += delta
    except Exception as exc:  # noqa: BLE001 - a failed arm is a recorded outcome.
        return {
            "error": f"{type(exc).__name__}: {str(exc)[:300]}",
            "total_s": round(time.monotonic() - started, 3),
            "first_s": first,
            "text": text,
        }
    return {
        "first_s": round(first, 3) if first is not None else None,
        "total_s": round(time.monotonic() - started, 3),
        "text": text,
        "usage": usage,
        "service_tier": granted,
    }


def results_path(out: Path, job: str) -> Path:
    return out / f"{job}.jsonl"


def load_results(out: Path, job: str) -> list[dict]:
    path = results_path(out, job)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


async def run(args: argparse.Namespace) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    fixtures = DETAIL_FIXTURES if args.job == "detail" else CARD_FIXTURES
    labels = args.arm or ([arm.label for arm in ARMS] if args.job == "detail" else CARD_ARMS)
    done = {(r["arm"], r["fixture"]) for r in load_results(out, args.job) if "error" not in r}
    async with httpx.AsyncClient() as http:
        # Fixture-major, so a provider's slow minute spreads across arms instead of
        # landing on one of them.
        for fixture in fixtures:
            for label in labels:
                if (label, fixture.id) in done:
                    continue
                arm = ARMS_BY_LABEL[label]
                record = await call(http, arm, prompt_for(args.job, fixture), args.timeout)
                record = {"arm": label, "model": arm.model, "fixture": fixture.id, **record}
                with results_path(out, args.job).open("a") as fh:
                    fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                status = record.get("error") or f"{len(record['text'])} chars"
                print(
                    f"{fixture.id:22} {label:16} first {record.get('first_s')} "
                    f"total {record['total_s']} {status}",
                    flush=True,
                )
                await asyncio.sleep(args.pace)


def _tokens(usage: dict | None) -> tuple[int, int, int]:
    if not usage:
        return 0, 0, 0
    details = usage.get("completion_tokens_details") or {}
    return (
        int(usage.get("prompt_tokens") or 0),
        int(usage.get("completion_tokens") or 0),
        int(details.get("reasoning_tokens") or 0),
    )


def _cost(record: dict) -> float:
    arm = ARMS_BY_LABEL[record["arm"]]
    tier = "priority" if record.get("service_tier") == "priority" else "default"
    price_in, price_out = PRICES[(arm.model, tier)]
    prompt_tokens, completion_tokens, _ = _tokens(record.get("usage"))
    return (prompt_tokens * price_in + completion_tokens * price_out) / 1_000_000


def _card_usable(record: dict) -> bool:
    fixture = next(f for f in CARD_FIXTURES if f.id == record["fixture"])
    parsed = extract_answer(
        record["text"],
        fixture.word,
        LANGUAGES[fixture.lang],
        unit_intent=fixture.unit,
        context=fixture.context,
        target=TARGET_NAME,
    )
    return parsed is not None


def _q(values: list[float], share: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(share * len(ordered)))]


def report(args: argparse.Namespace) -> None:
    out = Path(args.out)
    for job in ("detail", "card"):
        records = load_results(out, job)
        if not records:
            continue
        print(f"\n## {job}  (monthly volume {MONTHLY_CALLS[job]})\n")
        print(
            "| arm | n | errors | first med | first p90 | whole med | whole p90 | whole max "
            "| chars med | out tok med | reasoning med | tier | $/call | $/month |"
            + (" usable |" if job == "card" else "")
        )
        print("|---" * (15 if job == "card" else 14) + "|")
        by_arm: dict[str, list[dict]] = {}
        for record in records:
            by_arm.setdefault(record["arm"], []).append(record)
        for label in [arm.label for arm in ARMS if arm.label in by_arm]:
            rows = by_arm[label]
            ok = [r for r in rows if "error" not in r]
            if not ok:
                print(f"| {label} | {len(rows)} | {len(rows)} |" + " |" * 12)
                continue
            firsts = [r["first_s"] for r in ok if r["first_s"] is not None]
            totals = [r["total_s"] for r in ok]
            chars = [len(r["text"]) for r in ok]
            outs = [_tokens(r.get("usage"))[1] for r in ok]
            reasons = [_tokens(r.get("usage"))[2] for r in ok]
            tiers = sorted({str(r.get("service_tier")) for r in ok})
            per_call = statistics.mean(_cost(r) for r in ok)
            line = (
                f"| {label} | {len(rows)} | {len(rows) - len(ok)} "
                f"| {statistics.median(firsts):.2f} | {_q(firsts, 0.9):.2f} "
                f"| {statistics.median(totals):.2f} | {_q(totals, 0.9):.2f} | {max(totals):.2f} "
                f"| {statistics.median(chars):.0f} | {statistics.median(outs):.0f} "
                f"| {statistics.median(reasons):.0f} | {'/'.join(tiers)} "
                f"| {per_call:.4f} | {per_call * MONTHLY_CALLS[job]:.2f} |"
            )
            if job == "card":
                line += f" {sum(_card_usable(r) for r in ok)}/{len(ok)} |"
            print(line)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["run", "report"])
    parser.add_argument("--job", choices=["detail", "card"], default="detail")
    parser.add_argument("--arm", nargs="+", default=[], choices=list(ARMS_BY_LABEL))
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--pace", type=float, default=1.0)
    parser.add_argument("--out", default=str(Path(__file__).parent / ".bench-tier"))
    args = parser.parse_args()
    if args.phase == "run":
        asyncio.run(run(args))
    else:
        report(args)


if __name__ == "__main__":
    main()
