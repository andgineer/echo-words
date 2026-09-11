[![Build Status](https://github.com/andgineer/echo-words/workflows/CI/badge.svg)](https://github.com/andgineer/echo-words/actions)
[![Coverage](https://raw.githubusercontent.com/andgineer/echo-words/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/andgineer/echo-words/blob/python-coverage-comment-action-data/htmlcov/index.html)
# echo-words

A private AI vocabulary tutor for every word you meet. Send a word, phrase, or
whole sentence, and echo-words explains what a dictionary will not: distinct
senses and registers, real usage, origins, and examples worth remembering. It
also creates the Anki material for you — four cards that test one selected sense
in both directions, with natural pronunciation — in the deck you already review.
echo-words explains; Anki makes you remember.

<table>
<tr>
<td align="center" valign="top"><sub><b>A word, a phrase, a sentence</b></sub><br/><img src="docs/common/images/screenshots/add-word.png" width="280"/></td>
<td align="center" valign="top"><sub><b>Analysis, audio, card in Anki</b></sub><br/><img src="docs/common/images/screenshots/card-added.png" width="280"/></td>
<td align="center" valign="top"><sub><b>A sentence, translated and explained</b></sub><br/><img src="docs/common/images/screenshots/sentence.png" width="280"/></td>
</tr>
</table>

What one word gets you:

* **an explanation, not just a translation** — distinct senses and registers,
  collocations, prepositions, common confusions, origins, and translated examples;
  a phrase is taught as a whole while its words remain available as chips
* **one selected sense, reviewed four ways** — word and context test recognition
  and production; every other sense stays one tap away from its own note
* **a real voice, not a robot** — natural-sounding audio in the app and on the cards
* **a whole sentence becomes a lesson** — echo-words translates it, explains the
  hard parts, and turns every useful word or expression into a one-tap lesson
* **a deeper entry on demand** — one tap asks the strongest model for rare senses,
  deeper etymology, near-synonyms, and the mistakes learners make
* **light enough for the cheapest server** — runs on a 1 GB free-tier VM with no
  application database; answers come from a pool of free LLM providers

# Documentation

[echo-words](https://andgineer.github.io/echo-words/)

<details>
<summary><b>Development</b></summary>

```bash
uv sync
npm --prefix webapp ci
inv dev     # http://127.0.0.1:8080
inv test    # Python + frontend suites
inv pre     # ruff, ruff-format, pyrefly, file hygiene
```

`inv test` silently skips the frontend suite when `webapp/node_modules` is
missing, so `npm ci` is part of the setup, not an optional extra. Never call
Ruff directly — `inv pre` is the only gate that matches CI.

Deployment is `invoke` over ssh, and the frontend is built on the VM by the
deploy itself:

```bash
inv setup-app --with-host-prep   # one-time, idempotent
inv deploy --ref=main
inv status
inv logs
```

See [Development](https://andgineer.github.io/echo-words/development/) and
[Deploy to Oracle Cloud](https://andgineer.github.io/echo-words/deploy-oracle/)
in the docs.

## Reports

* [Allure test report](https://andgineer.github.io/echo-words/builds/tests/)

</details>

> Created with cookiecutter using [template](https://github.com/andgineer/cookiecutter-python-package)
