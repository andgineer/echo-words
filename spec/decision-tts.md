# TTS engines per language and host — decision

Status: **decided 2026-07-18 — the per-language engine matrix below; do
not re-open without new voice models appearing.** This document records
the research behind the TTS choices: which engine serves which
language. The backend has one home, the always-on
micro instance (`decision-interface.md`), so the matrix has one column
and every engine in it must fit that host.

## Requirements

- Free or open-source only — no metered TTS API anywhere (same cost NFR
  as the LLM).
- Host: a small always-on cloud instance. The realistically available
  Oracle Cloud Free Tier shape in the user's region is
  `VM.Standard.E2.1.Micro` — **1 GB RAM** (plus a swap file), 1/8 OCPU.
  The Arm `A1.Flex` shape (2 OCPU / 12 GB for Always Free tenancies)
  is frequently unobtainable ("out of capacity") and is not assumed.
  Every configured engine must fit this host; the laptop is only a dev
  environment running the same configuration.
- Output quality must be good enough for language learning: the card's
  audio is replayed dozens of times during spaced repetition, so a wrong
  or unnatural pronunciation is actively harmful, not just ugly.
- Languages: English, German, Serbian now; more later via config.

## Findings (verified 2026-07-18)

### Piper has no Serbian voice — the listed one is a trap

`sr_RS-serbian-medium` looks like the obvious choice and must never be
used. What verification found is worse than "missing":

- The **only** dataset under `sr/sr_RS` in the official voice repo
  (`huggingface.co/rhasspy/piper-voices`) is `serbski_institut`.
- "Serbski Institut" is the **Sorbian Institute** in Bautzen, Germany.
  The recordings are **Lower Sorbian** (a West Slavic language, closest
  to Polish/Czech) taken from the institute's MaryTTS corpora and
  miscatalogued under the Serbian locale in Piper's `VOICES.md`.
- For a Serbian learner this voice is not "low quality" — it is a
  different language. It must never be configured, whatever the file
  name says.

Piper has **no Croatian voice at all** (no `hr/` directory exists), and
of the South Slavic languages only Slovenian is genuinely covered. So
if Croatian is ever added as a source language, it lands in the same
bucket as Serbian below.

### The `sr-RS` voices pronounce Cyrillic, not Gaj's Latin

Microsoft's Serbian voices carry a Cyrillic locale, and the Latin script
is not a second input they accept: handed `haljina`, `sr-RS-SophieNeural`
returns audio whose mel-spectrogram is *closer* to an English voice
reading the same letters (DTW 1.5) than to the same Serbian voice reading
`хаљина` (DTW 2.6) — a foreign grapheme-to-phoneme pass, which is exactly
what a learner hears. Serbian text is therefore transliterated to Cyrillic
on its way to the voice. The conversion belongs to speech alone: the word
the user typed is what the answer shows and what the card stores, and the
mapping is Gaj's own one-to-one table, digraphs (`lj`, `nj`, `dž`)
included.

### Engine comparison

| | Kokoro-82M | Piper | edge-tts | Meta MMS-TTS | XTTS-v2 / Coqui |
|---|---|---|---|---|---|
| Serbian | no | **no** (see trap above) | **yes** — `sr-RS-SophieNeural` / `sr-RS-NicholasNeural`, Cyrillic input (see below) | yes (`mms-tts-srp`) | no |
| German | no | yes (`de_DE-thorsten-medium`) | yes | yes | yes / yes |
| English | **best in the lightweight class** | yes (many voices) | yes | weak | yes |
| Quality for learning | near-natural (en) | good | near-commercial neural | flat 16 kHz prosody (trained largely on Bible readings) | mediocre / heavy |
| License | Apache 2.0 | MIT | free but **unofficial** MS API | CC-BY-NC 4.0 | CPML (non-commercial) |
| Offline | yes | yes | **no** | yes | yes |
| Fits 1 GB RAM | **no** (~300 MB model + ONNX runtime alongside the backend + Anki pylib) | **yes** (~60–100 MB per voice, real-time on Raspberry-Pi-class CPUs) | trivially (network only) | no (torch + transformers stack) | no |

Rejected outright: XTTS-v2 (no sr/hr, heavy, non-commercial license),
MMS-TTS (intelligible but monotone; heavy dependency tail for a backup
role), SpeechT5-hr / Coqui `hr-cv` VITS community models (quality well
below edge-tts), eSpeak-NG (robotic), gTTS (quality, unofficial).
A single "universal" model does not beat a per-language pick of the
best lightweight engine — which is the architecture in place (`tts`
per language in `languages.toml`).

### Why edge-tts is acceptable as a *primary* engine for Serbian

edge-tts is an unofficial client of Microsoft Edge's online TTS and
breaks periodically (recurring 403 incidents). For Serbian it is still
the right primary because:

1. There is no local alternative of usable quality (see above), and
   Serbian is a pitch-accent language — flat MMS prosody or a wrong
   language would be drilled into the learner dozens of times per card.
2. The failure mode is structurally mild here: audio is generated
   **once per word** and stored forever in Anki media. An outage only
   affects words added during the outage, the status line already
   reports "🔇 no audio", and `/redo` retries.

## Decision

Engine matrix, selected purely by config (`languages.toml` + env), for
the one deployment target — the 1 GB (+ swap) micro instance:

| Language | engine |
|---|---|
| English | Piper (e.g. `en_US-lessac-medium`) or edge-tts |
| German | Piper `de_DE-thorsten-medium` |
| Serbian | edge-tts `sr-RS-SophieNeural`, fed Cyrillic |

- Kokoro — the best lightweight English engine in the comparison — is
  **not configured at all**: on a 1 GB host the model + runtime does
  not reliably fit next to the backend and Anki pylib, and an OOM kill
  takes down the whole process — the audio chain's exception-based
  fall-through never gets a chance to help. Sizing engines to the host
  is the **config's** job, done ahead of time; the runtime fall-through
  only covers genuine runtime errors. English pronunciation mostly comes
  from real dictionary recordings anyway, so an engine-quality gap shows
  only on words the dictionary lacks.
- Model downloads are config-driven: only engines and voices
  actually referenced by `languages.toml` are fetched — with no
  `kokoro` entry possible, the ~300 MB Kokoro model is never
  downloaded.
- The dictionary-recording step (real native recordings) stays first in
  the chain for languages that have it; edge-tts stays the last-resort
  fallback for every language, and is simultaneously Serbian's primary.

## Risks

- **edge-tts breakage** — mitigated by generate-once semantics (above);
  worst case is temporary "no audio" for Serbian words.
- **1 GB is tight even without Kokoro** — the web backend + Anki pylib
  + a Piper inference peak coexist only with a swap file (1–2 GB);
  documented as a hard setup requirement (`decision-deployment.md`,
  the README).
- **Future local Serbian voice** — Piper supports training custom
  voices (Common Voice has Serbian data), and community models may
  appear; if a genuine `sr_RS` voice ships, flipping Serbian to Piper
  is a one-line config change. Until then, do not mistake
  `sr_RS-serbski_institut` for one.
