# Decision: reverse translation

Status: **the reverse prompt is measured and reviewed four times, Serbian asked in
Latin letters six times more, the prompt with the sentence translation three times, and
the paid model's answers to it once; the app asks it and routes typed input by the
language line.** What the reader gets is
in `spec/functional-description.md`; this file holds the measurements and the reasoning
behind it.

## Alphabets, not letters, and a model where alphabets overlap

Whether input typed without `!` is in the target language is never read off its
letters. An alphabet decides only where the tab's and the target's cannot be confused:
input in a script the target writes and the tab does not is the target's (Cyrillic on
the English tab with a Russian target), and input in a script the tab writes and the
target does not is the tab's (Latin on the Serbian tab, since nobody types Russian in
Latin letters). Where both write the script, a model reads the input, and only a plain
target reading reverses: a missed reverse costs the reader a `!` or one tap on the
offer, a wrong one throws away the word they wanted.

Single letters prove nothing, and the operator ruled them out. Measured on wordfreq's
top lists, words of three or more letters, the first 2,000 per language, Serbian
taken from wordfreq's `sh` list (Latin) and transliterated for the Cyrillic row:

| Source → target | Target words a letter would prove | Source words a letter would leave open |
|---|---|---|
| Serbian → Russian | 43% | 73% in Cyrillic |
| German → English | 0% | 89% |
| Serbian → English | 0% | 83% |
| English → German | 11% | 100% |

And where a letter seems to prove something, it misleads: a Russian keyboard has no
ј љ њ ћ ђ џ, so Serbian typed on one carries Russian letters (йош for још, кньига for
књига, ноч for ноћ), and many Russian words use only letters Serbian shares (город,
книга, собака).

### Reading the input where alphabets overlap

A model reads input in a shared script and answers whether it is the tab's own wording,
a misspelling of it, or target wording typed without its `!`. It was measured on 72
cases fixed before the runs and audited blind by a fresh reviewer: Cyrillic on the
Serbian tab with a Russian target (Serbian words, forms and false friends, Serbian typed
on a Russian keyboard, Russian words, sentences) and Latin on the English and German
tabs with a Serbian target. A second fresh reviewer graded every answer:

| | First prompt, 3 samples | Prompt in the code, 2 samples |
|---|---|---|
| The tab's own wording reversed | 13 of 118 | 4 of 78 |
| Target wording caught | 77 of 78 | 48 of 50 |
| Open cases reversed | 9 of 14 | 4 of 10 |

The first prompt asked which of the three the input is. The one in the code has the
model first name the tab's word the input is, is a form of, or misspells, counting
letters a keyboard for another language puts in place of missing ones, and allows a
target reading only when it names none. It keeps the Serbian typed on a Russian keyboard
that the first prompt reversed (йош, ноч, девойка). It still reverses the same two words
in both samples: Serbian врач (a sorcerer; Russian a doctor) and English pas (a dance
step; Serbian a dog), each a word of the tab spelled like a common target word, its own
meaning the rarer one. A third sample was cut off by an exhausted pool and is not
counted. Jev, asked the same question, separates nothing: on the Serbian tab the tab's
own words score 0.17 to 0.86 and Russian ones 0.72 to 0.88.

The operator ruled out the separate call: the answer the app asks anyway names the
language the input is written in, and a single word reverses only when the judgement
the app also asks of the typed word finds it unused in the tab's language.

### The language line in the answer

Only typed input is asked; a chip or a rebuild comes from the app's own answer and
keeps the prompt it was measured with. The answer copies what the reader typed, then
names the language of that copy by its two-letter code: the tab's code for anything in
the tab's language (any form, regional standard, misspelling, a keyboard's stand-in
letters, a word that also means something elsewhere), otherwise the target's code for
the target in any alphabet or national standard, otherwise the language's own code.

Measured on the 117 language cases on the free pool, 2026-10-11 and 2026-10-12:

| | "source", "target" or a code | a code alone | the copy, then its code (two samples) |
|---|---|---|---|
| The tab's own wording named another language | 0 of 35 | 0 of 63 | 0 of 66, 1 of 66 |
| Target wording caught | 2 of 24 | 19 of 27 | 25 of 28, 22 of 25 |
| Another language named right | — | 10 of 16 | 11 of 17, 10 of 16 |

