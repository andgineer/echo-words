# Try it on your computer

This runs echo-words on your own computer so you can see what it does. It is not
how the app is meant to be used: it runs only while you keep it running, only the
browser on this computer can open it, and the cards it makes stay in a trial
collection that none of your Anki apps see. For real use,
[install it on Oracle Cloud](deploy-oracle.md). That costs nothing either.

## What you need

- [git](https://git-scm.com/) and [uv](https://docs.astral.sh/uv/getting-started/installation/)
- [Node.js](https://nodejs.org/) 22, because the first start builds the app's pages
- one free LLM provider key: `GROQ_API_KEY`, `OPENROUTER_API_KEY`,
  `GEMINI_API_KEY` or `ZAI_API_KEY`. [Configuration](configuration.md) lists where
  to get each one.

## Run it

```bash
git clone https://github.com/andgineer/echo-words.git
cd echo-words
export GROQ_API_KEY=...            # or any other free-pool key
export ECHOWORDS_ANKI_SYNC=false   # keep the trial cards out of your AnkiWeb account
uv run inv dev
```

Open <http://127.0.0.1:8080>. The first start builds the app and creates
`~/.echo-words/languages.toml` with English, German and Serbian, which you can
change from the app.

Leave `ECHOWORDS_ANKI_SYNC=false` set. Without it, adding a card needs your
AnkiWeb login, and the trial cards then go into your real decks.

Everything the trial keeps is in `~/.echo-words`. Delete that folder to remove
it. Nothing in it carries over to an Oracle Cloud install.
