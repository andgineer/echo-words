# Independent semantic review — Jev attestation experiment

Reviewed on 2026-10-01 by the fresh `jev_review` agent. The reviewer did not run
this benchmark, invoke either measured model, tune the prompt, or inspect secrets.
The reviewer audited the labels before any measured calls and inspected every one
of the 44 report items, including every raw pool answer and Jev Noul value.

Packet: `review-packet-attestation.json`. Frozen design fingerprint:
`ee967f80f56c61ec1575a549ad78307fee5b690e8cff7e86b0a2b17cb3efcc40`.

## Availability before quality

Both arms returned 44 usable logical answers from 44 logical attempts. No case was
missing or retried at the logical arm level. Pool winners were Gemini 17, Groq 21,
Nemotron 5, Laguna 1. The previous post experiment's last 100 answers were reported
as complete, with Gemini 94 and Groq 6. This is a materially different winner mix.

The reviewer inspected the saved broker call log, not only winning answers. Its
92 provider attempts comprise 45 `ok`, 43 `superseded`, two Nemotron errors, and two
Laguna HTTP 429 responses. Gemini records 18 successful attempts and 26 superseded
attempts, with no Gemini rate-limit response. Thus its lower winning share does
not establish an exhausted workhorse; it continued participating and often lost
races. There is no evidence here of whole-pool exhaustion that voids this run.
There **were** provider failures and rate limits: do not describe the providers as
failure-free. The result measures this pool's routing and availability on this run,
not a controlled comparison against one stable baseline model.

## Verdict

The exploratory result is usable for a candid research post. It does not support
replacing the production checker or claiming model-level superiority. Jev was
faster in 43 of 44 paired checks; its median latency was 0.288 seconds versus
0.923 seconds for the pool. The median of per-pair pool/Jev ratios was 2.94.
Observed p90 values were 0.383 and 7.190 seconds. These are end-to-end API approach
measurements, including different output contracts and pool routing.

At the fixed 0.5 cutoff, Jev rejected four of 35 source-backed attested inputs;
the pool rejected two. Jev rejected `bookshelfy`, `tablewards`, `Fahrradsuppe`, and
`zlopamtilo`. The pool shared the latter two errors. All three unverified challenge
strings were rejected by both models, but they are not proven factual negatives.
The six typo inputs remain a spelling-policy slice and are not included in a
factual accuracy denominator. No overall accuracy, precision, recall, or F1 is
justified by the legacy labels.

The Jev scores are not a measured calibration curve or linguistic probability.
The frozen exploratory band (0.1, 0.9) would abstain on 18/44 inputs, retaining
26/44. Among 23 retained source-backed positives there were no false rejections.
This is an observation on the same tiny dataset, not a validated abstention
policy, an accuracy guarantee, or evidence that a model fallback solves errors.
It also retains spelling-policy positives `vieleicht` (0.98) and `podrska` (0.94).

The 15,764 billed-input tokens imply an estimated $0.000662088 at the stated price.
This is an estimate for this 44-call run, not a provider invoice or measured cash
saving: the current pool has zero marginal API charge.

## Item-by-item review

`Yes`/`No` are the output labels at the frozen 0.5 cutoff. Noul is reproduced as
returned; it is not interpreted as proven confidence. `Attested` includes the
three preflight source corrections. `Policy` and `Unverified` are unscored for
factual correctness. Pool prose was examined for unsupported scope as well as
binary decisions. Its short `where` strings are model claims, not citations.