Asked for "source" or "target", the model reads "source" as the language the input is
in, which is always true; a clause about translations raised it only to 15 of 28. A code
alone, written after the article, names the article's language: «hvala» on the English
tab is answered with an article on «thank you» and named English, «Merci beaucoup» on
the German tab is named German by an answer that says it is French. Copying the input
first points the code at the input.

The full tier asked with the line passes every gate on a healthy pool (203 of 227 from
the workhorse); every one of its 196 typed answers names the tab's language, no article
mentions the line, and a fresh review of every item finds the same faults at the same
rates as the runs before it. Two hints from that one sample are watched, not findings:
one typo of six named as a typo against two to four before, and one word answer refused
for an empty field of the text shape.

What the line still gets wrong, from the fresh reviews of both samples:

- **Serbian on the English or German tab named Croatian** in both samples on the same
  three inputs («video moj telefon», «hvala lepo», «kuća»), words both languages spell
  alike. Croatian and Bosnian are the same language to the reader of a Serbian tab, so
  for a reader who has a Serbian tab and no tab for the language named, the answer's
  Croatian or Bosnian counts as Serbian and the input moves to the Serbian tab; a reader
  with a Croatian or Bosnian tab is moved there.
- **French greetings English and German dictionaries carry** («bonjour», «merci») are
  named the tab's language in both samples, an English phrase on the German tab in one.
  The reader gets today's answer.
- **About three target inputs of 28 per sample are missed**, different ones each time;
  one per sample is lost to a broken card (the workhorse garbled a Cyrillic escape in
  3 of the 482 answers of the three runs). The reader gets today's answer.
- **The tab's wording named the target once**: «йош», Serbian још typed on a Russian
  keyboard, named Russian in one sample of two. It is a single word, so the judgement of
  «йош» itself must also refuse it; when it does, the reverse call finds no Russian word
  and the floor returns the ordinary answer, one call later.

The same reviews found faults of the answer itself that reach the reader whatever the
line says, stable across both samples: look-alikes carded with the Russian sense (врач as
a doctor, жир as fat), the tab's sense missing (диван without «wonderful», сто without
«table»), Russian работа carded as standard Serbian, English «baba» given an invented
sense, German «Most» rewritten as «meist».

### What the routing costs, and where it stops

The reverse lookup is the last resort wherever a model decides. For a lookup the line
asked for, the tab's own answer is kept in hand while the lookup runs: when the lookup
finds no target word, or no model answers it, or only a pool model other than the main
one does, that answer goes on with nothing asked twice, and no paid answer is bought over
the lookup, because the reader is not left with an empty page. A lookup the reader asked
for with `!`, or one an alphabet decided, has nothing on the page yet, so an answer the
pool cannot make usable, or one a pool model other than the main one wrote, is bought
from the paid model without asking, and a lookup that finds no word says so rather than
falling back to a reading the reader has just ruled out.

Input the answer names as another of the reader's languages is asked again on that tab
once and without the line, so it can neither move a second time nor reverse; a tab whose
alphabet cannot write the input is not moved to. A word of a language no tab teaches
keeps its article past the judgement's refusal, since the judgement is about the tab's
language, in which a word of another one is rightly unused. A typed word the tab refuses
is not offered the lookup a second time once the lookup has answered that it is no word
of the target.

The line is the last thing an answer writes, so the tab's own answer to typed text is on
the page while it is being written, and a reversal or a move replaces it once it ends. A
single word is mostly spared this, because its text is held back until the judgement
vouches for it and a word of another language is usually refused. Holding typed text
back until its answer is complete would spare the rest, at the cost of every typed text
appearing all at once instead of as it is written; the operator chose on 2026-10-12 to
leave the answer visible, since it shows only after input the tab was not meant for and
corrects itself.

Text mixing the two alphabets where they differ («я люблю Python» on the English tab) is
read as the target's: the tab's own validation refuses any letter it does not write, so
no reading of the tab is lost.

### Dropped alternatives

- **Letter tests**: a letter proves too little and misleads where it seems to prove
  something (table above).
- **Converting Serbian Cyrillic input to Latin before asking**: it would hide the one
  signal the reader gave, and a Russian word converted is still a Russian word.
- **A separate reading call** before the answer: the operator ruled it out in favour of
  the line the answer already carries, which costs no call.
- **Jev as the reader**: its scores for the tab's own words and for Russian ones overlap
  (above).
- **Wiktionary translation tables** as the source of equivalents: no sentence for the
  card's front, and no reading of an inflected form or a slip.
