"""Production-flow bench for the merged answer, complete chips and four cards.

The `run` and `run-clicks` actions call the real free pool. The report uses
production prompt construction and answer parsing, combines the verdict matrix
with downstream text/unit checks, separates archived prompt generations, and
separates deterministic contracts from thresholded model quality. Provider
availability and exact-boundary diagnostics stay visible without being
misreported as semantic success or zero-tolerance product contracts.

Raw answers are append-only so scoring can be changed without buying them again.
The default smoke tier is 55 calls; confirmation is 125 and full is at most 216.

Run:
    uv run python experiments/one_note_bench.py run --tier smoke --resume \
      --wait 180 --pace 2 --concurrency 1 \
      --out experiments/.bench-one-note-post
    uv run python experiments/one_note_bench.py run-clicks --tier smoke --resume \
      --wait 300 --pace 2 --concurrency 1 \
      --out experiments/.bench-one-note-post
    uv run python experiments/one_note_bench.py report \
      --tier smoke --out experiments/.bench-one-note-post
"""

import argparse
import asyncio
import hashlib
import json
import logging
import os
import re
import statistics
import sys
import time
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass, field, replace
from html import unescape
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from backend_bench import (  # noqa: E402
    Pacer,
    answer_language,
    drain,
    load_keys,
    log,
    parse_json_object,
    split_answer,
)
from bench_items import SENTENCES  # noqa: E402
from echo_words.card import ParsedAnswer, ParsedText, ParsedUnit  # noqa: E402
from echo_words.languages import (  # noqa: E402
    fold_for_match,
    load_languages,
    split_words,
    validate_word,
)
from echo_words.prompt import (  # noqa: E402
    CARD_DELIMITER,
    MAX_COMPLETE_ANSWER_CHARS,
    build_attestation_prompt,
    build_prompt,
    extract_answer,
    parse_attestation,
)
from echo_words.sanitizer import sanitize_html  # noqa: E402
from echo_words.segments import fill_text_segments  # noqa: E402
from llmbroker import AsyncBroker  # noqa: E402
from unit_verdict_bench import FIXTURES as VERDICT_FIXTURES  # noqa: E402

TARGET_CODE = "ru"
TARGET_NAME = "Russian"
LANGUAGES = load_languages(REPO / "languages.example.toml")
_WORD = re.compile(r"[^\W\d_]+(?:[-'’][^\W\d_]+)*", re.UNICODE)
_ORIGIN = re.compile(r"происход|этимолог|заимств|восход|исконн|образован", re.IGNORECASE)
_USAGE = re.compile(r"употреб|использ|сочетан|сочетаем", re.IGNORECASE)
_MORPHOLOGY = re.compile(
    r"<table>|форм|спряж|склон|множествен|причаст|презенс|претерит|прошедш",
    re.IGNORECASE,
)
_ALLOWED_TAGS = {"b", "i", "table", "tr", "td"}
_BOLD_START = re.compile(r"^<b>[^<]+</b>")
_RAW_TAG = re.compile(r"<[^>]*>|[<>]")
_OBSOLETE_PROMPTS = (
    Path(__file__).parent / "prompts" / "one-note-text.txt",
    Path(__file__).parent / "prompts" / "one-note-vocab.txt",
)

EN_TEXT = [
    ("I gave up after ten minutes.", (("give up",),)),
    ("The book is on the table.", ()),
    ("The children are playing in the garden.", ()),
    ("He is looking forward to the trip.", (("look forward to",),)),
    ("Although it was raining, we went outside.", ()),
]

BARE_CASES = [
    ("bare-en-bank", "en", "bank", False, False),
    ("bare-en-reluctant", "en", "reluctant", False, False),
    ("bare-en-give-up", "en", "give up", True, True),
    ("bare-de-bank", "de", "Bank", True, False),
    ("bare-de-verantwortung", "de", "Verantwortung", True, False),
    ("bare-de-rad", "de", "Rad fahren", True, True),
    ("bare-sr-grad", "sr", "град", True, False),
    ("bare-sr-umoran", "sr", "уморан", True, False),
    ("bare-sr-voditi", "sr", "водити рачуна", True, True),
]
EXPECTED_EXPRESSION_PARTS = {
    "bare-en-give-up": ("give", "up"),
    "bare-de-rad": ("Rad", "fahren"),
    "bare-sr-voditi": ("водити", "рачуна"),
}
EXPRESSION_IDS = set(EXPECTED_EXPRESSION_PARTS)

INITIAL_FIXTURES = 157
VERDICT_FIXTURES_TOTAL = 122
TEXT_FIXTURES = 26
BARE_FIXTURES = 9
REGISTERED_UNITS = 21
CLICK_FIXTURES = 6
EXPRESSION_FIXTURES = 3

MIN_USABLE_INITIAL = 142
MIN_TEXT_BRANCH = 23
MIN_BARE_CARDABLE = 8
# A chip the learner would card wrong is not a unit recovered, so the gate counts
# only the two match kinds that card the registered entry: an exact chip, and a
# surface registered in ACCEPTED_SURFACE_ALTERNATIVES. An expanded or partial
# boundary is reported beside it as a diagnostic and gates nothing.
CARDABLE_MATCHES = frozenset({"exact", "accepted alternative"})
# The floor sits at the bottom of the measured spread rather than inside it. Six
# full runs answering every text shot, re-scored through the boundary repair, have
# measured 13 through 17 of 21, so a floor above 13 reddens on the draw. The report
# prints the spread beside the count, because one sample cannot tell a two-unit
# regression from a two-unit draw and only repeated runs can raise this floor.
MIN_CARDABLE_UNITS = 13
CARDABLE_UNITS_SPREAD = (13, 17)
MIN_SHARED_WORDS = 2
MAX_BOUNDARY_DRIFT = 1
MIN_CLICK_SUCCESS = 5
MIN_EXPRESSION_SUCCESS = 2
TIER_NAMES = ("smoke", "confirmation", "full")

_UNIT_BRANCH_FIELDS = frozenset(
    {"word", "word_relation", "suggestion", "meanings", "context_sense", "segments"},
)
_TEXT_BRANCH_FIELDS = frozenset({"combinations"})


@dataclass(frozen=True)
class ClickCase:
    shot_id: str
    text_id: str
    label: str
    segment_kind: str


@dataclass(frozen=True)
class TypoCase:
    shot_id: str
    lang: str
    submitted: str
    suggestion: str


CLICK_CASES = [
    ClickCase("click-en-combination", "text-en-0", "gave up", "combination"),
    ClickCase("click-en-function", "text-en-1", "on", "standalone"),
    ClickCase("click-de-combination", "text-de-0", "steht auf", "combination"),
    ClickCase("click-de-function", "text-de-0", "Er", "standalone"),
    ClickCase("click-sr-combination", "text-sr-0", "се вратио", "combination"),
    ClickCase("click-sr-function", "text-sr-0", "Он", "standalone"),
]
CLICK_BY_ID = {case.shot_id: case for case in CLICK_CASES}
CLICK_IDS = set(CLICK_BY_ID)

TYPO_CASES = (
    TypoCase("typo-en-recieve", "en", "recieve", "receive"),
    TypoCase("typo-de-strase", "de", "Strase", "Straße"),
    TypoCase("typo-sr-mozda", "sr", "мозда", "можда"),
    TypoCase("typo-en-definately", "en", "definately", "definitely"),
    TypoCase("typo-de-vieleicht", "de", "vieleicht", "vielleicht"),
    TypoCase("typo-sr-podrska", "sr", "podrska", "podrška"),
)
@dataclass(frozen=True)
class NeighbourCase:
    """A real word beside a near neighbour, and the neighbour if one is far commoner.

    An empty ``neighbour`` is an ordinary word that must be offered nothing: the cost
    of this feature is a needless replace offer on words the learner spelled fine.
    """

    shot_id: str
    lang: str
    submitted: str
    neighbour: str


NEIGHBOUR_CASES = (
    NeighbourCase("neighbour-en-causal", "en", "causal", "casual"),
    NeighbourCase("neighbour-en-kitchen", "en", "kitchen", ""),
    NeighbourCase("neighbour-de-wider", "de", "wider", "wieder"),
    NeighbourCase("neighbour-de-fenster", "de", "Fenster", ""),
    # `месо` beside `место` is the Serbian pair with the shape the other two have: one
    # letter inserted, and one plausible commoner word rather than a field of them.
    # `отад` was replaced because it stood one letter from several ordinary words, so a
    # model naming its own variant `отада` answered well and scored a miss.
    NeighbourCase("neighbour-sr-meso", "sr", "месо", "место"),
    NeighbourCase("neighbour-sr-prozor", "sr", "прозор", ""),
)
NEIGHBOUR_BY_ID = {case.shot_id: case for case in NEIGHBOUR_CASES}
NEIGHBOUR_IDS = frozenset(NEIGHBOUR_BY_ID)
SMOKE_NEIGHBOUR_IDS = frozenset(case.shot_id for case in NEIGHBOUR_CASES[:3])


TYPO_BY_ID = {case.shot_id: case for case in TYPO_CASES}
TYPO_IDS = frozenset(TYPO_BY_ID)
SMOKE_TYPO_IDS = frozenset(case.shot_id for case in TYPO_CASES[:3])


@dataclass(frozen=True)
class AttestedCase:
    """One string, and whether a card for exactly it would teach a real word.

    ``attested`` cases must come back as ordinary units. The rest must not: an
    article about them is a fabrication a learner would drill for months.
    """

    shot_id: str
    lang: str
    submitted: str
    attested: bool
    ordinary: bool = False


ATTESTED_CASES = (
    # Real, rare, and used: refusing these would gut the tool's whole point.
    AttestedCase("attested-en-petrichor", "en", "petrichor", True),
    AttestedCase("attested-en-susurrus", "en", "susurrus", True),
    AttestedCase("attested-de-kummerspeck", "de", "Kummerspeck", True),
    AttestedCase("attested-sr-inat", "sr", "инат", True),
    # Well formed, transparent, and said by nobody. German compounding and English
    # derivation produce these without limit, and no dictionary lists them even
    # when they are real — so only usage can tell them apart.
    AttestedCase("unused-de-fahrradsuppe", "de", "Fahrradsuppe", False),
    AttestedCase("unused-de-loeffelangst", "de", "Löffelangst", False),
    AttestedCase("unused-en-bookshelfy", "en", "bookshelfy", False),
    AttestedCase("unused-en-tablewards", "en", "tablewards", False),
    # Invented strings with no attested neighbour at all.
    AttestedCase("unused-en-blorptium", "en", "blorptium", False),
    AttestedCase("unused-sr-zmrkalica", "sr", "змркалица", False),
    # Ordinary, unremarkable and mid-frequency: the words nobody writes essays about.
    # The four attested cases above are all words with a literature — the kind that
    # fills "untranslatable words" lists a model has read many times — so passing them
    # may be recall of famous words rather than the judgement the product depends on.
    # These six were chosen on that principle alone and never tried against a model
    # first, which is what makes their score evidence rather than a fitted result.
    AttestedCase("ordinary-en-ledge", "en", "ledge", True, ordinary=True),
    AttestedCase("ordinary-en-scowl", "en", "scowl", True, ordinary=True),
    AttestedCase("ordinary-de-kuebel", "de", "Kübel", True, ordinary=True),
    AttestedCase("ordinary-de-muerrisch", "de", "mürrisch", True, ordinary=True),
    AttestedCase("ordinary-sr-klupa", "sr", "клупа", True, ordinary=True),
    AttestedCase("ordinary-sr-svraka", "sr", "сврака", True, ordinary=True),
)
ORDINARY_ATTESTED_IDS = frozenset(
    case.shot_id for case in ATTESTED_CASES if case.ordinary
)


@dataclass(frozen=True)
class WordListCase:
    """Two content words with no unit between them: a list, not a lexical unit.

    Distinct from FRAGMENTS, which are a use of a real unit typed with the words
    around it. Here there is nothing to extract, so the only right answers are the
    text branch or a refusal — and a refusal now leaves the reader a chip per word
    rather than nothing. Carding such a pair as a dictionary entry is the failure.
    """

    shot_id: str
    lang: str
    submitted: str


WORDLIST_CASES = (
    WordListCase("wordlist-de-ampel-links", "de", "Ampel links"),
    WordListCase("wordlist-en-window-quickly", "en", "window quickly"),
    WordListCase("wordlist-sr-prozor-brzo", "sr", "прозор брзо"),
)
WORDLIST_BY_ID = {case.shot_id: case for case in WORDLIST_CASES}
WORDLIST_IDS = frozenset(WORDLIST_BY_ID)
ATTESTED_BY_ID = {case.shot_id: case for case in ATTESTED_CASES}
ATTESTED_IDS = frozenset(ATTESTED_BY_ID)
SMOKE_ATTESTED_IDS = frozenset(
    case.shot_id
    for case in (*ATTESTED_CASES[:2], *ATTESTED_CASES[4:6], ATTESTED_CASES[8])
)

