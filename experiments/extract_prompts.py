"""The prompt variants under test, as deltas against the shipped vocabulary prompt.

A variant is a list of (anchor, replacement) edits applied to the production
template. Holding them as edits rather than as four hand-copied files is what
makes the comparison mean anything: everything outside the delta is provably
identical, so a difference in the numbers can only come from the rule that
changed. ``build`` raises when an anchor does not fire — a silently skipped edit
would measure the baseline four times and report it as four variants.

v0  the shipped prompt, unedited: the baseline every other variant is a delta
    against.
v1  the decision alone: is this input a unit, or a use of one? No criteria.
v2  v1 plus the test for unithood and the tie-break for picking a focus.
v3  v2 plus a ranked candidate list, which is what a chip row would be built
    from. One run then scores both designs: the top candidate is what would be
    carded automatically, the whole list is what a tap would choose from.
v4  v3 plus dropping modifiers and ranking the focus first. This is the wording
    that then shipped, which is why v0 builds it today.
v5  v4 plus the unit's surface in the input; v7 the same field worded to name
    only the unit's own words. Both add a field the shipped prompt no longer
    carries: it was measured, it bought nothing, and it was removed.
v6  the surface-free baseline both were measured against: the prompt as it then
    shipped, before the card catalogue joined it. The two numbers
    ``decision-phrases-and-sentences.md`` quotes for the card decision were
    taken under it — 89% of inflected units and 50% of fragments carded whole,
    over its 44 recorded answers. It is not rebuilt here and needs no delta:
    v0 is the shipped prompt, and what v6 asked survives in those answers.

v1-v4 no longer build. Every line they replace has since shipped, so their
anchors are not in the template any more, and reconstructing the wordings they
started from would be the hand-copying this delta form exists to avoid. They
are kept as the record of what was asked; ``build`` refuses them rather than
measuring the baseline under their name.
"""

# The echo rule, and the field description that repeats it. Both must move together:
# leaving either in place puts the prompt at war with itself.
_ECHO_ANCHOR = """Analyse EXACTLY the word given and do NOT substitute another. If it looks
like a typo, do not silently fix it:"""

_WORD_FIELD_ANCHOR = """word — the input word exactly as given (never corrected); suggestion — the
likely intended spelling of a typo, or an empty string."""

_JSON_ANCHOR = """{{"word": "...", "suggestion": "...",
 "meanings": ["""

_DECIDE = """The input is either one lexical unit, or a single unit shown with the
words around it. Decide which before you answer.
- If the input is one lexical unit — an idiom, a collocation, a phrasal or
  separable verb, a fixed expression — analyse it WHOLE. Never take it
  apart, and never analyse one of its words on its own.
- Otherwise the input is a use of one unit, given with its context.
  Analyse THAT unit, in the sense it carries here, and treat the rest of
  the input as context only.
The unit you analyse is the headword of the first line and the value of
the word field. Everything else in the answer is about that unit.
Do not substitute a different word. If it looks
like a typo, do not silently fix it:"""

_CRITERIA = """
The test for one unit: its meaning does not follow from its words taken
separately, or it is simply the fixed way the language says this. When the
test passes, the whole input is the unit — a verb's object, a preposition
the verb governs, an article inside a set phrase are PART of it, never
context around it. When in doubt, keep the input whole: a unit carded whole
is at worst too specific, while a unit taken apart is wrong.
When the test fails, find the focus: the one word or unit a learner would
have stopped at. Prefer the word carrying the meaning over grammar words;
prefer a word with several senses over a transparent one; never pick a
proper name, a number, or a word spelled nearly as in {target_lang}. If the
focus is a verb bound to a reflexive particle, a separable prefix or a
governed preposition, it is that whole verb in its dictionary form, never
the bare stem."""

_WORD_FIELD = """word — the unit you analysed, in the form a dictionary lists it and the way
it would be typed into a search box: letters, spaces, hyphens and
apostrophes only, in the same script as the input. It is the whole input
when the input was itself one unit, and the unit you found inside it
otherwise. suggestion — the
likely intended spelling of a typo, or an empty string."""

_CANDIDATES_JSON = """{{"word": "...", "suggestion": "...", "candidates": ["...", "..."],
 "meanings": ["""

_CANDIDATES_FIELD = """candidates — every unit of the input worth looking up on its own, most
useful first, at most three, each in the dictionary form the word field is
held to, and each able to stand as a headword alone. The first is always
identical to word. When the input was itself one unit, candidates holds
that one unit and nothing else.
"""

VARIANTS: dict[str, tuple[str, list[tuple[str, str]]]] = {
    "v0": ("shipped, unedited", []),
    "v1": (
        "decide unit vs use",
        [(_ECHO_ANCHOR, _DECIDE), (_WORD_FIELD_ANCHOR, _WORD_FIELD)],
    ),
    "v2": (
        "v1 + unithood test and focus tie-break",
        [(_ECHO_ANCHOR, _DECIDE + _CRITERIA), (_WORD_FIELD_ANCHOR, _WORD_FIELD)],
    ),
    "v3": (
        "v2 + ranked candidates",
        [
            (_ECHO_ANCHOR, _DECIDE + _CRITERIA),
            (_WORD_FIELD_ANCHOR, _WORD_FIELD + "\n" + _CANDIDATES_FIELD),
            (_JSON_ANCHOR, _CANDIDATES_JSON),
        ],
    ),
}

WITH_CANDIDATES = frozenset({"v3"})


