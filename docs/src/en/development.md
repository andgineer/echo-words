# Development

## Setting up

A bare `uv sync` is not enough to reach a green suite:

```bash
uv sync                  # default and dev groups
npm --prefix webapp ci   # inv test skips the frontend suite without this
```

`inv test` **skips** the frontend suite when `webapp/node_modules` is missing,
and CI does not — a run without `npm ci` is not a full run. Adding a Python
dependency also means `uv lock`; CI installs with `--frozen`.

`languages.toml` is needed only to run the app, and `inv dev` creates it from
`languages.example.toml`. `espeak-ng` is needed only to run Piper voices, never
by a test.

## Commands

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

!!! warning
    Never call Ruff directly. `inv pre` runs ruff, ruff-format, pyrefly and the
    file-hygiene hooks with the project's own configuration, and it is the only
    gate that matches CI.

For hot module replacement while working on Vue, run the Vite dev server in a
second terminal — it proxies `/api` to the backend on port 8080:

```bash
npm --prefix webapp run dev   # http://127.0.0.1:5173
```

`vite dev` does not register a service worker. Test offline and PWA behaviour
against a real `_static/` build.

## Interface language

The PWA's strings live in `webapp/src/i18n/{en,ru}.js` and are reached through
`t("key")`; the header selector writes the choice to `localStorage` and the
client sends it as `Accept-Language` on every API call. The backend's own
user-facing hints — input validation and unknown-language errors — live in
`src/echo_words/i18n.py` and are resolved per request from that header. Both
suites assert that the two catalogues carry exactly the same keys, so a string
added in one language cannot silently go missing in the other.

Text the server produces for the shared history and event stream — card statuses
and the analysis itself — is not per-client and is not translated this way. The
analysis language is `ECHOWORDS_TARGET_LANG`.

## Tests

Every new module or function ships its tests in the same commit. No real
network, Anki sync, LLM, or TTS calls in tests — every boundary is faked or
mocked. The harness in `experiments/` is the sanctioned exception and stays out
of CI.

CI runs the Python 3.12/3.13 matrix, the frontend Vitest suite, and Ruff. Test
reports are published in
[Allure](https://andgineer.github.io/echo-words/builds/tests/).

## Specifications

`spec/` holds the functional description, the implementation plan, and the
decision records behind the settled choices — spaced repetition, TTS, the LLM
backend, the interface, and the deployment host. They are not published to this
site. Where `spec/` and the code disagree, **the code wins**.
