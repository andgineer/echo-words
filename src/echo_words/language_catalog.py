"""The reference table of languages that can be studied, searched by the editor.

The reader picks a language from here instead of naming one. Both fields they
would otherwise have typed are load-bearing and unfixable afterwards: the code
addresses Wikipedia, Wiktionary, the audio cache and the per-language word
tables, and the name is what the prompt calls the source language. Neither is a
free-text box.

Only Latin- and Cyrillic-script languages are listed, because those are the
scripts the input validator can check (``languages._ALLOWED_SCRIPTS``); a
language whose writing it cannot read would refuse every word submitted to it.

``name`` is the endonym, which is what reaches the prompt and labels the
language button. ``english`` names the Anki deck, following the decks already in
use. ``russian`` exists so the search answers the interface's other language.
"""

from dataclasses import dataclass

_LATIN = "latin"
_CYRILLIC = "cyrillic"
_BOTH = "latin+cyrillic"

# What has been measured about the model's answers in a language. VOUCHED is the three
# the bench is built on; UNRELIABLE is where a fresh review read the answers and refused
# them; the rest is nobody having looked (spec/decision-llm-backend.md).
VOUCHED = "vouched"
UNRELIABLE = "unreliable"
UNMEASURED = "unmeasured"


@dataclass(frozen=True)
class CatalogLanguage:
    code: str
    name: str
    english: str
    russian: str
    script: str
    # The Wikimedia Commons file-name prefix of this language's recordings, which
    # is also the accent they are spoken in; none where Commons carries too few.
    recordings: str | None = None
    # Piper voices this language not at all: either its directory holds nothing, or
    # the model listed under this code speaks another language (spec/decision-tts.md).
    piper_unusable: bool = False
    # The reader cannot tell a fluent invention from an answer, so the editor says what
    # is known about this language's answers instead of leaving the row to imply it.
    answers: str = UNMEASURED

    @property
    def deck(self) -> str:
        return f"EchoWords: {self.english}"


