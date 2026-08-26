"""Fixtures for the unit-extraction arm: what a multi-word input should card.

Four classes, because the two error directions are not symmetric.

``UNITS``      the input is itself one lexical unit and must be carded whole.
               Splitting one — carding ``fahren`` out of ``Rad fahren`` — is the
               expensive error: the card looks right, so nothing catches it.
``INFLECTED``  the input is itself one lexical unit too, but typed in a form no
               dictionary lists — ``fährt Rad``. It must be carded whole exactly
               as ``UNITS`` is; what makes it its own class is that the headword
               cannot echo it, so an echo test reads it as a fragment. Its gate is
               therefore the card decision, not ``hit``: ``accepted`` names the
               dictionary form only so the report says whether the model
               lemmatised the headword, which is a separate question.
``FRAGMENTS``  the input is a *use* of a unit, typed with the words around it so
               the answer can address that sense. The focus has to be found.
``CLAUSES``    a short complete clause. Today it is carded whole, which the
               routing decision accepted as cheap. Its accepted answers are
               deliberately generous — the class exists to show whether
               extraction improves on a whole-clause card, not to settle a tie.
``CONTROLS``   ordinary single words. No variant may start touching these.

Each item is (text, accepted). ``accepted`` lists every extraction a human would
sign off on; an answer is a hit when it equals one of them after normalisation.
Nothing is matched by containment: ``fahren`` inside ``Rad fahren`` is precisely
the failure being measured, and a containment match would score it as success.

Every item stays inside the router's unit band (at most four words, no sentence
punctuation) so it actually reaches the vocabulary prompt in production. The two
five-word clauses are marked; they are here for the case where the band widens.
"""

# The input IS the unit. Splitting it is the expensive error.
UNITS: dict[str, list[tuple[str, tuple[str, ...]]]] = {
    "en": [
        ("give up", ("give up",)),
        ("put up with", ("put up with",)),
        ("break down", ("break down",)),
        ("look forward to", ("look forward to",)),
        ("get away with", ("get away with",)),
        ("spill the beans", ("spill the beans",)),
        ("under the weather", ("under the weather",)),
        ("bite the bullet", ("bite the bullet",)),
        ("by and large", ("by and large",)),
        ("once in a while", ("once in a while",)),
    ],
    "de": [
        ("Rad fahren", ("Rad fahren",)),
        ("eine Entscheidung treffen", ("eine Entscheidung treffen", "Entscheidung treffen")),
        ("zur Verfügung stehen", ("zur Verfügung stehen",)),
        ("in Betracht ziehen", ("in Betracht ziehen",)),
        ("eine Rolle spielen", ("eine Rolle spielen", "Rolle spielen")),
        ("Rücksicht nehmen", ("Rücksicht nehmen",)),
        ("Bescheid sagen", ("Bescheid sagen",)),
        ("Angst haben vor", ("Angst haben vor", "Angst haben")),
        ("auf jeden Fall", ("auf jeden Fall",)),
        ("unter vier Augen", ("unter vier Augen",)),
        ("von Zeit zu Zeit", ("von Zeit zu Zeit",)),
        ("meines Erachtens", ("meines Erachtens",)),
        ("nach wie vor", ("nach wie vor",)),
        ("in Frage kommen", ("in Frage kommen", "infrage kommen")),
        ("Guten Tag", ("Guten Tag", "guter Tag")),
        ("Auf Wiedersehen", ("Auf Wiedersehen",)),
    ],
    "sr": [
        ("voziti bicikl", ("voziti bicikl",)),
        ("донети одлуку", ("донети одлуку",)),
        ("imati pravo", ("imati pravo",)),
        ("водити рачуна", ("водити рачуна",)),
        ("igrati ulogu", ("igrati ulogu",)),
        ("обратити пажњу", ("обратити пажњу",)),
        ("ići pešice", ("ići pešice",)),
        ("држати реч", ("држати реч",)),
        ("у сваком случају", ("у сваком случају",)),
        ("на крају крајева", ("на крају крајева",)),
        ("с времена на време", ("с времена на време",)),
        ("у међувремену", ("у међувремену",)),
        ("Добар дан", ("Добар дан",)),
    ],
}