- **A rule of its own for a tab in the target language itself**: considered and dropped
  by the operator, since no such tab exists; there `!` asks for a word's equivalents in
  its own language and every refused word is offered that lookup.

### The empty field's hint

Measured in the field's own font at a 360 px viewport, where the field has 262 px of
text room; a browser test repeats it in Chromium and WebKit for the longest names in
the directory and the three that do not decline, with a Russian target, in both
interface languages.

| Hint | Width |
|---|---|
| «Текст или !русский текст» (the alphabets overlap) | 190 |
| «Русский или английский текст» | 232 |
| «Русский или азербайджанский текст» | 282 |
| «Русский текст или текст на африкаанс» | 293 |

Where the alphabets differ the hint is the two bare names («Русский или английский»):
with the noun after them the English and German tabs fit and six of the twelve tabs
measured do not, and a verb in front («Введите русский или английский текст») is longer
still.
A bare name also needs no ending, so the names that do not decline (африкаанс,
эсперанто, суахили) read the same way. Where the alphabets overlap the hint keeps the
shortcut and the noun, which fits with a Russian target.

## The reverse prompt

One call turns a target-language wording into the source language's words for it:
a verdict (a word, not a word, or a sentence), the target-language word it was read
as, and up to six source-language equivalents, one per meaning, the commonest
first, each with one everyday source-language sentence using it in that meaning.
The first equivalent is the one carded and its sentence is the card's front; the
others are offered as chips. A sentence comes back translated into natural
source-language text, so the same call tells the shapes apart and the sentence goes
down the text path; a sentence without its translation is an unusable answer.

An equivalent the source language's own validation refuses is dropped, and an
example is screened by the card's own front-sentence test — the source language's
script, no letter only the target writes, the context bound, and the equivalent's
words found whole in it, in order, by the form the answer says the sentence spells
it in — provided that form shares a stem with the equivalent, else by the equivalent
itself. A failing example costs its equivalent the sentence and leaves it a bare
chip; neither costs the answer. Serbian is asked in Latin letters, and an answer that
comes back in Cyrillic is read as written. A whole-word comparison with the equivalent would
refuse most inflected German and Serbian examples, and a substring one passes «сто»
inside «место»; the stem condition exists because an answer can name another word as
the form and write its sentence around that word, and it costs only a suppletive form
(went for go) its sentence. A one-word headword takes the letter case its own sentence
writes it in mid-sentence: the models return headwords in dictionary typography, or
with German nouns lowered, depending on how the case is asked for.

An answer is read past a string value that lacks its opening quote. The workhorse drops
that quote repeatably on some answers, so asking again buys the same break; re-reading
every recorded reverse answer and 4,840 recorded answers of other benches with the
tolerance changed only the broken ones, each to its right reading. The same break was
found once in a recorded article answer, which the article's own reader still refuses.

An answer is read, too, when it sets a string value between typographic quotes („…”,
“…”), the way its sentence would be printed, instead of straight ones. That reading is
tried last, after the answer as written and the missing-quote reading, so a
straight-quoted string that merely contains „…” is read as written. Of the 6,880
recorded answers one carries the break, a Serbian answer for мир, and reading it changed
no other answer.

## Measured on the free pool, Russian target

The fixtures were fixed before each run, each Russian wording asked into English,
German and Serbian unless marked: one clear meaning (стол, окно, собака), several
meanings (ключ, коса, лук, мир), an inflected form (столы, ключей), an expression
(в конце концов, сломя голову), no direct equivalent (тоска, авось), a misspelling
(сотл, сабака, ключь), not a word (фывапр), a sentence (я иду домой), and Serbian
typed on a Russian keyboard, into Serbian only (йош for још, моя for моја, йедан,
ньега, мойе). The same runs asked the Serbian tab's own judgement and article about
four Russian words spelled in letters Serbian shares (город, книга, девушка, собака).

### First prompt: not fit

50 reverse calls on 2026-10-09, all answered, the workhorse present but intermittently
refused by its provider for demand (gpt-oss-120b 34 reverse answers, gemini-flash-lite
14, two others one each). All 50 parsed and 47 verdicts were as expected. A fresh
reviewer read every item and found 8 blockers and 26 majors:

- other senses of the English word leaking into German and Serbian equivalents
  (Tabelle and табела for стол, Tonart for ключ, clamp and Kumpel for собака);
