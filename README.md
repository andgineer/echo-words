[![Build Status](https://github.com/andgineer/echo-words/workflows/CI/badge.svg)](https://github.com/andgineer/echo-words/actions)
[![Coverage](https://raw.githubusercontent.com/andgineer/echo-words/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/andgineer/echo-words/blob/python-coverage-comment-action-data/htmlcov/index.html)
# echo-words

**From a word you meet to a word you remember.**

Understand words and expressions in context, hear their pronunciation, and send
audio-backed flashcards straight to AnkiWeb — ready to sync into the Anki apps
you already use.

echo-words explains; Anki makes you remember.

<table>
<tr>
<td align="center" valign="top"><sub><b>A word, a phrase, a sentence</b></sub><br/><img src="docs/common/images/screenshots/add-word.png" width="280"/></td>
<td align="center" valign="top"><sub><b>Analysis, audio, card in Anki</b></sub><br/><img src="docs/common/images/screenshots/card-added.png" width="280"/></td>
<td align="center" valign="top"><sub><b>A sentence, translated and explained</b></sub><br/><img src="docs/common/images/screenshots/sentence.png" width="280"/></td>
</tr>
</table>

* **Understand the word.** Explore meanings, register, collocations, and translated
  examples. Choose the sense you want to learn.
* **Learn from a sentence.** Get a translation and an explanation of the difficult
  parts, then tap a word or expression to explore it.
* **Keep it in Anki.** Each selected sense becomes four cards covering recognition
  and production, with and without context, in its source-language deck.

[Documentation](https://andgineer.github.io/echo-words/)

## Under the hood

**Getting a complete answer from a changing model pool.** Free LLM providers vary
in availability, speed, and instruction-following. Through llmbroker, echo-words
races two models and selects the first complete, usable answer. Streaming lets the
reader start earlier; recovery preserves an existing explanation if card creation
fails.

If your application needs a pool of free LLM providers with automatic failover and
streaming, [llmbroker](https://github.com/andgineer/llmbroker) is available as a
standalone Python library.

**Checking what the cards actually teach.** Valid JSON can still contain the wrong
meaning, an invented origin, or a word from the wrong language. Model-facing changes
go through real-model benchmarks and a separate agent's review of the concrete
answers. The [evaluation records](spec/decision-llm-backend.md) document both
findings and remaining limitations.

**Keeping the backend operational in less than 1G.** FastAPI serves the Vue PWA and maintains Anki through
its headless Python library, syncing directly with AnkiWeb. There is no separate
application database or running Anki desktop instance. Access to the web app is
restricted to a Tailscale network.

### Development process

In this project, I experimented with a staged AI development workflow: Fable for
design, sol for the initial implementation with iterative reviews automatically
coordinated by Astra, and Opus for subsequent fixes, coordinating its own review
cycles.

The continuity between those stages lives in the repository: a functional
specification, decision records, and working plans. [Agent instructions](AGENTS.md)
define the verification gates, including browser tests and real-model evaluation
for changes to prompts or answer handling.

<details>
<summary><b>Contributing</b></summary>

```bash
uv sync
npm --prefix webapp ci
uv run playwright install chromium
uv run inv dev     # http://127.0.0.1:8080
uv run inv pre     # lint, format, type-check, file hygiene
uv run inv test    # Python + frontend suites
```

See [Development](https://andgineer.github.io/echo-words/development/) and
[Deploy to Oracle Cloud](https://andgineer.github.io/echo-words/deploy-oracle/)
in the docs.

[Allure test report](https://andgineer.github.io/echo-words/builds/tests/)

</details>
