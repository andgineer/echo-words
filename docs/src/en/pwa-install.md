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

An iOS Shortcut lets you send a word, an expression or a whole passage straight
from any app that can share text.

1. Create a Shortcut that **accepts text from the Share Sheet**.
2. Build a Dictionary with `word` set to the Shortcut input, `lang` set to a
   configured code such as `en`, and `lookup_only` set to false.
3. Use **Get Contents of URL** to POST that dictionary as JSON to
   `https://<node>.<tailnet>.ts.net/api/words`.
4. Add the shortcut to the Share Sheet.

Tailscale must be connected. The backend decides what the shared text is: a word
or an expression is analysed whole and becomes a card, while shared prose comes
back translated and explained, with the units worth looking up on their own —
without exposing the service publicly.
