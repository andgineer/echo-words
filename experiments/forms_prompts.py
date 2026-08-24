"""The forms-table prompt, as a delta against the shipped vocabulary prompt.

f0  shipped, unedited. It forbids tables outright and puts the part of speech in
    front of every translation, so it is the floor for both things being changed.
f1  the meaning first and bare, no part of speech anywhere, and a forms table
    whose cells are live phrases rather than grammatical labels.

Held as edits for the same reason the extraction variants are: everything
outside the delta is provably identical, so a difference in the numbers can only
come from the rule that changed. ``build`` raises when an anchor misses.
"""

_SECTIONS_ANCHOR = """1. First line: the word being analysed, in bold.
2. Translations, most frequent in everyday speech first; each with its
   part of speech and a register mark (colloquial, formal, slang, vulgar
   and so on) where it matters.
3. Usage: typical collocations and prepositions, what it is confused
   with; countability and irregular forms where they matter.
4. Origin: if the word was borrowed, 1-3 sentences on which language it
   came from and how it travelled; for a native word, one line.
5. Examples: 2-4 short everyday sentences, each followed by its translation."""

_SECTIONS = """1. First line: the word being analysed, in bold.
2. The translations, and nothing in front of them. Most frequent in
   everyday speech first. NEVER name the part of speech — not here, not
   anywhere in the answer. A register mark (colloquial, formal, slang,
   vulgar) goes AFTER the translation it belongs to, and only where it
   changes how the word is used.
3. Forms — ONLY when this word actually changes shape in a way a learner
   has to recognise or produce. When it does not, skip this section
   completely and say nothing about it at all. When it does, give a table
   of at most six rows: first cell a short everyday phrase in
   {source_lang} using the form, second cell that phrase in {target_lang}.
   The phrases carry the grammar, so name no person, number, gender, case
   or tense anywhere in the table — no labels, no abbreviations. Choose
   the forms that are irregular or that learners get wrong; leave out
   whatever follows the regular pattern. {forms_hint}
4. Usage: typical collocations and prepositions, what it is confused
   with; countability where it matters.
5. Origin: if the word was borrowed, 1-3 sentences on which language it
   came from and how it travelled; for a native word, one line.
6. Examples: 2-4 short everyday sentences, each followed by its translation."""

_EMPHASIS_ANCHOR = """ALL EMPHASIS IS HTML. Use exactly two tags and no others: <b> around the
headword, <i> around the {source_lang} example sentences and any
{source_lang} form quoted inside the text. Emphasis punctuation of any
kind is forbidden — no markdown, no headings, no bullet markers, no
tables, no code fences."""

_EMPHASIS = """ALL EMPHASIS IS HTML. Use these tags and no others: <b> around the
headword, <i> around the {source_lang} example sentences and any
{source_lang} form quoted inside the text, and <table>, <tr> and <td> for
the forms section and nowhere else. No attributes on any tag. Emphasis
punctuation of any kind is forbidden — no markdown, no headings, no
bullet markers, no code fences."""

VARIANTS: dict[str, tuple[str, list[tuple[str, str]]]] = {
    "f0": ("shipped: part of speech in front, tables forbidden", []),
    "f1": ("meaning first, no part of speech, forms table of live phrases",
           [(_SECTIONS_ANCHOR, _SECTIONS), (_EMPHASIS_ANCHOR, _EMPHASIS)]),
}


def build(template: str, variant: str) -> str:
    if variant not in VARIANTS:
        raise SystemExit(f"unknown variant {variant!r} — expected one of {sorted(VARIANTS)}")
    text = template
    for anchor, replacement in VARIANTS[variant][1]:
        if anchor not in text:
            raise RuntimeError(f"{variant}: anchor did not match the shipped prompt:\n{anchor}")
        text = text.replace(anchor, replacement, 1)
    return text


# Two seams f1 left open, measured: a gender note leaked onto a line just above
# the table ("Мужской род."), which the rule only forbade *inside* it; and one
# invariable word still got a table, so the negative control was not absolute.
_SECTIONS_F2 = _SECTIONS.replace(
    """3. Forms — ONLY when this word actually changes shape in a way a learner
   has to recognise or produce. When it does not, skip this section
   completely and say nothing about it at all. When it does, give a table
   of at most six rows: first cell a short everyday phrase in
   {source_lang} using the form, second cell that phrase in {target_lang}.
   The phrases carry the grammar, so name no person, number, gender, case
   or tense anywhere in the table — no labels, no abbreviations.""",
    """3. Forms — ONLY when this word actually changes shape in a way a learner
   has to recognise or produce. An adverb, a preposition, a particle, an
   invariable word and a fixed expression have none: for those, skip this
   section completely — no table, no heading, no remark about forms
   anywhere in the answer. When the word does change, give a table of at
   most six rows: first cell a short everyday phrase in {source_lang}
   using the form, second cell that phrase in {target_lang}.
   The phrases carry the grammar, so name no person, number, gender, case
   or tense — not inside the table, not on a line above or below it, not
   anywhere near it. No labels, no abbreviations, no gender note.""",
)

VARIANTS["f2"] = (
    "f1 + no grammar labels around the table, harder negative control",
    [(_SECTIONS_ANCHOR, _SECTIONS_F2), (_EMPHASIS_ANCHOR, _EMPHASIS)],
)
