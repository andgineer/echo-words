# Your keys

echo-words reads its keys from one file, `.deploy/.env` in your checkout,
wherever its server runs. Create it from the template:

```bash
mkdir -p .deploy
cp .deploy.example/.env .deploy/.env
```

On Oracle Cloud every deploy copies it to the VM; on your computer the app reads
it where it is.

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
them, and a paid card costs a fraction of a cent. A card goes to the paid model
only when the free pool fails to answer it, or when you ask for the paid model
on a failed card. On the author's own use over the 30 days to 2 October 2026, 14
deeper articles and 12 paid cards came to about $0.53 in all. The app also stops after 100 paid calls a day, which
`ECHOWORDS_API_DAILY_CAP` changes.
`ECHOWORDS_API_MODEL=` switches paid calls off entirely, even with the key set.

## AnkiWeb login

```
ECHOWORDS_ANKIWEB_USER=...
ECHOWORDS_ANKIWEB_PASSWORD=...
```

The server needs your AnkiWeb login so that cards reach your decks; see
[Configuration](configuration.md#ankiweb). `uv run inv dev` on your computer does
not sync with AnkiWeb, so it does not use the login.

## Checking them

The app's **Status** screen lists the keys it is missing. The free pool's key list
belongs to llmbroker, the library that runs the pool, and this command prints it
for the installed release, with the same signup links:

```bash
uv run python -m llmbroker env freetier
```