- padding toward the cap of six with narrower or merely related words;
- fixed expressions "corrected" into another form (сломя голову read as сломить
  голову), which the entry header would show as a correction;
- сотл refused twice, and йош (још on a Russian keyboard) read as a Russian
  euphemism and carded as a Serbian vulgarism with a profane front sentence — an
  answer that also takes it away from the Serbian article, which today corrects it
  to још;
- an insult as a chip's sentence;
- an example written around another word than its equivalent (Schalterfenster for
  Schiebefenster), which the parser kept because the answer named that word as the
  form;
- Serbian wrong words, non-words and agreement errors in front sentences.

The reviewer judged the last pattern to be the free models' command of Serbian, not
something wording can teach, and every other one to be the prompt's or the parser's.

### Second prompt

The prompt now asks only for meanings the Russian wording itself has, usually one to
three, so that a Russian speaker reading the example would put the wording back; a
bare dictionary form; a fixed expression kept as its own dictionary form; a misspelling
as one or two letters off a common word; no swearword, insult or slur; and it refuses
a source-language word typed in target letters that is no target word, instead of
reading it as a misspelling. The parser drops an example whose form shares no stem
with its equivalent's word.

59 reverse calls the same day, all answered, gemini-flash-lite carrying nearly all of
them. 58 parsed — the one that did not wrote "dog" as its verdict, which production
answers by asking the pool again and then the paid model. 55 verdicts were as
expected: every keyboard-Serbian word ended where it should (йош, йедан, ньега and
мойе refused, so the Serbian article takes them; моя carded as мој), and сабака and
ключь were read as собака and ключ. сотл was refused in all three languages: a
swapped pair of letters is a misspelling the models do not read, and the reader is
told to check the spelling. Equivalents per word answer fell from a mean of 2.9
(max 6) to 2.2 (max 3). The stem check dropped three examples, each a sentence about
another word (Tisch for Verpflegung, кључа for извор, инструмент for клавијатура),
and no valid one.

A second fresh reviewer read every item. English: 13 of 16 cards right, 2 of 22 chips
wrong, every front sentence natural. German: 13 of 16, but 9 of 13 noun headwords came
back in lower case (tisch, verpflegung) and one front sentence with them («hals über
kopf») — the prompt's own "lower case unless the language spells it otherwise", since
the first prompt had capitalised every one. Serbian: 13 of 17 cards right and 5 of 12
chips wrong (свемир for мир, a participle offered as an adverb, a false friend carding
коса as hair), which the reviewer judged to be the models' Serbian and the same class
of fault the Serbian article already ships with. No sentence carried a swearword, and
the keyboard-Serbian fallback held for all five.

### Third prompt: capitalisation

The headword was then asked for "spelled and capitalised exactly as a dictionary heads
its entry". 59 reverse calls the same day, all answered, gemini-flash-lite 53 of the
calls. 58 parsed — one answer broke its own JSON with a malformed escape — and 55
verdicts were as expected, the three misses again сотл in every language. The screen
dropped six examples, each rightly: four written around another word or not
containing their own, one Serbian sentence with a Russian щ.

A third fresh reviewer: 13 of 16 cards right in English, 13 of 16 in German, 14 of 17
in Serbian; 2 of 18, 5 of 22 and 4 of 13 chips wrong. German nouns were capitalised
again, but gpt-oss read "as a dictionary heads its entry" as dictionary typography
and returned World, Peace and СВЕТ, СПОКОЈСТВО in capitals; one German idiom was
misspelt by the model in its sentence too (hals über Kopf). Meanings reached through
English leaked into German on this run as on every earlier one (Tabelle twice for
стол, Noten for a key in music).

Wording can give a headword's case only so far, so the parser now takes it from the
sentence: a single word standing mid-sentence keeps the case it is spelled in there,
capitals are lowered, and a word opening its sentence keeps its own case unless the
answer copied its form in lower case. Re-scored on the third run's recorded answers,
it changed exactly the two answers in capitals and nothing else.

### Fourth prompt: no meaning by way of English

One sentence added: translate from the target language directly, never by way of
English or another third language, since a meaning only the go-between word has is no
meaning of the wording. 59 reverse calls the same day, all answered and all parsed,
gemini-flash-lite 56 of the calls; 56 verdicts as expected, the misses сотл in every
language. Of the meanings the earlier reviews had named as reached through English,
none recurred in German.

A fourth fresh reviewer read every item and compared each fixture with the three
earlier runs:

