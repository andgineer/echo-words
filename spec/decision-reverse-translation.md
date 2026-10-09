# Decision: reverse translation

Status: **the reverse prompt is measured and reviewed four times; nothing in the app
asks it yet.** The
feature is designed in `spec/plan/reverse-translation.md`, and what it will do for
the reader is described there until it lands.

## What letters can prove

Whether a typed word is in the target language rather than the selected one is
decided by its letters wherever they prove it: a letter the target writes and the
source does not proves the target, one the source writes and the target does not
proves the source, and a word with neither, or both, is proved neither way. The
letters are the directory's own per-language alphabets, the same ones the card's
front-sentence test reads; a target outside the directory has no known letters, so
there every letter counts as the source's own and letters never prove the target.

Measured on wordfreq's top lists, words of three or more letters, the first 2,000
per language; Serbian taken from wordfreq's `sh` list (Latin) and transliterated
for the Cyrillic row:

| Source → target | Target words proved by letters | Source words left open by letters |
|---|---|---|
| English / German → Russian | 100% | 0% |
| Serbian → Russian | 43% | 0% in Latin, 73% in Cyrillic |
| German → English | 0% | 89% |
| Serbian → English | 0% | 83% |
| English → German | 11% | 100% |
| Serbian → German | 11% | 83% |

Serbian Cyrillic lacks Russian й щ ъ ы ь э ю я ё; Ukrainian and Bulgarian separate
from Russian on 11% of Russian words. So with a Russian target, a Russian word
letters leave open (город, книга, стол) can only be met on the Serbian tab in
Cyrillic, which is 57% of Russian words.

The letter rule cannot see a loanword that keeps the target's diacritics, so with a
Latin target it reads some source words as the target's. Measured on the first
20,000 words of the same lists: with a French or Spanish target, 6–8 English or
German words, the only common ones café and fiancé and the rest names (josé,
pokémon, andré). Nothing at all with a Russian target.

Placeholder widths for the input field (built CSS, Chromium and WebKit, 360 px
viewport, 294 px of text room): «Текст или !русское слово» 193, «!английское» 219,
«!азербайджанское» 269 (the longest in the directory), «Текст или !слово на
суахили» 215.

## The reverse prompt

One call turns a target-language wording into the source language's words for it:
a verdict (a word, not a word, or a sentence), the target-language word it was read
as, and up to six source-language equivalents, one per meaning, the commonest
first, each with one everyday source-language sentence using it in that meaning.
The first equivalent is the one carded and its sentence is the card's front; the
others are offered as chips.

An equivalent the source language's own validation refuses is dropped, and an
example is screened by the card's own front-sentence test — the source language's
script, no letter only the target writes, the context bound, and the equivalent's
words found whole in it, in order, by the form the answer says the sentence spells
it in — provided that form shares a stem with the equivalent, else by the equivalent
itself. A failing example costs its equivalent the sentence and leaves it a bare
chip; neither costs the answer. A whole-word comparison with the equivalent would
refuse most inflected German and Serbian examples, and a substring one passes «сто»
inside «место»; the stem condition exists because an answer can name another word as
the form and write its sentence around that word, and it costs only a suppletive form
(went for go) its sentence. A one-word headword takes the letter case its own sentence
writes it in mid-sentence: the models return headwords in dictionary typography, or
with German nouns lowered, depending on how the case is asked for.

## Measured on the free pool, Russian target

The fixtures were fixed before each run, each Russian wording asked into English,
German and Serbian unless marked: one clear meaning (стол, окно, собака), several
meanings (ключ, коса, лук, мир), an inflected form (столы, ключей), an expression
(в конце концов, сломя голову), no direct equivalent (тоска, авось), a misspelling
(сотл, сабака, ключь), not a word (фывапр), a sentence (я иду домой), and Serbian
typed on a Russian keyboard, into Serbian only (йош for још, моя for моја, йедан,
ньега, мойе). The same runs asked the Serbian tab's own judgement and article about
four Russian words its letters leave open (город, книга, девушка, собака).

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

## Decision

The reverse prompt and its parser are what the reverse lookup is built on for every
source language: English and German carry it as measured. Serbian's first cards
carry faults of the kind its ordinary article already ships with, and its chips carry
more of them, non-words among them. Whether the Serbian tab shows those chips is the
operator's to decide; that decision, and acceptance of the faults listed above, are
open, and nothing here accepts them.
