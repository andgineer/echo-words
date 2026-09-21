# Implementation plan — defects seen in use and in the bench, none of them fixed yet

Eighteen items, from three readings.

Items 1, 2, 12, 13, 17 and 18 were found while running the app against the real
provider keys and reading what it did, or by tracing what it did in production. Each was reproduced and has its evidence written
down; two sibling defects found in the same session — the player speaking a
corrected misspelling, and sense chips that all carried the same word — are
already fixed and are not repeated here.

Items 3 to 11, 14 and 15 come from a different reading: the review packets of the
smoke-tier bench runs behind the source-language sense cue and the answer shape,
read item by item by a fresh agent each time. Every deterministic contract and
every quality threshold in those runs was green, so these are the faults an
automated screen cannot see. Each quotes the answer it was found in, because the
run directories are not checked in and the evidence has to outlive them.

Item 16 comes from neither: an audit of what the deployed host had actually
cached, which is what showed that the head of the audio chain had been answering
nothing at all.

## 1. A rebuilt bundle can leave the reader on a white screen

Observed locally: after `inv build-static` produced a new hashed bundle, the next
page load rendered nothing. The service worker served its cached `index.html`,
which references the previous asset hash, and that file no longer exists — the
request answered `404`, `#app` stayed empty, and the console was silent. A second
reload recovered it, because by then the new worker had taken over.

The PWA is configured `registerType: "autoUpdate"` with `skipWaiting` and
`clientsClaim`, so one reload is meant to be enough. What is unknown, and is the
first task here, is whether a deploy reproduces it: the local rebuild **deletes**
the old asset (`emptyOutDir`), while a deploy replaces a checkout and may leave the
precached pair internally consistent. Reproduce it against a deployed build before
changing anything — a fix aimed at a failure that does not happen there would be
machinery for nothing.

If it does reproduce, the reader meets a blank page after every release, which is
the most serious of the items on this page.

## 2. One user action makes two concurrent pool calls

Every unit submission opens two pool calls at once — the article and the
attestation. When the pool's first choice refuses, both meet the same refusal, so
one reader action counts twice against that provider and drives its cooldown ladder
at twice the rate a single call would.

This is recorded here as the defect it is, and not scheduled: llmbroker's queue
carries the routing fix that decides how much it still costs. Revisit once that
fix has shipped and the pool's behaviour has been re-measured — the app's own
call shape is not the cheaper end to change, since both calls are wanted and
neither can be deferred behind the other.

## 3. A wrong grammatical form reaches a card, and nothing can see it

Bulgarian `разказвам` was carded with three examples that wedge the first-person
citation form into sentences needing another person:

    Той често <b>разказвам</b> за своето детство.   (needs разказва)
    Какво ми <b>разказвам</b> сега?                 (needs разказваш)
    <<b>разказвам</b>> ти интересна история.        (stray literal angle brackets)

The third is example one, so it is the ContextRecognition front. This fixture
exists because Bulgarian cites a verb in the first person singular, and the model
failed the trap in every sentence.

The next run carded four more of the same kind, in four languages: `Мораните да
<b>водите рачуна</b> о свом здрављу.` (`Мораните` is no Serbian word — `Морате`),
`В<b>неділю</b> ми плануємо поїхати за місто.` (the space is gone, so the gapped
card reads `В___ ми плануємо…`), `Отвори <b>прозорец</b>, ...` (Bulgarian wants
the definite `прозореца`), and, on a tappable sense chip, the English
`The company went <b>bank</b>.` — a sentence of no language at all, carrying the
translation "банкрот".

The backend tests a sentence's alphabet, never its grammar, so nothing between the
model and the deck can see this. Whatever is done here is a judgement about how
much grammar the backend may claim to know, which is why it is written down before
anything is built: a repair that guesses an inflected form is the failure mode the
answer-shape decisions have refused elsewhere. The stray `<` `>` around the bold
span is separable and is a plain sanitizer question.

## 4. A coinage was carded because the judge vouched for it

`Löffelangst`, a word that does not exist, was carded with a confident sense —
"боязнь заболеть бешенством" — an invented folk etymology about rabies and
cutlery, and two invented citations. The standalone judgement is what should have
stopped it, and `openrouter-laguna-s-2.1` answered `{"used": true, "where":
"informal speech, southern Germany/Austria"}`.

The aggregate threshold tolerates this: the smoke tier asks that two of three
unused wordings be refused, two were, and the screen stayed green. So the guard
that exists for exactly this reader-facing harm can fail on a concrete item
without the run saying so. What is open is whether the judgement is asked
differently, asked of more than one model, or whether a single vouching answer
should stop being enough.