# Every smoke ID is named: the 20 registered-combination texts, the standalone
# English click source, and all nine bare/card examples which caught the v6 bug.
SMOKE_CANONICAL_IDS = frozenset(
    {
        "text-de-0",
        "text-de-1",
        "text-de-2",
        "text-de-3",
        "text-de-4",
        "text-de-5",
        "text-de-6",
        "text-de-7",
        "text-de-9",
        "text-en-0",
        "text-en-1",
        "text-en-3",
        "text-sr-0",
        "text-sr-1",
        "text-sr-2",
        "text-sr-3",
        "text-sr-4",
        "text-sr-5",
        "text-sr-6",
        "text-sr-7",
        "text-sr-8",
        "bare-en-bank",
        "bare-en-reluctant",
        "bare-en-give-up",
        "bare-de-bank",
        "bare-de-verantwortung",
        "bare-de-rad",
        "bare-sr-grad",
        "bare-sr-umoran",
        "bare-sr-voditi",
    },
)

# These are the 38 distinct verdict IDs which scored as hard errors in the five
# complete/comparable v1 and v3-v6 arms. The availability-collapsed v2 arm is
# excluded; its one additional ID has no comparable full-arm evidence.
HISTORICAL_HARD_IDS = frozenset(
    {
        "verdict:clauses:de:0",
        "verdict:clauses:de:5",
        "verdict:clauses:sr:0",
        "verdict:clauses:sr:2",
        "verdict:clauses:sr:3",
        "verdict:fragments:de:1",
        "verdict:fragments:de:3",
        "verdict:fragments:de:4",
        "verdict:fragments:de:5",
        "verdict:fragments:de:6",
        "verdict:fragments:de:7",
        "verdict:fragments:de:8",
        "verdict:fragments:de:9",
        "verdict:fragments:en:0",
        "verdict:fragments:en:2",
        "verdict:fragments:en:5",
        "verdict:fragments:sr:2",
        "verdict:fragments:sr:3",
        "verdict:fragments:sr:5",
        "verdict:fragments:sr:7",
        "verdict:inflected:de:6",
        "verdict:inflected:sr:0",
        "verdict:inflected:sr:1",
        "verdict:inflected:sr:6",
        "verdict:sentences-phrase:de:8",
        "verdict:sentences-phrase:de:9",
        "verdict:sentences-phrase:sr:5",
        "verdict:sentences-phrase:sr:8",
        "verdict:sentences-plain:sr:9",
        "verdict:sentences-split:de:0",
        "verdict:sentences-split:de:1",
        "verdict:sentences-split:de:2",
        "verdict:sentences-split:de:3",
        "verdict:sentences-split:de:4",
        "verdict:sentences-split:de:6",
        "verdict:sentences-split:de:7",
        "verdict:sentences-split:sr:4",
        "verdict:units:sr:0",
    },
)

# Stable direct units plus every declared tolerant boundary. Пада киша is
# already present in HISTORICAL_HARD_IDS because v6 called it text.
CONFIRMATION_ANCHOR_IDS = frozenset(
    {
        "verdict:units:en:0",
        "verdict:units:de:0",
        "verdict:units:sr:2",
        "verdict:fragments:en:1",
        "verdict:clauses:en:0",
        "verdict:clauses:de:2",
        "verdict:clauses:de:3",
        "verdict:clauses:sr:1",
    },
)

EXPECTED_SURFACE_GROUPS = {
    "text-de-0": (("steht", "auf"),),
    "text-de-1": (("freue", "mich", "auf"),),
    "text-de-2": (("sagt", "ab"),),
    "text-de-3": (("nehmen", "unter", "die", "Lupe"),),
    "text-de-4": (("habe", "die", "Nase", "voll"),),
    "text-de-5": (("fällt", "aus"),),
    "text-de-6": (("kommt", "in", "Frage"),),
    "text-de-7": (("zieht", "um"),),
    "text-de-9": (("uns", "auf", "beschränken"),),
    "text-sr-0": (("се", "вратио"),),
    "text-sr-1": (("се", "јавио"),),
    "text-sr-2": (("se", "oblači"),),
    "text-sr-3": (("се", "изненадио"),),
    "text-sr-4": (("ми", "се", "иде"),),
    "text-sr-5": (("bojim", "se"),),
    "text-sr-6": (("Nadam", "se"),),
    "text-sr-7": (("se", "igraju"),),
    "text-sr-8": (("mi", "se", "čini"), ("u", "redu")),
    "text-en-0": (("gave", "up"),),
    "text-en-3": (("looking", "forward", "to"),),
}

# A current experiencer can be omitted from these reusable impersonal/reflexive
# units. Other fixed reflexive particles and governed prepositions are required.
ACCEPTED_SURFACE_ALTERNATIVES = {
    ("text-sr-4", 0): (("се", "иде"),),
    ("text-sr-8", 0): (("se", "čini"),),
}

EXPECTED_LOOKUPS = {
    "text-de-0": ("aufstehen",),
    "text-de-1": ("sich freuen auf",),
    "text-de-2": ("absagen",),
    "text-de-3": ("unter die Lupe nehmen",),
    "text-de-4": ("die Nase voll haben",),
    "text-de-5": ("ausfallen",),
    "text-de-6": ("in Frage kommen",),
    "text-de-7": ("umziehen",),
    "text-de-9": ("sich beschränken auf",),
    "text-sr-0": ("вратити се",),
    "text-sr-1": ("јавити се",),
    "text-sr-2": ("oblačiti se",),
    "text-sr-3": ("изненадити се",),
    "text-sr-4": ("иде ми се",),
    "text-sr-5": ("bojati se",),
    "text-sr-6": ("nadati se",),
    "text-sr-7": ("igrati se",),
    "text-sr-8": ("činiti se", "u redu"),
    "text-en-0": ("give up",),
    "text-en-3": ("look forward to",),
}

NO_COMBINATION_SHOTS = {
    "text-de-8",
    "text-de-10",
    "text-en-1",
    "text-en-2",
    "text-en-4",
    "text-sr-9",
}

# These short clauses are also common reusable chunks. Keep the fixture labels
# unchanged so the raw matrix stays comparable, but report them separately from
# text whose contextual material makes a unit verdict plainly unsafe.
DEFENSIBLE_UNIT_VERDICTS = {
    "verdict:clauses:en:0",  # I have no idea
    "verdict:clauses:de:0",  # Ich habe keine Zeit
    "verdict:clauses:de:2",  # Ich weiß nicht
    "verdict:clauses:de:3",  # Das stimmt
    "verdict:clauses:sr:1",  # Не знам
}
ACCEPTABLE_UNIT_VERDICTS = {
    # The pronoun is dispensable and the intensifier is debatable, but the whole
    # phrase is still a useful conventional way to express reluctance.
    "verdict:fragments:en:1",  # was rather reluctant about it
}
EXPECTED_UNIT_OVERRIDES = {
    # The Serbian predicate is a learnable unit precisely because its natural
    # counterparts choose different verbs: дождь идёт, it rains, es regnet.
    "verdict:clauses:sr:0",  # Пада киша
}

FUNCTION_WORDS = {
    "en": {"i", "the", "is", "on", "after", "he", "to", "it", "was", "we", "in"},
    "de": {"er", "ich", "sie", "wir", "den", "jeden", "um", "sich", "auf", "das", "ist"},
    "sr": {"он", "се", "ми", "она", "ne", "da", "na", "је", "u", "није"},
}


@dataclass
class Shot:
    shot_id: str
    kind: str
    lang: str
    source: str
    context: str = ""
    expected_groups: list[list[str]] = field(default_factory=list)
    expects_morphology: bool = False
    expression: bool = False
    expected_kind: str | None = None
    accepted: list[str] = field(default_factory=list)
    selected_segment_kind: str = ""
    expected_suggestion: str = ""
    prompt_hash: str = ""
    answered_by: str | None = None
    t_first: float | None = None
    t_total: float | None = None
    error: str | None = None
    text: str = ""
    payload: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)


def normalize(value: object, lang: str = "") -> str:
    text = " ".join(unicodedata.normalize("NFC", str(value)).casefold().split()).strip(
        " .,;:!?…",
    )
    return fold_for_match(text, LANGUAGES[lang]) if lang else text


def tokens(value: object, lang: str = "") -> list[str]:
    return [normalize(token, lang) for token in _WORD.findall(str(value))]


def _unit_intent(shot: Shot) -> bool:
    # What the submit box sends: a one-word submission is forced to the unit branch
    # there, so an attested shot — every one of them a single word — has to carry the
    # same instruction. Measuring it on the open-branch prompt would measure a prompt
    # the app never sends for that input, and the selected-unit prompt has no text
    # branch at all, which is the very thing the split has to be scored on.
    return shot.kind in {"context", "typo"} or len(split_words(shot.source)) == 1


def prompt_for(shot: Shot) -> str:
    if shot.kind in {"attestation", "correction"}:
        return build_attestation_prompt(LANGUAGES[shot.lang], shot.source)
    return build_prompt(
        LANGUAGES[shot.lang],
        shot.source,
        TARGET_NAME,
        context=shot.context,
        unit_intent=_unit_intent(shot),
    )


def prompt_fingerprint(shot: Shot) -> str:
    return hashlib.sha256(prompt_for(shot).encode()).hexdigest()[:12]


def assert_no_prompt_drift() -> None:
    existing = [str(path) for path in _OBSOLETE_PROMPTS if path.exists()]
    if existing:
        raise RuntimeError(
            "obsolete branch prompt fixtures must be removed; production has one prompt: "
            + ", ".join(existing),
        )


def text_shots() -> list[Shot]:
    rows: list[Shot] = []
    for lang, fixtures in SENTENCES.items():
        for index, (source, expected, _fixture_kind) in enumerate(fixtures):
            rows.append(
                Shot(
                    f"text-{lang}-{index}",
                    "text",
                    lang,
                    source,
                    expected_groups=[list(group) for group in expected],
                    expected_kind="text",
                ),
            )
    for index, (source, expected) in enumerate(EN_TEXT):
        rows.append(
            Shot(
                f"text-en-{index}",
                "text",
                "en",
                source,
                expected_groups=[list(group) for group in expected],
                expected_kind="text",
            ),
        )
    return rows


def bare_shots() -> list[Shot]:
    return [
        Shot(
            shot_id,
            "bare",
            lang,
            source,
            expects_morphology=expects_morphology,
            expression=expression,
            expected_kind="unit",
        )
        for shot_id, lang, source, expects_morphology, expression in BARE_CASES
    ]


def verdict_shots() -> list[Shot]:
    return [
        Shot(
            f"verdict:{fixture.fixture_id}",
            "verdict",
            fixture.lang,
            fixture.text,
            expected_kind=(
                "unit"
                if fixture.expected_unit
                or f"verdict:{fixture.fixture_id}" in EXPECTED_UNIT_OVERRIDES
                else "text"
            ),
            accepted=list(fixture.accepted),
        )
        for fixture in VERDICT_FIXTURES
    ]


def typo_shots() -> list[Shot]:
    rows = [
        Shot(
            case.shot_id,
            "typo",
            case.lang,
            case.submitted,
            expected_kind="unit",
            expected_suggestion=case.suggestion,
        )
        for case in TYPO_CASES
    ]
    invalid = [
        shot.shot_id
        for shot in rows
        if validate_word(shot.source, LANGUAGES[shot.lang]) is not None
    ]
    if invalid:
        raise RuntimeError("invalid registered typo inputs: " + ", ".join(invalid))
    return rows


def neighbour_shots() -> list[Shot]:
    rows = [
        Shot(
            case.shot_id,
            "neighbour",
            case.lang,
            case.submitted,
            expected_kind="unit",
            expected_suggestion=case.neighbour,
        )
        for case in NEIGHBOUR_CASES
    ]
    invalid = [
        shot.shot_id
        for shot in rows
        if validate_word(shot.source, LANGUAGES[shot.lang]) is not None
    ]
    if invalid:
        raise RuntimeError("invalid registered neighbour inputs: " + ", ".join(invalid))
    return rows


def neighbour_ids_for_tier(tier: str) -> frozenset[str]:
    return SMOKE_NEIGHBOUR_IDS if tier == "smoke" else NEIGHBOUR_IDS


def attestation_id(shot_id: str) -> str:
    return f"attestation-{shot_id}"


def correction_id(shot_id: str) -> str:
    return f"correction-{shot_id}"


def attestation_shots() -> list[Shot]:
    """The standalone judgement, which production asks in parallel with the article.

    Asked for the misspellings too: it refuses most of them, and what production does
    with that refusal — nothing, when the article corrected the spelling — is the
    behaviour those fixtures exist to hold.
    """
    return [
        Shot(
            attestation_id(case.shot_id),
            "attestation",
            case.lang,
            case.submitted,
            expected_kind=None,
        )
        for case in (*ATTESTED_CASES, *TYPO_CASES)
    ]


