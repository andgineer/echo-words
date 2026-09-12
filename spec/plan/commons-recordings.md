# Human recordings from Wikimedia Commons

Replace the dictionaryapi.dev step at the head of the audio chain with a
direct fetch from Wikimedia Commons, the place those recordings come from.

**Where this stands:** nothing of the code change is written. The
measurements below are done and settle the design. Three fixes found in the
same investigation are not part of this work and are already in: the
two-voice Piper cache and `MemorySwapMax=0` in the unit, both in the repo,
and `vm.swappiness=10`, applied to the host by
`inv setup-app --with-host-prep`. The unit change reaches the box on the
next deploy.

---

## Why

Measured 12 Sep 2026, from the deploy host and repeated from a second
network.

**dictionaryapi.dev cannot serve this app, in any configuration.**

- `de/Haus`, `de/schneiden`, `de/*` — Cloudflare `522` on every request,
  ~19.7 s each. The site and the project README document only the English
  endpoint now; the dozen-language list our `dict_api` rows were written
  against is gone.
- `en/hello` — `200` five times out of five, but in 19.60 / 19.45 / 19.45 /
  39.41 / 19.45 s. The step's own timeout is 10 s, so a success was never
  reachable, and 19 s is unusable anyway for a page whose whole answer takes
  2–3 s. The returned JSON is exactly what the parser expects: the request
  and the parsing were never the fault, the budget was.
- Nothing has ever come out of it. Fingerprinting the mp3 frames of all 305
  cached recordings on the host gives 293 at 22 050 Hz (Piper) and 12 at
  24 000 Hz (edge-tts), and none at 44.1/48 kHz. The same holds for the 10
  files in a local dev cache.
- The dead step is not free: it spends the audio budget the answer waits on,
  and 42 of the 200 cards made since 21 Aug carry no recording at all.

**Commons serves them directly, in a third of a second.**

- The URL needs no API call: the md5 of the file name gives the two
  directory levels, and TimedMediaHandler publishes an mp3 transcode beside
  the ogg. `De-schneiden.ogg` → md5 `4c…` →
  `https://upload.wikimedia.org/wikipedia/commons/transcoded/4/4c/De-schneiden.ogg/De-schneiden.ogg.mp3`.
- 16 of the 16 words carded on 12 Sep resolved: `Haus schneiden braten
  backen Sahne Mischung schälen Würfel verrühren gießen Auflauf Zwiebel
  Knoblauch Teig Ofen bestreut`, 0.12–0.40 s each, one request.
- A word with no recording answers `404` in 0.26 s (`De-blorptium.ogg`).
- 14 requests fired back to back drew `429`; it cleared within seconds. One
  request per submitted word is far below that ceiling.
- The transcode is MPEG1 44.1 kHz with an ID3 tag, so a cached file stays
  tellable from Piper's 22 050 Hz and edge-tts's 24 000 Hz — the audit above
  keeps working after the change.

---

## What the step becomes

One `GET` to a derived URL, in the place the dictionary step holds today,
ahead of Piper and edge-tts.

- **Single words only**, as now. A headword carded with its article — `die
  Zwiebel`, `der Knoblauch` — is not one word, and a recording of the bare
  noun would speak a text the card does not show, which the operator has
  ruled out. Those keep their Piper recording. 14 of the 21 headwords carded
  on 12 Sep were single words.
- **Name:** `f"{prefix}-{word}.ogg"`, the word as carded, case included
  (Commons follows German capitalisation: `De-Sahne.ogg`, `De-schneiden.ogg`).
- **Path:** `md5(name.encode())` hex; directories are `hex[0]` and `hex[:2]`;
  each path segment percent-encoded.
- **User-Agent** identifying the app and its repo — Wikimedia's policy
  refuses generic client agents, and httpx's default is one.
- **Timeout** of its own, 3 s against a measured worst case of 0.40 s. The
  10 s `HTTP_TIMEOUT_SECONDS` stays for the edge-tts path.
- **404, 429, timeout, any error → fall through to Piper**, silently as the
  chain does now; log at warning with the status so a change in Commons'
  behaviour is visible in `inv logs`.
- **No negative cache.** Piper writes the mp3 at the same cache path, so a
  word that missed once is answered from disk on every later submission and
  never reaches Commons again.
- **Licensing:** the recordings are CC-BY-SA / CC0. Nothing is attributed on
  the card; the app is private and tailnet-only, and redistribution is not
  in question. Note it in `decision-tts.md` rather than in code.

---

## Config

`dict_api` names an API that no longer takes part. Rename it to
`recordings`, whose value is the Commons prefix and therefore also the
accent choice: `"De"`, `"En-us"`, `"En-uk"`, `"Ru"`.

Touch, in this order:

1. `src/echo_words/languages.py` — `Language.dict_api` → `recordings`;
   `_language_from_entry` reads the new key and, when only the old one is
   present, derives the prefix from the code and `accent` (`en` + `us` →
   `En-us`, `de` → `De`) so the deployed `data/languages.toml` keeps its
   recordings through the deploy that ships this. The editor writes
   `recordings` from then on.
2. `src/echo_words/language_catalog.py` — `CatalogLanguage.dict_api` →
   `recordings`, with the prefix per row: `De`, `Fr`, `It`, `Ru`, `Es`,
   `Pt`, `Tr`, `En-us`. Serbian stays `None` — Commons has few `Sr-` word
   recordings, and the row is free to gain one later.
