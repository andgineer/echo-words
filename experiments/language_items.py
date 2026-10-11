"""Typed input and the language its answer should name, fixed before the run.

`expected` is "source" for the tab's own language — any form, misspelling or national
standard of it, look-alikes included — "target" for the learner's own language typed
without "!", another language's ISO 639-1 code, or "either" where the input is genuinely
open, which counts neither way. The reading cases of the reverse lookup are asked here
too: the answer's language line replaced the reading question.
"""

from dataclasses import dataclass

from reverse_items import READING_CASES


@dataclass(frozen=True)
class LanguageCase:
    case_id: str
    lang: str
    text: str
    expected: str
    note: str = ""
    target: str = "Russian"


_FROM_READING = {"not": "source", "target": "target", "either": "either"}

LANGUAGE_CASES = (
    *(
        LanguageCase(f"{case.case_id}", case.lang, case.word, _FROM_READING[case.expected], case.note, case.target)
        for case in READING_CASES
    ),
    # Another language the learner has a tab for: the app switches to it.
    LanguageCase("umziehen-sentence", "en", "Du ziehst in eine neue Wohnung um", "de", "the reported case"),
    LanguageCase("umziehen", "en", "umziehen", "de"),
    LanguageCase("miete", "en", "Wann muss ich die Miete bezahlen", "de"),
    LanguageCase("telefon-sr", "en", "Da li si video moj telefon", "sr", "Serbian in Latin"),
    LanguageCase("kuca-on-en", "en", "kuća", "sr"),
    LanguageCase("all-day", "de", "Where have you been all day", "en"),
    LanguageCase("breakfast", "de", "breakfast", "en"),
    LanguageCase("hvala-lepo", "de", "Hvala lepo", "sr"),
    LanguageCase("dont-know", "sr", "I don't know what to do", "en"),
    LanguageCase("wohnung", "sr", "Wohnung", "de"),
    LanguageCase("weiss-nicht", "sr", "Ich weiß es nicht", "de"),
    # A language no tab teaches: translated, nothing carded.
    LanguageCase("je-ne-sais", "en", "Je ne sais pas", "fr"),
    LanguageCase("bonjour", "en", "bonjour", "fr"),
    LanguageCase("dove-sei", "en", "Dove sei stato ieri", "it"),
    LanguageCase("merci", "de", "Merci beaucoup", "fr"),
    LanguageCase("gracias", "de", "Gracias por todo", "es"),
    LanguageCase("dziekuje", "sr", "Dziękuję bardzo", "pl"),
    # The tab's own language, however it looks.
    LanguageCase("sto-radis", "sr", "Što radiš danas", "source", "Croatian standard"),
    LanguageCase("kruh", "sr", "kruh", "source", "Croatian standard"),
    LanguageCase("tjedan", "sr", "tjedan", "source", "Croatian standard"),
    LanguageCase("vikend", "sr", "vikend", "source", "loanword"),
    LanguageCase("kindergarten-en", "en", "a Kindergarten teacher", "source", "German loanword in English"),
    LanguageCase("gift-en", "en", "Gift", "source", "English; German poison"),
    LanguageCase("angst-en", "en", "angst", "source", "German loanword in English"),
    LanguageCase("deja-vu", "en", "déjà vu", "source", "French loanword in English"),
    LanguageCase("rucksack", "en", "rucksack", "source", "German loanword in English"),
    LanguageCase("meeting-de", "de", "Das Meeting ist heute", "source", "English loanword in German"),
    LanguageCase("hand-de", "de", "Hand", "source", "German and English alike"),
    LanguageCase("computer-de", "de", "Computer", "source", "English loanword in German"),
    LanguageCase("gift-de", "de", "Gift", "source", "German poison; English present"),
)
