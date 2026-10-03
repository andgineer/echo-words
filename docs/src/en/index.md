# echo-words

A private vocabulary tutor for every word you meet. Send a word, a phrase or a
whole sentence, and echo-words explains what a dictionary will not — then writes
the flashcard for you, into the Anki deck you already review. It explains; Anki
makes you remember.

<table>
<tr>
<td align="center" valign="top"><sub><b>A word, a phrase, a sentence</b></sub><br/><img src="images/screenshots/add-word.png" width="280"/></td>
<td align="center" valign="top"><sub><b>Analysis, audio, card in Anki</b></sub><br/><img src="images/screenshots/card-added.png" width="280"/></td>
<td align="center" valign="top"><sub><b>A sentence, translated and explained</b></sub><br/><img src="images/screenshots/sentence.png" width="280"/></td>
</tr>
</table>

- **Understand the word**: its senses, register, collocations and translated
  examples, and the sense you choose to learn.
- **Learn from a sentence**: a translation, the hard parts explained, and every
  word one tap away.
- **Keep it in Anki**: four cards for each sense, with a real voice, in the decks
  you already review.

[Everything it does](#what-it-does)

## Quick start

echo-words is a small server of your own, and the app on your phone is the page it
serves. Running it costs nothing: Oracle's Always Free VM, Tailscale's free plan
and a free Gemini key.

=== "With an AI agent"

    Have Claude Pro or Max, or ChatGPT Plus? Open the **Code** tab of the Claude
    desktop app, or **Codex** in the ChatGPT desktop app, and paste:

    ```text
    Install echo-words on Oracle Cloud for me, following
    https://andgineer.github.io/echo-words/agent-install/
    ```

    The agent tells you each step only you can do — signing up for Oracle and
    Tailscale, putting your keys in a file — and does the rest.

=== "By hand"

    1. [Get your keys](keys.md): one free Gemini key is enough.
    2. [Create the free VM](deploy-oracle.md) and join it to your Tailscale network.
    3. Write the VM's address, your keys and your AnkiWeb login into `.deploy/.env`,
       then run `uv run inv setup-app --with-host-prep` once and
       `uv run inv deploy --ref=main`, as [Install on Oracle Cloud](deploy-oracle.md)
       describes.
    4. [Install the app on your phone](pwa-install.md), and add the share-sheet
       Shortcut if you want it.
    5. Choose your languages in the app. It starts with English, German and Serbian,
       each with its own Anki deck and voice.

=== "Just a look"

    [Try it on your computer](try-locally.md) to see what it does. It runs only while
    you keep it running, only the browser on that computer opens it, and its cards
    stay in a trial collection that none of your Anki apps see.

## What it does

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
  optional and capped, and on the author's own use it costs about half a dollar a
  month

It keeps **no database**: your Anki collection is the only thing it stores.

<table>
<tr>
<td align="center" valign="top"><sub><b>Any language, any script</b></sub><br/><img src="images/screenshots/cyrillic-card.png" width="280"/></td>
<td align="center" valign="top"><sub><b>What went into the decks</b></sub><br/><img src="images/screenshots/stats.png" width="280"/></td>
<td align="center" valign="top"><sub><b>Providers, sync, and cost</b></sub><br/><img src="images/screenshots/status.png" width="280"/></td>
</tr>
</table>

## Under the hood

**Getting a complete answer from a changing model pool.** Free LLM providers vary
in availability, speed, and instruction-following. Through
[llmbroker](https://github.com/andgineer/llmbroker), echo-words races two models and
selects the first complete, usable answer. Streaming lets the reader start earlier;
recovery preserves an existing explanation if card creation fails.

**Checking what the cards actually teach.** Valid JSON can still contain the wrong
meaning, an invented origin, or a word from the wrong language. Model-facing changes
go through real-model benchmarks and a separate agent's review of the concrete
answers. The
[evaluation records](https://github.com/andgineer/echo-words/blob/main/spec/decision-llm-backend.md)
document both findings and remaining limitations.

**Keeping the backend operational in less than 1 GB.** FastAPI serves the Vue PWA
and maintains Anki through its headless Python library, syncing directly with
AnkiWeb. There is no separate application database or running Anki desktop
instance. Access to the web app is restricted to a Tailscale network.
