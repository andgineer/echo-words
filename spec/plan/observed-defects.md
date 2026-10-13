# Implementation plan — defects seen in use and in the bench, none of them fixed yet

Fifteen items, from two readings.

Items 9 and 11 were found while running the app against the real provider keys
and reading what it did, or by tracing what it did in production. Each was
reproduced and has its evidence written down.

Items 1 to 8, 10 and 12 to 15 come from a different reading: the review packets
of the smoke-tier bench runs behind the source-language sense cue and the answer shape,
and of the language-line and reverse-lookup runs of 2026-10-11 to 2026-10-13, read
item by item by a fresh agent each time. Every deterministic contract and
every quality threshold in those runs was green, so these are the faults an
automated screen cannot see. Each quotes the answer it was found in, because the
run directories are not checked in and the evidence has to outlive them.

## 1. A wrong grammatical form reaches a card, and nothing can see it

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

## 2. A word of two scripts reaches a card front

`bare-sr-grad` carded this example:

    Naš <b>grad</b> ima mnogo lepiх parkova.

`lepiх` is Latin `lepi` followed by CYRILLIC SMALL LETTER HA. It is the only
occurrence in the run, and it lands on the ContextRecognition front and the
ContextProduction gapped front. The note also has the Cyrillic headword `град`
beside a Latin sentence, so one note shows two scripts across its four cards.

Serbian is configured `latin+cyrillic`, so both alphabets are legal letters and
the sentence passes the source-language test. Mixing scripts within one word is not
a spelling any of these languages has, but the operator has ruled out letter checks
on a model's answer: the fix is a prompt line or a model check, measured like any
prompt change.

## 3. Invented origins reach the reader

Three confident and wrong, in one smoke tier: `олівець` said to be borrowed from
Turkic (it is from `олово`); `разказвам` traced to "казнить" (the root is
`казать`); `Löffelangst`, a word that does not exist, given a folk etymology about
rabies and cutlery. Two more say nothing while
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

## 4. A near-neighbour warning that does not fire, and a collocation invented in its place

`wider` was answered with no mention of `wieder`, which is the whole reason that
fixture exists. The same article invents the collocation `wider Erwachten` — the
wording is `wider Erwarten` — and glosses `wider besseres Wissen` as "против
собственной совести" when it is against better knowledge, not conscience. Its
prose translations ("против, навстречу, о") also disagree with the ones it carded
("против, вопреки, наперекор").

`causal` did warn about `casual`, so the arm is not dead; one of two fired.

## 5. The article's markup and prose are not held to what the format rules ask

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

## 6. Card content in the wrong language, and reader-visible translations that invert the sense

`typo-en-recieve` carried "приймать" into the `Translations` field — the Ukrainian
word, not a Russian one, and it is the answer the card gives. Separately, and
short of a card, `bare-en-reluctant` translated both of its examples as though the
action happened: "He was <b>reluctant</b> to sign the contract." → "Он неохотно
подписал контракт." `reluctant to X` asserts unwillingness, not reluctant
performance. Example translations are shown to the reader and are not one of the
six fields, so this one stops at the article.

The next run put two more wrong translations on card backs: `вина` for
`Verantwortung`, which is responsibility and not guilt, and `это` beside `он` for
Serbian `Он`; a third, `неділя`, is item 10.

The translations that do reach a card are the ones worth a guard, if any is
possible: the target language's alphabet is testable, a wrong word inside it is
not.

## 7. A target-language word inside a source-language sentence, where the letter test cannot see it

`bare-sr-grad` carded `Живим у красивом старом граду.` — `красивом` is Russian;
Serbian is `лепом`. `cyrillic-uk-rozmovlyaty` printed the Russian ending in its
forms table, `ти розмовляешь` for `розмовляєш`. The reverse-translation bench
(2026-10-09) met it again where Russian is the input: the Serbian article for a
typed `собака` carded `пас` with the example `В моем дворе живет велики пас.`,
three Russian words of five, and its article for `книга` wrote «Моя сестра обожает
читать хорошую књигу пред спавање.». On 2026-10-12 its article for a typed `город`
wrote «Усев је потпуно унищен због кад је пао град» in its prose — a Russian щ in
`уништен` and a broken clause — while the card's example of the same sentence was
right.

