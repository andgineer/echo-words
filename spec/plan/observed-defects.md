# Implementation plan — defects seen in local use, none of them fixed yet

Found while running the app locally against the real provider keys and reading
what it did. Each item below was reproduced and has its evidence written down; two
sibling defects found in the same session — the player speaking a corrected
misspelling, and sense chips that all carried the same word — are already fixed and
are not repeated here.

The items are independent. None blocks another, and each is finished on its own.

## 1. `.env` is not ignored by git

`.gitignore` does not carry `.env`, and `git check-ignore -v .env` reports nothing.
That file is the documented home of local secrets: `config.py` reads it through
`ENV_FILE`, and llmbroker's zero-config secrets resolver reads `./.env` behind the
process environment. So the one file a developer is told to put provider keys in is
the one file `git add -A` will commit.

Nothing else about it changes: the file stays untracked and stays the local home
for keys. The fix is the ignore rule, and it is worth doing before the next person
follows the documentation.

## 2. A rebuilt bundle can leave the reader on a white screen

Observed locally: after `inv build-static` produced a new hashed bundle, the next
page load rendered nothing. The service worker served its cached `index.html`,
which references the previous asset hash, and that file no longer exists — the
request answered `404`, `#app` stayed empty, and the console was silent. A second
reload recovered it, because by then the new worker had taken over.

The PWA is configured `registerType: "autoUpdate"` with `skipWaiting` and
`clientsClaim`, so one reload is meant to be enough. What is unknown, and is the
first task here, is whether a deploy reproduces it: the local rebuild **deletes**
the old asset (`emptyOutDir`), while a deploy replaces a checkout and may leave the
precached pair internally consistent. Reproduce it against a deployed build before
changing anything — a fix aimed at a failure that does not happen there would be
machinery for nothing.

If it does reproduce, the reader meets a blank page after every release, which is
the most serious of the items on this page.

## 3. The status screen prints markdown links as text

The "no free-pool keys" panel shows provider help verbatim, and that help arrives
as markdown from llmbroker: the screen reads
`Create a free API key at [groq](https://console.groq.com/keys)`, brackets and all.
The text is correct and the rendering is not, so the reader is shown a URL they
cannot follow beside punctuation that means nothing to them.

Whether the interface renders the link or the backend hands over something already
plain is the open choice; the constraint is that the wording stays llmbroker's,
because it is the party that knows how a key is obtained.

## 4. Search denies a language that is merely already added

Typing `eng` while English is configured answers "the directory has no such
language". The directory does have it — the search excludes languages already in
the table, which is right, and then reports the exclusion with the sentence for a
word the directory never carried, which is not.

Both cases are legitimate and they need different sentences: nothing matched, and
everything that matched is already yours.

## 5. One user action makes two concurrent pool calls

Every unit submission opens two pool calls at once — the article and the
attestation. When the pool's first choice refuses, both meet the same refusal, so
one reader action counts twice against that provider and drives its cooldown ladder
at twice the rate a single call would.

This is recorded here as the defect it is, and not scheduled: llmbroker's queue
carries the routing fix that decides how much it still costs, and the measurement
that would justify changing our call shape is described in
[`two-prompts.md`](two-prompts.md), which is itself waiting. Revisit once the
routing fix has shipped and the pool's behaviour has been re-measured.

## What is deliberately not here

- **The cooldown ladder that took a working model out of the pool for half an
  hour.** It is llmbroker's, its queue carries the reasoning, and its condition for
  returning is written there.
- **The two defects already fixed in this session.** They are in the code and in
  the tests; a plan that lists finished work is an archive.