# The input is a USE of a unit. The focus has to be found and carded alone.
FRAGMENTS: dict[str, list[tuple[str, tuple[str, ...]]]] = {
    "en": [
        ("is completely exhausted today", ("exhausted",)),
        ("was rather reluctant about it", ("reluctant",)),
        ("turned out quite differently", ("turn out",)),
        ("seems fairly withdrawn lately", ("withdrawn",)),
        ("despite the heavy rain", ("despite",)),
        ("a remarkably shrewd move", ("shrewd",)),
    ],
    "de": [
        # The case that opened this: typed whole, but the word wanted was allein.
        ("ist allein im Restaurant", ("allein",)),
        ("wurde gestern entlassen", ("entlassen",)),
        ("ziemlich anstrengend heute", ("anstrengend",)),
        ("sehr schüchtern gewesen", ("schüchtern",)),
        ("äußerst gelungener Abend", ("gelungen",)),
        ("trotz des Regens gekommen", ("trotz",)),
        ("hat sich gestern beworben", ("sich bewerben", "bewerben")),
        ("völlig durcheinander gebracht", ("durcheinanderbringen", "durcheinander bringen")),
        ("kaum vorstellbar wirklich", ("vorstellbar",)),
        ("wirkt ziemlich verschlossen", ("verschlossen",)),
    ],
    "sr": [
        ("потпуно сам у соби", ("сам",)),
        ("веома уморан данас", ("уморан",)),
        ("изненада се појавио", ("појавити се",)),
        ("врло тешко разумљиво", ("разумљив", "разумљиво")),
        ("упркос киши дошао", ("упркос",)),
        ("nije se javio juče", ("javiti se",)),
        ("делује прилично затворено", ("затворен", "затворено")),
        ("био веома срамежљив", ("срамежљив",)),
    ],
}

# The input IS the unit, typed in a form other than the one a dictionary lists.
# The class the first sweep had no fixtures for: every UNITS item was handed over
# already lemmatised, so nothing measured what happens when the reader types the
# unit the way it stood in the text they met it in.
INFLECTED: dict[str, list[tuple[str, tuple[str, ...]]]] = {
    "en": [
        ("gave up", ("give up",)),
        ("broke down", ("break down",)),
        ("spilled the beans", ("spill the beans",)),
        ("bit the bullet", ("bite the bullet",)),
        ("looking forward to", ("look forward to",)),
        ("got away with", ("get away with",)),
    ],
    "de": [
        ("fährt Rad", ("Rad fahren",)),
        ("spielt eine Rolle", ("eine Rolle spielen", "Rolle spielen")),
        ("steht zur Verfügung", ("zur Verfügung stehen",)),
        ("nimmt Rücksicht", ("Rücksicht nehmen",)),
        ("kommt in Frage", ("in Frage kommen", "infrage kommen")),
        ("zog in Betracht", ("in Betracht ziehen",)),
        ("eine Entscheidung getroffen", ("eine Entscheidung treffen", "Entscheidung treffen")),
    ],
    "sr": [
        ("возим бицикл", ("возити бицикл",)),
        ("донео одлуку", ("донети одлуку",)),
        ("води рачуна", ("водити рачуна",)),
        ("обратио пажњу", ("обратити пажњу",)),
        ("пада ми на памет", ("пасти на памет", "падати на памет", "не падати на памет")),
        ("држи реч", ("држати реч",)),
        ("ide pešice", ("ići pešice",)),
    ],
}

