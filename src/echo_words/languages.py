"""The source-language table (``languages.toml``) and per-language input validation."""

import re
import tomllib
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from echo_words.i18n import DEFAULT_LOCALE, message

MAX_WORD_LENGTH = 50
MAX_CONTEXT_LENGTH = 500
# Tapping a suggested unit resubmits it with its text as the context, so a text
# longer than the context bound would be truncated on the way back in.
MAX_TEXT_LENGTH = MAX_CONTEXT_LENGTH

LATIN = "latin"
CYRILLIC = "cyrillic"

_ALLOWED_SCRIPTS: dict[str, frozenset[str]] = {
    LATIN: frozenset({LATIN}),
    CYRILLIC: frozenset({CYRILLIC}),
    "latin+cyrillic": frozenset({LATIN, CYRILLIC}),
}

# Word-internal punctuation the languages in scope actually use.
_EXTRA_WORD_CHARS = frozenset(" -'’")

_WORD_EDGES = re.compile(r"^[^\w]+|[^\w]+$", re.UNICODE)

_REQUIRED_FIELDS = ("name", "deck", "script")


class LanguagesConfigError(RuntimeError):
    """The languages table is missing or unusable — a startup config error."""


@dataclass(frozen=True)
class Language:
    code: str
    name: str
    deck: str
    script: str
    dict_api: str | None = None
    tts: str | None = None
    tts_voice: str | None = None
    edge_tts_voice: str | None = None
    accent: str | None = None
    api_model: str | None = None
    prompt_hints: str | None = None


def load_languages(path: Path) -> dict[str, Language]:
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise LanguagesConfigError(f"languages config is not readable: {path} ({exc})") from exc
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise LanguagesConfigError(f"languages config is not valid TOML: {path} ({exc})") from exc

    table = data.get("languages")
    if not isinstance(table, dict) or not table:
        raise LanguagesConfigError(f"languages config has no [languages.*] entries: {path}")

    return {code: _language_from_entry(code, entry, path) for code, entry in table.items()}


def _language_from_entry(code: str, entry: object, path: Path) -> Language:
    if not isinstance(entry, dict):
        raise LanguagesConfigError(f"[languages.{code}] is not a table in {path}")
    missing = [field for field in _REQUIRED_FIELDS if not entry.get(field)]
    if missing:
        raise LanguagesConfigError(
            f"[languages.{code}] in {path} is missing: {', '.join(missing)}",
        )
    script = entry["script"]
    if script not in _ALLOWED_SCRIPTS:
        raise LanguagesConfigError(
            f"[languages.{code}] in {path} has unknown script {script!r}; "
            f"expected one of {', '.join(sorted(_ALLOWED_SCRIPTS))}",
        )
    known = {field.name for field in Language.__dataclass_fields__.values()} - {"code"}
    return Language(code=code, **{k: v for k, v in entry.items() if k in known})


def normalize_submission(text: str, lookup_only: bool = False) -> tuple[str, bool]:
    """Strip the leading ``?`` lookup-only shortcut; return the text and the resulting flag."""
    normalized = unicodedata.normalize("NFC", text).strip()
    if normalized.startswith("?"):
        return normalized[1:].strip(), True
    return normalized, lookup_only


def split_words(text: str) -> list[str]:
    """Split into words, dropping the punctuation that hangs off their edges."""
    return [word for word in (_WORD_EDGES.sub("", part) for part in text.split()) if word]


def plain_unit(text: str) -> str:
    """Drop the punctuation hanging off a unit's edges: a shared selection carries it."""
    return _WORD_EDGES.sub("", text)


def plain_text(text: str) -> str:
    """Reduce pasted text to single-spaced printable characters, under no length bound."""
    printable = "".join(char if char.isprintable() else " " for char in text)
    return " ".join(unicodedata.normalize("NFC", printable).split())


def sanitize_context(text: str) -> str:
    """Reduce a pasted phrase to plain single-spaced text of bounded length."""
    return plain_text(text)[:MAX_CONTEXT_LENGTH]


def validate_word(word: str, language: Language, locale: str = DEFAULT_LOCALE) -> str | None:
    """Return a short hint for the user when the word is unusable, or ``None`` when it is fine."""
    if not word:
        return message("word.empty", locale)
    if len(word) > MAX_WORD_LENGTH:
        return message("word.too_long", locale, limit=MAX_WORD_LENGTH)
    return _validate_script(word, language, locale)


def validate_text(text: str, language: Language, locale: str = DEFAULT_LOCALE) -> str | None:
    """Return a short hint when running text is unusable, or ``None`` when it is fine."""
    if not text:
        return message("word.empty", locale)
    if len(text) > MAX_TEXT_LENGTH:
        return message("text.too_long", locale, limit=MAX_TEXT_LENGTH)
    words = split_words(text)
    if not words:
        return message("word.empty", locale)
    for word in words:
        hint = _validate_script(word, language, locale, letters_only=True)
        if hint is not None:
            return hint
    return None


def _validate_script(
    word: str,
    language: Language,
    locale: str,
    *,
    letters_only: bool = False,
) -> str | None:
    # ``letters_only`` skips digits and punctuation instead of refusing them, so running
    # text keeps its commas, numbers and quotation marks while each word keeps the rule.
    allowed = _ALLOWED_SCRIPTS[language.script]
    seen: set[str] = set()
    for char in word:
        script = _letter_script(char)
        if script is None:
            if char.isalpha():
                return _script_hint(language, locale)
            if letters_only or char in _EXTRA_WORD_CHARS:
                continue
            return message("word.non_letter", locale)
        if script not in allowed:
            return _script_hint(language, locale)
        seen.add(script)
    if not seen:
        return None if letters_only else message("word.empty", locale)
    if len(seen) > 1:
        return message("word.mixed_scripts", locale)
    return None


def _letter_script(char: str) -> str | None:
    name = unicodedata.name(char, "")
    if name.startswith("LATIN "):
        return LATIN
    if name.startswith("CYRILLIC "):
        return CYRILLIC
    return None


def _script_hint(language: Language, locale: str) -> str:
    return message(
        "word.script",
        locale,
        language=language.name,
        script=message(f"script.{language.script}", locale),
    )


def unknown_language_hint(code: str, locale: str = DEFAULT_LOCALE) -> str:
    return message("language.unknown", locale, code=code)
