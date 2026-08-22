# echo-words

Look up a word, get a linguistic analysis, and have the card in your Anki deck
before you finish reading it.

echo-words is a private, tailnet-only vocabulary assistant: a FastAPI backend and
a Vue 3 PWA that

- streams a compact analysis of a word or phrase — translations, senses, usage,
  origin, and examples with their translations
- pronounces it, locally with Piper or online with edge-tts
- adds a two-direction note to that language's own Anki deck, deduplicated
- runs on free LLM providers first and only falls back to a paid model
- keeps **no database**, and is reachable only over your Tailscale tailnet

<table>
<tr>
<td align="center" valign="top"><sub><b>A word, or a phrase to pick from</b></sub><br/><img src="images/screenshots/add-word.png" width="280"/></td>
<td align="center" valign="top"><sub><b>Analysis, pronunciation, card</b></sub><br/><img src="images/screenshots/card-added.png" width="280"/></td>
<td align="center" valign="top"><sub><b>Any language, any script</b></sub><br/><img src="images/screenshots/cyrillic-card.png" width="280"/></td>
</tr>
<tr>
<td align="center" valign="top"><sub><b>What went into the decks</b></sub><br/><img src="images/screenshots/stats.png" width="280"/></td>
<td align="center" valign="top"><sub><b>Providers, sync, and cost</b></sub><br/><img src="images/screenshots/status.png" width="280"/></td>
<td></td>
</tr>
</table>

### Quick start

1. [Install it](installation.md) and run it on your own machine.
2. [Configure your languages](configuration.md) — one Anki deck and one voice per
   source language, plus at least one free LLM provider key.
3. [Deploy to Oracle Cloud](deploy-oracle.md) — $0/month forever, tailnet-only.
4. [Install the PWA](pwa-install.md) on your phone and add the share-sheet
   Shortcut.