3. `src/echo_words/api.py` — the submission field and its `max_length`.
4. `webapp/src/views/LanguageDetailView.vue`,
   `webapp/src/views/LanguagesView.vue` — the field name and its label; the
   current label says "dictionaryapi.dev code" and would be a lie.
5. `webapp/src/i18n/en.js` and `webapp/src/i18n/ru.js` — the keys
   `languages.dictApi`, `languages.dictApiPlaceholder`,
   `languages.accent`, `languages.accentPlaceholder`. The editor's
   two-field pair becomes one field, because the prefix states the accent:
   `"En-us"` is the answer the `accent` box used to give.
6. **The row's `accent` goes with it.** `audio.py` picking a dictionary
   recording by accent is its only reader, and the prefix replaces it. Drop
   it from `Language`, from the submission model, from the editor and its
   fixtures. `Settings.accent` in `config.py` is a different field — it
   chooses the default edge-tts voice — and stays.
7. `languages.example.toml`, `docs/src/en/configuration.md`,
   `docs/src/ru/configuration.md`, `tests/conftest.py` fixtures,
   `tests/test_api.py` (the catalog-write test asserts `dict_api ==
   "pt-BR"`), `webapp/tests/LanguageDetailView.test.js`,
   `webapp/tests/LanguagesView.test.js`.
8. `spec/decision-interface.md` describes the editor as carrying a
   "dictionary code and accent" and the catalog as carrying a dictionary
   code; both sentences become the recordings prefix.

---

## Code

In `src/echo_words/audio.py`:

- Delete `_DICTIONARY_URL`, `_dictionary_audio`, `_try_dictionary_audio`.
- Add, in their place:

  ```python
  _COMMONS_URL = (
      "https://upload.wikimedia.org/wikipedia/commons/transcoded/{a}/{ab}/{name}/{name}.mp3"
  )
  RECORDING_TIMEOUT_SECONDS = 3
  _USER_AGENT = "echo-words/1.x (https://github.com/andgineer/echo-words)"

  def _commons_url(word: str, lang: Language) -> str: ...
  async def _commons_recording(word, lang, output, client) -> bool: ...
  async def _try_commons_recording(word, lang, output, client) -> bool: ...
  ```

  `_try_commons_recording` keeps the shape of the step it replaces: it owns
  a client when none is passed, catches every exception, logs, returns
  `False`. `_commons_recording` writes through `_write_atomic` after
  `_raise_if_cancelling()`, exactly as the dictionary step did.
- `fetch_pronunciation` swaps `lang.dict_api` for `lang.recordings` in the
  guard and calls the new step.

---

## Tests

All on `httpx.MockTransport`; no test reaches the network.
In `tests/test_audio.py`:

- `test_a_commons_recording_is_used_before_the_local_voice` — a 200 with mp3
  bytes wins, Piper is never called.
- `test_the_commons_url_is_derived_from_the_file_name_md5` — pin
  `De-schneiden.ogg` → `.../transcoded/4/4c/...`, the one case verified
  against the real service.
- `test_a_word_commons_does_not_have_falls_through_to_the_voice` — 404 →
  Piper's file, no exception.
- `test_a_throttled_commons_leaves_the_word_to_the_voice` — 429 → Piper, one
  request only, nothing retried inside the deadline.
- `test_commons_is_not_asked_for_a_phrase` — two words → no request at all.
- `test_a_commons_request_names_the_app` — the User-Agent header is sent.
- `test_a_language_without_recordings_never_asks_commons`.
- Delete what tested the source being replaced:
  `test_dictionary_recording_prefers_the_configured_english_accent` and
  `test_dictionary_miss_and_http_error_fall_through_to_piper`. The rest of
  `tests/test_audio.py` reaches Piper by passing `dict_api=None` on the
  language and needs the field's new name at those seven call sites.
- In `tests/test_languages.py`: `recordings` round-trips through the editor,
  and a file still carrying `dict_api` loads with the derived prefix.

---

## Verification

```bash
uv run pytest tests/test_audio.py tests/test_languages.py tests/test_language_catalog.py
uv run inv pre
uv run inv test
```

No bench run: nothing here reaches a model, a prompt or the payload parser.

Out of CI, against the real service, before asking to deploy:

```bash
python -c "import hashlib,urllib.parse;n='De-Sahne.ogg';h=hashlib.md5(n.encode()).hexdigest();q=urllib.parse.quote(n);print(f'https://upload.wikimedia.org/wikipedia/commons/transcoded/{h[0]}/{h[:2]}/{q}/{q}.mp3')"
```

After the deploy, the first new single-word German card should carry a
44.1 kHz mp3 — the fingerprint that told the sources apart above — and
`inv logs` should show no chain that ends at the voice for a word Commons
has.

---

## Left when this lands

- The 42 cards already made silent. Re-fetching each headword and attaching
  the media to its note is a maintenance pass of its own, and it needs the
  operator's word before anything writes to the collection.
- `spec/decision-tts.md` carries the chain's head: the dictionary bullet
  becomes the Commons one, with the latency and coverage measured here and
  the licensing note. This plan is deleted in the same commit.