| | First card right, commonest meaning | Wrong chips | Blockers / majors / minors |
|---|---|---|---|
| English | 14 of 16 | 4 of 23 | 1 / 5 / 6 |
| German | 13 of 16 | 2 of 21 | 2 / 3 / 5 |
| Serbian | 13 of 17 | 5 of 12 | 3 / 6 / 3 |

German wrong chips fell from 5 to 2. What remains, and what wording has not moved
in four runs:

- сотл is refused in every language. The prompt names swapped letters; the models
  refuse the swap anyway, and the reader is told to check the spelling.
- коса is carded as the scythe in English and German, with the braid — the commonest
  meaning — only a chip.
- «Hals über Kopf» has been misspelt in its own headword and sentence on every run.
- Meanings reached through English still reach English and Serbian chips (tonality
  for a clef, клавијатура, излог for a shop window), and gpt-oss once offered a
  swearword chip the prompt forbids.
- Serbian: a broken agreement in the лук front sentence, авось carded as «надати
  се» after the right word was refused for mixing scripts, коса carded through the
  false friend (Serbian коса is hair), and non-words among the chips (клијух,
  помрсуму). The same models' Serbian article shows faults of the same kind.

Every verdict on a non-word, a sentence and keyboard Serbian was right on the last
three runs. A rescue for an example whose form the answer gave in its dictionary
form, matching the sentence's words by stem instead, was measured on all four runs'
answers and rejected: of the seven sentences it would have kept, five were about
another word or broken.

### Latency

The reverse call answered in a median of 0.97 s, p90 1.81 s, on the fourth run,
0.99 s and 4.10 s on the third, and 1.13 s and 1.78 s on the second. On the first, 46 of 50 answers came within the
pool's 25-second budget (median 2.40 s, p90 4.01 s); four waited behind provider
cooldowns, and production would have stepped those up to the paid model at the
budget.

### Serbian in Latin letters

Serbian is asked in Latin letters, the script its reader reads it in and the one nearly
everyone in Serbia types. To that reader Croatian, Bosnian and ijekavian forms (svjež,
napokon) are the same language and no fault. Cyrillic Serbian also shares its letters
with Russian, so there a Russian word passes for Serbian, where in Latin any Cyrillic
letter is foreign. The 23 Serbian lookups were asked three times with the one sentence
the prompt carries, and three times with a fuller one that also asked for the ekavian
standard of Serbia, a dictionary word for every equivalent and an expression kept in its
own words. A fresh reviewer graded all six samples and the three Cyrillic runs on one
scale; on the workhorse's answers:

| | Cyrillic, 3 runs | Latin, 3 samples | Fuller Latin, 3 samples |
|---|---|---|---|
| First card right | 37 of 44 | 40 of 47 | 36 of 47 |
| Wrong chips | 14 of 36 | 6 of 38 | 5 of 35 |
| Invented headwords | 3, all chips | 2, both first cards | 3, all first cards |
| Ijekavian or Croatian forms | 0 | 5 | 0 |
| Unreadable answers | 0 | 0 | 2 |

In Latin the card is as good and the chips are as clean as English's. авось is carded as
valjda, the closest word, in every Latin sample. The false friend коса, carded as hair,
survives both scripts. Every Latin answer for сломя голову fused the idiom into a word no
dictionary lists (glavobezobzirovno, glavobezobzirno, glavobezobziro, glavobezobzirom),
five of five, the fuller wording forbidding exactly that, where every Cyrillic answer gave
главом без обзира. The fuller wording is not used: it removed only forms the reader
counts as Serbian, and brought in answers that dropped both quotes around their sentences
(тоска, two of three), «kučka» offered for a dog (two of three) and a broken front
sentence in each sample.

A fused idiom does not reach a card under its own spelling. The first equivalent goes
through the Serbian judgement like any typed word, and asked once about each of the four
spellings it refused all four. Two entries then ended refused, one as a misspelling whose
article names glavom bez obzira, and one corrected to glavom bez obzirom, a wrong case of
the idiom that the second judgement accepted and that is carded.

Two of the 138 Latin answers came back in Cyrillic, both from fallback models, and are
read as written. The one the prompt carries heads the card for стол with стол, the
Croatian and Bosnian word for a table, under a sentence that makes no sense, beside two
wrong chips (маса, бора).

### Sentences