## 5. A word of two scripts reaches a card front

`bare-sr-grad` carded this example:

    Naš <b>grad</b> ima mnogo lepiх parkova.

`lepiх` is Latin `lepi` followed by CYRILLIC SMALL LETTER HA. It is the only
occurrence in the run, and it lands on the ContextRecognition front and the
ContextProduction gapped front. The note also has the Cyrillic headword `град`
beside a Latin sentence, so one note shows two scripts across its four cards.

Serbian is configured `latin+cyrillic`, so both alphabets are legal letters and
the sentence passes the source-language test. This is the one item on this page
the backend can settle deterministically: a word-shaped token of a
`latin+cyrillic` language may not mix the two scripts inside itself. Whether the
example is dropped or the note refused is the open choice; mixing scripts within
one word is not a spelling any of these languages has.

## 6. Invented origins reach the reader

Three confident and wrong, in one smoke tier: `олівець` said to be borrowed from
Turkic (it is from `олово`); `разказвам` traced to "казнить" (the root is
`казать`); `Löffelangst` given the rabies story above. Two more say nothing while
sounding like an origin: `прозорец` "восходящее к общему индоевропейскому фонду с
кодом *or-*", `causal` "происходит от латинского слова через английские суффиксы".

The next run added three more: `reluctant` from a Latin verb `*reductare` (it is
`reluctari`), `олівець` given the Turkic story that belongs to Russian `карандаш`,
and `прозорец` from a reconstructed `*prъzъrcъ`.

The prompt already says to leave the origin out where it is not known, because an
origin reasoned out from the parts of a word reads exactly like one that is known.
The instruction is not obeyed, and no screen tests it — an etymology is prose, and
prose is only checked for its markup. What is open is whether this is worth a
measurement of its own or is the price of the section.

## 7. A near-neighbour warning that does not fire, and a collocation invented in its place

`wider` was answered with no mention of `wieder`, which is the whole reason that
fixture exists. The same article invents the collocation `wider Erwachten` — the
wording is `wider Erwarten` — and glosses `wider besseres Wissen` as "против
собственной совести" when it is against better knowledge, not conscience. Its
prose translations ("против, навстречу, о") also disagree with the ones it carded
("против, вопреки, наперекор").

`causal` did warn about `casual`, so the arm is not dead; one of two fired.

## 8. The article's markup and prose are not held to what the format rules ask

From one run: `text-sr-8` returns Markdown, not HTML — `**Sve mi se čini da …**`,
whose asterisks print literally. Several answers nest bold inside bold
(`<b>…<b>…</b>…</b>`). `cyrillic-bg-prozorec` glues words to tags:
`Затворих<b>прозорец</b>а`. `neighbour-en-causal` prints a half-Russian example,
"Мы ищем <b>causal</b> links between the two events." `text-de-4` prints the
corrupted token `сыat по горло` — Latin letters spliced into a Cyrillic word — and
opens with the ungrammatical "Мне надоело этот шум."

The sanitizer decides what tags survive; it does not decide whether the text
around them is one language, one script, or grammatical. Some of this is
sanitizer work and some is not, which is the first thing to separate.

## 9. Card content in the wrong language, and reader-visible translations that invert the sense

`typo-en-recieve` carried "приймать" into the `Translations` field — the Ukrainian
word, not a Russian one, and it is the answer the card gives. Separately, and
short of a card, `bare-en-reluctant` translated both of its examples as though the
action happened: "He was <b>reluctant</b> to sign the contract." → "Он неохотно
подписал контракт." `reluctant to X` asserts unwillingness, not reluctant
performance. Example translations are shown to the reader and are not one of the
six fields, so this one stops at the article.

The next run put three more wrong translations on card backs: `вина` for
`Verantwortung`, which is responsibility and not guilt; `это` beside `он` for
Serbian `Он`; and `неделя` as a co-equal translation of Ukrainian `неділя`, which
is Sunday — the very false friend that fixture exists to catch, carded as the
mistake.

The translations that do reach a card are the ones worth a guard, if any is
possible: the target language's alphabet is testable, a wrong word inside it is
not.

## 10. A target-language word inside a source-language sentence, where the letter test cannot see it

`bare-sr-grad` carded `Живим у красивом старом граду.` — `красивом` is Russian;
Serbian is `лепом`. `cyrillic-uk-rozmovlyaty` printed the Russian ending in its
forms table, `ти розмовляешь` for `розмовляєш`.

