# echo-words — agent instructions

echo-words is a private, tailnet-only vocabulary assistant: a FastAPI
backend plus a Vue 3 PWA, streaming a linguistic analysis of a word and
adding a two-direction note to the source language's Anki deck. It keeps
no application database.

`AGENTS.md` is a symlink to this file — one document, whichever name the
tool looks for.

---

## Where the specification lives

- `spec/functional-description.md` — WHAT to build. The source of truth:
  on any conflict with this file or any other document, it wins.
- `spec/implementation-plan.md` — HOW to build it: milestones M0–M8.
  Work is driven by its "Execution protocol" section — one milestone per
  session, strictly in order, implementing exactly that milestone's
  scope.
- `spec/decision-*.md` — background for settled decisions: the guard list
  of product decisions (`decision-product.md`), the user interface
  (`decision-interface.md`, `decision-chat-interface.md`), spaced
  repetition, TTS, the LLM backend, and the deployment host and tooling
  (`decision-deployment.md`). They hold the reasoning and the
  measurements so the plan can stay instructions only. Do not re-open
  them.

---

## Key commands

| Task | Command |
|---|---|
| Lint + format + type-check | `uv run inv pre` |
| Full test suite (Python + frontend) | `uv run inv test` |
| Python tests only | `uv run pytest` |
| Frontend tests only | `npm --prefix webapp test` |
| Dev server (auto-reload) | `uv run inv dev` |
| Build the PWA into `_static/` | `uv run inv build-static` |
| List every task | `uv run inv --list` |

The `uv run` prefix is optional inside an activated `.venv`.

**Never call Ruff directly** — not `ruff`, not `uv run ruff`, not `uvx
ruff`. `inv pre` runs ruff, ruff-format, pyrefly and the file-hygiene
hooks with the project's own configuration, and it is the only gate that
matches CI. An editor's lint panel does not substitute for it: it misses
ruff-format drift, pyrefly findings, and hook-driven file rewrites.

---

## Environment setup

A bare `uv sync` is not enough to reach a green suite:

1. `uv sync` — the default and `dev` groups (pytest, ruff, pyrefly,
   invoke, pre-commit). The pyrefly hook runs `.venv/bin/python`, so the
   venv has to exist. Adding a dependency also means `uv lock`; CI
   installs with `--frozen`.
2. `npm --prefix webapp ci` — `inv test` **skips** the frontend suite
   when `webapp/node_modules` is missing, and CI does not. A run without
   it is not a full run.

`espeak-ng` is needed only to *run* Piper voices, never by a test.
`languages.toml` is needed only to run the app, and `inv dev` creates it
from `languages.example.toml`. Never work around a missing dependency or
binary by skipping tests — fix the environment.

---

## Non-negotiable done gate

Before telling the user anything is "done", "ready", "fixed", "landed" or
"green", both of these must have been run, in this order, and seen fully
green:

1. `uv run inv pre` → "All checks passed!" on every hook, `0 errors` from
   pyrefly.
2. `uv run inv test` → pytest `N passed` with zero failures or errors,
   and the frontend suite passed rather than skipped.

A milestone is done only when both are green.

- Run `inv pre` after each discrete batch of changes, not once at the end
  of the session. If a hook rewrites files (ruff-format,
  end-of-file-fixer, trailing-whitespace), re-run it until it converges —
  "files were modified by this hook" is a pending fixup, not green.
- Fix what `inv pre` reports even when it looks pre-existing or unrelated
  to the change. The only way to defer one: confirm it fails on `main`
  too, and get the user to agree to defer it in the same turn. Silently
  calling an error out of scope misreports the state of the tree.
- No exceptions — not for a docs-only change, not for a green run from
  three turns ago, not for a narrow `pytest -k` subset.
- Never bypass a hook with `--no-verify`.
- Never present changes as ready, or ask for permission to commit, before
  both commands have completed successfully.

---

## Tests

- Every new module or function ships its tests in the same commit. Never
  skip them, never defer them to a later milestone.
- Iterate with `pytest -k …` if it helps, but verify with the full suite.
- No real network, Anki sync, LLM, or TTS calls in tests — fake or mock
  every boundary. The deploy tests must stay blind to the operator's own
  `.deploy/.env`. The M0 harness in `experiments/` is the sanctioned
  exception and stays out of CI.