The prompt with the sentence's translation was asked three times with the same
fixtures and four Russian sentences into each tab language (я иду домой, не опаздываем
ли мы на поезд, где ты был вчера, мне нужно купить хлеб): sample a on 2026-10-12, and
samples b and c on 2026-10-12 and 2026-10-13. Each is 68 reverse calls, and every one
was answered. gemini-flash-lite gave all 68 answers of sample a, 54 of b and 56 of c;
the rest came from gpt-oss-120b (13 and 9), laguna (1 and 1) and nemotron (2 in c),
seven of b's after the workhorse's daily quota had run out and the others while it
cooled off for a minute after each rate-limit refusal the bench's pace drew. A fresh
reviewer read every item of sample a, and a second one every item of b and c on one
scale.

On the workhorse's answers:

| | Sample a | Sample b | Sample c |
|---|---|---|---|
| English, first card right | 13 of 15 | 10 of 12 | 11 of 12 |
| English, wrong chips | 4 of 22 | 1 of 19 | 2 of 20 |
| German, first card right | 13 of 15 | 9 of 9 | 12 of 13 |
| German, wrong chips | 3 of 19 | 1 of 11 | 2 of 17 |
| Serbian, first card right | 15 of 16 | 13 of 13 | 11 of 12 |
| Serbian, wrong chips | 3 of 11 | 3 of 12 | 0 of 6 |
| Sentences translated right, all tabs | 12 of 12 | 12 of 12 | 10 of 10 |

The three samples agree. Every translation is faithful, natural and in the tab's
language: "I am going home", «Wo warst du gestern?», «moram da kupim hleb». The one
shift is «не опаздываем ли мы на поезд» given as "Are we going to miss the train?" and
«Verpassen wir den Zug?»: the sense holds, but a reader after опаздывать gets miss
rather than be late; sample c's English gave "Are we late for the train?". Punctuation
follows the input unevenly (a question mark added in English and German, none in
Serbian). Every first card the workhorse got wrong in b and c is one of the accepted
misses: коса four times and English авось once. Every non-word was refused, сабака and
ключь were read as their words, and «crni luk» was rightly first for лук.

What the workhorse repeats across the samples:

- сотл refused, eight times of eight.
- коса carded as the scythe in English and German with the braid a chip, and as
  Serbian kosa, hair, with no other meaning.
- English авось carded as hope, which is надежда, in two samples and as chance in the
  third; German vielleicht and Serbian valjda are right.
- Two Serbian answers come back in Cyrillic in every sample and are read as written:
  the card for сломя голову, «главом без обзира», which is the exact idiom, and the
  sentence «да ли каснимо на воз», the same string three times.
- Chips whose sentence is nonsense or about another word (board in "room and board",
  Abteilung, ministarstvo and katedra for стол, kuća for a dog, Gemeinschaft for мир,
  Chance for окно, «a rich food»), and three that give наконец for в конце концов. On
  the workhorse it is a chip in seven over the three samples.
- Serbian в конце концов is carded as «konačno», the word for наконец; «na kraju
  krajeva» is never offered. Serbian ключ repeats «ključ» for every meaning, so the
  reader gets one card, no chips and never «izvor».
- An answer the parser cannot read: three of the 78 Serbian answers as first given. The
  sentences of тоска came twice with both quotes missing, and собака once with the bare
  word Description where each sentence belongs. Asked again, as production does, тоска
  and собака came back readable. Sample c's answer for мир, its sentences set inside
  typographic quotes („…”), is read: «mir» with «svet» a chip, both sentences right, so
  sample c reads 67 of its 68 answers.

Seen once on the workhorse: «halsüberkopf» misspelt in the German headword and its
front sentence (a); йош on the Serbian tab read as ещё and carded as još, so the reader
lands on the word they meant under a header claiming they typed ещё (a); and ньега,
which is њега on a Russian keyboard, read as него and carded as «nego», a false friend
that means "but rather" (c). The other thirteen keyboard-Serbian answers, two of them
from gpt-oss, ended where they should.

**Which model answers matters more than the wording.** The second reviewer's count of
samples b and c, split by who answered:

| | Workhorse | Other pool models |
|---|---|---|
| First card right | 66 of 71 | 15 of 20 |
| Wrong chips | 9 of 85 | 17 of 30 |
| Sentences | 22 of 22 translated right | 2 of 2 carded as a word |

