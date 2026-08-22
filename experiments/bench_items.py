"""Fixed benchmark items for the M0 backend spike — ~40 per source language.

Each item is (word, shape). The shapes are the ones the prompt must handle:
common, rare, idiom (incl. phrasal/separable verbs), borrowed (etymology has
something to say), typo (a misspelling the answer must NOT silently fix), and
homonym (genuinely unrelated meanings -> several card meanings).

The Serbian set deliberately mixes Cyrillic and Latin: both are the language.
"""

ITEMS: dict[str, list[tuple[str, str]]] = {
    "en": [
        ("run", "common"),
        ("set", "common"),
        ("keep", "common"),
        ("light", "common"),
        ("way", "common"),
        ("draw", "common"),
        ("point", "common"),
        ("board", "common"),
        ("perfunctory", "rare"),
        ("recalcitrant", "rare"),
        ("quotidian", "rare"),
        ("pellucid", "rare"),
        ("obfuscate", "rare"),
        ("defenestration", "rare"),
        ("susurrus", "rare"),
        ("give up", "idiom"),
        ("put up with", "idiom"),
        ("break down", "idiom"),
        ("look forward to", "idiom"),
        ("get away with", "idiom"),
        ("spill the beans", "idiom"),
        ("under the weather", "idiom"),
        ("bite the bullet", "idiom"),
        ("kindergarten", "borrowed"),
        ("schadenfreude", "borrowed"),
        ("tsunami", "borrowed"),
        ("algebra", "borrowed"),
        ("sauna", "borrowed"),
        ("bungalow", "borrowed"),
        ("recieve", "typo"),
        ("definately", "typo"),
        ("occurence", "typo"),
        ("seperate", "typo"),
        ("acommodate", "typo"),
        ("bank", "homonym"),
        ("bat", "homonym"),
        ("spring", "homonym"),
        ("match", "homonym"),
        ("bark", "homonym"),
        ("seal", "homonym"),
    ],
    "de": [
        ("machen", "common"),
        ("Sache", "common"),
        ("Weg", "common"),
        ("stellen", "common"),
        ("gerade", "common"),
        ("Schluss", "common"),
        ("gern", "common"),
        ("sorgen", "common"),
        ("Fernweh", "rare"),
        ("Kummerspeck", "rare"),
        ("verschlimmbessern", "rare"),
        ("Backpfeifengesicht", "rare"),
        ("Torschlusspanik", "rare"),
        ("Sturheit", "rare"),
        ("aufgeben", "idiom"),
        ("sich freuen auf", "idiom"),
        ("Daumen drücken", "idiom"),
        ("die Nase voll haben", "idiom"),
        ("unter die Lupe nehmen", "idiom"),
        ("ins Fettnäpfchen treten", "idiom"),
        ("abhauen", "idiom"),
        ("vorkommen", "idiom"),
        ("Balkon", "borrowed"),
        ("Portemonnaie", "borrowed"),
        ("Keks", "borrowed"),
        ("Streik", "borrowed"),
        ("Chef", "borrowed"),
        ("Karussell", "borrowed"),
        ("Strase", "typo"),
        ("vieleicht", "typo"),
        ("seperat", "typo"),
        ("Standart", "typo"),
        ("wiederspiegeln", "typo"),
        ("Bank", "homonym"),
        ("Schloss", "homonym"),
        ("Ball", "homonym"),
        ("Kiefer", "homonym"),
        ("Gericht", "homonym"),
        ("Ton", "homonym"),
        ("Zug", "homonym"),
    ],
    "sr": [
        ("кућа", "common"),
        ("raditi", "common"),
        ("врата", "common"),
        ("dobar", "common"),
        ("рука", "common"),
        ("misliti", "common"),
        ("време", "common"),
        ("hteti", "common"),
        ("чежња", "rare"),
        ("инат", "rare"),
        ("мерак", "rare"),
        ("sevdah", "rare"),
        ("докон", "rare"),
        ("zlopamtilo", "rare"),
        ("не пада ми на памет", "idiom"),
        ("бацити копље у трње", "idiom"),
        ("имати путра на глави", "idiom"),
        ("gledati kroz prste", "idiom"),
        ("praviti se Englez", "idiom"),
        ("izbiti iz glave", "idiom"),
        ("од немила до недрага", "idiom"),
        ("trla baba lan", "idiom"),
        ("пенџер", "borrowed"),
        ("ćevap", "borrowed"),
        ("комшија", "borrowed"),
        ("džem", "borrowed"),
        ("мајстор", "borrowed"),
        ("sat", "borrowed"),
        ("izvinte", "typo"),
        ("мозда", "typo"),
        ("sumljiv", "typo"),
        ("podrska", "typo"),
        ("jel", "typo"),
        ("коса", "homonym"),
        ("лук", "homonym"),
        ("рок", "homonym"),
        ("чело", "homonym"),
        ("sto", "homonym"),
        ("град", "homonym"),
        ("para", "homonym"),
    ],
}


# ---------------------------------------------------------------------------
# Phrase and sentence mode (spec/decision-phrases-and-sentences.md, in progress)
# ---------------------------------------------------------------------------

"""Collocations that are NOT idioms.

The 160 multi-word runs already recorded in .bench are all idioms, so the shape
that motivated the feature — a plain collocation whose structure differs across
languages — was never measured. Russian "ездить на велосипеде" takes a
preposition; German and Serbian take a bare object, which is exactly why the
words cannot be looked up one at a time.
"""

