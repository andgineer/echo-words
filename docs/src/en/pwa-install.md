# Install on your phone

Open the node's Tailscale HTTPS URL in Safari, tap **Share**, then **Add to Home
Screen**. The installed app opens standalone and its shell stays available
offline; API requests are network-only and never served from cache.

## Words submitted with no connection

A word submitted while the server is unreachable stays in a local FIFO queue and
is retried on the next app open or on the browser's `online` event.

Each submission carries a UUID that is stored with the queue item. If the server
accepted a POST but its response was lost, retrying that UUID returns the
original entry instead of repeating the LLM and audio work. This receipt map is
in-memory like the history: it holds at most 4096 accepted IDs for seven days and
resets when the backend restarts. A retry outside that window is a new request,
but Anki's durable word/deck duplicate check still prevents a second card.

## Share-sheet Shortcut

An iOS Shortcut lets you send a word straight from any app that can share text.

1. Create a Shortcut that **accepts text from the Share Sheet**, and save
   Shortcut Input as the `Phrase` variable.
2. Use **Match Text** with

    ```
    \p{L}(?:[\p{L}\p{N}'’-]*[\p{L}\p{N}])?
    ```

    to turn it into a list of word tokens. Like the PWA's own picker, this
    requires a letter at the start and a letter or number at the end, while
    keeping an internal apostrophe or hyphen: `“don’t,”` becomes `don’t`, and
    `'(go-over)'` becomes `go-over`.

3. If the list has more than one item, use **Choose from List** and set `Word` to
   the chosen token; otherwise set `Word` directly to the only token.
4. Build a Dictionary with `word` set to `Word`, `lang` set to a configured code
   such as `en`, and `lookup_only` set to false. Only in the multi-word branch,
   also set `context` to the original `Phrase`.
5. Use **Get Contents of URL** to POST that dictionary as JSON to
   `https://<node>.<tailnet>.ts.net/api/words`.
6. Add the shortcut to the Share Sheet.

Tailscale must be connected. A single shared word goes straight through, while
shared prose asks which word to analyse and preserves the whole selection as
context — without exposing the service publicly.