The guard that exists is `sentence_is_source_language`, and it works by letters:
it holds a sentence to the alphabet the source language spells with. Against
Russian, that leaves it four letters or fewer for Ukrainian and Bulgarian, and
almost nothing for Serbian Cyrillic — so a whole Russian word inside a Serbian
sentence passes, and reaches a card front. The same blindness is written into
`decision-card-shapes.md` as a limitation of the sense cue; this is the same hole
seen from the sentence side, where what it lets through is what the reader
reviews. The `красивом` sentence and `bare-sr-voditi`'s `Моратите ___ о свом здрављу.`
(`Моратите` is no Serbian word; `Морате`) were ContextRecognition fronts and
ContextProduction stimuli, so both are drilled. Any fix is a judgement about how
the backend can know a word belongs to a language at all, which is why nothing is
proposed here.

## 8. A note carded on the wrong language's word

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

## 9. A sense chip repeats the sense already on the card

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

## 10. A false friend confirmed on the card's translations field

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

## 11. The answer budget bounds silence, not the answer

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

## 12. Serbian look-alikes carded with the Russian meaning, and their own missing

Both samples of the language bench (2026-10-11 and 2026-10-12, the Serbian tab, a
Russian target) carded five Serbian words that Russian spells alike as though they were
the Russian word, the same way in every answer that could be read:

- `врач` (a soothsayer) carded as a doctor: «врач, доктор (неформ.)», then «ветеринар,
  врач».
- `жир` (acorns fed to pigs) given, after the right «желудь», a second meaning «жир,
  сало» under «свињски» and «животињски» — the Russian fat.
- `сто` carded only as «сто, сотня»: the hundred, with no table, which is what Serbian
  `сто` most often means.
- `диван` carded only as «диван, софа, тахта»: the sofa, with no «wonderful», the
  adjective Serbian uses it for; the other sample's answer was unreadable.
- `работа` carded as plain Serbian for work («работа, труд, занятие»), where Serbian
  says `рад` or `посао` and `работа` is colloquial at most.

The language line named all five Serbian, rightly, so the reader stays on the Serbian
tab and drills the Russian meaning. The judgement's attestation does not catch it
either: each is a real Serbian spelling. The same blindness as items 7 and 10, from
the headword's side.

## 13. A real word answered as another word, or with a meaning it does not have

From the same two samples, with Serbian as the language translated into:

- English `baba` carded with «grandmother» («baka, nana») and a second meaning «rug»
  («tepih, tepihče» in one sample, «baka» in the other), which English `baba` does not
  have.
- German `Most` (must, cider) carded as `meist` in one sample and `am meisten` in the
  other: the reader typed a correct German word and got a card for a different one,
  with no correction announced.

## 14. An answer broken past reading costs the reader a second call

3 of the 482 answers of the language runs and the full tier of 2026-10-11 and
2026-10-12 garbled a Cyrillic escape inside the card block, splicing letters of
another script into it: `\u04нд` (Serbian `диван`), `\u04िलों` (`kuća`), `\u04해서`
(`вопрос`). The card block does not parse, and production asks again — the pool, then
the paid model — so the reader waits for a second answer. Each came from
gemini-flash-lite, and only answers that chose to escape their Cyrillic did it (3 of
13).

The reverse lookup has its own form of it: the Serbian answer for `тоска` on
2026-10-12 dropped both quotes around its example sentences —
`"example": obuzela ga je neopisiva tuga zbog odlaska, form": "tuga"` — where the parser
reads past one missing opening quote and no more. The same break came back in two of
three answers under a fuller wording measured earlier.