| # | Input | Evidence class | Pool | Jev Noul / label | Semantic assessment |
| --- | --- | --- | --- | --- | --- |
| 1 | `mürrisch` | Attested | Yes | 0.96 / Yes | Both accept the ordinary German adjective. Pool register is sound. |
| 2 | `Strase` | Policy | No | 0.17 / No | Both reject. Current spelling policy agrees; literal attestation is not adjudicated. Historical/address occurrences prevent a factual nonexistence claim. |
| 3 | `verschlimmbessern` | Attested | Yes | 0.58 / Yes | Both accept a Duden-listed verb. Jev 0.58 shows that a low margin need not indicate a rare or doubtful lexical item; colloquial register is sound. |
| 4 | `bookshelfy` | Attested | Yes | 0.20 / No | Jev false negative. Western Living uses the adjective in interior-design writing, precisely matching the pool's claimed register. Source found before outputs. |
| 5 | `definately` | Policy | Yes | 0.56 / Yes | Both accept as used. Pool explicitly identifies a misspelling. This is defensible attestation, not endorsement of spelling; no factual error scored. |
| 6 | `докон` | Attested | Yes | 0.65 / Yes | Both accept the Serbian adjective. Pool's archaic/literary qualifier is overly restrictive: standard colloquial use also exists. No binary error. |
| 7 | `vieleicht` | Policy | No | 0.98 / Yes | Arms disagree. Jev accepts very strongly, pool rejects. Contemporary spelling differs, but historical usage is attested in Lichtenberg letters. Do not call Jev wrong or this calibrated confidence. |
| 8 | `recieve` | Policy | Yes | 0.57 / Yes | Both accept. Pool identifies a common misspelling; formal occurrence does not make it normative. No factual error scored. |
| 9 | `змркалица` | Unverified | No | 0.40 / No | Both reject an unverified challenge. No independent usage found; agreement does not prove universal nonexistence. |
| 10 | `definitely` | Attested | Yes | 0.99 / Yes | Both accept ordinary English. Pool's all-registers/all-dialects wording is broad but not material to the correct binary answer. |
| 11 | `perfunctory` | Attested | Yes | 0.97 / Yes | Both accept established English. Formal/professional register is appropriate. |
| 12 | `Fahrradsuppe` | Attested | No | 0.34 / No | Shared false negative. An Austrian cafe names its soup with exactly this compound. Local/contextual usage satisfies the prompt; no conventional dictionary sense is required. |
| 13 | `blorptium` | Unverified | No | 0.08 / No | Both reject unverified challenge. Jev 0.08 is a model score, not independent proof of nonexistence. |
| 14 | `petrichor` | Attested | Yes | 0.92 / Yes | Both accept established English. Scientific/literary usage is sound. |
| 15 | `sevdah` | Attested | Yes | 0.85 / Yes | Both accept Serbian usage. RTS supports the cultural/music register; Bosnian origin/association does not exclude use in Serbian. |
| 16 | `tablewards` | Attested | Yes | 0.20 / No | Jev false negative. Dictionary entry and historical prose support usage; the pool's descriptive/spatial register is sound. Source found before outputs. |
| 17 | `defenestration` | Attested | Yes | 0.88 / Yes | Both accept established English. Historical/political usage supports the answer. Computing is a specialized extra claim, not needed for acceptance and not independently checked here. |
| 18 | `мозда` | Policy | No | 0.48 / No | Both reject a spelling-policy challenge. Jev 0.48 is near the fixed threshold. No factual nonexistence score assigned. |
| 19 | `можда` | Attested | Yes | 0.90 / Yes | Both accept standard Serbian. Pool's all-dialects claim is overbroad and unnecessary, not a substantiated dialect survey. |
| 20 | `ledge` | Attested | Yes | 0.98 / Yes | Both accept ordinary English. Geological/architectural/general uses are sound. |
| 21 | `Kübel` | Attested | Yes | 0.95 / Yes | Both accept ordinary German. Bucket/tub gloss and general/regional usage are sound. |
| 22 | `quotidian` | Attested | Yes | 0.91 / Yes | Both accept established English. Formal/literary register is sound. |
| 23 | `scowl` | Attested | Yes | 0.98 / Yes | Both accept ordinary English. General usage is sound; all-registers phrasing is broader than evidence needed. |
| 24 | `Fernweh` | Attested | Yes | 0.95 / Yes | Both accept established German. Travel/literary/emotional register is sound. |
| 25 | `чежња` | Attested | Yes | 0.94 / Yes | Both accept standard Serbian. Literary/poetic use is sound; calling it archaic is too restrictive. It remains current. |
| 26 | `Löffelangst` | Unverified | No | 0.34 / No | Both reject an unverified challenge. Productive German compounding makes the form interpretable but does not supply independent attestation. |
| 27 | `Kummerspeck` | Attested | Yes | 0.93 / Yes | Both accept established German colloquial usage. |
| 28 | `Sturheit` | Attested | Yes | 0.55 / Yes | Both accept ordinary German stubbornness noun. Jev 0.55 is unexpectedly close to threshold for an ordinary word; the score cannot serve as frequency or truth. |
| 29 | `сврака` | Attested | Yes | 0.94 / Yes | Both accept standard Serbian bird name. |
| 30 | `pellucid` | Attested | Yes | 0.88 / Yes | Both accept established English. Formal/literary usage is sound. |
| 31 | `Torschlusspanik` | Attested | Yes | 0.92 / Yes | Both accept Duden-listed German noun. Everyday use supports the binary answer; psychology/sociology are coarse register claims, not citations. |
| 32 | `Backpfeifengesicht` | Attested | Yes | 0.75 / Yes | Both accept Duden-listed colloquial derogatory noun. Pool characterization is sound. |
| 33 | `podrška` | Attested | Yes | 0.95 / Yes | Both accept standard Serbian support noun. |
| 34 | `zlopamtilo` | Attested | No | 0.47 / No | Shared false negative. Serbian academic morphology paper and dramatic text attest exactly this form. Jev 0.47 is near threshold; source supports a positive independently of either model. |
| 35 | `receive` | Attested | Yes | 0.99 / Yes | Both accept ordinary English. Pool's across all dialects and periods is an unnecessary universal claim, not evidence of historical coverage. |
| 36 | `инат` | Attested | Yes | 0.96 / Yes | Both accept established Serbian. Stubbornness/obstinacy and colloquial/literary register are sound. |
| 37 | `susurrus` | Attested | Yes | 0.83 / Yes | Both accept established English literary noun. |
| 38 | `podrska` | Policy | Yes | 0.94 / Yes | Both accept attested ASCII Serbian usage. Pool mixes standard Serbian with informal spelling; the lexeme is standard but this spelling omits a diacritic. Not a normative-spelling pass. |
| 39 | `obfuscate` | Attested | Yes | 0.96 / Yes | Both accept established English. Formal/technical contexts are sound. |
| 40 | `Straße` | Attested | Yes | 0.98 / Yes | Both accept ordinary German. This is the sole pair where Jev is slower (0.674s versus 0.448s). |
| 41 | `клупа` | Attested | Yes | 0.96 / Yes | Both accept standard Serbian bench noun. |
| 42 | `мерак` | Attested | Yes | 0.94 / Yes | Both accept Serbian usage. Pool says everyday speech, especially southern regions; RTS supports Serbian occurrence. Register statement is plausible. |
| 43 | `vielleicht` | Attested | Yes | 0.99 / Yes | Both accept ordinary German. General usage is sound. |
| 44 | `recalcitrant` | Attested | Yes | 0.96 / Yes | Both accept established English. Formal/literary register is sound. |

