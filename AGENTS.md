# wordgram — agent instructions

## Where the specification lives

- `spec/functional-description.md` — WHAT to build. The source of
  truth: on any conflict with other documents, it wins.
- `spec/implementation-plan.md` — HOW to build it: milestones M0–M8.
  Work is driven by its "Execution protocol" section — one milestone
  per session, strictly in order.
- `spec/decision-*.md` — background for settled decisions (chat
  interface, spaced repetition, TTS). Do not re-open them.

## Hard rules

- Python 3.12+, `src` layout, hatchling packaging — do not restructure
  the packaging.
- Dependencies via `uv`; run `uv lock` when adding any (CI uses
  `--frozen`).
- Every new module ships its tests in the same commit. A milestone is
  done only when `uv run pytest` and `ruff check` (line-length 99) are
  green.
- No real network, Telegram, Anki sync, or LLM/agent calls in tests —
  fake or mock every boundary. The M0 harness in `experiments/` is the
  sanctioned exception and stays out of CI.
- English-only comments and docs. All imports at module top level (the
  one sanctioned exception is marked in the plan, M6).
