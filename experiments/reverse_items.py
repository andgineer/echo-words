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
    # Another verdict that ends with the reader on the right word just the same.
    also: tuple[str, ...] = ()
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
        read_as=("в конце концов",),
        must_hold="an equivalent expression (after all, in the end), not a word-for-word one",
    ),
    ReverseCase(
        "slomya-golovu",
        "expression",
        "сломя голову",
        read_as=("сломя голову",),
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
        "sabaka",
        "misspelling",
        "сабака",
        read_as=("собака",),
        first={"en": ("dog",), "de": ("hund",), "sr": ("pas", "kuče")},
        must_hold="read as собака and carded as its word",
    ),
    ReverseCase(
        "klyuch-soft",
        "misspelling",
        "ключь",
        read_as=("ключ",),
        first=_KEY,
        must_hold="read as ключ and carded as its word",
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
        also=("not_a_word",),
        must_hold=(
            "either the Russian word carded as its Serbian equivalent мој or моја, or "
            "not_a_word, which hands моја typed on a Russian keyboard to the Serbian "
            "article: both leave the reader on the right word"
        ),
    ),
    ReverseCase(
        "yedan",
        "Russian-keyboard Serbian",
        "йедан",
        verdict="not_a_word",
        langs=("sr",),
        must_hold="not_a_word: Serbian један typed on a Russian keyboard",
    ),
    ReverseCase(
        "nyega",
        "Russian-keyboard Serbian",
        "ньега",
        verdict="not_a_word",
        langs=("sr",),
        must_hold="not_a_word: Serbian њега typed on a Russian keyboard",
    ),
    ReverseCase(
        "moye",
        "Russian-keyboard Serbian",
        "мойе",
        verdict="not_a_word",
        langs=("sr",),
        must_hold="not_a_word: Serbian моје typed on a Russian keyboard",
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


@dataclass(frozen=True)
class ReadingCase:
    """Input typed without "!" where the tab's and the target's alphabets overlap.

    Only these reach the model: an alphabet the tab writes and the target does not, or
    the reverse, decides by itself. `target` is plainly target-language wording the
    learner meant to reverse; `not` is the tab's own wording, a form or a misspelling of
    it, look-alikes included; `either` is genuinely open and counts neither way.
    """

    case_id: str
    lang: str
    word: str
    expected: str
    note: str = ""
    target: str = "Russian"


READING_CASES = (
    # The Serbian tab and a Russian target share Cyrillic.
    ReadingCase("pas", "sr", "пас", "not", "dog"),
    ReadingCase("kuca", "sr", "кућа", "not", "house"),
    ReadingCase("grad", "sr", "град", "not", "city; Russian hail"),
    ReadingCase("kosa", "sr", "коса", "not", "hair, scythe; Russian braid, scythe"),
    ReadingCase("voda", "sr", "вода", "not", "water, shared"),
    ReadingCase("sto", "sr", "сто", "not", "table, hundred; Russian hundred"),
    ReadingCase("zivot", "sr", "живот", "not", "life; Russian belly"),
    ReadingCase("pravo", "sr", "право", "not", "right, straight; shared"),
    ReadingCase("hvala", "sr", "хвала", "not", "thanks"),
    ReadingCase("mozda", "sr", "мозда", "not", "можда misspelled"),
    ReadingCase("na-kraju", "sr", "на крају крајева", "not", "after all"),
    ReadingCase("stol", "sr", "стол", "not", "Croatian and Bosnian table, archaic Serbian throne"),
    ReadingCase("kniga", "sr", "книга", "either", "Russian book; књига misspelled"),
    ReadingCase("yosh", "sr", "йош", "not", "још on a Russian keyboard"),
    ReadingCase("devoyka", "sr", "девойка", "not", "девојка on a Russian keyboard"),
    ReadingCase("kniga-soft", "sr", "кньига", "not", "књига on a Russian keyboard"),
    ReadingCase("lyubav", "sr", "льубав", "not", "љубав on a Russian keyboard"),
    ReadingCase("noch", "sr", "ноч", "not", "ноћ on a Russian keyboard; Russian is ночь"),
    ReadingCase("dzhep", "sr", "джеп", "not", "џеп on a Russian keyboard"),
    ReadingCase("moy", "sr", "мой", "either", "мој on a Russian keyboard; Russian my"),
    ReadingCase("lyudi", "sr", "люди", "either", "људи on a Russian keyboard; Russian people"),
    ReadingCase("kucha", "sr", "куча", "either", "кућа on a Russian keyboard; Russian heap"),
    ReadingCase("ponos", "sr", "понос", "not", "pride; Russian diarrhoea"),
    ReadingCase("pozor", "sr", "позор", "not", "attention; Russian disgrace"),
    ReadingCase("vrach", "sr", "врач", "not", "sorcerer; Russian doctor"),
    ReadingCase("hleb", "sr", "хлеб", "not", "bread, shared"),
    ReadingCase("reka", "sr", "река", "not", "river, shared"),
    ReadingCase("zena", "sr", "жена", "not", "wife, woman; shared"),
    ReadingCase("covek", "sr", "човек", "not", "man; Russian человек"),
    ReadingCase("lepo", "sr", "лепо", "not", "nicely"),
    ReadingCase("sutra", "sr", "сутра", "not", "tomorrow; Russian с утра"),
    ReadingCase("otec", "sr", "отец", "either", "Russian father; отац misspelled"),
    ReadingCase("ne-razume", "sr", "Он не разуме", "not", "a Serbian sentence"),
    # A tab word spelled like a common target word, its own meaning the rarer one.
    ReadingCase("bulka", "sr", "булка", "not", "Serbian Muslim woman, archaic; Russian bun"),
    ReadingCase("cheta", "sr", "чета", "not", "Serbian company of soldiers; Russian couple"),
    ReadingCase("zhir", "sr", "жир", "not", "Serbian acorns, mast; Russian fat"),
    ReadingCase("divan", "sr", "диван", "not", "Serbian wonderful; Russian sofa"),
    ReadingCase("sobaka", "sr", "собака", "target", "dog"),
    ReadingCase("devushka", "sr", "девушка", "target", "girl"),
    ReadingCase("gorod", "sr", "город", "target", "city"),
    ReadingCase("spasibo", "sr", "спасибо", "target", "thanks"),
    ReadingCase("khorosho", "sr", "хорошо", "target", "good"),
    ReadingCase("zdravstvuyte", "sr", "здравствуйте", "target", "hello"),
    ReadingCase("yazyk", "sr", "язык", "target", "tongue, language"),
    ReadingCase("mysh", "sr", "мышь", "target", "mouse"),
    ReadingCase("seychas", "sr", "сейчас", "target", "now"),
    ReadingCase("rabota", "sr", "работа", "either", "Russian work; south-eastern Serbian regional"),
    ReadingCase("vopros", "sr", "вопрос", "target", "question"),
    ReadingCase("v-kontse", "sr", "в конце концов", "target", "after all"),
    ReadingCase("ne-ponimaet", "sr", "Он не понимает", "target", "a Russian sentence in shared letters"),
    ReadingCase("ya-ne-znayu", "sr", "Я не знаю", "target", "a Russian sentence"),
    ReadingCase("ne-opazdyvaem", "sr", "Не опаздываем ли мы на поезд", "target", "a Russian question"),
    ReadingCase("gde-ty-byl", "sr", "Где ты был вчера", "target", "a Russian question"),
    ReadingCase("sutra-idem", "sr", "Сутра идем на посао", "not", "a Serbian sentence"),
    ReadingCase("da-li-kasnim", "sr", "Да ли касним на воз", "not", "Serbian in letters Russian shares"),
    ReadingCase("gde-si-bio", "sr", "Где си био јуче", "not", "a Serbian question"),
    # A Serbian target shares Latin with the English and German tabs.
    ReadingCase("sto-sr", "en", "sto", "target", "table, hundred", "Serbian"),
    ReadingCase("kuca-sr", "en", "kuća", "target", "house", "Serbian"),
    ReadingCase("kuca-bare-sr", "en", "kuca", "target", "kuća without its diacritic", "Serbian"),
    ReadingCase("hvala-sr", "en", "hvala", "target", "thanks", "Serbian"),
    ReadingCase("jabuka-sr", "en", "jabuka", "target", "apple", "Serbian"),
    ReadingCase("zdravo-sr", "en", "zdravo", "target", "hello", "Serbian"),
    ReadingCase("kafa-sr", "en", "kafa", "target", "coffee", "Serbian"),
    ReadingCase("dobar-dan-sr", "en", "dobar dan", "target", "good day", "Serbian"),
    ReadingCase("kasnimo-sr", "en", "Da li kasnimo na voz", "target", "a Serbian question", "Serbian"),
    ReadingCase("late-en", "en", "Are we late for the train", "not", "an English question", "Serbian"),
    ReadingCase("most-en", "en", "most", "not", "English most; Serbian bridge", "Serbian"),
    ReadingCase("pas-en", "en", "pas", "not", "English pas, a dance step; Serbian dog", "Serbian"),
    ReadingCase("kit-en", "en", "kit", "not", "English kit; Serbian whale", "Serbian"),
    ReadingCase("net-en", "en", "net", "not", "English net", "Serbian"),
    ReadingCase("ran-en", "en", "ran", "not", "form of run", "Serbian"),
    ReadingCase("recieve-en", "en", "recieve", "not", "receive misspelled", "Serbian"),
    ReadingCase("teh-en", "en", "teh", "not", "the misspelled", "Serbian"),
    ReadingCase("baba-en", "en", "baba", "not", "English rum cake; Serbian grandmother", "Serbian"),
    ReadingCase("dan-en", "en", "dan", "not", "English martial-arts grade; Serbian day", "Serbian"),
    ReadingCase("sir-en", "en", "sir", "not", "English sir; Serbian cheese", "Serbian"),
    ReadingCase("brat-en", "en", "brat", "not", "English brat; Serbian brother", "Serbian"),
    ReadingCase("voda-de", "de", "voda", "target", "water", "Serbian"),
    ReadingCase("hvala-de", "de", "hvala", "target", "thanks", "Serbian"),
    ReadingCase("knjiga-de", "de", "knjiga", "target", "book", "Serbian"),
    ReadingCase("dobar-de", "de", "dobar", "target", "good", "Serbian"),
    ReadingCase("most-de", "de", "Most", "not", "German cider; Serbian bridge", "Serbian"),
    ReadingCase("rot-de", "de", "rot", "not", "German red", "Serbian"),
    ReadingCase("mir-de", "de", "mir", "not", "German me; Serbian peace", "Serbian"),
    ReadingCase("dom-de", "de", "Dom", "not", "German cathedral; Serbian home", "Serbian"),
    ReadingCase("ging-de", "de", "ging", "not", "form of gehen", "Serbian"),
    ReadingCase("maedschen-de", "de", "Mädschen", "not", "Mädchen misspelled", "Serbian"),
)