def correction_shots(recorded: dict[str, Shot]) -> list[Shot]:
    """The second judgement, about the wording an answer put in place of a refused one.

    Derived rather than registered: that wording is the answer's own, so it cannot be
    written down before the run. Production asks it wherever a refusal would otherwise
    be overruled by the bare word `typo`, and its count therefore varies with the draw,
    which is why these calls sit outside every frozen tier total.
    """
    rows = []
    for shot in recorded.values():
        if not judgement_refused(recorded.get(attestation_id(shot.shot_id))):
            continue
        corrected = _correction_wording(shot)
        if corrected:
            rows.append(Shot(correction_id(shot.shot_id), "correction", shot.lang, corrected))
    return rows


def _correction_wording(shot: Shot) -> str:
    """The second wording a note would carry, read exactly as production reads it.

    The reconciled relation, not the claimed one, and empty where the answer headed
    itself with the submission: there is no second wording there to ask about.
    """
    if shot.metrics.get("word_relation") != "typo":
        return ""
    word = str(shot.payload.get("word") or "")
    return "" if normalize(word, shot.lang) == normalize(shot.source, shot.lang) else word


def wordlist_shots() -> list[Shot]:
    return [
        Shot(case.shot_id, "wordlist", case.lang, case.submitted, expected_kind="text")
        for case in WORDLIST_CASES
    ]


def attested_shots() -> list[Shot]:
    return [
        Shot(
            case.shot_id,
            "attested",
            case.lang,
            case.submitted,
            expected_kind="unit" if case.attested else None,
        )
        for case in ATTESTED_CASES
    ]


def canonical_ids_for_tier(tier: str) -> frozenset[str]:
    if tier == "smoke":
        return SMOKE_CANONICAL_IDS
    if tier == "confirmation":
        downstream = {shot.shot_id for shot in (*text_shots(), *bare_shots())}
        return frozenset(downstream | HISTORICAL_HARD_IDS | CONFIRMATION_ANCHOR_IDS)
    if tier == "full":
        return frozenset(shot.shot_id for shot in initial_shots())
    raise ValueError(f"unknown benchmark tier: {tier}")


def typo_ids_for_tier(tier: str) -> frozenset[str]:
    return SMOKE_TYPO_IDS if tier == "smoke" else TYPO_IDS


def attested_ids_for_tier(tier: str) -> frozenset[str]:
    if tier == "smoke":
        return SMOKE_ATTESTED_IDS
    # The ordinary-word class is a measurement, and it is taken on the full tier only:
    # twelve calls is a real share of a smaller tier's budget.
    return ATTESTED_IDS if tier == "full" else ATTESTED_IDS - ORDINARY_ATTESTED_IDS


def attestation_ids_for_tier(tier: str) -> frozenset[str]:
    judged = attested_ids_for_tier(tier) | typo_ids_for_tier(tier)
    return frozenset(attestation_id(shot_id) for shot_id in judged)


def wordlist_ids_for_tier(tier: str) -> frozenset[str]:
    # Three calls, on the full tier only: the class exists to be measured, not gated.
    return WORDLIST_IDS if tier == "full" else frozenset()


def initial_jobs_for_tier(tier: str) -> list[Shot]:
    wanted = (
        canonical_ids_for_tier(tier)
        | typo_ids_for_tier(tier)
        | attested_ids_for_tier(tier)
        | attestation_ids_for_tier(tier)
        | neighbour_ids_for_tier(tier)
        | wordlist_ids_for_tier(tier)
    )
    return [
        shot
        for shot in (
            *initial_shots(),
            *typo_shots(),
            *attested_shots(),
            *attestation_shots(),
            *neighbour_shots(),
            *wordlist_shots(),
        )
        if shot.shot_id in wanted
    ]


def output_path(out: Path) -> Path:
    return out / "answers.jsonl"


def append(out: Path, shot: Shot) -> None:
    path = output_path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(shot), ensure_ascii=False) + "\n")


def read_attempts(out: Path) -> list[Shot]:
    path = output_path(out)
    if not path.exists():
        return []
    rows = []
    prompt_logger = logging.getLogger("echo_words.prompt")
    previous_level = prompt_logger.level
    prompt_logger.setLevel(logging.ERROR)
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(score(Shot(**json.loads(line))))
        return rows
    finally:
        prompt_logger.setLevel(previous_level)


def initial_shots() -> list[Shot]:
    return [*text_shots(), *bare_shots(), *verdict_shots()]


def _job_metadata(shot: Shot) -> tuple[object, ...]:
    return (
        shot.shot_id,
        shot.kind,
        shot.lang,
        shot.source,
        shot.context,
        tuple(tuple(group) for group in shot.expected_groups),
        shot.expects_morphology,
        shot.expression,
        shot.expected_kind,
        tuple(shot.accepted),
        shot.selected_segment_kind,
        shot.expected_suggestion,
    )


def _matches_canonical(stored: Shot, canonical: Shot) -> bool:
    return (
        _job_metadata(stored) == _job_metadata(canonical)
        and stored.prompt_hash == prompt_fingerprint(canonical)
    )


def _score_canonical(stored: Shot, canonical: Shot) -> Shot:
    return score(
        replace(
            canonical,
            prompt_hash=stored.prompt_hash,
            answered_by=stored.answered_by,
            t_first=stored.t_first,
            t_total=stored.t_total,
            error=stored.error,
            text=stored.text,
        ),
    )


def _select_canonical(
    attempts: list[Shot],
    canonical: dict[str, Shot],
) -> dict[str, Shot]:
    rows: dict[str, Shot] = {}
    for stored in attempts:
        job = canonical.get(stored.shot_id)
        if job is not None and _matches_canonical(stored, job):
            current = rows.get(stored.shot_id)
            if current is None or not complete(current):
                rows[stored.shot_id] = _score_canonical(stored, job)
    return rows


def read(out: Path, attempts: list[Shot] | None = None) -> dict[str, Shot]:
    """Return canonical answers, retaining the first terminal attempt."""
    recorded = attempts if attempts is not None else read_attempts(out)
    initial = {
        shot.shot_id: shot
        for shot in (
            *initial_shots(),
            *typo_shots(),
            *attested_shots(),
            *attestation_shots(),
            *neighbour_shots(),
            *wordlist_shots(),
        )
    }
    rows = _select_canonical(recorded, initial)
    clicks = {shot.shot_id: shot for shot in context_shots(rows)}
    rows.update(_select_canonical(recorded, clicks))
    corrections = {shot.shot_id: shot for shot in correction_shots(rows)}
    rows.update(_select_canonical(recorded, corrections))
    return rows


def read_arms(
    out: Path,
    attempts: list[Shot] | None = None,
) -> list[dict[str, Shot]]:
    """Group append-only attempts by each shot's prompt-hash generation."""
    hashes: dict[str, list[str]] = {}
    arms: list[dict[str, Shot]] = []
    for shot in attempts if attempts is not None else read_attempts(out):
        if shot.kind in {"context", "correction", "typo"}:
            continue
        seen = hashes.setdefault(shot.shot_id, [])
        if shot.prompt_hash not in seen:
            seen.append(shot.prompt_hash)
        generation = seen.index(shot.prompt_hash)
        while len(arms) <= generation:
            arms.append({})
        current = arms[generation].get(shot.shot_id)
        if current is None or not complete(current):
            arms[generation][shot.shot_id] = shot
    return arms


def _raw_payload(text: str) -> tuple[dict, str | None]:
    _analysis, raw = split_answer(text)
    value, error = parse_json_object(raw)
    return value or {}, error


