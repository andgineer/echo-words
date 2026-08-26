"""Fixtures for the context arm: does a context leave the word's other senses visible?

Three classes, because the question is not whether the model *can* read a context
but whether the senses survive being given one.

``PINS``          a word with several unrelated senses, submitted with a context
                  that selects exactly one of them. Several senses in the answer
                  is the feature working: the context is carded under the sense
                  it uses, and the others reach the reader as chips.
``ADDS_NOTHING``  a word with one everyday sense, submitted with an ordinary
                  sentence it happens to stand in. **The negative control.** One
                  sense in the answer is the context discarded and an ordinary
                  bare note made; several would card the context on everything
                  that arrives from the share sheet.
``EXPRESSION``    a set expression submitted with the text it came from. One unit
                  with one sense, so it should behave like ``adds_nothing``.
                  Several senses would mean the expression is being read as its
                  parts — worth knowing, but a different defect.

Each item is ``(word, context)``. The word is what a user submits — it stays
inside the router's unit band — and the context is the running text it was taken
from, which is what the share sheet and the suggested-unit tap both send.

The word stands in the context verbatim wherever a learner would meet it that
way, because a context the word is not literally in cannot be gapped and its
production card is dropped by a mechanical rule. The handful of inflected
occurrences are deliberate: they measure how often that rule fires on real text.

Nothing here is scored against an expected answer. What is scored is how many
senses the answer holds — a lexical fact, checkable against a dictionary — and,
reported beside it, whether the answer names which sense the context uses.
"""

# A polysemous word in a context that settles which sense is meant.
PINS: dict[str, list[tuple[str, str]]] = {
    "en": [
        ("bank", "We sat on the bank and watched the river go by."),
        ("bat", "A bat flew out of the cave just after sunset."),
        ("spring", "The water comes from a spring high in the hills."),
        ("charge", "The lawyer read out the charge against him."),
        ("draft", "There is a draft coming from under the door."),
        ("pitch", "She could not reach the high pitch in the second verse."),
        ("scale", "He removed every scale from the fish before cooking it."),
        ("volume", "The third volume is missing from the shelf."),
    ],
    "de": [
        ("Bank", "Wir saßen auf der Bank im Park und warteten."),
        ("Schloss", "Das Schloss an der Tür klemmt schon wieder."),
        ("Gericht", "Das Gericht schmeckte nach viel zu viel Salz."),
        ("Absatz", "Der Absatz meines rechten Schuhs ist abgebrochen."),
        ("Steuer", "Er saß am Steuer und fuhr sehr vorsichtig."),
        ("Ton", "Die kleine Figur ist aus rotem Ton gebrannt."),
        ("Kiefer", "Der Zahnarzt untersuchte den unteren Kiefer."),
        ("Zug", "Mit diesem Zug gewann er die ganze Partie."),
    ],
    "sr": [
        ("коса", "Њена коса је била сасвим мокра од кише."),
        ("језик", "Опекла је језик врелим чајем."),
        ("лист", "Са дрвета је пао један жут лист."),
        ("сат", "Сат на зиду је стао у три ујутру."),
        ("под", "Под у кухињи је од старог храста."),
        ("кључ", "Изгубио је кључ од стана негде у парку."),
        ("глава", "Прва глава ове књиге је најтежа."),
        ("кола", "Кола су се покварила на путу за море."),
    ],
}