The guard that exists is `sentence_is_source_language`, and it works by letters:
it holds a sentence to the alphabet the source language spells with. Against
Russian, that leaves it four letters or fewer for Ukrainian and Bulgarian, and
almost nothing for Serbian Cyrillic — so a whole Russian word inside a Serbian
sentence passes, and reaches a card front. The same blindness is written into
`decision-card-shapes.md` as a limitation of the sense cue; this is the same hole
seen from the sentence side, where what it lets through is what the reader
reviews. Any fix is a judgement about how the backend can know a word belongs to
a language at all, which is why nothing is proposed here.

## 11. A note carded on the wrong language's word

`neighbour-de-wider` was answered as though `wider` were the English word: the
note carries the translations "шире, более широкий", the carded sentence
`Dieser Fluss ist hier viel wider als dort oben.`, a forms table of `wider gehen`
and `wider werden`, and an etymology from `weit` + `-er`. German `wider` means
*against*. Every card of that note teaches a word that does not exist, and it
reached the reader.

The request names the source language plainly, and nothing downstream can catch
this: the spelling is a real German string, the sentences are in German letters,
and the payload is well formed. What the same fixture returned in the run before
it was correct, from another provider, so this is one model reading a homograph
as English rather than a standing behaviour — which is why the open question is
whether a note this wrong is reachable by any check the app can run, or whether
it belongs with the qualitative model errors the backend does not adjudicate.

## 12. The deeper article has no length anyone chose

Reported from ordinary use: "Подробнее" — the paid deeper article — comes back
"безумно длинный". The extended prompt now asks for around 2000 characters and never
more than 4000, and nothing in the code enforces either. Measured on 2026-09-21 over
171 deeper articles from nine configurations, none exceeded 4000 characters and the
medians per configuration ran from 2080 to 2980; the configuration the app now asks
wrote a median of 2740. The instruction holds as a ceiling and overshoots the target
by a third to a half. Whether that is still too long for the reader is theirs to say.

Length is the whole complaint, so it is the thing to decide: a reader who taps
"the full entry" wants more than the article, not an essay. Whether that is a
sentence in the prompt, a bound like the answer's, or both is open — but the
budget the paid step spends is real money, and a longer answer also costs the
reader the wait it takes to write.

## 13. A sense chip repeats the sense already on the card

`die Tafel` was carded, and the entry still offered a chip reading "плитка" with
the same sense the note carries. A chip is an invitation to analyse that sense as
its own unit; one that repeats the carded sense invites the reader to make the
card they already have.

The chip that was saved is hidden by index — the sense the note was built from is
the one dropped from the display. That catches the ordinary case and misses this
one, where the answer returned two senses whose content is the same and only one
of them was carded. So there are two faults here and they need telling apart: an
answer that returns a duplicate sense, and a display rule that can only recognise
the duplicate by position. Neither a text comparison of the translations nor the
mere count of senses settles it — the reader's question is whether the second chip
would produce a different card.

## 14. A false friend confirmed on the card's translations field

`неділя` (uk) was carded with translations `воскресенье, неделя`. It means
Sunday; the Ukrainian for week is `тиждень`. The Recall front therefore reads
"воскресенье, неделя" and teaches the false friend the fixture exists to catch.
The article compounds it — four of six table rows render `неділі` as "неделе".

This is worse than the article defects around it because the translations field is
a card field: the reader drills it. Nothing downstream can see it — the spelling
is a real Ukrainian word, the sentences are in Ukrainian letters, the payload is
well formed. Recorded in `decision-answer-shape.md` with the run that found it;
the false-friend pair is not vouched for on the strength of that run, since `стол`
passed and this one failed.

## 15. Two card-front sentences that are not the language they claim

From the same reading: `bare-sr-voditi` carded `Моратите ___ о свом здрављу.` —
`Моратите` is not a Serbian word, the form is `Морате` — and `bare-sr-grad`
carded `Живим у красивом старом ___.`, where `красивом` is the Russian adjective
and Serbian wants `лепом`. Both are ContextRecognition fronts and
ContextProduction stimuli, so both are drilled.

The letter test cannot see either: every character is legal Serbian Cyrillic. It
is the same class as 10 and 11 — a word that is spelled plausibly for the source
language and is not a word of it — and it is what a reader meets rather than what
a screen can catch.

## 16. Cards already made silent still carry no recording

Of the 200 cards made since 21 Aug, 42 carry no audio at all: the head of the
audio chain was answering nothing, and where the engines had no voice either the
note was written silent. Fingerprinting the mp3 frames of the 305 recordings
cached on the host found 293 at 22 050 Hz and 12 at 24 000 Hz — the two engines —
and none at the 44.1 kHz a human recording carries, so nothing came from the
chain's first step at all.