## Evidence and strongest examples

- `bookshelfy`: [Western Living's 2016 interior-design editorial](https://westernliving.ca/shopping/accessories/editors-picks-organizing-accessories-home/).
  It is particularly revealing that the pool names the correct register while
  Jev rejects it. This is a retrieval/knowledge observation, not proof the pool
  actually retrieved that article.
- `Fahrradsuppe`: [Austrian cafe's own menu description](https://radler-rast.com/radler-rast-kaffee).
  Both systems reject a word a real business uses. A dictionary-only definition
  of word existence would be a different task from the broad prompt.
- `tablewards`: [dictionary record](https://kaikki.org/dictionary/English/meaning/t/ta/tablewards.html)
  and [historical prose, Under the Rose, printed page 183](https://upload.wikimedia.org/wikipedia/commons/c/c8/Under_the_rose_%28IA_underrose00ishaiala%29.pdf).
- `zlopamtilo`: [Serbian academic morphology paper](https://digitalna.ff.uns.ac.rs/sites/default/files/db/books/JEZICI%20I%20KULTURE%20U%20VREMENU%20I%20PROSTORU_12.pdf)
  and [Serbian dramatic text](https://rastko.rs/drama/ssd/ssd19/m_obradovic.pdf).
  The automated Wiktionary reference alone would have been inadequate because
  its Cyrillic entry identifies Macedonian; independent Serbian evidence matters.
- `vieleicht`: [Lichtenberg letters in a publisher preview](https://api.pageplace.de/preview/DT0400.9783406704611_A43062865/preview-9783406704611_A43062865.pdf).
  A historical attestation and a modern misspelling can coexist. A 0.98 score
  cannot tell the reader which interpretation caused the model's answer.

The full preflight source audit is in `preflight-review.md`. These sources were
found before the measured model answers, and the three corrected positive
adjudications were encoded before calls; this was not post-result relabeling to
favor either arm.

## Publication restrictions and useful story

A strong, supported story is: testing a new low-latency decision model exposed
problems in the existing benchmark labels before it exposed model differences.
An independent agent found actual usage for half of six supposedly invented
forms. The measured run then found a real speed advantage for this workload,
with a quality tradeoff and two failures shared by both approaches.

The agent-assisted work consists of fixture inspection, independent source
checks, repeatable measurement, and a fresh all-item review. Do not describe any
of these sources as human validation or claim a human checked every reference
unless the operator subsequently does so. A human/operator chooses the product
criterion and publication wording; another model's agreement is not ground truth.

Publish the three languages and 44 inputs, one response per arm per input, the
heterogeneous free pool, source-backed positive errors, separate policy slice,
and API-latency scope. Do not claim universal superiority, calibrated Noul
probabilities, representative language coverage, production readiness, or an
application-level speedup. Do not call the three remaining unverified strings
proven fake words. Do not infer zero hallucinations from this all-binary output.

Review decision: **accept the exploratory measurement with the restrictions
above; reject any production-promotion or universal-quality claim.** This review
must be linked or summarized in a durable `spec/decision-*.md` by the experiment
owner; the reviewer did not alter application behavior or prompt code.
