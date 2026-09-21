# Implementation plan — a paid tier for the card, chosen by the job

**Where it stands (2026-09-21).** The latency screen is done for both paid jobs. The
deeper article is settled and built: it asks `gpt` with reasoning off on priority
processing, configured as its own model-and-parameters pair — the measurements and the
blind review are in `decision-llm-backend.md`, § "The deeper article". What is left is
the card: one configuration survived the latency screen, and its quality is unmeasured.

## Why the card is still open

Most of what is left unfixed in `observed-defects.md` is the model's own work:
invented origins, a wrong grammatical form on a card front, a false friend carded as a
translation, a note built on the wrong language's word. No deterministic guard can see
any of them. The levers are the prompt and which model answers; this plan is the second.

`decision-llm-backend.md` measured what money buys on cards: over the same fixtures the
paid tier carried none of the target-language example sentences, corrupted or
mixed-script cells, corrupted Serbian words, parts of speech named in prose, invented
etymologies stated as fact or cards headed by another word — where the free pool carried
11, 10, 8, 10, 2 and 3. **That was `gpt-fast` reasoning at its default effort**, which is
also why it took ten seconds. Whether the same model without reasoning keeps those gains
is exactly what is unmeasured.

## What step 1 established for the card

Eight card fixtures — bare units, a selected unit in context, running text in German and
Serbian — through the production card prompt, one call at a time
(`experiments/tier_screen.py --job card`):

| configuration | first character | whole answer, median / p90 | payloads usable | a month at production volume |
|---|---:|---:|---:|---:|
| pool, production since 2026-09-06 | ~0.8 s | 2.1 / 2.6 s | — | free |
| `gpt-fast`, no reasoning, standard | 0.63 s | 4.3 / 6.1 s | 8/8 | $0.45 |
| **`gpt-fast`, no reasoning, priority** | **0.61 s** | **3.6 / 4.5 s** | 8/8 | **$0.87** |
| `gpt-fast`, low reasoning, priority | 3.0 s | 6.1 / 8.2 s | 8/8 | $1.26 |
| `gpt-mini`, no reasoning, priority | 0.70 s | 5.0 / 7.0 s | 8/8 | $9.37 |
| `haiku` | 0.66 s | 7.2 / 9.2 s | 7/8 | $2.42 |
| `sonnet`, no thinking | 1.15 s | 11.5 / 13.8 s | 8/8 | $5.40 |

Production volume is 462 answered entries in the 30 days to 2026-09-21. The bar fixed
before the run — median whole answer ≤ 4 s and median first character ≤ 1.5 s — is met by
one configuration: `gpt-fast` without reasoning on priority. It starts sooner than the
pool and finishes 1.5 s later.

## Step 2 — the quality tier, on that survivor only

A full tier through `experiments/one_note_bench.py` over the registered fixtures, the
paid arm called with the survivor's request parameters, read on the metrics the pool and
`gpt-fast` were read on: contract validity, formatting, verdict correctness,
target-language card sentences, payload repair, and the card-level classes of
`decision-llm-backend.md`. Then the mandatory reading: a fresh agent reads every item of
the review packet.

The bench's paid arm has to carry request parameters for this, the same way the tier
screen does. That is harness work, not a change to what the app says to a model.

Cost: a full tier is a few hundred calls at about $0.002 each — under a dollar.

## Step 3 — the configuration that follows

- **If the survivor matches reasoning `gpt-fast` on the defect classes**, it becomes the
  card's model where a language asks for it, with the pool as the fallback for a refusal
  or a spent cap. The setting belongs on the language row, beside the recordings prefix
  and the voice, because what is known about answers is already per language. The
  default stays the pool: no metered API may be required to run the app.
- **If it does not**, the card stays on the pool, and the choice between the pool's 2 s
  and reasoning `gpt-fast`'s ten is a product judgement about waiting to put to the
  operator with these numbers.
- Whatever wins, re-read which deterministic repairs it makes dead weight. A repair goes
  only if its measured rate on the new tier is zero over a full tier, and only while that
  tier answers; it stays while the pool can answer at all.

## What this plan must not do

- **Do not move the judgement off the pool.** Paid judgement is the one class where money
  buys a worse answer: `Löffelangst` and `змркалица` were vouched for by the paid model.
- **Do not fold the tier question into a prompt change.** A tier arm and a prompt
  revision in the same run measure neither.
- **Do not build a step up to the paid tier because a payload looked wrong.** Production
  says fourteen of fifteen rejected payloads carried an answer the reader would have
  accepted; the paid answer stays a button.
- **Do not remove a deterministic repair on the strength of a single arm.**