The other models' wrong cards are of a kind the workhorse never gave: коса answered
with a necktie, a bridal bouquet and a tile (laguna); сотл read as «сотить», no Russian
word, and carded as lay (gpt-oss); сломя голову as «kopfüber», head first into water
(gpt-oss), and as «in Eile» (laguna), so that expression has no right German card in
three samples; собака under the front sentence «Dog barks loudly.» (gpt-oss); and
«я иду домой» cut into its words and carded as I and as gehen (gpt-oss). gpt-oss also
returns headwords in capitals, and five of its six Serbian chips were wrong (kos, rt,
Nadamo se, Za svaki slučaj, Operi), though it alone carded Serbian коса as «pletenica»,
the braid.

How often that happens in use: of the 311 answers production gave in the three weeks
to 2026-10-13, the workhorse wrote 228 and gpt-oss 82. Before 2026-10-11 it is 220 of
259 against 38, about one answer in seven. On 2026-10-11 to 2026-10-13, while benches
were spending the workhorse's daily quota, gpt-oss wrote 44 of 52: the quota is the
app's own, and after the bench of 2026-10-12 had exhausted it the reader's next
morning, before the reset, got 27 of 29 answers from gpt-oss. The operator leaves the
benches' timing as it is.

Sample c, asked on a fresh quota, answered in a median of 0.87 s (p90 2.83 s). In
sample a the first ten answers took under 1.4 s each and the rest 3 to 12 s (median
6.5 s) as the pool neared its daily quota, which ran out half an hour later.

### The paid model

A lookup the reader asked for is asked of the paid model whenever the pool's main model
does not answer it and the paid step is open to it, with a paid key set and the day's
cap not spent, so the same 68 reverse calls were bought from it on 2026-10-13:
gpt-5.6-luna, the model the paid step asks by default. Every call was answered and every
answer could be read. It is slower: a median of 5.6 s, p90 11.3 s, the slowest 20.5 s,
none past the 25-second budget.

A fresh reviewer graded it blind, beside the workhorse's answers to the same inputs
with the models' names withheld — sample c's where the workhorse had answered readably,
sample a's for the other fourteen:

| | Paid model | Workhorse |
|---|---|---|
| First card right | 48 of 49 | 42 of 46 |
| Wrong chips | 2 of 72 | 5 of 53 |
| Sentences translated right | 12 of 12 | 12 of 12 |
| сотл read as стол | 3 of 3 | 0 of 3 |
| Serbian answers in Cyrillic | 0 | 2 |
| The better answer of the two | 24 fixtures | 6 fixtures |

The paid model does not make the misses accepted of the workhorse. It cards коса as
the braid on every tab (braid, Zopf, pletenica) with the scythe a chip, авось as
perhaps, and сломя голову as «in Windeseile» beside a correctly spelt «Hals über Kopf»;
its Serbian is all in Latin letters, and its translations are capitalised and
punctuated («Kommen wir nicht zu spät zum Zug?», «Zar ne kasnimo na voz?»).

Its own faults:

- Serbian typed on a Russian keyboard is carded where it should be refused, three
  inputs of four: йош read as ёж and carded as «jež», a hedgehog; ньега read as нега
  and carded as «uživanje»; мойе read as мой and carded as «moj». The workhorse refused
  three of the same four.
- Its lists run longer, a mean of 2.4 equivalents and up to six, the tail made of
  obsolete or technical senses (throne and presto for стол, Schalter for ключ). Two
  chips are wrong: «Taste» for ключ, and Serbian «okno», a mine shaft, for окно.
- One Serbian card, «sto», lost its sentence: the answer named the dictionary form for
  a sentence that inflects it («Knjiga je na stolu.»), and the card is then made from
  the article's own example.

It is fit to answer the lookup on all three tabs, and nothing here asks for another
paid model.

### A Jev check on the Serbian equivalents