def raw_combinations(shot: Shot) -> list[dict]:
    raw = shot.payload.get("combinations")
    return [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []


def _match_label(label: str, source: list[str], claimed: set[int], lang: str) -> list[int]:
    available = [index for index in range(len(source)) if index not in claimed]
    matched: list[int] = []
    for part in split_words(label):
        wanted = normalize(part, lang)
        found = next(
            (index for index in available if normalize(source[index], lang) == wanted),
            None,
        )
        if found is None:
            return []
        matched.append(found)
        available.remove(found)
    return sorted(matched)


def coverage(shot: Shot, parsed: ParsedText) -> dict:
    source = split_words(shot.source)
    claimed: set[int] = set()
    unmatched: list[str] = []
    # The one-word chips must walk the source left to right; a combination repeats
    # words which already have their own chip, so it is only located, never consumed.
    cursor = 0
    for segment in parsed.segments:
        parts = split_words(segment.label)
        if len(parts) > 1:
            if not _match_label(segment.label, source[cursor:], set(), shot.lang):
                unmatched.append(segment.label)
            continue
        if cursor < len(source) and normalize(source[cursor], shot.lang) == normalize(
            parts[0] if parts else segment.label,
            shot.lang,
        ):
            claimed.add(cursor)
            cursor += 1
        else:
            unmatched.append(segment.label)
    function_indices = {
        index
        for index, token in enumerate(source)
        if normalize(token) in FUNCTION_WORDS[shot.lang]
    }
    expected = EXPECTED_SURFACE_GROUPS.get(shot.shot_id, ())
    combination_labels = _filled_combination_labels(shot)
    lookups = [tokens(item.get("label", ""), shot.lang) for item in raw_combinations(shot)]
    expected_lookups = EXPECTED_LOOKUPS.get(shot.shot_id, ())
    registered = _registered_unit_matches(
        shot,
        expected,
        combination_labels,
        standalone={normalize(source[index], shot.lang) for index in claimed},
    )
    return {
        "words_total": len(source),
        "words_covered": len(claimed),
        "coverage": len(claimed) / len(source) if source else 1.0,
        "missing": [word for index, word in enumerate(source) if index not in claimed],
        "unmatched_labels": unmatched,
        "source_order": len(claimed) == len(source),
        "function_total": len(function_indices),
        "function_covered": len(function_indices & claimed),
        "contexts_exact": all(segment.context == shot.source for segment in parsed.segments),
        "labels_valid": all(bool(segment.label) for segment in parsed.segments),
        "expected_found": registered["exact"],
        "expected_total": len(expected),
        "registered_units_found": registered["found"],
        "registered_units_cardable": registered["cardable"],
        "registered_units_total": len(expected),
        "registered_unit_matches": registered["matches"],
        "registered_unit_misses": registered["misses"],
        "registered_merged_neighbor_chips": registered["merged"],
        "expected_lookups_found": sum(
            _lookup_named(tokens(label, shot.lang), lookups)
            for label in expected_lookups
        ),
        "expected_lookups_total": len(expected_lookups),
    }


def _lookup_named(wanted: list[str], returned: list[list[str]]) -> bool:
    # A label may name the unit with its object or subject slot spelled out. A label
    # missing one of the expected parts still names a different, narrower entry.
    # Closing up the internal spaces also accepts `infrage` for `in Frage`.
    joined = "".join(wanted)
    return any(
        set(wanted) <= set(found) or "".join(found) == joined
        for found in returned
        if found
    )


def _filled_combination_labels(shot: Shot) -> list[tuple[int, str]]:
    tagged = []
    for index, item in enumerate(raw_combinations(shot)):
        value = dict(item)
        value["why"] = f"__bench_combination_{index}__"
        tagged.append(value)
    filled = fill_text_segments(tagged, shot.source, LANGUAGES[shot.lang])
    result = []
    for segment in filled:
        match = re.fullmatch(r"__bench_combination_(\d+)__", segment.reason)
        if match is not None:
            result.append((int(match.group(1)), segment.label))
    return result


def _registered_unit_matches(
    shot: Shot,
    expected_surfaces: tuple[tuple[str, ...], ...],
    filled: list[tuple[int, str]],
    *,
    standalone: set[str] | None = None,
) -> dict[str, object]:
    claimed: set[int] = set()
    matches: list[dict[str, object]] = []
    misses: list[str] = []
    for position, group in enumerate(expected_surfaces):
        wanted_ordered = tuple(normalize(word, shot.lang) for word in group)
        wanted = {normalize(word, shot.lang) for word in group}
        candidates: list[tuple[int, int, str, str]] = []
        for raw_index, visible in filled:
            if raw_index in claimed:
                continue
            visible_ordered = tuple(tokens(visible, shot.lang))
            visible_parts = set(tokens(visible, shot.lang))
            if visible_ordered == wanted_ordered:
                candidates.append((0, raw_index, visible, "exact"))
                continue
            if wanted.issubset(visible_parts):
                candidates.append((1, raw_index, visible, "expanded boundary"))
                continue
            alternatives = ACCEPTED_SURFACE_ALTERNATIVES.get(
                (shot.shot_id, position),
                (),
            )
            if visible_ordered in {
                tuple(normalize(word, shot.lang) for word in alternative)
                for alternative in alternatives
            }:
                candidates.append((2, raw_index, visible, "accepted alternative"))
                continue
            omitted = wanted - visible_parts
            if (
                len(wanted & visible_parts) >= MIN_SHARED_WORDS
                and len(omitted) <= MAX_BOUNDARY_DRIFT
                and len(visible_parts - wanted) <= MAX_BOUNDARY_DRIFT
                and omitted <= (standalone or set())
            ):
                candidates.append((3, raw_index, visible, "partial boundary"))
        if not candidates:
            misses.append(" ".join(group))
            continue
        _priority, raw_index, visible, match_kind = min(candidates)
        claimed.add(raw_index)
        matches.append(
            {
                "expected": " ".join(group),
                "chip": visible,
                "match": match_kind,
            },
        )

    merged: list[dict[str, object]] = []
    for _raw_index, visible in filled:
        visible_parts = set(tokens(visible, shot.lang))
        contained = [
            " ".join(group)
            for group in expected_surfaces
            if {normalize(word, shot.lang) for word in group}.issubset(visible_parts)
        ]
        if len(contained) > 1:
            merged.append({"chip": visible, "contains": contained})

    return {
        "found": len(matches),
        "exact": sum(match["match"] == "exact" for match in matches),
        "cardable": sum(match["match"] in CARDABLE_MATCHES for match in matches),
        "matches": matches,
        "misses": misses,
        "merged": merged,
    }


def _registered_units_found(
    shot: Shot,
    expected_surfaces: tuple[tuple[str, ...], ...],
    filled: list[tuple[int, str]],
) -> int:
    return int(_registered_unit_matches(shot, expected_surfaces, filled)["found"])


# Mostly written in the target language, because that is what a forms table labels its
# rows in and this bench answers into Russian only. The Latin names are here because a
# German or Serbian article labels a paradigm in its own grammatical tradition, and the
# abbreviations because a table cell is where a category gets shortened.
_GRAMMAR_TERMS = re.compile(
    r"падеж|именительн|родительн|дательн|винительн|творительн|предложн|звательн|местн"
    r"|\b(?:им|род|дат|вин|твор|предл|мест)\.?\s?п(?:ад)?\.|"
    r"настоящ|прошедш|будущ|наклонени|спряжен|склонен|"
    r"[123]-е лицо|лицо\b|единственное число|множественное число|\b(?:ед|мн)\.\s?ч\.|"
    r"мужской род|женский род|средний род|"
    r"инфинитив|причасти|деепричасти|императив|"
    r"существительное|прилагательное|наречие|глагол\b|предлог\b|союз\b|местоимение|"
    r"\bон, она, оно\b|"
    r"\b(?:Nominativ|Genitiv|Dativ|Akkusativ|Vokativ|Instrumental|Lokativ|"
    r"Präsens|Präteritum|Perfekt|Futur|Konjunktiv|Imperativ|Partizip|Infinitiv|"
    r"Singular|Plural|Maskulinum|Femininum|Neutrum)\b",
    re.IGNORECASE,
)


def forms_table_terms(analysis: str) -> list[str]:
    """Forms-table cells naming a grammatical category, which the answer may not do.

    A presence regex over the whole article would score an ordinary usage note as a
    violation, so only table cells are read, and the cell itself is returned rather
    than the fragment that matched: the reviewer needs to see what was printed.
    """
    return sorted(
        {
            cell
            for table in re.findall(r"<table>.*?</table>", analysis, re.DOTALL)
            for raw in re.findall(r"<td>(.*?)</td>", table, re.DOTALL)
            if _GRAMMAR_TERMS.search(cell := re.sub(r"<[^>]*>", "", raw).strip())
        },
    )


def format_ok(analysis: str) -> bool:
    tags = {tag.casefold() for tag in re.findall(r"</?([A-Za-z][A-Za-z0-9]*)", analysis)}
    markdown = bool(
        re.search(
            # A numbered or bulleted line is prose under pre-wrap and the prompt
            # allows it; only what the prompt forbids counts as a violation.
            r"\*\*|\*[^*\n]+\*|^#{1,6} ",
            analysis,
            re.MULTILINE,
        ),
    )
    return not (tags - _ALLOWED_TAGS) and not markdown


def _mixed_branch(payload: dict) -> bool:
    kind = payload.get("kind")
    return bool(
        (kind == "text" and _UNIT_BRANCH_FIELDS & set(payload))
        or (kind == "unit" and _TEXT_BRANCH_FIELDS & set(payload))
    )


def _sanitized_html_safe(value: str) -> bool:
    stack: list[str] = []
    for token in _RAW_TAG.findall(value):
        opening = re.fullmatch(r"<([a-z]+)>", token)
        if opening is not None and opening.group(1) in _ALLOWED_TAGS:
            stack.append(opening.group(1))
            continue
        closing = re.fullmatch(r"</([a-z]+)>", token)
        if (
            closing is None
            or closing.group(1) not in _ALLOWED_TAGS
            or not stack
            or stack.pop() != closing.group(1)
        ):
            return False
    return not stack


def _parsed_payload_sanitized(parsed: ParsedText | ParsedUnit | None) -> bool:
    if not isinstance(parsed, ParsedUnit):
        return True
    return all(
        _sanitized_html_safe(value)
        for meaning in parsed.note.meanings
        for example in meaning.examples
        for value in (example.highlighted, example.gapped)
    )


def _sentence_form_issue(
    highlighted: object,
    *,
    submitted: str = "",
    target_lexeme: str = "",
) -> str | None:
    """Read the one sentence form the contract asks for, and nothing beside it.

    The example carries its sentence once, marked; a separate plain copy was asked for
    by an older contract and is not sent any more. Reading that absent field reported
    every example as malformed and hid the real defects behind the noise.
    """
    if not isinstance(highlighted, str):
        return "missing sentence form"
    spans = list(re.finditer(r"<b>([^<>]+)</b>", highlighted))
    if not spans:
        return "missing highlight"
    # With no plain copy to compare against, markup is what the sentence is judged on:
    # anything but the highlight itself changes what the card front says.
    if re.search(r"<(?!/?b>)[^<>]*>", highlighted):
        return "markup other than the highlight"
    text = re.sub(r"<b>([^<>]+)</b>", r"\1", highlighted)
    outside = re.sub(r"<b>[^<>]+</b>", "", highlighted)
    if not any(char.isalpha() for char in unescape(outside)):
        return "whole sentence is the unit"
    if submitted:
        target_tokens = set(tokens(target_lexeme))
        submitted_counts = Counter(
            token for token in tokens(submitted) if token in target_tokens
        )
        text_counts = Counter(tokens(text))
        target_counts = Counter(
            tokens(" ".join(match.group(1) for match in spans)),
        )
        if any(
            target_counts[token] < min(count, text_counts[token])
            for token, count in submitted_counts.items()
            if text_counts[token]
        ):
            return "submitted token occurs outside target"
    return None


def _raw_sentence_issues(shot: Shot) -> list[dict[str, object]]:
    issues = []
    meanings = shot.payload.get("meanings")
    if not isinstance(meanings, list):
        return issues
    for meaning_index, meaning in enumerate(meanings):
        if not isinstance(meaning, dict) or not isinstance(meaning.get("examples"), list):
            continue
        for example_index, example in enumerate(meaning["examples"]):
            if not isinstance(example, dict):
                continue
            issue = _sentence_form_issue(
                example.get("highlighted"),
                submitted=shot.source if not shot.context else "",
                target_lexeme=str(shot.payload.get("word", "")),
            )
            if issue is not None:
                issues.append(
                    {
                        "meaning": meaning_index,
                        "example": example_index,
                        "issue": issue,
                        "evidence": example,
                    },
                )
    return issues


def vocab_metrics(shot: Shot, parsed: ParsedUnit, analysis: str) -> dict:
    note = parsed.note
    example = note.meaning.examples[0]
    requested_parts = tokens(shot.source)
    highlighted_parts = tokens(" ".join(re.findall(r"<b>(.*?)</b>", example.highlighted)))
    expected_expression_parts = EXPECTED_EXPRESSION_PARTS.get(shot.shot_id)
    expression_parts = tuple(segment.label for segment in parsed.segments)
    click_case = CLICK_BY_ID.get(shot.shot_id)
    raw_sentence_issues = _raw_sentence_issues(shot)
    typo_case = TYPO_BY_ID.get(shot.shot_id)
    # The correction is applied rather than offered: the note carries the attested
    # spelling, and the entry tells the reader their own spelling was not a word.
    typo_word_exact = typo_case is None or normalize(note.word, shot.lang) == normalize(
        typo_case.suggestion,
        shot.lang,
    )
    # The harm this arm exists to prevent: an entry headed by the very spelling the
    # reader mistyped, which is the one card that would teach them the mistake.
    typo_heads_submission = typo_case is not None and normalize(
        note.word,
        shot.lang,
    ) == normalize(typo_case.submitted, shot.lang)
    typo_relation_exact = typo_case is None or parsed.word_relation == "typo"
    typo_suggestion_exact = typo_case is None or not parsed.suggestion
    neighbour_case = NEIGHBOUR_BY_ID.get(shot.shot_id)
    # Nothing routes a near neighbour into a field any more. What the reader can still
    # be told is what the article says, so that is what the arm measures.
    neighbour_offered = bool(parsed.suggestion)
    neighbour_kept = normalize(note.word, shot.lang) == normalize(
        shot.source,
        shot.lang,
    ) and parsed.word_relation != "typo"
    neighbour_named = bool(
        neighbour_case
        and neighbour_case.neighbour
        and normalize(neighbour_case.neighbour, shot.lang)
        in set(tokens(analysis, shot.lang))
    )
    return {
        "word_valid": bool(note.word),
        "meanings": len(note.meanings),
        "meanings_valid": bool(note.meanings),
        "four_cards_ready": bool(
            note.word
            and note.meaning.translations
            and example.highlighted
            and example.gapped
        ),
        "sense_chips_ready": all(meaning.examples for meaning in note.meanings),
        "origin": bool(_ORIGIN.search(analysis)),
        "usage": bool(_USAGE.search(analysis)),
        "morphology": bool(_MORPHOLOGY.search(analysis)),
        "morphology_required": shot.expects_morphology,
        "has_forms_table": "<table>" in analysis,
        "forms_table_terms": forms_table_terms(analysis),
        "context_example_exact": example.text == shot.context if shot.context else True,
        "context_parts_highlighted": all(
            part in highlighted_parts for part in requested_parts
        )
        if shot.context
        else True,
        "context_surface_exact": highlighted_parts == requested_parts
        if shot.context
        else True,
        "context_segments_empty": not parsed.segments if shot.context else True,
        "click_target_exact": click_case is None
        or normalize(shot.source) == normalize(click_case.label),
        "click_target_kind_exact": click_case is None
        or shot.selected_segment_kind == click_case.segment_kind,
        "expression_parts": len(parsed.segments)
        if shot.expression and not shot.context
        else 0,
        "expression_parts_exact": expected_expression_parts is None
        or expression_parts == expected_expression_parts,
        "expression_contexts_exact": expected_expression_parts is None
        or (
            len(parsed.segments) == len(expected_expression_parts)
            and all(segment.context == example.text for segment in parsed.segments)
        ),
        "targeted_sentence_forms": all(
            _sentence_form_issue(item.highlighted) is None
            for meaning in note.meanings
            for item in meaning.examples
        ),
        "raw_sentence_issues": raw_sentence_issues,
        "raw_sentence_forms_exact": not raw_sentence_issues,
        "word_relation": parsed.word_relation,
        "typo_word_exact": typo_word_exact,
        "typo_heads_submission": typo_heads_submission,
        "typo_relation_exact": typo_relation_exact,
        "typo_suggestion_exact": typo_suggestion_exact,
        "typo_success": (
            typo_word_exact and typo_relation_exact and typo_suggestion_exact
        ),
        "neighbour_offered": neighbour_offered,
        "neighbour_kept_submission": neighbour_kept,
        "neighbour_named_in_prose": neighbour_named,
        "neighbour_false_offer": (
            neighbour_case is not None and not neighbour_case.neighbour and neighbour_offered
        ),
        "card_fronts": [
            note.word,
            ", ".join(note.meaning.translations),
            example.highlighted,
            example.gapped,
        ],
    }


def judgement_refused(shot: Shot | None) -> bool:
    """Whether the standalone judgement withheld the wording.

    It is the only call that judges: the article prompt asks for no verdict of its
    own. An unreadable answer is an absent judgement, never a refusal.
    """
    if shot is None:
        return False
    verdict = parse_attestation(shot.text)
    return verdict is not None and not verdict.used


def attested_carded(shot: Shot) -> bool:
    """A dictionary article headed by the submitted wording, which is what cards it."""
    if shot.payload.get("kind") != "unit":
        return False
    return normalize(shot.payload.get("word"), shot.lang) == normalize(shot.source, shot.lang)


def _withheld_in_production(rows: list[Shot]) -> set[str]:
    """The fixtures whose answer never reaches a reader, read exactly as production
    decides it: the judgement refused the submission, and where the answer replaced
    that submission with a correction, the second judgement refused that one too."""
    by_id = {row.shot_id: row for row in rows}
    withheld = set()
    for row in rows:
        if row.kind != "attestation" or not judgement_refused(row):
            continue
        shot_id = row.shot_id.removeprefix("attestation-")
        answer = by_id.get(shot_id)
        overruled = (
            answer is not None
            and bool(_correction_wording(answer))
            and not judgement_refused(by_id.get(correction_id(shot_id)))
        )
        if not overruled:
            withheld.add(shot_id)
    return withheld


def _recoverable(shot: Shot) -> bool:
    accepted = {normalize(value, shot.lang) for value in shot.accepted}
    labels = {normalize(item.get("label", ""), shot.lang) for item in raw_combinations(shot)}
    return bool(accepted & labels)


def _first_lookup_exact(shot: Shot) -> bool:
    accepted = {normalize(value, shot.lang) for value in shot.accepted}
    items = raw_combinations(shot)
    return bool(items) and normalize(items[0].get("label", ""), shot.lang) in accepted


def _verdict_outcome(shot: Shot, actual_kind: str | None) -> str:
    if actual_kind not in {"unit", "text"}:
        return "unusable"
    if actual_kind == shot.expected_kind:
        return "correct"
    if shot.shot_id in ACCEPTABLE_UNIT_VERDICTS and actual_kind == "unit":
        return "acceptable"
    if shot.shot_id in DEFENSIBLE_UNIT_VERDICTS and actual_kind == "unit":
        return "ambiguous"
    return "hard_error"


def _payload_parses_unrepaired(text: str) -> bool:
    """Whether the card JSON stood on its own, before `extract_answer` repaired it."""
    at = text.find(CARD_DELIMITER)
    if at < 0:
        return False
    try:
        json.JSONDecoder().raw_decode(text[at + len(CARD_DELIMITER) :].lstrip())
    except (json.JSONDecodeError, TypeError):
        return False
    return True


def _wordlist_chips(shot: Shot, parsed: ParsedAnswer | None) -> int:
    """The chips the reader ends with. Nothing judges a submit-box submission, so the
    text branch is the only thing that leaves the reader a chip per word."""
    return len(parsed.segments) if isinstance(parsed, ParsedText) else 0


def score(shot: Shot) -> Shot:
    if shot.shot_id in EXPECTED_UNIT_OVERRIDES:
        shot.expected_kind = "unit"
    analysis, _raw = split_answer(shot.text)
    shot.payload, raw_error = _raw_payload(shot.text)
    unit_intent = _unit_intent(shot)
    parsed = extract_answer(
        shot.text,
        shot.source,
        LANGUAGES[shot.lang],
        unit_intent=unit_intent,
        context=shot.context,
    )
    semantic_parsed = parsed
    unit_intent_wrong_branch = False
    if parsed is None and unit_intent and shot.payload.get("kind") == "text":
        candidate = extract_answer(
            shot.text,
            shot.source,
            LANGUAGES[shot.lang],
            context=shot.context,
        )
        if isinstance(candidate, ParsedText):
            semantic_parsed = candidate
            unit_intent_wrong_branch = True
    actual_kind = semantic_parsed.kind if semantic_parsed is not None else None
    verdict_outcome = _verdict_outcome(shot, actual_kind)
    article_unit = bool(_BOLD_START.match(analysis.strip()))
    within_answer_bound = len(shot.text) <= MAX_COMPLETE_ANSWER_CHARS
    sanitized_analysis = sanitize_html(analysis)
    raw_sentence_issues = _raw_sentence_issues(shot) if shot.payload.get("kind") == "unit" else []
    common = {
        "answered": bool(shot.text) and not shot.error,
        "raw_parse_error": raw_error,
        "payload_valid": parsed is not None,
        "payload_repaired": parsed is not None and not _payload_parses_unrepaired(shot.text),
        "semantic_payload_valid": semantic_parsed is not None,
        "unit_intent_wrong_branch": unit_intent_wrong_branch,
        "actual_kind": actual_kind,
        "verdict_correct": actual_kind == shot.expected_kind,
        "verdict_outcome": verdict_outcome,
        "hard_verdict_error": verdict_outcome == "hard_error",
        "answer_language": answer_language(analysis) if shot.text else None,
        "format_ok": format_ok(analysis) if shot.text else False,
        "article_chars": len(analysis),
        "article_unit": article_unit,
        "article_matches": actual_kind is not None
        and article_unit is (actual_kind == "unit"),
        "mixed_branch": _mixed_branch(shot.payload),
        "within_answer_bound": within_answer_bound,
        "accepted_payload_safe": parsed is None
        or (
            within_answer_bound
            and _sanitized_html_safe(sanitized_analysis)
            and _parsed_payload_sanitized(parsed)
        ),
        "context_sense_leak": (
            "context_sense" in shot.payload and not shot.context
        ),
        "raw_sentence_issues": raw_sentence_issues,
        "raw_sentence_forms_exact": not raw_sentence_issues,
        # A word list has no unit to extract, so carding one as a dictionary entry is
        # the failure. A refusal is not: production reads a refused multi-word
        # submission as text and leaves the reader a chip for each word.
        "wordlist_carded": shot.kind == "wordlist" and isinstance(parsed, ParsedUnit),
        "wordlist_chips": _wordlist_chips(shot, semantic_parsed)
        if shot.kind == "wordlist"
        else 0,
    }
    if isinstance(semantic_parsed, ParsedText):
        raw_items = raw_combinations(shot)
        shot.metrics = {
            **common,
            **coverage(shot, semantic_parsed),
            "segments": len(semantic_parsed.segments),
            "combination_contract_valid": isinstance(
                shot.payload.get("combinations"),
                list,
            ),
            "negative_control_clean": not raw_items
            if shot.shot_id in NO_COMBINATION_SHOTS
            else True,
            "minimal_combination_contract": all(
                set(item).issubset({"label", "surface", "why"})
                for item in raw_items
            ),
            "no_card_fields": not (
                {"word", "meanings", "segments"} & set(shot.payload)
            ),
            "recoverable": _recoverable(shot),
            "first_lookup_exact": _first_lookup_exact(shot),
        }
    elif isinstance(semantic_parsed, ParsedUnit):
        shot.metrics = {
            **common,
            **vocab_metrics(shot, semantic_parsed, analysis),
        }
    else:
        shot.metrics = common
    return shot


def find_segment(shot: Shot, case: ClickCase):
    if shot.metrics.get("actual_kind") != "text":
        return None
    parsed = extract_answer(shot.text, shot.source, LANGUAGES[shot.lang])
    if not isinstance(parsed, ParsedText):
        return None
    combination_labels = {
        normalize(label, shot.lang) for _index, label in _filled_combination_labels(shot)
    }
    wanted = normalize(case.label, shot.lang)
    return next(
        (
            (segment, segment_kind)
            for segment in parsed.segments
            if normalize(segment.label, shot.lang) == wanted
            and (
                segment_kind := (
                    "combination"
                    if normalize(segment.label, shot.lang) in combination_labels
                    else "standalone"
                )
            )
            == case.segment_kind
        ),
        None,
    )


def context_shots(recorded: dict[str, Shot]) -> list[Shot]:
    rows: list[Shot] = []
    for case in CLICK_CASES:
        source = recorded.get(case.text_id)
        selected = find_segment(source, case) if source is not None else None
        if source is None or selected is None:
            continue
        segment, segment_kind = selected
        rows.append(
            Shot(
                case.shot_id,
                "context",
                source.lang,
                segment.label,
                context=segment.context,
                expects_morphology=case.segment_kind == "combination",
                expected_kind="unit",
                selected_segment_kind=segment_kind,
            ),
        )
    return rows


def click_success(shot: Shot) -> bool:
    return bool(
        shot.shot_id in CLICK_IDS
        and shot.metrics.get("answered")
        and shot.metrics.get("payload_valid")
        and shot.metrics.get("actual_kind") == "unit"
        and shot.metrics.get("four_cards_ready")
        and shot.metrics.get("context_example_exact")
        and shot.metrics.get("context_surface_exact")
        and shot.metrics.get("click_target_exact")
        and shot.metrics.get("click_target_kind_exact")
    )


def click_gate(rows: list[Shot]) -> dict[str, bool]:
    successful = {row.shot_id for row in rows if click_success(row)}
    return {"at least five successful click cases": len(successful) >= MIN_CLICK_SUCCESS}


def expression_success(shot: Shot) -> bool:
    return bool(
        shot.shot_id in EXPRESSION_IDS
        and shot.kind == "bare"
        and shot.expression
        and shot.metrics.get("answered")
        and shot.metrics.get("payload_valid")
        and shot.metrics.get("actual_kind") == "unit"
        and shot.metrics.get("four_cards_ready")
        and shot.metrics.get("expression_parts_exact")
        and shot.metrics.get("expression_contexts_exact")
    )


def expression_gate(rows: list[Shot]) -> dict[str, bool]:
    successful = {row.shot_id for row in rows if expression_success(row)}
    return {
        "at least two successful expression cases": len(successful)
        >= MIN_EXPRESSION_SUCCESS,
    }


async def run_batch(args, out: Path, broker: AsyncBroker, jobs: list[Shot]) -> None:
    gate = asyncio.Semaphore(args.concurrency)
    pacer = Pacer(args.pace)

    async def one(shot: Shot) -> None:
        shot.prompt_hash = prompt_fingerprint(shot)
        await pacer.wait()
        async with gate:
            handle = broker.stream(
                prompt_for(shot),
                operation=f"one-note-{shot.kind}-{shot.lang}",
                wait=args.wait,
            )
            try:
                await drain(handle, shot)
                shot.answered_by = handle.llm_name
            except Exception as exc:  # noqa: BLE001 - provider failure is benchmark data
                shot.error = f"{type(exc).__name__}: {exc}"
                shot.answered_by = handle.llm_name
            finally:
                await handle.aclose()
        score(shot)
        append(out, shot)
        log(
            f"{shot.shot_id}: {shot.source!r} -> {shot.answered_by or '?'} "
            f"{shot.t_total}s {shot.error or ''}",
        )

    await asyncio.gather(*(one(shot) for shot in jobs))


def complete(shot: Shot) -> bool:
    # A standalone judgement answers with neither branch, so completeness for it is a
    # readable judgement. Judging it by the branch keys made every resume re-ask all of
    # them, and kept the last attempt where every other kind keeps the first.
    if shot.kind in {"attestation", "correction"}:
        return parse_attestation(shot.text) is not None
    return bool(
        shot.metrics.get("answered")
        and (
            shot.metrics.get("payload_valid")
            or shot.metrics.get("semantic_payload_valid")
        )
        and shot.metrics.get("actual_kind") in {"unit", "text"}
    )


def pending(jobs: list[Shot], recorded: dict[str, Shot], resume: bool) -> list[Shot]:
    result = []
    for shot in jobs:
        old = recorded.get(shot.shot_id)
        if (
            resume
            and old is not None
            and old.prompt_hash == prompt_fingerprint(shot)
            and old.source == shot.source
            and old.context == shot.context
            and complete(old)
        ):
            continue
        result.append(shot)
    return result


async def run(args, out: Path) -> None:
    assert_no_prompt_drift()
    os.environ.update(load_keys())
    broker = AsyncBroker(home=out / "llmbroker")
    try:
        jobs = initial_jobs_for_tier(args.tier)
        if args.shot:
            requested = set(args.shot)
            jobs = [
                shot
                for shot in (
                    *initial_shots(),
                    *typo_shots(),
                    *attested_shots(),
                    *attestation_shots(),
                    *neighbour_shots(),
                    *wordlist_shots(),
                )
                if shot.shot_id in requested
            ]
            missing = requested - {shot.shot_id for shot in jobs}
            if missing:
                raise SystemExit("unknown shot ids: " + ", ".join(sorted(missing)))
        todo = pending(jobs, read(out), args.resume)
        log(f"initial: {len(todo)} calls")
        await run_batch(args, out, broker, todo)
    finally:
        await broker.aclose()


async def run_clicks(args, out: Path) -> None:
    assert_no_prompt_drift()
    os.environ.update(load_keys())
    broker = AsyncBroker(home=out / "llmbroker")
    try:
        recorded = read(out)
        jobs = context_shots(recorded)
        if args.shot:
            requested = set(args.shot)
            unknown = requested - CLICK_IDS
            if unknown:
                raise SystemExit("unknown click ids: " + ", ".join(sorted(unknown)))
            jobs = [shot for shot in jobs if shot.shot_id in requested]
        unavailable = CLICK_IDS - {job.shot_id for job in jobs}
        if unavailable:
            log("click sources unavailable: " + ", ".join(sorted(unavailable)))
        todo = pending(jobs, recorded, args.resume)
        log(f"clicks: {len(todo)} calls")
        await run_batch(args, out, broker, todo)
    finally:
        await broker.aclose()


async def run_corrections(args, out: Path) -> None:
    assert_no_prompt_drift()
    os.environ.update(load_keys())
    broker = AsyncBroker(home=out / "llmbroker")
    try:
        recorded = read(out)
        jobs = correction_shots(recorded)
        todo = pending(jobs, recorded, args.resume)
        log(f"corrections: {len(todo)} calls")
        await run_batch(args, out, broker, todo)
    finally:
        await broker.aclose()


def ratio(rows: list[Shot], key: str) -> str:
    passed = sum(bool(row.metrics.get(key)) for row in rows)
    return f"{passed}/{len(rows)} ({passed / len(rows):.0%})" if rows else "-"


def usable_result(shot: Shot) -> bool:
    return complete(shot)


def _text_fill_preserved(shot: Shot) -> bool:
    return bool(
        shot.metrics.get("actual_kind") == "text"
        and shot.metrics.get("words_covered") == shot.metrics.get("words_total")
        and shot.metrics.get("function_covered") == shot.metrics.get("function_total")
        and not shot.metrics.get("missing")
        and not shot.metrics.get("unmatched_labels")
        and shot.metrics.get("source_order")
        and shot.metrics.get("contexts_exact")
        and shot.metrics.get("labels_valid")
    )


def hard_verdict_rate_ok(errors: int, usable: int) -> bool:
    return usable > 0 and errors * 10 <= usable


def quality_counts(
    initial_rows: list[Shot],
    context_rows: list[Shot],
    corrections: list[Shot] = [],  # noqa: B006 - read only, and empty is the honest default
) -> dict[str, int]:
    verdict_rows = [row for row in initial_rows if row.kind == "verdict"]
    usable_verdicts = [row for row in verdict_rows if usable_result(row)]
    text_rows = [row for row in initial_rows if row.kind == "text"]
    bare_rows = [row for row in initial_rows if row.kind == "bare"]
    typo_rows = [row for row in initial_rows if row.kind == "typo"]
    neighbour_rows = [row for row in initial_rows if row.kind == "neighbour"]
    wordlist_rows = [row for row in initial_rows if row.kind == "wordlist"]
    attested_rows = [row for row in initial_rows if row.kind == "attested"]
    withheld = _withheld_in_production([*initial_rows, *corrections])
    actual_text_rows = [
        row
        for row in text_rows
        if usable_result(row) and row.metrics.get("actual_kind") == "text"
    ]
    return {
        "usable_initial": sum(
            usable_result(row)
            for row in initial_rows
            if row.kind not in {"typo", "attested", "attestation", "neighbour", "wordlist"}
        ),
        "usable_verdicts": len(usable_verdicts),
        "hard_verdict_errors": sum(
            bool(row.metrics.get("hard_verdict_error")) for row in usable_verdicts
        ),
        "text_branch": len(actual_text_rows),
        "bare_cardable": sum(
            usable_result(row)
            and row.metrics.get("actual_kind") == "unit"
            and bool(row.metrics.get("meanings_valid"))
            for row in bare_rows
        ),
        "registered_units": sum(
            int(row.metrics.get("registered_units_found", 0))
            for row in actual_text_rows
        ),
        "cardable_units": sum(
            int(row.metrics.get("registered_units_cardable", 0))
            for row in actual_text_rows
        ),
        # The selected-unit prompt has no text branch to answer with, so an answer
        # that still takes one is the whole cost of the split.
        "unit_intent_wrong_branch": sum(
            bool(row.metrics.get("unit_intent_wrong_branch")) for row in initial_rows
        ),
        "click_success": len(
            {row.shot_id for row in context_rows if click_success(row)},
        ),
        "expression_success": len(
            {row.shot_id for row in bare_rows if expression_success(row)},
        ),
        # Zero tolerance, and the only typo gate: what the reader ends up with. A
        # refusal counts as safe, because production shows nothing rather than a card.
        "typo_carded_misspelling": len(
            {
                row.shot_id
                for row in typo_rows
                if row.metrics.get("payload_valid")
                and row.metrics.get("typo_heads_submission")
                and row.shot_id not in withheld
            },
        ),
        # Diagnostics. How often the pool names the misspelling as one measures its
        # manners, not the reader's card: an entry that silently heads itself with the
        # correct spelling gives the right card and scores nothing here.
        "typo_word_exact": len(
            {row.shot_id for row in typo_rows if row.metrics.get("typo_word_exact")},
        ),
        "typo_success": len(
            {row.shot_id for row in typo_rows if row.metrics.get("typo_success")},
        ),
        # What the reader is left with once the field is gone: the article naming the
        # commoner word in its prose, which is where that knowledge always was.
        "neighbour_named_in_prose": len(
            {
                row.shot_id
                for row in neighbour_rows
                if row.metrics.get("neighbour_named_in_prose")
            },
        ),
        "neighbour_false_offers": len(
            {row.shot_id for row in neighbour_rows if row.metrics.get("neighbour_false_offer")},
        ),
        # Diagnostic. The functional description forbids naming a grammatical category
        # in a forms table, and until this counted it the defect was invisible to every
        # gate: a case-labelled table scored as morphology like any other.
        "tables_printed": sum(
            bool(row.metrics.get("has_forms_table")) for row in initial_rows
        ),
        "tables_naming_terms": sum(
            bool(row.metrics.get("forms_table_terms")) for row in initial_rows
        ),
        "attested_kept": len(
            {
                row.shot_id
                for row in attested_rows
                if ATTESTED_BY_ID[row.shot_id].attested
                and not ATTESTED_BY_ID[row.shot_id].ordinary
                and row.shot_id not in withheld
                and attested_carded(row)
            },
        ),
        "wordlist_carded": len(
            {row.shot_id for row in wordlist_rows if row.metrics.get("wordlist_carded")},
        ),
        "wordlist_chipped": len(
            {row.shot_id for row in wordlist_rows if int(row.metrics.get("wordlist_chips", 0)) >= 2},
        ),
        # Diagnostic, deliberately outside every gate: what the ordinary class scores
        # is the open question, and a threshold set before the measurement would be a
        # guess reddening the run for a reason nobody has decided.
        "ordinary_kept": len(
            {
                row.shot_id
                for row in attested_rows
                if ATTESTED_BY_ID[row.shot_id].ordinary
                and row.shot_id not in withheld
                and attested_carded(row)
            },
        ),
        "unused_refused": len(
            {
                row.shot_id
                for row in attested_rows
                if not ATTESTED_BY_ID[row.shot_id].attested
                and row.shot_id in withheld
            },
        ),
    }


def quality_gates(counts: dict[str, int], tier: str) -> dict[str, bool]:
    usable_min = {"smoke": 27, "confirmation": 73, "full": MIN_USABLE_INITIAL}[tier]
    text_min = 19 if tier == "smoke" else MIN_TEXT_BRANCH
    # What the free pool's own first answer manages, which is all this arm sees.
    # Production is measurably better than this number: a declared misspelling is
    # settled by the paid model at six of six, and an undetected one that the
    # standalone judgement refuses is not carded at all. Measured here: three and
    # four of six across runs.
    # No floor on how often the pool names a misspelling as one: that number measures
    # the answer's manners, and the reader's card is gated by the harm rule instead.
    # Measured on the free pool over these fixtures, with the prompts the app sends.
    # Real rare wording survives every run. Coinages: the article's own leading verdict
    # withholds two of six, the standalone judgement three to six over six samples, and
    # production refuses when either does. The floor sits at the bottom of that spread
    # rather than inside it — a well-formed compound is refused in most runs and carded
    # in some, and a floor above the minimum reddens on that draw rather than on a
    # change. It still separates a working judgement from an absent one, which measures
    # two of six twice.
    attested_min = 2 if tier == "smoke" else 3
    unused_min = 2 if tier == "smoke" else 3
    return {
        "usable initial results": counts["usable_initial"] >= usable_min,
        "obvious hard verdict errors": not counts["usable_verdicts"]
        or hard_verdict_rate_ok(
            counts["hard_verdict_errors"],
            counts["usable_verdicts"],
        ),
        "known text reaches text branch": counts["text_branch"] >= text_min,
        "bare units are cardable": counts["bare_cardable"] >= MIN_BARE_CARDABLE,
        "registered units cardable": counts["cardable_units"] >= MIN_CARDABLE_UNITS,
        "successful click cases": counts["click_success"] >= MIN_CLICK_SUCCESS,
        "successful expression cases": counts["expression_success"]
        >= MIN_EXPRESSION_SUCCESS,
        "a misspelling is never carded": counts["typo_carded_misspelling"] == 0,
        # With no field to fill, a suggestion on a correctly spelled ordinary word is
        # the answer calling it misspelled, which is the harm this pair always guarded.
        "no correction is invented for an ordinary word": counts["neighbour_false_offers"]
        == 0,
        # The branch is settled before the call, so an answer that takes the other one
        # is asking for a contract its prompt does not carry.
        "a selected unit is never answered as text": counts["unit_intent_wrong_branch"]
        == 0,
        "rare real wording still cards": counts["attested_kept"] >= attested_min,
        "unused wording is refused": counts["unused_refused"] >= unused_min,
    }


def deterministic_gates(  # noqa: PLR0913 - the screen's inputs, and every arm of them.
    initial_rows: list[Shot],
    context_rows: list[Shot],
    tier: str,
    corrections: list[Shot] = [],  # noqa: B006 - read only, and empty is the honest default
) -> dict[str, bool]:
    canonical = initial_jobs_for_tier(tier)
    expected_ids = {shot.shot_id for shot in canonical}
    accepted_initial = [
        row for row in initial_rows if row.metrics.get("payload_valid")
    ]
    accepted_context = [
        row for row in context_rows if row.metrics.get("payload_valid")
    ]
    accepted = [*accepted_initial, *accepted_context]
    accepted_units = [
        row for row in accepted if row.metrics.get("actual_kind") == "unit"
    ]
    accepted_text = [
        row
        for row in accepted_initial
        if row.metrics.get("actual_kind") == "text"
    ]
    accepted_clicks = [
        row
        for row in accepted_context
        if row.metrics.get("actual_kind") == "unit"
    ]
    withheld = _withheld_in_production([*initial_rows, *corrections])
    # A withheld misspelling is carded by nothing in production, so there is no card
    # here for the contract to hold to a spelling — the carve-out excuses none that is
    # made.
    accepted_typos = [
        row
        for row in accepted_initial
        if row.kind == "typo" and row.shot_id not in withheld
    ]
    expected_canonical = {30: "smoke", 81: "confirmation", 157: "full"}
    expected_typo_count = 3 if tier == "smoke" else 6
    expected_attested_count = len(attested_ids_for_tier(tier))
    expected_attestation_count = len(attestation_ids_for_tier(tier))
    expected_neighbour_count = len(neighbour_ids_for_tier(tier))
    expected_wordlist_count = len(wordlist_ids_for_tier(tier))
    return {
        "all tier manifest fixtures attempted": len(initial_rows) == len(canonical)
        and {row.shot_id for row in initial_rows} == expected_ids,
        "tier manifests have frozen call counts": expected_canonical[
            len(canonical)
            - expected_typo_count
            - expected_attested_count
            - expected_attestation_count
            - expected_neighbour_count
            - expected_wordlist_count
        ]
        == tier
        and sum(row.kind == "wordlist" for row in canonical) == expected_wordlist_count
        and sum(row.kind == "neighbour" for row in canonical) == expected_neighbour_count
        and sum(row.kind == "typo" for row in canonical) == expected_typo_count
        and sum(row.kind == "attested" for row in canonical) == expected_attested_count
        and sum(row.kind == "attestation" for row in canonical) == expected_attestation_count
        and len(CLICK_IDS) == CLICK_FIXTURES
        and len(canonical) + len(CLICK_IDS)
        == {"smoke": 55, "confirmation": 125, "full": 216}[tier],
        "accepted payloads contain one branch": all(
            not row.metrics.get("mixed_branch") for row in accepted
        ),
        "accepted payloads are bounded and sanitized": all(
            row.metrics.get("accepted_payload_safe") for row in accepted
        ),
        "no context selector leaks into context-free answers": all(
            not row.metrics.get("context_sense_leak") for row in accepted_initial
        ),
        "accepted unit notes have four cards": all(
            row.metrics.get("four_cards_ready") for row in accepted_units
        ),
        "accepted unit examples target less than the whole sentence": all(
            row.metrics.get("targeted_sentence_forms") for row in accepted_units
        ),
        "accepted text fill preserves every source token": all(
            _text_fill_preserved(row) for row in accepted_text
        ),
        "accepted clicks preserve their carried context": all(
            row.metrics.get("context_example_exact")
            and row.metrics.get("context_surface_exact")
            for row in accepted_clicks
        ),
        "accepted typos card the corrected spelling": all(
            row.metrics.get("typo_word_exact") for row in accepted_typos
        ),
    }


def report_verdict(rows: list[Shot]) -> None:
    usable = [row for row in rows if usable_result(row)]
    matrix = Counter(
        (row.expected_kind, row.metrics.get("actual_kind")) for row in usable
    )
    print("UNDECIDED SUBMIT BOX → MODEL VERDICT")
    print(f"  usable verdicts              {len(usable)}/{len(rows)}")
    print("  raw confusion matrix")
    print(f"  unit → unit                  {matrix['unit', 'unit']}")
    print(f"  unit → text                  {matrix['unit', 'text']}")
    print(f"  text → unit                  {matrix['text', 'unit']}")
    print(f"  text → text                  {matrix['text', 'text']}")
    print(f"  article/verdict agreement    {ratio(usable, 'article_matches')}")
    context_clean = sum(
        not row.metrics.get("context_sense_leak") for row in usable
    )
    print(f"  context_sense absent         {context_clean}/{len(usable)}")
    false_text = [
        row
        for row in usable
        if row.expected_kind == "unit" and row.metrics.get("actual_kind") == "text"
    ]
    print(f"  false-text exact lookup      {ratio(false_text, 'recoverable')}")
    print(f"  false-text first exact lookup {ratio(false_text, 'first_lookup_exact')}")
    outcomes = Counter(str(row.metrics.get("verdict_outcome")) for row in rows)
    print("  tolerant interpretation")
    print(f"  correct                      {outcomes['correct']}")
    print(f"  acceptable boundary          {outcomes['acceptable']}")
    print(f"  ambiguous/defensible         {outcomes['ambiguous']}")
    print(f"  hard errors                  {outcomes['hard_error']}")
    print(f"  unusable                     {outcomes['unusable']}")
    for outcome in ("acceptable", "ambiguous", "hard_error"):
        disagreements = [
            row for row in rows if row.metrics.get("verdict_outcome") == outcome
        ]
        if disagreements:
            labels = ", ".join(
                f"{row.shot_id} ({row.metrics.get('actual_kind')})"
                for row in disagreements
            )
            print(f"    {outcome}: {labels}")
    for lang in ("en", "de", "sr"):
        subset = [row for row in usable if row.lang == lang]
        correct = sum(row.metrics.get("verdict_correct") for row in subset)
        hard = sum(row.metrics.get("hard_verdict_error") for row in subset)
        print(f"  {lang} exact / hard errors      {correct}/{len(subset)} / {hard}")
    print()


def report_arm(
    rows: list[Shot],
    index: int,
    canonical_jobs: dict[str, Shot],
) -> None:
    verdict_rows = [row for row in rows if row.kind == "verdict"]
    serbian = [row for row in rows if row.lang == "sr"]
    current = bool(rows) and all(
        (canonical := canonical_jobs.get(row.shot_id)) is not None
        and _matches_canonical(row, canonical)
        for row in rows
    )
    suffix = " — production prompt" if current else " — archived prompt"
    print(f"PROMPT ARM v{index}{suffix}")
    print(f"  recorded attempts             {len(rows)}/157")
    print(f"  provider answers              {ratio(rows, 'answered')}")
    print(f"  parseable payload             {ratio(rows, 'payload_valid')}")
    # `payload_valid` counts answers `extract_answer` repaired into shape, so on its
    # own it overstates how often a model produces JSON that conforms.
    print(f"    of which repaired first     {ratio(rows, 'payload_repaired')}")
    print(f"  Serbian provider answers      {ratio(serbian, 'answered')}")
    print(f"  Serbian parseable payload     {ratio(serbian, 'payload_valid')}")
    report_verdict(verdict_rows)


def _review_item(
    shot: Shot,
    categories: set[str],
    *,
    expected: dict[str, object],
    actual: dict[str, object],
) -> dict[str, object]:
    return {
        "fixture_id": shot.shot_id,
        "categories": sorted(categories),
        "input": {
            "language": shot.lang,
            "submitted": shot.source,
            "context": shot.context,
        },
        "expected": expected,
        "actual": actual,
        "raw_evidence": {"error": shot.error, "answer": shot.text},
    }


def review_packet(
    tier: str,
    expected_initial: list[Shot],
    current: dict[str, Shot],
    screen: dict[str, object] | None = None,
) -> dict[str, object]:
    items = []
    expected_rows = [*expected_initial]
    expected_rows.extend(
        Shot(case.shot_id, "context", "", case.label) for case in CLICK_CASES
    )
    expected_rows.extend(
        row for row in current.values() if row.kind == "correction"
    )
    withheld = _withheld_in_production(list(current.values()))
    for expected_shot in expected_rows:
        shot = current.get(expected_shot.shot_id)
        if shot is None:
            items.append(
                _review_item(
                    expected_shot,
                    {"provider_miss"},
                    expected={"attempt": "current prompt hash"},
                    actual={"attempt": "missing"},
                ),
            )
            continue
        categories: set[str] = set()
        expected: dict[str, object] = {"kind": shot.expected_kind}
        actual: dict[str, object] = {
            "kind": shot.metrics.get("actual_kind"),
            "provider": shot.answered_by,
            "payload_valid": shot.metrics.get("payload_valid"),
        }
        if not shot.metrics.get("answered"):
            categories.add("provider_miss")
        elif not shot.metrics.get("payload_valid"):
            categories.add("unusable")
        if shot.kind == "verdict":
            outcome = str(shot.metrics.get("verdict_outcome"))
            if outcome != "correct":
                categories.add(outcome)
            if shot.expected_kind == "unit" and shot.metrics.get("actual_kind") == "text":
                categories.add("recovery")
            actual["verdict_outcome"] = outcome
            actual["recoverable"] = shot.metrics.get("recoverable")
        if shot.kind == "text":
            exact = (
                shot.metrics.get("expected_found") == shot.metrics.get("expected_total")
                and shot.metrics.get("expected_lookups_found")
                == shot.metrics.get("expected_lookups_total")
            )
            if not exact:
                categories.add("non_exact")
            expected["registered_surfaces"] = shot.expected_groups
            actual["registered_matches"] = shot.metrics.get("registered_unit_matches")
            actual["registered_misses"] = shot.metrics.get("registered_unit_misses")
            actual["merged_chips"] = shot.metrics.get("registered_merged_neighbor_chips")
        if shot.metrics.get("raw_sentence_issues"):
            categories.add("non_exact")
            actual["sentence_form_issues"] = shot.metrics["raw_sentence_issues"]
        if shot.metrics.get("forms_table_terms"):
            categories.add("forms_table_terms")
            actual["forms_table_terms"] = shot.metrics["forms_table_terms"]
        if shot.kind == "context":
            categories.add("click")
            expected["surface"] = CLICK_BY_ID[shot.shot_id].label
            actual["success"] = click_success(shot)
            actual["context_exact"] = shot.metrics.get("context_example_exact")
            actual["surface_exact"] = shot.metrics.get("context_surface_exact")
        if shot.kind in {"attested", "bare", "neighbour", "wordlist"}:
            # Every one of these is read, whatever it scored. The first thing this
            # review exists to catch is a coinage carded with a confident sense, and a
            # carded coinage scores nothing: it earns no category of its own, so a
            # packet built from categories alone cannot show the reviewer the class it
            # was called for.
            categories.add(shot.kind)
            actual["headword"] = shot.payload.get("word")
            # The production outcome, not the payload's: a coinage whose article would
            # have carded and was then withheld must not read as a coinage carded.
            actual["carded"] = bool(shot.metrics.get("meanings_valid")) and (
                shot.shot_id not in withheld
            )
            if shot.kind == "attested":
                case = ATTESTED_BY_ID[shot.shot_id]
                expected["attested"] = case.attested
                expected["class"] = "ordinary" if case.ordinary else "famous"
                judged = current.get(attestation_id(shot.shot_id))
                actual["standalone_refused"] = (
                    judgement_refused(judged) if judged is not None else None
                )
                if judged is not None and shot.metrics.get("payload_valid"):
                    actual["reaches_the_reader"] = shot.shot_id not in withheld
            if shot.kind == "neighbour":
                expected["neighbour"] = NEIGHBOUR_BY_ID[shot.shot_id].neighbour
                actual["neighbour_named_in_prose"] = shot.metrics.get(
                    "neighbour_named_in_prose",
                )
            if shot.kind == "wordlist":
                actual["chips"] = shot.metrics.get("wordlist_chips")
                actual["carded_as_unit"] = shot.metrics.get("wordlist_carded")
        if shot.kind in {"attestation", "correction"}:
            # The judge's own answer, so a reviewer can see it invent an attestation.
            # It carries no card block by design, so it is never an unusable answer.
            categories.discard("unusable")
            categories.add(shot.kind)
            judgement = parse_attestation(shot.text)
            actual["used"] = None if judgement is None else judgement.used
            actual["readable"] = judgement is not None
            actual.pop("payload_valid", None)
        if shot.kind == "typo":
            categories.add("typo")
            # Only where the pool's own answer settles it. An unusable payload steps up
            # to the paid model, which this arm does not call, so what the reader ends
            # up with is not this run's to say.
            if shot.metrics.get("payload_valid"):
                actual["reaches_the_reader"] = shot.shot_id not in withheld
            expected["word"] = shot.expected_suggestion
            expected["word_relation"] = "typo"
            expected["suggestion"] = ""
            actual["word"] = shot.payload.get("word")
            actual["word_relation"] = shot.payload.get("word_relation")
            actual["suggestion"] = shot.payload.get("suggestion")
            actual["success"] = shot.metrics.get("typo_success")
        if categories:
            items.append(_review_item(shot, categories, expected=expected, actual=actual))
    expected_ids = {shot.shot_id for shot in expected_rows}
    attempted = expected_ids & set(current)
    return {
        # The reviewer reads concrete items, and the numbers the screen already passed
        # are what tells them which of those items the screen was blind to.
        "screen": screen if screen is not None else {},
        "tier": tier,
        "prompt_status": (
            "pending_semantic_review" if attempted == expected_ids else "unmeasured"
        ),
        "semantic_review_required": True,
        "acceptance_instruction": (
            "A fresh agent must semantically review every concrete item and record "
            "the prompt-bound decision in a checked-in decision spec before acceptance."
        ),
        "items": items,
    }


def write_review_packet(
    out: Path,
    tier: str,
    expected_initial: list[Shot],
    current: dict[str, Shot],
    screen: dict[str, object] | None = None,
) -> Path:
    path = out / f"review-packet-{tier}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            review_packet(tier, expected_initial, current, screen),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def report(out: Path, tier: str) -> None:
    assert_no_prompt_drift()
    attempts = read_attempts(out)
    if not attempts:
        raise SystemExit(f"no answers in {output_path(out)}")
    arms = read_arms(out, attempts)
    initial_jobs = initial_shots()
    canonical_jobs = {shot.shot_id: shot for shot in initial_jobs}
    print(f"{len(attempts)} recorded attempts across {len(arms)} prompt arms\n")
    for index, arm in enumerate(arms, start=1):
        report_arm(list(arm.values()), index, canonical_jobs)

    current = read(out, attempts)
    wanted_initial = initial_jobs_for_tier(tier)
    wanted_ids = {shot.shot_id for shot in wanted_initial}
    rows = [
        row
        for row in current.values()
        if row.shot_id in wanted_ids
        or row.shot_id in CLICK_IDS
        or row.shot_id.removeprefix("correction-") in wanted_ids
    ]
    current_initial = [row for row in rows if row.kind not in {"context", "correction"}]
    corrections = [row for row in rows if row.kind == "correction"]
    missing = wanted_ids - {
        row.shot_id for row in current_initial
    }
    text_rows = [row for row in current_initial if row.kind == "text"]
    actual_text_rows = [
        row for row in text_rows if row.metrics.get("actual_kind") == "text"
    ]
    vocab_rows = [row for row in rows if row.kind in {"bare", "context"}]
    context_rows = [row for row in rows if row.kind == "context"]
    verdict_rows = [row for row in current_initial if row.kind == "verdict"]
    required_morph = [row for row in vocab_rows if row.expects_morphology]
    counts = quality_counts(current_initial, context_rows, corrections)
    hard = deterministic_gates(current_initial, context_rows, tier, corrections)
    quality = quality_gates(counts, tier)
    canonical_total = len(canonical_ids_for_tier(tier))
    typo_total = len(typo_ids_for_tier(tier))
    attested_total = len(attested_ids_for_tier(tier))
    attestation_total = len(attestation_ids_for_tier(tier))
    neighbour_total = len(neighbour_ids_for_tier(tier))
    initial_total = (
        canonical_total + typo_total + attested_total + attestation_total + neighbour_total
    )
    usable_min = {"smoke": 27, "confirmation": 73, "full": 142}[tier]

    print(f"AUTOMATED SCREEN — {tier.upper()} TIER")
    print("Fresh-agent semantic review of the concrete review packet is mandatory before acceptance.")
    print("Record the prompt-bound review decision in a checked-in decision spec.\n")
    print("CURRENT ATTEMPTS AND AVAILABILITY")
    print(f"  tier initial IDs              {len(current_initial)}/{initial_total}")
    print(
        "  provider answers              "
        f"{sum(bool(row.metrics.get('answered')) for row in current_initial)}"
        f"/{initial_total}",
    )
    print(
        "  parseable payloads            "
        f"{sum(bool(row.metrics.get('payload_valid')) for row in current_initial)}"
        f"/{initial_total}",
    )
    print(
        f"  usable canonical results      {counts['usable_initial']}"
        f"/{canonical_total}",
    )
    if missing:
        print("  missing current IDs           " + ", ".join(sorted(missing)))
    print()

    print("DETERMINISTIC CONTRACTS — ZERO TOLERANCE")
    for name, passed in hard.items():
        print(f"  {'PASS' if passed else 'FAIL':4}  {name}")
    print()

    print("MODEL QUALITY — AGGREGATE THRESHOLDS")
    quality_lines = (
        (
            "usable initial results",
            counts["usable_initial"],
            canonical_total,
            f">= {usable_min}",
        ),
        (
            "obvious hard verdict errors",
            counts["hard_verdict_errors"],
            counts["usable_verdicts"],
            "<= 10% of usable verdicts",
        ),
        (
            "known text reaches text branch",
            counts["text_branch"],
            sum(row.kind == "text" for row in wanted_initial),
            f">= {19 if tier == 'smoke' else MIN_TEXT_BRANCH}",
        ),
        (
            "bare units are cardable",
            counts["bare_cardable"],
            BARE_FIXTURES,
            f">= {MIN_BARE_CARDABLE}",
        ),
        (
            "registered units cardable",
            counts["cardable_units"],
            REGISTERED_UNITS,
            f">= {MIN_CARDABLE_UNITS}",
        ),
        (
            "successful click cases",
            counts["click_success"],
            CLICK_FIXTURES,
            f">= {MIN_CLICK_SUCCESS}",
        ),
        (
            "successful expression cases",
            counts["expression_success"],
            EXPRESSION_FIXTURES,
            f">= {MIN_EXPRESSION_SUCCESS}",
        ),
        (
            "a misspelling is never carded",
            counts["typo_carded_misspelling"],
            typo_total,
            "== 0",
        ),
        (
            "no correction is invented for an ordinary word",
            counts["neighbour_false_offers"],
            len(neighbour_ids_for_tier(tier)),
            "== 0",
        ),
        (
            "a selected unit is never answered as text",
            counts["unit_intent_wrong_branch"],
            len([
                row
                for row in current_initial
                if _unit_intent(row) and row.kind != "attestation"
            ]),
            "== 0",
        ),
        (
            "rare real wording still cards",
            counts["attested_kept"],
            sum(
                1
                for i in attested_ids_for_tier(tier)
                if ATTESTED_BY_ID[i].attested and not ATTESTED_BY_ID[i].ordinary
            ),
            f">= {2 if tier == 'smoke' else 3}",
        ),
        (
            "unused wording is refused",
            counts["unused_refused"],
            sum(1 for i in attested_ids_for_tier(tier) if not ATTESTED_BY_ID[i].attested),
            f">= {2 if tier == 'smoke' else 3}",
        ),
    )
    wordlist_total = len(wordlist_ids_for_tier(tier))
    if wordlist_total:
        print(
            f"  word list carded as a unit    {counts['wordlist_carded']}/{wordlist_total}"
            f"  ·  reader keeps chips {counts['wordlist_chipped']}/{wordlist_total}"
            "  (diagnostic, gates nothing)",
        )
    ordinary_total = sum(1 for i in attested_ids_for_tier(tier) if ATTESTED_BY_ID[i].ordinary)
    if ordinary_total:
        print(
            "  ordinary real wording still cards "
            f"{counts['ordinary_kept']}/{ordinary_total}  (diagnostic, gates nothing)",
        )
    if counts["tables_printed"]:
        print(
            "  forms tables naming a grammatical category "
            f"{counts['tables_naming_terms']}/{counts['tables_printed']}"
            "  (diagnostic, gates nothing)",
        )
    for name, numerator, denominator, threshold in quality_lines:
        passed = quality[name]
        print(
            f"  {'PASS' if passed else 'FAIL':4}  {name:<36} "
            f"{numerator}/{denominator}; {threshold}",
        )
    print()

    print("DIAGNOSTICS — NOT QUALITY GATES")
    words_total = sum(int(row.metrics.get("words_total", 0)) for row in actual_text_rows)
    words_covered = sum(
        int(row.metrics.get("words_covered", 0)) for row in actual_text_rows
    )
    function_total = sum(
        int(row.metrics.get("function_total", 0)) for row in actual_text_rows
    )
    function_covered = sum(
        int(row.metrics.get("function_covered", 0)) for row in actual_text_rows
    )
    expected_found = sum(int(row.metrics.get("expected_found", 0)) for row in text_rows)
    lookup_found = sum(
        int(row.metrics.get("expected_lookups_found", 0)) for row in text_rows
    )
    merged = [
        (row.shot_id, item)
        for row in actual_text_rows
        for item in row.metrics.get("registered_merged_neighbor_chips", [])
    ]
    print(f"  accepted-text source tokens   {words_covered}/{words_total}")
    print(f"  accepted-text function words  {function_covered}/{function_total}")
    print(f"  exact raw dictionary labels   {lookup_found}/{REGISTERED_UNITS}")
    print(f"  exact source boundaries       {expected_found}/{REGISTERED_UNITS}")
    print(f"  merged-neighbor chips         {len(merged)}")
    for shot_id, item in merged:
        print(f"    {shot_id}: {item['chip']} -> {', '.join(item['contains'])}")
    negatives = [
        row for row in actual_text_rows if row.shot_id in NO_COMBINATION_SHOTS
    ]
    print(f"  optional-chip controls empty  {ratio(negatives, 'negative_control_clean')}")
    print(f"  article/verdict agreement     {ratio([r for r in current_initial if usable_result(r)], 'article_matches')}")
    print(f"  strict article format         {ratio(current_initial, 'format_ok')}\n")

    print("VOCAB/CLICK DETAIL")
    print(f"  parseable unit payload        {ratio(vocab_rows, 'payload_valid')}")
    print(f"  every meaning cardable        {ratio(vocab_rows, 'meanings_valid')}")
    print(f"  four card fronts ready        {ratio(vocab_rows, 'four_cards_ready')}")
    print(f"  sense chips ready             {ratio(vocab_rows, 'sense_chips_ready')}")
    print(f"  usage present                 {ratio(vocab_rows, 'usage')}")
    print(f"  origin present                {ratio(vocab_rows, 'origin')}")
    # Where an origin is asked for unconditionally, the answers that have none supply
    # one anyway: a wolf-lupa story for Lupe, viel + leicht for a misspelling. These
    # are the fixtures with nothing to tell, so the share here is the invention rate.
    invented_risk = [
        row
        for row in current_initial
        if row.metrics.get("actual_kind") == "unit"
        and (
            row.kind == "typo"
            or (row.kind == "attested" and not ATTESTED_BY_ID[row.shot_id].attested)
        )
    ]
    print(f"    on coinages and misspellings {ratio(invented_risk, 'origin')}")
    print(f"  required morphology present   {ratio(required_morph, 'morphology')}")
    print(f"  clicked context is example 1  {ratio(context_rows, 'context_example_exact')}")
    print(f"  clicked surface exact         {ratio(context_rows, 'context_surface_exact')}")
    print(f"  click has no components       {ratio(context_rows, 'context_segments_empty')}\n")
    expression_rows = [row for row in vocab_rows if row.kind == "bare" and row.expression]
    print(f"  expression parts exact        {ratio(expression_rows, 'expression_parts_exact')}")
    print(f"  expression contexts exact     {ratio(expression_rows, 'expression_contexts_exact')}\n")

    print("REGISTERED UNITS")
    print(f"  cardable units                {counts['cardable_units']}/{REGISTERED_UNITS}")
    print(f"  distinct units found          {counts['registered_units']}/{REGISTERED_UNITS}")
    print(f"  measured spread across runs   {CARDABLE_UNITS_SPREAD[0]}-{CARDABLE_UNITS_SPREAD[1]}")
    print(f"  floor, at the spread's bottom {MIN_CARDABLE_UNITS}\n")

    typo_rows = [row for row in current_initial if row.kind == "typo"]
    print("TYPO DETAIL — diagnostics; the reader's outcome is gated above")
    print(f"  entry is about the right word {ratio(typo_rows, 'typo_word_exact')}")
    print(f"  headed by the mistyped word   {ratio(typo_rows, 'typo_heads_submission')}")
    print(f"  typo relation declared        {ratio(typo_rows, 'typo_relation_exact')}")
    print(f"  no redundant suggestion       {ratio(typo_rows, 'typo_suggestion_exact')}")
    print(f"  named as a typo and corrected {ratio(typo_rows, 'typo_success')}\n")

    neighbour_rows = [row for row in current_initial if row.kind == "neighbour"]
    wanted = [row for row in neighbour_rows if NEIGHBOUR_BY_ID[row.shot_id].neighbour]
    ordinary = [row for row in neighbour_rows if not NEIGHBOUR_BY_ID[row.shot_id].neighbour]
    print("NEAR-NEIGHBOUR DETAIL — what the dropped field cost the reader")
    print(f"  commoner word named in prose  {ratio(wanted, 'neighbour_named_in_prose')}")
    print(f"  article stayed on submission  {ratio(wanted, 'neighbour_kept_submission')}")
    print(f"  ordinary word left alone      "
          f"{sum(not row.metrics.get('neighbour_offered') for row in ordinary)}/{len(ordinary)}\n")

    print("SECOND JUDGEMENT — the correction put in place of a refused wording")
    print(f"  corrections asked about       {len(corrections)}")
    print(
        "  vouched for, so the note ships "
        f"{sum(not judgement_refused(row) for row in corrections)}/{len(corrections)}\n",
    )

    serbian = [row for row in current_initial if row.lang == "sr" and row.kind != "typo"]
    serbian_verdicts = [row for row in serbian if row.kind == "verdict"]
    print("SERBIAN SLICE — REPORT ONLY")
    serbian_total = sum(
        row.lang == "sr" and row.kind != "typo" for row in wanted_initial
    )
    print(f"  current attempts              {len(serbian)}/{serbian_total}")
    print(
        "  provider answers              "
        f"{sum(bool(row.metrics.get('answered')) for row in serbian)}/{serbian_total}",
    )
    print(
        f"  usable results                {sum(usable_result(row) for row in serbian)}"
        f"/{serbian_total}",
    )
    print(f"  exact verdicts                {ratio(serbian_verdicts, 'verdict_correct')}")
    print(f"  hard verdict errors           {ratio(serbian_verdicts, 'hard_verdict_error')}")
    print(f"  article format clean          {ratio(serbian, 'format_ok')}")

    times = [row.t_total for row in rows if row.t_total is not None and not row.error]
    if times:
        print(f"\nlatency p50 {statistics.median(times):.1f}s")

    packet_path = write_review_packet(
        out,
        tier,
        wanted_initial,
        current,
        {"counts": counts, "deterministic_contracts": hard, "quality_thresholds": quality},
    )
    print(f"review packet: {packet_path}")
    print("AUTOMATED SCREEN ONLY — semantic acceptance is not auto-proven.")

    failed_hard = [name for name, passed in hard.items() if not passed]
    failed_quality = [name for name, passed in quality.items() if not passed]
    if failed_hard or failed_quality:
        failures = []
        if failed_hard:
            failures.append("deterministic contracts: " + ", ".join(failed_hard))
        if failed_quality:
            failures.append("quality thresholds: " + ", ".join(failed_quality))
        raise SystemExit("benchmark failed — " + "; ".join(failures))


def show(out: Path, shot_ids: list[str]) -> None:
    rows = read(out)
    for shot_id in shot_ids or sorted(rows):
        shot = rows.get(shot_id)
        if shot is None:
            continue
        print(f"\n=== {shot.shot_id} {shot.lang} {shot.source!r} ===")
        print(shot.text)
        print("\nMETRICS", json.dumps(shot.metrics, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=["run", "run-clicks", "run-corrections", "report", "show"],
    )
    parser.add_argument("--tier", choices=TIER_NAMES, default="smoke")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--pace", type=float, default=2.0)
    parser.add_argument("--wait", type=float, default=180.0)
    parser.add_argument("--shot", nargs="+", default=[])
    parser.add_argument("--out", default=str(Path(__file__).parent / ".bench-one-note"))
    args = parser.parse_args()
    out = Path(args.out)
    if args.action == "run":
        asyncio.run(run(args, out))
    elif args.action == "run-clicks":
        asyncio.run(run_clicks(args, out))
    elif args.action == "run-corrections":
        asyncio.run(run_corrections(args, out))
    elif args.action == "report":
        report(out, args.tier)
    else:
        show(out, args.shot)


if __name__ == "__main__":
    main()
