# Your keys

echo-words needs the same keys wherever its server runs, and you write them the
same way, as `KEY=value` lines. Only the file differs:

- **On Oracle Cloud**, they go in `.deploy/.env` in your checkout. Create it with
  `cp .deploy.example/.env .deploy/.env`. Every deploy copies it to the VM.
- **On your computer**, they go in `.env` at the root of your checkout.

## Gemini: the one key you need

```
GEMINI_API_KEY=...
```

Create it free at [Google AI Studio](https://aistudio.google.com/apikey). Gemini
is the main model of the free pool and does most of the work: in measured runs
with every key filled, it wrote about four answers in five. With this key alone
the app works.

## More free keys: optional failover

```
GROQ_API_KEY=...
OPENROUTER_API_KEY=...
ZAI_API_KEY=...
```

Each is free: [Groq](https://console.groq.com/keys),
[OpenRouter](https://openrouter.ai/keys), [Z.AI](https://z.ai/manage-apikey/apikey-list).
Every key you add puts more models into the pool. They race Gemini for each
answer and take over when Gemini is slow, out of its free quota or down.

## OpenAI: optional, paid

```
OPENAI_API_KEY=...
```

Create it at [OpenAI](https://platform.openai.com/api-keys). It pays for two
things: the deeper article you ask for with one tap, and a card the free pool
failed to answer. Without it, the deeper article says it is unavailable, and a
card the pool failed shows the failure.

It costs little. A deeper article costs about $0.036, so a dollar buys about 28 of
them. On the author's own use, 17 deeper articles in 30 days, that came to about
$0.60 a month. A card goes to the paid model only when the free pool fails to
answer it. The app also stops after 100 paid calls a day, which
`ECHOWORDS_API_DAILY_CAP` changes.
`ECHOWORDS_API_MODEL=` switches paid calls off entirely, even with the key set.

## AnkiWeb login

```
ECHOWORDS_ANKIWEB_USER=...
ECHOWORDS_ANKIWEB_PASSWORD=...
```

The server needs your AnkiWeb login so that cards reach your decks; see
[Configuration](configuration.md#ankiweb). A trial on your computer runs without
it, with `ECHOWORDS_ANKI_SYNC=false` instead.

## Checking them

The app's **Status** screen lists the keys it is missing. The free pool's key list
belongs to llmbroker, the library that runs the pool, and this command prints it
for the installed release, with the same signup links:

```bash
uv run python -m llmbroker env freetier
```