# A short complete clause. Generous on purpose — this class reports, it does not decide.
CLAUSES: dict[str, list[tuple[str, tuple[str, ...]]]] = {
    "en": [
        ("I have no idea", ("have no idea", "no idea")),
        ("It is raining", ("rain",)),
    ],
    "de": [
        ("Ich habe keine Zeit", ("keine Zeit haben", "Zeit haben", "keine Zeit")),
        ("Es regnet", ("regnen",)),
        ("Ich weiß nicht", ("wissen",)),
        ("Das stimmt", ("stimmen",)),
        ("Sie kommt heute nicht", ("kommen",)),
        # Five words: past the router's band today, reachable only if it widens.
        ("Der Zug kommt zu spät", ("zu spät kommen", "zu spät")),
    ],
    "sr": [
        ("Пада киша", ("пада киша", "падати")),
        ("Не знам", ("знати",)),
        ("Немам времена за то", ("немати времена", "имати времена")),
        # Five words: past the router's band today, reachable only if it widens.
        ("Voz kasni pola sata", ("kasniti",)),
    ],
}

# Ordinary single words: no variant may start rewriting these.
CONTROLS: dict[str, list[tuple[str, tuple[str, ...]]]] = {
    "en": [("reluctant", ("reluctant",)), ("board", ("board",))],
    "de": [("allein", ("allein",)), ("Verantwortung", ("Verantwortung",))],
    "sr": [("уморан", ("уморан",)), ("одлука", ("одлука",))],
}

# The prefix and the reflexive particle are part of the word, not decoration on it.
# Every item names its trap: the bare root the narrowing rule might strip down to.
# The trap is always a real word of the language meaning something else, which is
# what makes the loss silent — the card still looks like a card.
MORPHOLOGY: dict[str, list[tuple[str, tuple[str, ...], tuple[str, ...]]]] = {
    "de": [
        # Separable prefix, stranded away from its verb in the surface.
        ("steht früh auf", ("aufstehen",), ("stehen",)),
        ("fällt heute aus", ("ausfallen",), ("fallen",)),
        ("ruft morgen an", ("anrufen",), ("rufen",)),
        ("gibt nie auf", ("aufgeben",), ("geben",)),
        ("kommt gut an", ("ankommen",), ("kommen",)),
        # Inseparable prefix; the bare root is a common verb with another meaning.
        ("wurde gestern entlassen", ("entlassen",), ("lassen",)),
        ("hat viel bekommen", ("bekommen",), ("kommen",)),
        ("kann gut verstehen", ("verstehen",), ("stehen",)),
        ("hat sich versprochen", ("sich versprechen", "versprechen"), ("sprechen",)),
        ("hat den Text übersetzt", ("übersetzen",), ("setzen",)),
        # The dictionary form itself: it must survive being handed over whole.
        ("sich bewerben", ("sich bewerben",), ("bewerben",)),
        ("aufstehen", ("aufstehen",), ("stehen",)),
    ],
    "sr": [
        # Reflexive particle; without it the verb exists and means something else.
        ("вратио се кући", ("вратити се",), ("вратити",)),
        ("сећа се свега", ("сећати се",), ("сећати",)),
        ("боји се мрака", ("бојати се",), ("бојати",)),
        ("смеје се гласно", ("смејати се",), ("смејати",)),
        ("догодило се јуче", ("догодити се",), ("догодити",)),
        ("nada se uspehu", ("nadati se",), ("nadati",)),
        # Prefix carrying the meaning.
        ("препознао га одмах", ("препознати",), ("познати",)),
        ("dogovorili su se", ("dogovoriti se",), ("govoriti", "dogovoriti")),
        # The dictionary form itself, handed over whole.
        ("појавити се", ("појавити се",), ("појавити",)),
        ("вратити се", ("вратити се",), ("вратити",)),
    ],
}

CLASSES: dict[str, dict[str, list[tuple]]] = {
    "units": UNITS,
    "inflected": INFLECTED,
    "fragments": FRAGMENTS,
    "clauses": CLAUSES,
    "controls": CONTROLS,
    "morphology": MORPHOLOGY,
}


def items(klass: str, lang: str) -> list[tuple[str, tuple[str, ...], tuple[str, ...]]]:
    """(text, accepted, traps) for one class and language; only morphology names traps."""
    return [(row[0], row[1], row[2] if len(row) > 2 else ()) for row in CLASSES[klass].get(lang, [])]