- **Never leave a failing test. Every session starts from green.** `main`
  is green, so there is no "pre-existing failure" to ignore: red is
  either something you broke or a test that rotted — most often a flaky
  or date-dependent one (a hardcoded date aged out of a rolling window,
  an order-dependent assumption, a real clock). Diagnose the root cause
  and make the test deterministic; do not skip, `xfail`, delete, or hand
  back a red suite calling the failures unrelated. If the cause is
  environmental, fix the environment, not the assertion.

---

## Code conventions

- Python 3.12+, `src` layout, hatchling packaging — do not restructure
  the packaging. Dependencies via `uv`, with `uv lock` on every change.
- **English only** in comments, docstrings, plans, and in-repo docs.
  Reply to the user in the language they used, in its native script.
  Data literals — a language name, a deck name, a voice id — keep their
  original script and stay quoted so they remain grep-able; never
  transliterate them.
- **All imports at module top level.** No in-function imports for lazy
  loading, none to break a cycle — fix the dependency structure instead.
  The two sanctioned exceptions are marked in the plan: llmbroker in M2,
  piper in M6.
- No `from __future__ import annotations`.
- **No re-export shims.** When a symbol moves, update its importers to
  the new module instead of leaving a proxy behind. This does not forbid
  importing a shared helper — duplicating logic to avoid an import is the
  worse outcome.
- Comments and docstrings are for a non-obvious *why*, in one or two
  lines: a hidden constraint, a workaround for a library quirk, an
  invariant, behaviour that would surprise a reader. Never restate what
  the code does, never argue a design decision there (that belongs in
  `spec/`), and never cite a plan file or a milestone number — plans are
  ephemeral, the code is not.

### Plans and specs

- `spec/` captures architectural decisions and business requirements
  only. Never function signatures, argument lists, field names, or class
  structure — the code is the source of truth for those.
- Specs describe the **current state**. Motivation, experiments, and
  measurements are welcome; implementation history ("previously X, now
  Y", "approach Z was removed") is not — git records the evolution.
- Plans are implementation guides and may be as detailed as needed:
  signatures, exact patterns, snippets, verification commands. When a
  plan's work has fully landed, its spec-worthy content moves into a spec
  file; a plan is not an archive.
- Where the plan and the functional description disagree, the functional
  description wins, and the plan is corrected in the same commit.

---

## DevOps

- Deployment is `invoke` tasks run over ssh from the operator's machine:
  `inv setup-app` (one-time, idempotent), `inv deploy --ref=…`,
  `inv status`, `inv logs`. The host, the rules it imposes, and what each
  task does are in the plan's "Deployment" section and
  `spec/decision-deployment.md`.
- **Deploy an exact ref from a clean tree.** `inv deploy` refuses a dirty
  working tree and a ref that is not the checked-out HEAD, because the
  frontend it uploads is built from the local source.
- **Never edit files on the server.** The remote checkout is a deploy
  target, not a working copy — fix it in the repo and deploy again.
  `deploy` refuses to run over remote working-tree changes.
- **Never build the frontend on the VM** (1 GB RAM): `inv deploy` builds
  `_static/` locally and rsyncs the result. No Node is installed there.
- **Secrets live in the gitignored `.deploy/.env`**, documented variable
  by variable in the committed `.deploy.example/.env`. Provider API keys
  and AnkiWeb credentials never enter the repo, a test fixture, or a log
  line.
- A deploy is finished only when its health poll passes — `inv deploy`
  gates on `GET /api/health` instead of a fixed sleep. Confirm afterwards
  with `inv status` and `inv logs`.
- Host changes belong in the `setup-app` / host-prep scripts in
  `tasks.py`, so the VM stays reproducible from the repo — never in a
  one-off ssh session.
- Releases go through `inv ver-release` / `ver-feature` / `ver-bug`,
  which tag the commit; the tag drives the PyPI publish workflow once CI
  is green.
- Commit straight to `main` — no working branches, no PRs. Releases are
  protected by their tag and by the PyPI publication, so `main` is a
  working surface and breaking it costs nothing.