COLLOCATIONS: dict[str, list[tuple[str, str]]] = {
    "de": [
        ("Rad fahren", "collocation"),
        ("eine Entscheidung treffen", "collocation"),
        ("Angst haben vor", "collocation"),
        ("zur Verfügung stehen", "collocation"),
        ("in Betracht ziehen", "collocation"),
        ("eine Rolle spielen", "collocation"),
        ("Rücksicht nehmen", "collocation"),
        ("Bescheid sagen", "collocation"),
    ],
    "sr": [
        ("voziti bicikl", "collocation"),
        ("донети одлуку", "collocation"),
        ("imati pravo", "collocation"),
        ("водити рачуна", "collocation"),
        ("igrati ulogu", "collocation"),
        ("обратити пажњу", "collocation"),
        ("ići pešice", "collocation"),
        ("држати реч", "collocation"),
    ],
}

"""Sentences, each with the units the segment list is expected to surface.

(text, expected, kind). ``expected`` is a tuple of alternative-spelling groups:
one group per unit that must be found, each group holding the spellings that
count as the same unit — which is how Serbian's two scripts are handled without
a transliterator. ``kind``:

    split   the unit is torn apart in the surface (separable prefix, reflexive
            clitic, negation) — the case the whole feature exists for
    phrase   the unit is contiguous but its citation form differs from the surface
    plain    no trap at all — the negative control: a segment list that fills up
             here is noise, not help
"""

SENTENCES: dict[str, list[tuple[str, tuple[tuple[str, ...], ...], str]]] = {
    "de": [
        ("Er steht jeden Morgen um sechs auf.", (("aufstehen",),), "split"),
        ("Ich freue mich schon sehr auf den Sommer.", (("sich freuen auf", "freuen auf"),), "split"),
        ("Sie sagt den Termin leider ab.", (("absagen",),), "split"),
        ("Wir nehmen den Vorschlag genau unter die Lupe.", (("unter die Lupe nehmen",),), "split"),
        ("Ich habe die Nase voll von diesem Lärm.", (("die Nase voll haben",),), "split"),
        ("Der Zug fällt heute wegen des Streiks aus.", (("ausfallen",),), "split"),
        ("Das kommt für mich überhaupt nicht in Frage.", (("in Frage kommen", "infrage kommen"),), "split"),
        ("Sie zieht nächste Woche nach Berlin um.", (("umziehen",),), "split"),
        ("Er hat mich gestern überhaupt nicht angerufen.", (("anrufen",),), "phrase"),
        ("Wir müssen uns auf das Wesentliche beschränken.", (("sich auf etwas beschränken", "sich beschränken auf", "beschränken auf"),), "phrase"),
        ("Heute ist das Wetter richtig schön.", (), "plain"),
    ],
    "sr": [
        ("Он се синоћ вратио кући веома касно.", (("вратити се", "vratiti se"),), "split"),
        ("Он ми се јуче јавио телефоном.", (("јавити се", "javiti se"),), "split"),
        ("Ona se svako jutro oblači vrlo brzo.", (("oblačiti se", "облачити се"),), "split"),
        ("Он се није ни најмање изненадио.", (("изненадити се", "iznenaditi se"),), "split"),
        ("Данас ми се уопште не иде на посао.", (("ићи се", "ide mi se", "иде ми се", "ići se"),), "split"),
        ("Ne bojim se više ničega.", (("bojati se", "бојати се"),), "phrase"),
        ("Nadam se da ćeš doći na vreme.", (("nadati se", "надати се"),), "phrase"),
        ("Deca se igraju napolju ceo dan.", (("igrati se", "играти се"),), "phrase"),
        ("Sve mi se čini da nešto nije u redu.", (("činiti se", "чинити се"), ("biti u redu", "u redu", "бити у реду")), "phrase"),
        ("Данас је лепо време.", (), "plain"),
    ],
}

"""Routing fixtures beyond what ITEMS/COLLOCATIONS/SENTENCES already label.

The adversarial middle: true clauses short enough to look like lexemes, and
fixed expressions long enough to look like clauses. ``truth`` is what the input
actually is, labelled honestly — the sweep then shows which side the heuristic
errs on and at what cost.
"""

ROUTING_EXTRA: dict[str, list[tuple[str, str]]] = {
    "de": [
        ("Es regnet", "sentence"),
        ("Ich weiß nicht", "sentence"),
        ("Das stimmt", "sentence"),
        ("Wie geht es dir?", "sentence"),
        ("Ich habe keine Zeit", "sentence"),
        ("Sie kommt heute nicht", "sentence"),
        ("Der Zug kommt zu spät", "sentence"),
        ("Das Wetter ist heute schön", "sentence"),
        ("Guten Tag", "lexeme"),
        ("Auf Wiedersehen", "lexeme"),
        ("Haus.", "lexeme"),
        ("meines Erachtens", "lexeme"),
        ("auf jeden Fall", "lexeme"),
        ("unter vier Augen", "lexeme"),
        ("von Zeit zu Zeit", "lexeme"),
    ],
    "sr": [
        ("Пада киша", "sentence"),
        ("Не знам", "sentence"),
        ("Тако је", "sentence"),
        ("Како си?", "sentence"),
        ("Не разумем шта кажеш", "sentence"),
        ("Немам времена за то", "sentence"),
        ("Voz kasni pola sata", "sentence"),
        ("Он данас не ради ништа", "sentence"),
        ("Добар дан", "lexeme"),
        ("Довиђења", "lexeme"),
        ("кућа.", "lexeme"),
        ("у сваком случају", "lexeme"),
        ("на крају крајева", "lexeme"),
        ("с времена на време", "lexeme"),
        ("у међувремену", "lexeme"),
    ],
}
