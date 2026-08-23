# echo-words

A private vocabulary tutor for every word you meet. Send a word, a phrase or a
whole sentence, and echo-words explains what a dictionary will not — then writes
the flashcard for you, into the Anki deck you already review. It explains; Anki
makes you remember.

echo-words is a FastAPI backend and a Vue 3 PWA that gives you

- **an explanation, not a translation** — every sense with its part of speech
  and register, the collocations and prepositions the word takes, what it is
  confused with, its origin, and examples with their translations; an idiom or
  a phrase is explained whole, never taken apart
- **the sense you actually met** — a word looked up out of a text is explained
  in that text's sense, not replaced by the nearest dictionary meaning
- **a card built for review, not a word→translation pair** — recognition and
  recall, unrelated senses kept apart, a gapped example so the reverse card
  asks a real question, and the pronunciation inside the note
- **a real voice, not a robot** — natural-sounding audio, locally with Piper or
  online with edge-tts, in the app and on the card; whatever you send is voiced
  whole, so a word taken out of a sentence is played beside that sentence
- **a whole sentence gets a lesson instead** — translated, with what is hard in
  it explained, and the expressions worth learning offered as cards of their own
- **a deeper entry when you want one** — one tap re-asks the strongest model for
  a lexicographer's article: every sense including the rare ones, etymology in
  depth, near-synonyms, the mistakes learners make
- **nothing to pay** — a pool of free LLM providers answers; a paid model is
  optional and capped

It keeps **no database**: your Anki collection is the only thing it stores.

<table>
<tr>
<td align="center" valign="top"><sub><b>A word, a phrase, a sentence</b></sub><br/><img src="images/screenshots/add-word.png" width="280"/></td>
<td align="center" valign="top"><sub><b>Analysis, audio, card in Anki</b></sub><br/><img src="images/screenshots/card-added.png" width="280"/></td>
<td align="center" valign="top"><sub><b>A sentence, translated and explained</b></sub><br/><img src="images/screenshots/sentence.png" width="280"/></td>
</tr>
<tr>
<td align="center" valign="top"><sub><b>Any language, any script</b></sub><br/><img src="images/screenshots/cyrillic-card.png" width="280"/></td>
<td align="center" valign="top"><sub><b>What went into the decks</b></sub><br/><img src="images/screenshots/stats.png" width="280"/></td>
<td align="center" valign="top"><sub><b>Providers, sync, and cost</b></sub><br/><img src="images/screenshots/status.png" width="280"/></td>
</tr>
</table>

### Quick start

1. [Install it](installation.md) and run it on your own machine.
2. [Configure your languages](configuration.md) — one Anki deck and one voice per
   source language, plus at least one free LLM provider key.
3. [Deploy to Oracle Cloud](deploy-oracle.md) — $0/month forever, tailnet-only.
4. [Install the PWA](pwa-install.md) on your phone and add the share-sheet
   Shortcut.