CATALOG: tuple[CatalogLanguage, ...] = (
    CatalogLanguage("af", "Afrikaans", "Afrikaans", "африкаанс", _LATIN),
    CatalogLanguage("sq", "Shqip", "Albanian", "албанский", _LATIN),
    CatalogLanguage("az", "Azərbaycan dili", "Azerbaijani", "азербайджанский", _LATIN),
    CatalogLanguage("eu", "Euskara", "Basque", "баскский", _LATIN),
    CatalogLanguage("be", "Беларуская", "Belarusian", "белорусский", _CYRILLIC),
    CatalogLanguage("bs", "Bosanski", "Bosnian", "боснийский", _LATIN),
    CatalogLanguage("bg", "Български", "Bulgarian", "болгарский", _CYRILLIC, answers=UNRELIABLE),
    CatalogLanguage("ca", "Català", "Catalan", "каталанский", _LATIN),
    CatalogLanguage("hr", "Hrvatski", "Croatian", "хорватский", _LATIN, piper_unusable=True),
    CatalogLanguage("cs", "Čeština", "Czech", "чешский", _LATIN),
    CatalogLanguage("da", "Dansk", "Danish", "датский", _LATIN),
    CatalogLanguage("nl", "Nederlands", "Dutch", "нидерландский", _LATIN),
    CatalogLanguage(
        "en",
        "English",
        "English",
        "английский",
        _LATIN,
        recordings="En-us",
        answers=VOUCHED,
    ),
    CatalogLanguage("eo", "Esperanto", "Esperanto", "эсперанто", _LATIN),
    CatalogLanguage("et", "Eesti", "Estonian", "эстонский", _LATIN),
    CatalogLanguage("fi", "Suomi", "Finnish", "финский", _LATIN),
    CatalogLanguage("fr", "Français", "French", "французский", _LATIN, recordings="Fr"),
    CatalogLanguage("gl", "Galego", "Galician", "галисийский", _LATIN),
    CatalogLanguage(
        "de",
        "Deutsch",
        "German",
        "немецкий",
        _LATIN,
        recordings="De",
        answers=VOUCHED,
    ),
    CatalogLanguage("hu", "Magyar", "Hungarian", "венгерский", _LATIN),
    CatalogLanguage("is", "Íslenska", "Icelandic", "исландский", _LATIN),
    CatalogLanguage("id", "Bahasa Indonesia", "Indonesian", "индонезийский", _LATIN),
    CatalogLanguage("ga", "Gaeilge", "Irish", "ирландский", _LATIN),
    CatalogLanguage("it", "Italiano", "Italian", "итальянский", _LATIN, recordings="It"),
    CatalogLanguage("kk", "Қазақ тілі", "Kazakh", "казахский", _CYRILLIC),
    CatalogLanguage("ky", "Кыргызча", "Kyrgyz", "киргизский", _CYRILLIC),
    CatalogLanguage("la", "Latina", "Latin", "латинский", _LATIN),
    CatalogLanguage("lv", "Latviešu", "Latvian", "латышский", _LATIN),
    CatalogLanguage("lt", "Lietuvių", "Lithuanian", "литовский", _LATIN),
    CatalogLanguage("mk", "Македонски", "Macedonian", "македонский", _CYRILLIC),
    CatalogLanguage("ms", "Bahasa Melayu", "Malay", "малайский", _LATIN),
    CatalogLanguage("mn", "Монгол", "Mongolian", "монгольский", _CYRILLIC),
    CatalogLanguage("no", "Norsk", "Norwegian", "норвежский", _LATIN),
    CatalogLanguage("pl", "Polski", "Polish", "польский", _LATIN),
    CatalogLanguage("pt", "Português", "Portuguese", "португальский", _LATIN, recordings="Pt"),
    CatalogLanguage("ro", "Română", "Romanian", "румынский", _LATIN),
    CatalogLanguage("ru", "Русский", "Russian", "русский", _CYRILLIC, recordings="Ru"),
    CatalogLanguage(
        "sr",
        "Српски",
        "Serbian",
        "сербский",
        _BOTH,
        piper_unusable=True,
        answers=VOUCHED,
    ),
    CatalogLanguage("sk", "Slovenčina", "Slovak", "словацкий", _LATIN),
    CatalogLanguage("sl", "Slovenščina", "Slovene", "словенский", _LATIN),
    CatalogLanguage("es", "Español", "Spanish", "испанский", _LATIN, recordings="Es"),
    CatalogLanguage("sw", "Kiswahili", "Swahili", "суахили", _LATIN),
    CatalogLanguage("sv", "Svenska", "Swedish", "шведский", _LATIN),
    CatalogLanguage("tg", "Тоҷикӣ", "Tajik", "таджикский", _CYRILLIC),
    CatalogLanguage("tt", "Татарча", "Tatar", "татарский", _CYRILLIC),
    CatalogLanguage("tr", "Türkçe", "Turkish", "турецкий", _LATIN, recordings="Tr"),
    CatalogLanguage("uk", "Українська", "Ukrainian", "украинский", _CYRILLIC, answers=UNRELIABLE),
    CatalogLanguage("uz", "Oʻzbekcha", "Uzbek", "узбекский", _LATIN),
    CatalogLanguage("vi", "Tiếng Việt", "Vietnamese", "вьетнамский", _LATIN),
    CatalogLanguage("cy", "Cymraeg", "Welsh", "валлийский", _LATIN),
)

BY_CODE: dict[str, CatalogLanguage] = {entry.code: entry for entry in CATALOG}


def catalog_language(code: str) -> CatalogLanguage | None:
    return BY_CODE.get(code)


# Every spelling a language answers to: its code, its endonym and both names the
# interface has for it. The target language is configured as one of these.
BY_NAME: dict[str, CatalogLanguage] = {
    spelling.casefold(): entry
    for entry in reversed(CATALOG)
    for spelling in (entry.code, entry.name, entry.english, entry.russian)
}


def catalog_language_named(name: str) -> CatalogLanguage | None:
    return BY_NAME.get(name.strip().casefold())
