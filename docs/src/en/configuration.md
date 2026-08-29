# Configuration

echo-words is configured in two places: a TOML table of source languages, and
environment variables for everything else.

## Source languages

`languages.toml` is the source of truth for the languages you look words up in.
It lives in `ECHOWORDS_DATA_DIR` and moves with it;
`ECHOWORDS_LANGUAGES_CONFIG` overrides that path. Adding a language is a
configuration change, not a code change.

```toml
[languages.en]
name       = "English"
deck       = "EchoWords: English"
dict_api   = "en"              # dictionaryapi.dev code; omit if unsupported
tts        = "piper"           # piper | edge
tts_voice  = "en_US-lessac-medium"
accent     = "us"              # meaningful for English
script     = "latin"           # latin | cyrillic | latin+cyrillic

[languages.sr]
name           = "Српски"
deck           = "EchoWords: Serbian"
tts            = "edge"
edge_tts_voice = "sr-RS-SophieNeural"
script         = "latin+cyrillic"
prompt_hints   = "for nouns give gender and plural, for verbs give aspect"
```

Each entry names its display name, its own Anki `deck`, the `script` accepted
from the input field, the dictionary code where one exists, and its
pronunciation engine and voice. `languages.example.toml` in the repository
carries complete English, German, and Serbian entries.

!!! note
    Serbian is spoken in Cyrillic on purpose: the `sr-RS` voices mispronounce
    the Latin spelling.

## Environment variables

Every variable is prefixed `ECHOWORDS_`. The committed `.deploy.example/.env`
documents them one by one; these are the ones you are likely to change.

| Variable | Meaning | Default |
|---|---|---|
| `ECHOWORDS_DATA_DIR` | Anki collection, voice models, broker state, cached audio — no database of its own | `~/.echo-words` |
| `ECHOWORDS_TARGET_LANG` | the language every explanation and translation is written in | `ru` |
| `ECHOWORDS_LANGUAGES_CONFIG` | path to the languages table | `<data dir>/languages.toml` |
| `ECHOWORDS_LLMBROKER_HOME` | where llmbroker keeps its curated model list and call journal | `<data dir>/llmbroker` |
| `ECHOWORDS_API_MODEL` | paid-catalog alias the cascade steps up to; empty disables paid calls entirely | `gpt-fast` |
| `ECHOWORDS_API_DAILY_CAP` | paid calls per day, `0` for unlimited | `100` |
| `ECHOWORDS_ANKI_SYNC` | sync the collection to AnkiWeb after additions | `true` |
| `ECHOWORDS_ANKIWEB_USER` / `_PASSWORD` | AnkiWeb credentials | required when sync is on |
| `ECHOWORDS_SYNC_ENDPOINT` | self-hosted Anki sync server instead of AnkiWeb | empty |
| `ECHOWORDS_ACCENT` | `us` or `uk` for English audio | `us` |
| `ECHOWORDS_AUDIO_TIMEOUT` | shared post-generation seconds to wait for pronunciation before sending without it | `10` |
| `ECHOWORDS_HOST` / `ECHOWORDS_PORT` | bind address; keep it on loopback and let Tailscale be the front door | `127.0.0.1:8080` |

Pronunciation roles share this one post-generation wait. Values below ten
seconds shorten it; values above ten seconds cannot extend the hard cap. The
wait ends as soon as the audio arrives, so it is only ever paid in full when
there will be no audio at all.

The **interface language** of the PWA is not an environment variable. It is a
per-device choice in the header (EN/RU), remembered in the browser, and it does
not change `ECHOWORDS_TARGET_LANG` — the language your cards are written in.

## LLM provider keys

The free pool needs at least one of `GROQ_API_KEY`, `OPENROUTER_API_KEY`,
`GEMINI_API_KEY`, or `ZAI_API_KEY`; filling all four gives the pool its full
failover set. `python -m llmbroker env freetier` prints the authoritative list
for the installed llmbroker release, with signup links.

The default paid fallback, `ECHOWORDS_API_MODEL=gpt-fast`, additionally needs
`OPENAI_API_KEY`. Set `ECHOWORDS_API_MODEL=` to run on the unmetered pool only.

The **Status** screen shows which keys are missing, how many providers are
usable, and how many paid calls the day has cost.

## AnkiWeb

Set `ECHOWORDS_ANKIWEB_USER` and `ECHOWORDS_ANKIWEB_PASSWORD` and leave
`ECHOWORDS_ANKI_SYNC=true`. On the first run the headless collection performs a
full download of the existing account collection before any local card is added.
The password is used once to obtain a sync key; the key is then kept under
`ECHOWORDS_DATA_DIR` and reused.

Keep outbound HTTPS unrestricted for `*.ankiweb.net`: AnkiWeb redirects sync to
numbered shards, so allowing only `sync.ankiweb.net` fails intermittently.

A self-hosted Anki sync server can be selected with `ECHOWORDS_SYNC_ENDPOINT`
instead.
