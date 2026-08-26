# State and maintenance

echo-words has **no database and needs no database backup**. Only
`ECHOWORDS_DATA_DIR` matters: it holds the Anki collection, the voice models, the
broker state, and the cached audio.

The collection itself is replicated through AnkiWeb, so even that directory is
not the only copy of your cards.

## What is deliberately not persisted

History, undo state, session counters, and the accepted-submission receipt map
live in memory and reset when the backend restarts. This is by design: the
durable record of every lookup is the Anki note it produced.

The **Stats** screen shows this split directly — `Today`, `Last 7 days`, and
`All time` are counted from the collection, while `Since startup: N without a
card` is the in-memory session counter.

## The audio cache

`ECHOWORDS_DATA_DIR/audio/` keeps one small MP3 per looked-up word and has no
cleanup policy. These files are safe to delete at any time: Anki reviews play the
separate copy in the collection's own media directory.

## Health

`GET /api/health` answers with the running version and is what `inv deploy`
gates on. The **Status** screen adds the operational picture: usable LLM
providers, missing provider keys, paid calls spent against the daily cap, the
last AnkiWeb sync and any sync error, and the last call each language made.