Over the three samples of 2026-10-12 and 2026-10-13 it is 4 of the 78 Serbian reverse
answers as first given, every one from gemini-flash-lite and none in English or German:
`тоска` twice with no quotes, `мир` once with its sentences inside typographic quotes
(`"example": „Posle dugih pregovora konačno je sklopljen mir između dve zemlje.”`), and
`собака` once with the bare word `Description` in place of each sentence. The two that
were asked again came back readable. A lookup the reader asked for with `!` then waits
for a second answer, the pool's or a paid one; a lookup tried as the last resort is
dropped and the tab's own answer stands.

## 15. A reverse lookup answered by one of the pool's other models

The reverse lookup is asked of the pool like every other answer, so when
gemini-flash-lite is out of quota or cooling off, another model answers it. In samples
b and c of 2026-10-12 and 2026-10-13 that was 26 of 136 answers (gpt-oss-120b 22,
laguna 2, nemotron 2), and a fresh reviewer read them beside the workhorse's:

| | gemini-flash-lite | The other models |
|---|---|---|
| First card right | 66 of 71 | 15 of 20 |
| Wrong chips | 9 of 85 | 17 of 30 |
| Sentences | 22 of 22 translated right | 2 of 2 carded as a word |

Every card the workhorse got wrong is a miss the operator has accepted. The others'
are not of that kind:

- German `коса` (laguna): carded as Krawatte «Er trug eine breite Krawatte.», with the
  chips Brautstrauß and Fliese — a necktie, a bridal bouquet and a tile.
- English `сотл` (gpt-oss): read as «сотить», which is no Russian word and is what the
  entry's heading would show, and carded as lay «The hen will lay a clutch of eggs
  tomorrow.», with the chip breed.
- German `сломя голову`: kopfüber «Er sprang kopfüber ins Wasser.» (gpt-oss) and
  in Eile «Er hat das in Eile gemacht.» (laguna).
- English `собака` (gpt-oss): the right word under a front sentence that is not
  English, «Dog barks loudly.», beside the chip Cur «Cur snarls at strangers.».
- `я иду домой` (gpt-oss), English and German: answered as a word, so the sentence is
  never translated: it is carded as I «I walked to the store.» with the chips go and
  home, and as gehen.
- Serbian chips from gpt-oss, five wrong of six: kos (a blackbird) and rt «Na Jadranu
  se nalazi poznata rt.» for `коса`, Nadamo se and Za svaki slučaj for `авось`, Operi
  «Operi ruke pre jela.» for `моя`.
- A chip whose sentence insults somebody, which the prompt forbids: Drachen «Die alte
  Nachbarin ist ein richtiger Drachen.» for `собака` (nemotron).

How often a reader meets it: in production's own journal the workhorse wrote 220 of
the 259 answers of 2026-09-21 to 2026-10-10 and gpt-oss 38, about one in seven. A
bench that exhausts the workhorse's daily quota raises that for everyone until the
reset, because the quota is the app's: after the bench of 2026-10-12 the next
morning's use got 27 of 29 answers from gpt-oss.

Nothing in the app tells a reverse answer of one model from another's. The paid model
was measured on the same inputs on 2026-10-13 and answers them better than the
workhorse does (48 of 49 first cards right, 2 of 72 chips wrong, a median of 5.6 s), so
an answer bought from it in place of another model's is known to be the better one;
nothing buys it yet except a silent pool or an unreadable answer.

## What is deliberately not here

- **The cooldown ladder that took a working model out of the pool for half an
  hour.** It is llmbroker's, its queue carries the reasoning, and its condition for
  returning is written there.
- **Two blanks for a contiguous two-word unit.** `I ___ ___ after ten minutes.`
  says the answer is two words, and the operator does not read that as a defect:
  a two-word unit is two words, and the front is not a riddle about its length.