Every distinct Serbian equivalent the recorded runs offered, 96 across the Cyrillic runs
and the Latin samples, was labelled by a fresh reviewer who saw no score, and scored by
Jev (TypeSafe's jev-1.13.0) on two questions: is it a real Serbian word, Croatian,
Bosnian and ijekavian forms included, and does it translate the Russian word in the
sense its sentence uses. The reviewer found half of them unfit to show, every one for
its meaning, 14 also no word at all, and none a Russian word passed off as Serbian. What
goes wrong is invented words (клијух, Пружница, glavobezobzirno), meanings reached
through English (табела, тоналност, клавијатура) and neighbouring meanings (поток for a
spring, косина), not Russian leaking in.

Dropping an equivalent Jev scores under one half on either question:

| | Unfit, dropped | Fit, dropped |
|---|---|---|
| Cards | 6 of 12 | 2 of 24 |
| Chips | 28 of 36 | 10 of 24 |

Among the fit ones it drops are главом без обзира, the exact idiom for сломя голову, and
извор for the spring sense of ключ every time it is offered; among the unfit ones it
keeps are the false friend нега, brzopleto and непромишљено (rashly) for сломя голову,
and a vulgar card for йош, which is no Russian word. A check took a quarter of a second,
and the 96 cost under a fifth of a cent. Jev is not asked: it would lose a third of the
good chips and a twelfth of the good cards to catch half the bad cards, and its two
questions were fixed before the labels, so rewording them on these same labels would
measure nothing.

### The offer on the Serbian tab

The Serbian judgement accepted город ("archaic, Church Slavonic"), девушка ("a
Russianism among younger speakers") and собака ("standard Serbian, all registers") as
Serbian; the reviewer found all three wrong, собака plainly so. It refused книга. The
Serbian article headed each with its Serbian equivalent (град, девојка, пас, књига)
and called the Russian word a form of it. So with a Russian word typed without `!`:
for three of the four the reader gets a card for the right Serbian word through the
ordinary path, under a judgement that is wrong about the typed word, and only книга
is refused and offered the reverse lookup — whose answer is the same књига. The
offer is reached rarely, and the false acceptances are a finding about the
attestation judgement on Russian input, not about the reverse prompt.

The judgement does not hold its answer: asked again on 2026-10-12 and twice on
2026-10-13 it refused город, девушка and собака and accepted книга ("Old Church
Slavonic, archaic, or regional"), the opposite on every word. The articles headed the
four with the same Serbian words, and the language line, asked with them, named all
four Russian.

## Decision

The reverse prompt and its parser are what the reverse lookup is built on for every
source language: English and German carry it as measured, and Serbian in Latin
letters with its chips, which the operator chose on 2026-10-09 over the first card
only and over Cyrillic. The language line is what routes typed input where the
alphabets overlap, as measured above.

The operator accepted on 2026-10-12, as known limitations of the reverse lookup and the
language line, the misses that every run repeated and no wording moved: сотл refused,
коса carded as the scythe or as Serbian hair, «Hals über Kopf» misspelt, English авось
carded as hope, a chip in about six with a wrong meaning or a sentence about another
word, йош read as ещё, French greetings named the tab's language, and the few target
inputs per sample the line misses. On 2026-10-13 the operator accepted one more of the
same kind as йош: ньега read as него and carded as «nego». On 2026-10-15 the operator
accepted the faults of the ordinary article the same reviews found: look-alikes carded
with the Russian sense, recorded with the other card faults in
`decision-answer-shape.md`, and answers broken past reading — 3 of 78 Serbian reverse
answers, every one from gemini-flash-lite — which are asked again at the cost of a few
seconds' wait.

The reverse answers of the pool's other models are not accepted, by the operator's
decision of the same day. A lookup the reader asked for with `!`, or one an alphabet
decided, that any pool model but the main one answered is set aside unseen and answered
by the paid model instead, inside the daily cap; the pool's answer stands only when the
paid step is refused, or gives no answer that can be read, because an entry that failed
is worse than a weaker lookup. A last-resort lookup such a model answered counts as no
answer: the tab's own answer stands, and a refused word is still offered the lookup with
one tap. The rating a lookup gives the pool model that answered it is unchanged, because
the rating is per language and shared with the article, where these models' answers are
not what was measured here.

Which pool models are main is a setting of the app's, gemini-flash-lite alone by
default, and an empty one keeps every pool model's answer. The model names are
llmbroker's and change with its catalog; which of them may answer this task is the
app's choice, so it does not live in llmbroker's catalog.

What it costs the reader: a lookup bought this way waits for the other model's answer
and then for the paid one. Asking only the main model and stepping up as soon as it
cannot answer would need llmbroker to take a per-call list of the models it may use,
which it does not offer; that is an llmbroker release and is built only if the extra
wait proves noticeable in use.

Not yet observed in use: how many lookups the paid model takes over this way and what
they cost. The service log names each lookup bought over another pool model's answer
and each last-resort lookup dropped for the same reason; for a week after the routing
is first deployed, those lines are counted against the reverse lookups in the log, and
the share and the paid spend are recorded here.
