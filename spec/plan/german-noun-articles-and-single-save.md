# German noun articles and duplicate cards from one save

Status: step 1 built and measured; its fresh semantic review of the bench
packets is pending. Steps 2 and 3 have not started. Nothing is pushed or
deployed.

Step 1 as built: the German unit prompt asks each meaning whether the unit
is a noun, its article or articles, and the headword after the article; the
parser enforces the claim on the carded meaning only and keeps the lemma as
the note's identity; the card's word field and the entry's correction notice
print the article form. Measured once on the free pool in
`experiments/.bench-noun-articles` (smoke tier German re-asks plus the
fourteen `run-articles` fixtures, 33 calls, all answered): 7 of 9 noun
fixtures carded as expected, 5 of 5 controls carded as typed, the tier
green. The two misses (`das schwarzes Brett`, a refused `Kindern`) are
recorded as limitations in `spec/decision-card-shapes.md`. The packets to
review are `review-packet-articles.json` and, for the German items,
`review-packet-smoke.json`, both in that directory.

## What the reader should see

- A saved German noun or noun phrase carries its nominative definite article
  with the dictionary headword. The German → Russian bare front and every
  answer that prints the German headword use the same form. Examples keep
  their own articles, agreement, and case.
- One submission saves at most one note. It normally yields four cards.
  When both bare directions ask the same question with the same answer,
  the note yields one bare card and two context cards. A delivery retry
  cannot create another note. An intentional repeat save has a new
  submission ID and still creates its own note, even for the same word
  and sense.

This plan changes future saves. The existing collection and its schedules
are outside its scope.

## What was checked

The pipeline has one storage call on the final answer path. The Anki store
renders one selected meaning and adds one note. Existing tests pin one
note from a normal browser submission and four card templates per note,
even when an answer has several meanings. The existing same-process
receipt also handles a browser resend after a late response.

There is a confirmed multiple-write path for a single submission. With
the real local server and Anki store, a fake model, and sync disabled,
posting a unit once produced one note and four cards. Restarting the
server on the same collection and replaying the identical request body
and UUID produced a second entry, two notes, and eight cards in total.
The receipt lives only in the old process. The same receipt is also
eligible for expiry and capacity eviction while the server is running.
This reproduction does not establish how the duplicates found in
production were created.

A single note can also contain duplicates directly. Using the current
unit parser and Anki renderer, a German `Wi-Fi` headword with Russian
translation `Wi-Fi`, one valid context, and no audio made four cards.
Recognition and Recall both rendered `Wi-Fi → Wi-Fi`. The two context
cards differed. This was a constructed local fixture. The earlier
read-only production snapshot had no repeated visible front within
any of the 824 EchoWords notes inspected.

## 1. Carry German noun articles on new cards

- In `prompt.py` and `card.py`, ask German unit answers for explicit
  grammatical information per meaning. Distinguish nouns or nominal
  phrases from other units. For nouns require the nominative article
  (`der`, `die`, or `das`) and support validated alternate genders where
  the same meaning genuinely takes more than one. Use plural `die` when
  the stored headword is plural. Where an adjectival noun phrase changes
  its endings after the article, carry its agreed dictionary display
  form and validate that it is the same lexical unit. Use the configured
  German language code to select this contract.
- Keep card display wording separate from the lemma used for spelling
  relations, attestation, context matching, chip navigation, and audio
  reuse. Handle an already article-bearing lookup without doubling the
  article or treating its removal from the lemma as a spelling
  correction. Preserve article-bearing fixed expressions and pronouns
  in their own right. Use selected-sense metadata for homographs such as
  `der See` and `die See`. Keep the existing audio policy for the lexical
  unit.
- Render the selected form into the existing Anki `Word` field using
  `card_fields`. The existing templates already place that word on the appropriate
  sides. Keep the Anki note type and sentence fields intact in this step. Display and storage must
  agree on which headword was carded where the PWA names it.
- Require valid grammatical data before a German unit is saved. A
  missing, malformed, or contradictory nominal result should take the
  existing bounded answer recovery path. If no usable answer is
  available, use the existing card failure outcome. Do not silently
  store a bare noun or guess an article from capitalization or a suffix.
  Check direct lookups, selected chips, reverse-selected German words,
  and correction or rebuild paths through the shared unit parser.
- Ship tests with the change. Pin parsing with recorded model answers
  and exercise rendered Anki fronts and backs. Cover all three
  articles, plural, an agreed noun phrase, an article already in the
  input, a same-spelling different-gender pair, a legitimate alternate
  gender, a verb, an article-like nonnoun, and an invalid payload.
  Assert that the highlighted and gapped sentences keep their original
  grammar. Cover any changed browser-visible notice or fallback in an
  e2e test.
