"""Fixtures for the forms-table arm: does the table appear, and is it right?

A conjugation table is checkable content, which is what makes it worth a bench
and what makes it dangerous: a wrong past participle reads exactly as
authoritative as a right one, and the reader who could tell would not have
asked. So each item names both sides.

``required``  forms the table must contain. Only the discriminating ones — the
              stem changes, the irregular pasts, the suppletive plurals. A form
              a learner could have guessed proves nothing about the model.
``traps``     forms that must NEVER appear: the regularised shapes the model
              invents when it does not know (``bekommte``, ``childs``,
              ``човеци``). A trap hit is the expensive failure.
``NOTHING``   words with no paradigm worth showing. The table must be absent
              entirely — the negative control, the same discipline the sentence
              arm's trap-free fixtures serve.

Matching is by whole word inside the table region only, so prose elsewhere in
the answer cannot satisfy a requirement or trip a trap.
"""

FORMS: dict[str, list[tuple[str, tuple[str, ...], tuple[str, ...]]]] = {
    "de": [
        # Only the discriminating forms are required. A regular first person
        # ("ich nehme") proves nothing and penalises the answer that showed the
        # stem change instead ("er nimmt"), which is the better table.
        ("aufstehen", ("steht", "stand", "aufgestanden"), ("aufgestehen", "gestanden")),
        ("bekommen", ("bekam",), ("bekommte", "gebekommen")),
        ("nehmen", ("nimmt", "nahm", "genommen"), ("nehmte", "genehmt")),
        ("denken", ("dachte", "gedacht"), ("denkte", "gedenkt")),
        ("fahren", ("fährt", "fuhr", "gefahren"), ("fahrte", "gefahrt")),
        ("wissen", ("weiß", "wusste", "gewusst"), ("gewisst", "wisste")),
        ("sein", ("bin", "ist", "war", "gewesen"), ("seinte", "geseint")),
        # Nouns: the nominative article carries the gender, the plural is the trap.
        # Only nominative-position errors are traps — German case syncretism makes
        # a bare "der Verantwortung" a legitimate genitive, not a mistake.
        ("Verantwortung", ("die Verantwortung",), ("das Verantwortung", "ein Verantwortung")),
        ("Buch", ("das Buch", "Bücher"), ("die Buch", "der Buch", "Buchen")),
        ("Mann", ("der Mann", "Männer"), ("die Mann", "das Mann")),
    ],
    "en": [
        ("withdraw", ("withdrew", "withdrawn"), ("withdrawed",)),
        ("bring", ("brought",), ("bringed", "brang")),
        ("teach", ("taught",), ("teached",)),
        ("go", ("went", "gone"), ("goed",)),
        ("child", ("children",), ("childs",)),
        ("foot", ("feet",), ("foots",)),
    ],
    "sr": [
        ("писати", ("пишем",), ("писам",)),
        ("ићи", ("идем", "ишао"), ("ићим", "ићао")),
        ("моћи", ("могу", "може"), ("моћим",)),
        ("вратити", ("вратио",), ("вратијем",)),
        ("човек", ("људи",), ("човеци", "човекови")),
        ("одлука", ("одлуке",), ("одлукови",)),
    ],
}

# No paradigm worth a table. Its absence is the result.
NOTHING: dict[str, list[tuple[str, tuple[str, ...], tuple[str, ...]]]] = {
    "de": [("vorgestern", (), ()), ("sehr", (), ()), ("unter vier Augen", (), ())],
    "en": [("very", (), ()), ("by and large", (), ())],
    "sr": [("веома", (), ()), ("на крају крајева", (), ())],
}

CLASSES: dict[str, dict[str, list[tuple]]] = {"forms": FORMS, "nothing": NOTHING}

# What counts as a form worth showing differs by language; the shipped
# languages.toml already carries this kind of instruction per language.
FORMS_HINTS = {
    "de": (
        "For a verb: the present forms whose stem changes, the simple past, and "
        "the perfect. For a noun: an article showing its gender, and the plural. "
        "For an adjective: the comparative when it is irregular."
    ),
    "en": (
        "For an irregular verb: the past and the past participle. For an "
        "irregular noun: the plural. Skip anything that just takes -ed or -s."
    ),
    "sr": (
        "For a verb: the present forms whose stem changes, the l-participle, and "
        "the aspect partner. For a noun: the plural, and the gender where the "
        "ending does not give it away."
    ),
}


def items(klass: str, lang: str) -> list[tuple[str, tuple[str, ...], tuple[str, ...]]]:
    return list(CLASSES[klass].get(lang, []))
