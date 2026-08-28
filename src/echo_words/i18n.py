"""User-facing message texts, resolved per request from ``Accept-Language``."""

DEFAULT_LOCALE = "en"

MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "word.empty": "Enter a word.",
        "word.too_long": "Too long: no more than {limit} characters.",
        "text.too_long": "This text is too long: no more than {limit} characters.",
        "text.no_rebuild": "Running text makes no card, so there is nothing to rebuild.",
        "card.no_rebuild": "This entry has no card to rebuild.",
        "text.no_detail": "A deeper analysis is for a word, not for running text.",
        "word.non_letter": "Letters, spaces, hyphens and apostrophes only.",
        "word.mixed_scripts": "Do not mix Latin and Cyrillic in one word.",
        "word.script": "“{language}” needs {script}.",
        "script.latin": "the Latin script",
        "script.cyrillic": "the Cyrillic script",
        "script.latin+cyrillic": "the Latin or the Cyrillic script",
        "language.unknown": "Unknown language “{code}” — pick one from the list.",
    },
    "ru": {
        "word.empty": "Введите слово.",
        "word.too_long": "Слишком длинно: не больше {limit} символов.",
        "text.too_long": "Текст слишком длинный: не больше {limit} символов.",
        "text.no_rebuild": "Текст не создаёт карточку — пересобирать нечего.",
        "card.no_rebuild": "У этой записи нет карточки — пересобирать нечего.",
        "text.no_detail": "Подробный разбор бывает у слова, а не у текста.",
        "word.non_letter": "Только буквы, пробел, дефис и апостроф.",
        "word.mixed_scripts": "Не смешивайте латиницу и кириллицу в одном слове.",
        "word.script": "Для «{language}» нужна {script}.",
        "script.latin": "латиница",
        "script.cyrillic": "кириллица",
        "script.latin+cyrillic": "латиница или кириллица",
        "language.unknown": "Неизвестный язык «{code}» — выберите язык из списка.",
    },
}


def pick_locale(accept_language: str | None) -> str:
    """Return the best supported locale for an ``Accept-Language`` header value."""
    if not accept_language:
        return DEFAULT_LOCALE
    weighted: list[tuple[float, int, str]] = []
    for position, part in enumerate(accept_language.split(",")):
        tag, _, params = part.strip().partition(";")
        language = tag.strip().partition("-")[0].lower()
        if language not in MESSAGES:
            continue
        quality = 1.0
        if params.strip().startswith("q="):
            try:
                quality = float(params.strip()[2:])
            except ValueError:
                continue
        if quality > 0:
            weighted.append((-quality, position, language))
    return min(weighted)[2] if weighted else DEFAULT_LOCALE


def message(key: str, locale: str = DEFAULT_LOCALE, **params: object) -> str:
    texts = MESSAGES.get(locale, MESSAGES[DEFAULT_LOCALE])
    return texts.get(key, MESSAGES[DEFAULT_LOCALE][key]).format(**params)
