# echo-words — agent instructions

## Where the specification lives

- `spec/functional-description.md` — WHAT to build. The source of
  truth: on any conflict with other documents, it wins.
- `spec/implementation-plan.md` — HOW to build it: milestones M0–M8.
  Work is driven by its "Execution protocol" section — one milestone
  per session, strictly in order.
- `spec/decision-*.md` — background for settled decisions: the guard
  list of product decisions (`decision-product.md`), the user interface
  (`decision-interface.md`, `decision-chat-interface.md`), spaced
  repetition, TTS, the LLM backend, and the deployment host and tooling
  (`decision-deployment.md`). They hold the reasoning and the
  measurements so the plan can stay instructions only. Do not re-open
  them.

## Hard rules

- Python 3.12+, `src` layout, hatchling packaging — do not restructure
  the packaging.
- Dependencies via `uv`; run `uv lock` when adding any (CI uses
  `--frozen`).
- Every new module ships its tests in the same commit. Run static checks
  only through `inv pre`, never by invoking Ruff directly. A milestone is
  done only when `inv pre` and the full `inv test` suite are green.
- Never present changes as ready or ask for permission to commit before
  both required commands have completed successfully.
- No real network, Anki sync, or LLM calls in tests — fake or mock
  every boundary. The M0 harness in `experiments/` is the sanctioned
  exception and stays out of CI.
- English-only comments and docs. All imports at module top level (the
  two sanctioned exceptions are marked in the plan: llmbroker in M2,
  piper in M6).
- Commit straight to `main` — no working branches, no PRs. Releases are
  protected by their tag and by the PyPI publication, so `main` is a
  working surface and breaking it costs nothing.