def build(template: str, variant: str) -> str:
    """Apply one variant's edits, refusing to return a template an anchor missed."""
    if variant not in VARIANTS:
        raise SystemExit(f"unknown variant {variant!r} — expected one of {sorted(VARIANTS)}")
    text = template
    for anchor, replacement in VARIANTS[variant][1]:
        if anchor not in text:
            raise RuntimeError(f"{variant}: anchor did not match the shipped prompt:\n{anchor}")
        text = text.replace(anchor, replacement, 1)
    return text

# ---------------------------------------------------------------------------
# The running-text family.
#
# The sentence prompt already names the unit inside a text, and the sentence arm
# measured it at 100% surfaced. It cannot serve a fragment only because one line
# forbids the answer a fragment needs: the focus of "ist allein im Restaurant"
# IS a single ordinary word. These variants lift exactly that line and nothing
# else, which is the cheapest way to find out whether the capability was there
# the whole time.
# ---------------------------------------------------------------------------

_ORDINARY_ANCHOR = """A single ordinary word never
qualifies."""

_ORDINARY_ALLOWED = """A single ordinary word
qualifies only when the text is a fragment rather than a whole sentence and
that word is the one a learner would have stopped at; in a whole sentence it
never qualifies."""

TEXT_VARIANTS: dict[str, tuple[str, list[tuple[str, str]]]] = {
    "t0": ("shipped sentence prompt", []),
    "t1": ("sentence prompt, single ordinary word allowed in a fragment",
           [(_ORDINARY_ANCHOR, _ORDINARY_ALLOWED)]),
}


def build_text(template: str, variant: str) -> str:
    """Apply one running-text variant's edits, refusing a template an anchor missed."""
    if variant not in TEXT_VARIANTS:
        raise SystemExit(f"unknown variant {variant!r} — expected one of {sorted(TEXT_VARIANTS)}")
    text = template
    for anchor, replacement in TEXT_VARIANTS[variant][1]:
        if anchor not in text:
            raise RuntimeError(f"{variant}: anchor did not match the shipped prompt:\n{anchor}")
        text = text.replace(anchor, replacement, 1)
    return text

_NARROW = """
Give the SMALLEST form a dictionary would list on its own. A word that only
modifies is never part of the unit and is dropped, however natural it sounds
attached: degree adverbs and intensifiers, quantifiers, adverbs of time, and
an auxiliary carrying no meaning of its own. "very tired" is not a unit and
"tired" is; keep the modifier only when dropping it changes the meaning, as
in a set phrase whose parts have stopped meaning what they say."""

_RANK = """
Order them by what the learner most likely did not know and put that one
first. Never lead with the input restated."""

VARIANTS["v4"] = (
    "v3 + drop modifiers, rank the focus first",
    [
        (_ECHO_ANCHOR, _DECIDE + _CRITERIA + _NARROW),
        (_WORD_FIELD_ANCHOR, _WORD_FIELD + "\n" + _CANDIDATES_FIELD + _RANK.strip() + "\n"),
        (_JSON_ANCHOR, _CANDIDATES_JSON),
    ],
)
WITH_CANDIDATES = frozenset({"v3", "v4"})

TEXT_VARIANTS["t2"] = (
    "t1 + drop modifiers, rank the focus first",
    [(_ORDINARY_ANCHOR, _ORDINARY_ALLOWED + _NARROW + _RANK)],
)


# The surface field, which the shipped prompt no longer carries. v5 and v7 put it
# back, in the place and the wording it stood in, and differ from v0 and from each
# other in nothing else. What it is for: an inflected unit cannot echo its input,
# so the echo test calls it a fragment; surface says how much of the input the unit
# actually occupies, and the whole input means a unit.
_JSON_WITHOUT_SURFACE = """{{"word": "...", "suggestion": "...", "candidates": ["...", "..."],"""

_JSON_WITH_SURFACE = """{{"word": "...", "surface": "...", "suggestion": "...",
 "candidates": ["...", "..."],"""

_SUGGESTION_ANCHOR = """otherwise. suggestion — the"""

_SURFACE_LOOSE = """surface — the part of the input that unit occupies, copied from the input
exactly as it stands there, its words in the order they appear, and its
pieces joined by a space, an ellipsis character and a space when they stand
apart. It is the whole input, word for word, when the input was itself that
unit however it was inflected; it is only the part the unit occupies when
the rest of the input is context around it.
"""

# v7 says what v5 left the model free to ignore: which words of the input are NOT
# in the surface. v5 returned the whole input as the surface for four fragments
# out of five, including ones whose headword was a single word of it.
_SURFACE_STRICT = """surface — the words of the input that belong to the unit itself, copied from
the input in the order they appear and joined by a space, an ellipsis
character and a space wherever a word that is not part of the unit stands
between them. Every word of the input that is not part of the unit is left
out of it: a degree adverb or an intensifier, a quantifier, an adverb of
time, an auxiliary carrying no meaning of its own, anything you dropped when
you gave the dictionary form. The whole input goes here only when every one
of its words belongs to the unit; when the unit is one word of a longer
input, the surface is that one word.
"""


def _with_surface(field: str) -> list[tuple[str, str]]:
    return [
        (_JSON_WITHOUT_SURFACE, _JSON_WITH_SURFACE),
        (_SUGGESTION_ANCHOR, f"otherwise.\n{field}suggestion — the"),
    ]


VARIANTS["v5"] = ("v4 + the unit's surface in the input", _with_surface(_SURFACE_LOOSE))
VARIANTS["v7"] = (
    "v5 + the surface names only the unit's own words",
    _with_surface(_SURFACE_STRICT),
)
WITH_CANDIDATES = frozenset({"v3", "v4", "v5", "v6", "v7"})