# The negative control: one everyday sense, and a sentence that adds nothing to it.
ADDS_NOTHING: dict[str, list[tuple[str, str]]] = {
    "en": [
        ("elbow", "He hurt his elbow playing tennis on Sunday."),
        ("bicycle", "Her bicycle is still standing in front of the house."),
        ("kitchen", "The kitchen was painted white last summer."),
        ("umbrella", "Take an umbrella, it is going to rain."),
        ("passport", "I left my passport in the hotel safe."),
        ("neighbour", "Our neighbour is away for two weeks."),
        ("blanket", "She pulled the blanket over her shoulders."),
        ("carpet", "The carpet in the hallway needs cleaning."),
    ],
    "de": [
        ("Ellenbogen", "Er hat sich beim Tennis den Ellenbogen verletzt."),
        ("Fahrrad", "Ihr Fahrrad steht immer noch vor dem Haus."),
        ("Küche", "Die Küche wurde im Sommer weiß gestrichen."),
        ("Regenschirm", "Nimm einen Regenschirm mit, es regnet gleich."),
        ("Reisepass", "Ich habe meinen Reisepass im Hotelsafe gelassen."),
        ("Nachbar", "Unser Nachbar ist zwei Wochen verreist."),
        ("Decke", "Sie zog die Decke über die Schultern."),
        ("Teppich", "Der Teppich im Flur muss gereinigt werden."),
    ],
    "sr": [
        ("лакат", "Повредио је лакат играјући тенис у недељу."),
        ("бицикл", "Њен бицикл још увек стоји испред зграде."),
        ("кухиња", "Кухиња је прошлог лета окречена у бело."),
        ("кишобран", "Понеси кишобран, ускоро ће киша."),
        ("пасош", "Заборавио сам пасош у хотелском сефу."),
        ("комшија", "Наш комшија је отпутовао на две недеље."),
        ("ћебе", "Навукла је ћебе преко рамена."),
        ("тепих", "Тепих у ходнику треба очистити."),
    ],
}

# A set expression, submitted with the sentence it was read in.
EXPRESSION: dict[str, list[tuple[str, str]]] = {
    "en": [
        ("spill the beans", "He promised not to spill the beans about the party."),
        ("under the weather", "She is a bit under the weather and stayed home today."),
        ("break down", "The car chose to break down in the middle of nowhere."),
        ("put up with", "I cannot put up with the noise any longer."),
        ("bite the bullet", "We had to bite the bullet and pay the fine."),
        ("look forward to", "I look forward to hearing from you soon."),
        ("once in a while", "We meet for coffee once in a while."),
        ("get away with", "He always seems to get away with it."),
    ],
    "de": [
        ("Rad fahren", "Am Wochenende gehen wir im Park Rad fahren."),
        ("eine Entscheidung treffen", "Wir müssen bis Freitag eine Entscheidung treffen."),
        ("zur Verfügung stehen", "Ich werde Ihnen morgen zur Verfügung stehen."),
        ("in Betracht ziehen", "Wir sollten auch diese Möglichkeit in Betracht ziehen."),
        ("eine Rolle spielen", "Das Wetter wird morgen eine Rolle spielen."),
        ("unter vier Augen", "Wir sollten das lieber unter vier Augen besprechen."),
        ("auf jeden Fall", "Wir kommen auf jeden Fall zu deinem Geburtstag."),
        ("von Zeit zu Zeit", "Von Zeit zu Zeit ruft er noch an."),
    ],
    "sr": [
        ("донети одлуку", "Морамо донети одлуку до петка."),
        ("на крају крајева", "На крају крајева, то и није толико важно."),
        ("у сваком случају", "У сваком случају, јавићу ти сутра ујутру."),
        ("с времена на време", "С времена на време свратимо на кафу."),
        ("водити рачуна", "Морате водити рачуна о томе шта потписујете."),
        ("имати у виду", "Треба имати у виду и трошкове превоза."),
        ("бацити копље у трње", "Немој одмах бацити копље у трње."),
        ("у међувремену", "У међувремену, он је већ отишао."),
    ],
}

CLASSES: dict[str, dict[str, list[tuple[str, str]]]] = {
    "pins": PINS,
    "adds_nothing": ADDS_NOTHING,
    "expression": EXPRESSION,
}

# Pre-registered, and read as "at least". Below ``PINS_GATE`` the context is still
# suppressing the senses and the design does not work; below ``ADDS_NOTHING_GATE``
# the context gets carded on words that do not need it.
PINS_GATE = 0.80
ADDS_NOTHING_GATE = 0.80


def items(klass: str, lang: str) -> list[tuple[str, str]]:
    """(word, context) for one class and language."""
    return list(CLASSES[klass].get(lang, []))