- Before spending quota, select a tier and independently check the
  fixture inputs and expectations in `experiments/one_note_bench.py`.
  Include `Hund`, `Katze`, `Haus`, plural `Ferien`, `der Hund`, the lake
  and sea senses of `See` in explicit context, an inflected noun, an
  adjective-plus-noun phrase, and nonnoun and non-German controls.
  Exercise the same parse and rendering path used by the live app.
  Check availability before scoring, resume any interrupted run, and
  have a fresh agent read every item in the review packet in the same
  turn. Require correct articles on the rendered sides for the tested
  noun paths, no added articles for controls, and no spelling or
  context regressions. Record the model coverage, decision and
  limitations in the decision specs. Do not spend paid budget without
  operator approval.

## 2. Prevent the confirmed single-submission replay

- Extend the existing request-ID receipt to cover a saved note after
  process restart or in-memory receipt eviction. Keep the proof of
  save with the EchoWords note in Anki, using an internal tag carrying
  the UUID and a versioned, canonical fingerprint of the normalized
  request.
  Store the tag in the same Anki add as the note and check it under the
  existing collection writer lock before adding media or notes. Leave
  the in-memory receipt as the fast path. Keep the scope to requests
  that actually saved a note and supplied an ID.
- A matching receipt returns success for the previous save without
  rewriting its note, audio, or review schedule. A different body under
  that ID remains a conflict. Check the receipt before starting another
  model call after restart, and define an explicit already-saved reply
  the PWA can use to clear its retry queue when the original analysis
  entry has expired. Do not return an expired entry as a new live entry
  or give the replay a new Delete or Undo target. A fresh request ID must
  follow the ordinary save path, even when word, sense and example are
  identical.
- Carry the original receipt through an intentional correction or
  rebuild that replaces its note. Roll it back with the note if
  replacement fails. A deleted note need not leave a durable receipt
  behind. Older notes have no request ID and cannot be matched safely
  by word or front. This fix does not compare meanings across deliberate
  saves or deduplicate an existing deck.
- Add real-collection regression tests with fake external boundaries.
  Simulate the lost receipt after Anki commits, restart on the same
  collection, and replay the same ID and normalized body. Assert one
  note, the original four card IDs and schedules, and no new model call
  or media in the replay. Also cover same-process concurrent replay,
  receipt eviction, a different body under the same ID, replacement
  success and rollback, and two intentional same-word saves with
  different IDs. Extend the late-response browser test to cover restart
  and verify both what the reader sees and that the queue clears without
  writing another note. This step does not change model instructions or
  interpretation.

## 3. Generate each distinct prompt once within a note

- Compare the two bare cards after the selected sense and display
  headword have been rendered. When both visible question texts and
  both visible answer texts match, keep Recognition, including its
  pronunciation where available. Keep both contextual cards. Compare
  normalized visible wording with conservative Unicode and whitespace
  normalization. Audio availability, HTML wrapping, and punctuation
  used only by the template do not make a second copy useful. Preserve
  meaningful punctuation, case, extra translations, and actual sense
  cues. Equal fronts with different answers require separate review.
- Make the Recall template conditional per note. On a disposable
  collection the installed Anki library already generated ordinals
  0, 2, and 3 with a populated suppression field and all four with
  it empty. Extend that proof to note edits, replacement, close and
  reopen, and sync or card regeneration. Prefer
  preventing generation to deleting the new Recall card after save.
  Verify that stored card kinds, reported counts, and undo and delete
  reflect the cards actually generated.
- Check how the installed Anki version handles existing notes and
  schedules before settling the field and template migration. Preserve
  legacy cards and their schedules. If the migration requires a
  one-way full sync, stop for a separate operator decision before
  applying it to the server. Document the effect and verify on a
  collection copy, including unchanged non-EchoWords notes.
- Ship a regression through the real parser and Anki renderer. Cover
  an identical question and answer with and without audio, an ordinary
  German noun after article formatting, a same-spelling pair whose
  answers differ, a visible sense cue, a translation list, and the
  four-card multilingual controls. Verify the two contextual prompts
  separately. Include an existing e2e save path if the browser
  exposes a changed card count or card-kind status.
- Replay recorded answers and add the collision and ordinary controls
  to the Anki output checks in `experiments/one_note_bench.py`. Validate
  the collision fixture against the rules after step 1. Include a
  source/target pair where the same surface remains valid after that
  change. Use a separate free-pool measurement and fresh semantic
  review if the approach changes the prompt, parser, or model-answer
  contract. Amend the four-card rule in the functional description and
  decision specs when this step lands.

## Handoff

Use the repository's fresh-agent implementation and review loop one
step at a time. When each change lands, update the functional description
and the relevant card, answer, and spaced-repetition decision specs to
describe current behavior. The intentional-repeat product decision
remains in force. Run `uv run inv pre` to convergence, then
`uv run inv test` with the frontend suite included, for each step.
Remove this plan once all three steps land. A push and a deployment each
require separate operator approval.
