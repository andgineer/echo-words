"""Fixtures for the reverse lookup: a Russian wording carded as its source-language word.

Fixed before the run. Each wording is asked into English, German and Serbian unless
its case names fewer. Accepted first equivalents are written as `normalize` folds
them, so Serbian is listed in Latin and matches either script.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ReverseCase:
    case_id: str
    requirement: str
    word: str
    verdict: str = "word"
    langs: tuple[str, ...] = ("en", "de", "sr")
    # The readings the requirement accepts, where it is about the reading at all.
    read_as: tuple[str, ...] = ()
    # The first equivalents accepted per language, where one meaning clearly leads.
    first: dict[str, tuple[str, ...]] = field(default_factory=dict)
    must_hold: str = ""


_TABLE = {"en": ("table",), "de": ("tisch",), "sr": ("sto",)}
_KEY = {"en": ("key",), "de": ("schlüssel",), "sr": ("ključ",)}

REVERSE_CASES = (
    ReverseCase(
        "stol",
        "one clear meaning",
        "стол",
        first=_TABLE,
        must_hold="the word for the piece of furniture",
    ),
    ReverseCase(
        "okno",
        "one clear meaning",
        "окно",
        first={"en": ("window",), "de": ("fenster",), "sr": ("prozor",)},
        must_hold="the word for a window",
    ),
    ReverseCase(
        "sobaka",
        "one clear meaning",
        "собака",
        first={"en": ("dog",), "de": ("hund",), "sr": ("pas", "kuče")},
        must_hold="the word for a dog",
    ),
    ReverseCase(
        "klyuch",
        "several meanings",
        "ключ",
        first=_KEY,
        must_hold=(
            "the key that opens a lock first; a spring, a wrench or a clef only after "
            "it, each example in its own meaning"
        ),
    ),
    ReverseCase(
        "kosa",
        "several meanings",
        "коса",
        must_hold=(
            "the commonest meaning first (a braid of hair), then the scythe and the spit "
            "of land, each example in its own meaning"
        ),
    ),
    ReverseCase(
        "luk",
        "several meanings",
        "лук",
        first={"en": ("onion",), "de": ("zwiebel",), "sr": ("luk",)},
        must_hold="the onion first, the bow after it, each example in its own meaning",
    ),
    ReverseCase(
        "mir",
        "several meanings",
        "мир",
        must_hold="the world and peace as separate equivalents, each example in its own meaning",
    ),
    ReverseCase(
        "stoly",
        "inflected form",
        "столы",
        read_as=("стол",),
        first=_TABLE,
        must_hold="read as the dictionary form стол and carded as its word",
    ),
    ReverseCase(
        "klyuchey",
        "inflected form",
        "ключей",
        read_as=("ключ",),
        first=_KEY,
        must_hold="read as the dictionary form ключ and carded as its word",
    ),
    ReverseCase(
        "v-kontse-kontsov",
        "expression",
        "в конце концов",
        must_hold="an equivalent expression (after all, in the end), not a word-for-word one",
    ),
    ReverseCase(
        "slomya-golovu",
        "expression",
        "сломя голову",
        must_hold="an equivalent expression (headlong, at breakneck speed), not a word-for-word one",
    ),
    ReverseCase(
        "toska",
        "no direct equivalent",
        "тоска",
        must_hold="a close word speakers use (longing, yearning, melancholy), not an invention",
    ),
    ReverseCase(
        "avos",
        "no direct equivalent",
        "авось",
        must_hold=(
            "a close word or expression speakers use (maybe, on the off chance, hoping "
            "it works out), not an invention"
        ),
    ),
    ReverseCase(
        "sotl",
        "misspelling",
        "сотл",
        read_as=("стол",),
        first=_TABLE,
        must_hold="read as стол and carded as its word",
    ),
    ReverseCase(
        "fyvapr",
        "not a word",
        "фывапр",
        verdict="not_a_word",
        must_hold="not_a_word: a row of the Russian keyboard",
    ),
    ReverseCase(
        "ya-idu-domoy",
        "sentence",
        "я иду домой",
        verdict="sentence",
        must_hold="sentence: a clause with its own subject and finite verb",
    ),
    ReverseCase(
        "yosh",
        "Russian-keyboard Serbian",
        "йош",
        verdict="not_a_word",
        langs=("sr",),
        must_hold=(
            "not_a_word: Serbian још typed on a Russian keyboard, which the letter rule "
            "then hands to the Serbian article"
        ),
    ),
    ReverseCase(
        "moya",
        "Russian-keyboard Serbian",
        "моя",
        langs=("sr",),
        read_as=("мой", "моя"),
        first={"sr": ("moja", "moj")},
        must_hold="a Russian word, carded as its Serbian equivalent моја",
    ),
)

# Russian words the Serbian Cyrillic letters leave open: the only ones a refusal on the
# Serbian tab can offer the reverse lookup for.
OFFER_WORDS = (
    ("gorod", "город"),
    ("kniga", "книга"),
    ("devushka", "девушка"),
    ("sobaka", "собака"),
)
