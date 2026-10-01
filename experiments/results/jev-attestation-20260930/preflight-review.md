# Independent preflight review — 2026-09-30

Reviewer: the fresh `jev_review` agent. No benchmark calls, model output inspection,
prompt edits, or secret access preceded these findings.

The selected 44 inputs are a useful exploratory workload. The repository labels
are not a factual ground-truth set. Preserve all inputs and legacy labels, but
adjudicate source-backed attestation separately before the measured run.

## Three constructed negatives are attested

| Input | Evidence | Judgment under the actual broad usage criterion |
| --- | --- | --- |
| `tablewards` | [Wiktionary-derived dictionary entry](https://kaikki.org/dictionary/English/meaning/t/ta/tablewards.html); [historical prose, Under the Rose, printed p. 183](https://upload.wikimedia.org/wikipedia/commons/c/c8/Under_the_rose_%28IA_underrose00ishaiala%29.pdf), where a spigot projects toward a table | Attested. The legacy negative label is unsuitable. |
| `Fahrradsuppe` | [First-party Austrian cafe menu description](https://radler-rast.com/radler-rast-kaffee), which names its soup and lists ingredients; [German Euronews usage](https://de.euronews.com/2024/05/26/die-meisten-niederlander-fahren-jede-woche-rad-wie-haben-sie-das-radfahren-zum-nationalen-) also uses the compound figuratively | Attested as a context-specific compound. Its lack of a conventional dictionary sense does not make it unused. |
| `bookshelfy` | [Western Living editorial, 17 March 2016](https://westernliving.ca/shopping/accessories/editors-picks-organizing-accessories-home/), using the adjective to describe conventional bookshelves | Attested as an occasional adjective. Do not mistake productive or occasional formation for nonusage. |

Exact searches found no independent usage evidence for `Löffelangst`, `blorptium`,
or `змркалица`. Mark these **unverified challenges**, not proven nonexistent
strings. A rejection agrees with the legacy challenge expectation; an approval
requires checking the claimed usage rather than automatically declaring a
hallucination.

## Six spelling-policy inputs

`recieve`, `definately`, `Strase`, `vieleicht`, `мозда`, and `podrska` test a
different boundary: normative spelling versus whether people use the literal
sequence. The prompt accepts every register and historical period. A typo can
be attested, and an ASCII spelling can be common informal writing.

- [Wiktionary: recieve](https://en.wiktionary.org/wiki/recieve) and
  [Wiktionary: definately](https://en.wiktionary.org/wiki/definately) explicitly
  record misspellings. Their existence does not make them standard spellings.
- [Lichtenberg letters, publisher preview](https://api.pageplace.de/preview/DT0400.9783406704611_A43062865/preview-9783406704611_A43062865.pdf)
  contain `vieleicht`; historical spelling is specifically allowed by the prompt.
- [Berlin parliamentary answer](https://pardok.parlament-berlin.de/starweb/adis/citat/VT/18/SchrAnfr/s18-18773.pdf)
  contains `Strase` in an address list. This demonstrates written occurrence,
  not standard spelling.
- [Serbian users' workplace reports](https://www.helloworld.rs/iskustva/stranica/60?job_title=podrska)
  use `podrska` in ASCII Serbian. Treating this as lexical nonexistence conflates
  orthographic normalization with attestation.

Keep their six corrected forms as ordinary positive controls. Publish typo
results as policy disagreements, never as a universal factual error rate.

## Positive-control audit

The original 32 positive labels are semantically sound. None appears invented.
The names “rare” and “ordinary” are repository fixture categories, not measured
frequency bins: `Sturheit`, `докон`, and `инат`, for example, should not support a
claim that every positive input is genuinely rare.

Less obvious Serbian positives were checked independently:

- [докон](https://en.wiktionary.org/wiki/%D0%B4%D0%BE%D0%BA%D0%BE%D0%BD): idle.
- [чежња / čežnja](https://en.wiktionary.org/wiki/%C4%8De%C5%BEnja): longing.
- [RTS uses мерак](https://www.rts.rs/magazin/zanimljivosti/2334789/merak-nema-niko-na-svetu.html).
- [RTS explains sevdah](https://www.rts.rs/lat/radio/radio-beograd-1/2135837/etnika.html).
- [University of Novi Sad research explicitly lists zlopamtilo as a Serbian
  compound](https://digitalna.ff.uns.ac.rs/sites/default/files/db/books/JEZICI%20I%20KULTURE%20U%20VREMENU%20I%20PROSTORU_12.pdf);
  [Serbian dramatic text also uses it](https://rastko.rs/drama/ssd/ssd19/m_obradovic.pdf).

The dictionary entry for `злопамтило` in English Wiktionary is Macedonian;
an automatically generated Wiktionary URL is not sufficient evidence for the
Serbian label. The Serbian sources above resolve that problem.

German checks include Duden's [Backpfeifengesicht](https://www.duden.de/deklination/substantive/Backpfeifengesicht),
[verschlimmbessern](https://www.duden.de/konjugation/verschlimmbessern), and
[Torschlusspanik](https://www.duden.de/rechtschreibung/Torschlusspanik).

## Design restrictions

- Publish latency as observed end-to-end latency of two usable approaches.
  Jev emits a Noul; the current pool emits JSON with provenance. This does not
  isolate architecture, equal output work, or inherent model speed.
- No pooled accuracy, precision, recall, or F1 over the legacy labels. Positive
  rejections are defensible; uncertain and spelling-policy slices remain separate.
- A single call per item cannot establish stability, calibration, statistical
  superiority, or production readiness. An exploratory uncertainty band is not
  a deployed fallback policy.
- Retain exact requests and a hash of the experiment harness: source HEAD alone
  cannot identify an uncommitted new harness.
- Availability must precede quality interpretation. All pairs and provider
  composition must be inspected against prior pool runs; no missing response is
  a wrong linguistic answer.

Preflight verdict: proceed after encoding the three source-backed adjudications
separately from legacy challenge labels. Keep the workload unchanged.