New cards are unaffected: the head of the chain reaches Wikimedia Commons now.
The 42 are a maintenance pass of its own, and it **needs the operator's word
before anything writes to the collection**, which is why it is here rather than
done.

Three ways to close it, and what each costs.

- **A pass of its own**, in the shape of the two maintenance commands that
  already exist: it names the notes it would touch, writes nothing until that is
  confirmed, runs with the service stopped, fetches each headword through the
  chain as it now stands, attaches the media to the existing note, leaves every
  other field alone, and syncs. No model call, about two minutes for the
  forty-two, and it stays useful for any card made silent later. Roughly a
  hundred and fifty lines with its tests.
- **Re-submitting the words by hand** needs no code and buys a fresh analysis for
  each one: forty-two pool answers against a daily cap of a hundred, and
  forty-two cards whose text changes for the sake of their audio.
- **Leaving them** costs nothing and leaves a fifth of that window's cards mute.

The pass is the one worth building, and it is built: `inv backfill-recordings`
names what it would fill, writes nothing until that is confirmed, fetches through
the chain as it stands, changes only the audio of a silent note, leaves a word the
chain still cannot speak alone, and syncs. The defect stands until it is run,
which is the operator's word.

## 17. The answer budget bounds silence, not the answer

`stream_api` passes `ANSWER_BUDGET_SECONDS` to `client.stream(prompt, timeout=…)`,
llmbroker hands that number to httpx as a bare float, and httpx spreads a bare float
across connect, read, write and pool separately. For a streaming response the one that
governs is `read` — the gap between two chunks. So the constant bounds silence rather
than the answer: a model that trickles for two minutes is never cut off, and one that
thinks quietly for twenty-six seconds is, before it has written anything.

`functional-description.md` calls that number the complete-answer budget of one model
attempt and says plainly that time to the first token is deliberately not a
requirement, because bounding it would prefer a model that trickles for a minute over
one that thinks briefly and then answers at once. The implementation bounds exactly
what the description refuses to bound.

Two ways to close it.

- **Fix the semantics**: an overall deadline around the stream plus a short connect
  timeout, which is what the description asks for and what a bare float cannot
  express.
- **Wait for the next occurrence first.** The one call that may have hit it left no
  record of whether it timed out or failed some other way; the step now logs its
  first-token and total time, so the next one says which, and a number changed without
  knowing which failure it caused is tuning blind.

Waiting is the one worth taking, and it costs nothing but the wait.

## 18. A word the chain could not speak has no second chance the reader can give it

The chain runs once, when the card is made. A word it could not speak — Commons
throttled, a voice not yet downloaded, the network gone — is carded silent, and
the next step writes at the same cache path, so nothing in ordinary use asks
again. The reader sees a card with no sound and has no way to say "try that
again": the only thing that can heal it is an operator running
`inv backfill-recordings` over the whole collection with the service stopped.

The cost is small per word and it accumulates in the only place that matters, the
deck the reader reviews. It is also invisible: nothing on the page says the audio
failed rather than that this word simply has no recording.

Two ways to give it back to the reader.

- **A retry beside the entry**, shown when the answer produced no audio: it asks
  the chain again with the cache discarded, and on success attaches the recording
  to the note that was already saved, so the deck gets it without the card being
  rebuilt. The pieces exist — the chain already takes a refresh that ignores what
  the cache holds, and the maintenance pass already replaces a note's media and
  syncs it. What is new is the affordance, an endpoint behind it, and saying on
  the page whether the word has no recording or the attempt failed.
- **Leave it to the operator's pass**, which is where it stands. It works, it is
  measured, and it costs the reader nothing — but it needs the service stopped, it
  runs over the whole collection, and a reader who is not the operator has no way
  to ask for it.

The retry is the one worth building, and the same affordance covers the word an
engine spoke where Commons has a recording — the condition is wider, the
machinery identical.

## What is deliberately not here

- **The cooldown ladder that took a working model out of the pool for half an
  hour.** It is llmbroker's, its queue carries the reasoning, and its condition for
  returning is written there.
- **Two blanks for a contiguous two-word unit.** `I ___ ___ after ten minutes.`
  says the answer is two words, and the operator does not read that as a defect:
  a two-word unit is two words, and the front is not a riddle about its length.
- **The two defects already fixed in this session.** They are in the code and in
  the tests; a plan that lists finished work is an archive.
