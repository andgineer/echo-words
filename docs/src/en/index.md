# echo-words

A private vocabulary tutor for every word you meet. Send a word, a phrase or a
whole sentence, and echo-words explains what a dictionary will not — then writes
the flashcard for you, into the Anki deck you already review. It explains; Anki
makes you remember.

echo-words is a FastAPI backend and a Vue 3 PWA that gives you

- **an explanation, not a translation** — every target-language-distinct sense
  with its register, the collocations and prepositions the word takes, what it is
  confused with, its origin, and examples with their translations; an idiom or
  phrase is explained as a whole and also offers its component words as chips
- **the sense you actually met** — a word looked up out of a text is explained
  in that text's sense, not replaced by the nearest dictionary meaning
- **one selected sense, reviewed four ways** — the unit and its translations are
  asked in both directions, then its example is asked once highlighted and once
  gapped; every sense remains available as a chip for a separate note
- **a real voice, not a robot** — natural-sounding audio, locally with Piper or
  online with edge-tts, in the app and on the card; whatever you send is voiced
  whole, so a word taken out of a sentence is played beside that sentence
- **a whole sentence gets a lesson instead** — translated, with what is hard in
  it explained, and every word plus the expressions worth learning offered as
  chips; tapping one creates its own four-card note
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

echo-words is not an app you download from a store. It is a small server of your
own, and the app on your phone is the page that server serves. So the first step
is putting the server somewhere, and there are two places it can run:

| | **Oracle Cloud: for real use** | **Your computer: for a quick look** |
|---|---|---|
| Runs | always, on a free cloud VM | only while you keep it running |
| Opens on | your phone and your computers, wherever you are | the browser on that one computer |
| Cards | land in your Anki decks through AnkiWeb | stay in a trial collection no Anki app sees |
| Costs | $0/month | $0 |
| Your part | create the VM once; two commands do the rest | one free LLM key and a few commands |

**Install it on Oracle Cloud.** It costs nothing: the VM is Oracle's Always Free
tier, the private network is Tailscale's free Personal plan, and the answers come
from a pool of free LLM providers. A paid OpenAI key is optional, and without one
nothing is ever billed. The install is automated. Once you have created the VM
and joined it to your Tailscale network, one command prepares the machine and
one command builds and starts the app, and that second command is also how you
update it. Run it on your own computer only to see what the app does before you
set that up.

#### On Oracle Cloud

1. [Create the free VM](deploy-oracle.md) and join it to your Tailscale network.
2. Write the VM's address, at least one free LLM provider key and your AnkiWeb
   login into the deploy settings on your computer, as
   [Configuration](configuration.md) describes.
3. Run `uv run inv setup-app --with-host-prep` once, then
   `uv run inv deploy --ref=main`, as [Install on Oracle Cloud](deploy-oracle.md)
   describes.
4. [Install the app on your phone](pwa-install.md), and add the share-sheet
   Shortcut if you want it.
5. Choose your languages in the app. It starts with English, German and Serbian,
   each with its own Anki deck and voice.

#### On your computer

[Try it on your computer](try-locally.md): one free LLM key and `uv run inv dev`.
