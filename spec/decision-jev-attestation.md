# Jev for attestation — exploratory result

Status: **measured 2026-09-30, independently reviewed 2026-10-01; no production
replacement justified.** Jev is a promising latency experiment, with a false
rejection tradeoff on this small multilingual workload. The free-pool checker
remains the product behavior.

## The question and workload

The experiment asks whether a specialized decision model can replace the
standalone judgment of actual usage. It compares Jev 1.13.0 through TypeSafe's
direct API with the current pool checker through the existing production-flow
benchmark. The request has the same broad usage criterion: any register,
dialect or historical period counts. The pool also generates a short account of
where the wording is used; Jev returns a number. This compares complete checking
approaches, not model architecture with identical output work.

All 44 inputs were selected before outputs: 17 English, 14 German and 13 Serbian.
They come from the repository's existing attestation, typo/correction and
rare-word fixtures, deduplicated by language and spelling. The set is a challenge
sample, not representative traffic or measured frequency strata. Each approach
answered each input once, in a fixed shuffled order with alternating first arm.
There was no test-set prompt tuning or repeated search for favorable answers.

## The labels needed correction before the run

Independent source review found actual uses of three of the six forms the old
benchmark calls invented:

- `bookshelfy` appears in a [2016 Western Living interior-design editorial](https://westernliving.ca/shopping/accessories/editors-picks-organizing-accessories-home/).
- `Fahrradsuppe` names a soup in an [Austrian cafe's own menu description](https://radler-rast.com/radler-rast-kaffee).
- `tablewards` has a [dictionary entry](https://kaikki.org/dictionary/English/meaning/t/ta/tablewards.html)
  and appears in historical prose.

All inputs and historical labels are retained for traceability, but these three
are source-backed positive cases in this experiment. With the original 32
positives, there are 35 attested inputs. Three remaining constructed strings are
unverified challenges, not proven nonexistent words. Six typo inputs measure
spelling policy; written occurrence and standard spelling are different facts.

The legacy six-word coinage rejection counts elsewhere in this repository must
therefore be read as agreement with historical fixture labels, not factual
hallucination detection rates. This experiment does not alter production prompts
or silently relabel the existing promotion suite. A future change to that suite
needs to resolve whether it tests observed usage or conventional lexical status.

## Availability and measurements

Both approaches delivered 44 usable answers. The pool's winning models were
Gemini 17, Groq 21, Nemotron 5 and Laguna 1. Across 92 underlying provider attempts,
45 completed successfully, 43 lost races, two failed and two were rate limited.
Gemini continued participating in all 44 logical calls with no rate-limit
response. Its smaller winning share than in the prior recorded run does not
show exhaustion; there is no evidence that exhaustion invalidates this run.
The changing model mix still limits comparison with other dates.

| Measure | Jev | Free-pool checker |
| --- | ---: | ---: |
| Usable logical answers | 44/44 | 44/44 |
| Median end-to-end check | 0.288 s | 0.923 s |
| Observed p90 check | 0.383 s | 7.190 s |
| Rejected attested inputs | 4/35 | 2/35 |
| Approved unverified challenges | 0/3 | 0/3 |
| Approved spelling-policy inputs | 4/6 | 3/6 |

Jev was faster in 43 of 44 pairs. The median per-pair pool/Jev latency ratio was
2.94. These are checker-call timings, not an application-level speedup; article
generation runs alongside the check in the product. Jev used 15,764 input tokens,
an estimated $0.000662088 at the published direct price of $0.042 per million
input tokens. The free pool has zero marginal API charge. A separate connection
probe is excluded from every figure.

Jev rejected `bookshelfy`, `tablewards`, `Fahrradsuppe`, and `zlopamtilo` at the
preselected 0.5 cutoff. The pool rejected the last two as well. The pool's
interior-design register for `bookshelfy` matches the independently found source;
Jev returned 0.20. Both refused the cafe's `Fahrradsuppe`, illustrating that
agreement is not usage evidence. Serbian `zlopamtilo` is supported by a Serbian
academic morphology paper and dramatic text, linked in the review.

An exploratory uncertainty band chosen before calls would defer 18 of the 44
Jev answers. Its remaining 23 attested positives have no false rejection. This
small observation does not validate calibration, a threshold policy, or a
fallback model; a production policy needs independent data and a stated cost
for mistaken acceptance versus mistaken rejection.

## Independent review and decision

The fresh `jev_review` agent did not run the benchmark or tune its questions.
It checked labels before calls, then inspected every one of the 44 result pairs,
including the pool's prose. Its decision is **accept the exploratory measurement
with limits; reject production-promotion or universal-quality claims**.

The experiment supports an honest research post about faster typed decisions,
source-audited benchmark labels and agent-assisted investigation. It does not
support overall accuracy over the historical labels, zero hallucinations,
representative multilingual coverage, or replacing the live checker.

[The reproducibility bundle](../experiments/results/jev-attestation-20260930/README.md)
contains exact requests, raw answers, the preflight audit, all-item semantic
review, chart and reproduction commands. The next product decision would first
clarify the usage criterion and label policy, rather than tune Jev to the old
negative examples.
