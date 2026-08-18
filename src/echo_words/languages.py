"""The source-language table (``languages.toml``) and per-language input validation."""

import tomllib
import unicodedata
from dataclasses import dataclass
from pathlib import Path

MAX_WORD_LENGTH = 50
MAX_CONTEXT_LENGTH = 500

LATIN = "latin"
CYRILLIC = "cyrillic"

_ALLOWED_SCRIPTS: dict[str, frozenset[str]] = {
    LATIN: frozenset({LATIN}),
    CYRILLIC: frozenset({CYRILLIC}),
    "latin+cyrillic": frozenset({LATIN, CYRILLIC}),
}

_SCRIPT_HINT = {
    LATIN: "латиница",
    CYRILLIC: "кириллица",
    "latin+cyrillic": "латиница или кириллица",
}

# Word-internal punctuation the languages in scope actually use.
_EXTRA_WORD_CHARS = frozenset(" -'’")

_NON_LETTER_HINT = "Только буквы, пробел, дефис и апостроф."

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


def sanitize_context(text: str) -> str:
    """Reduce a pasted phrase to plain single-spaced text of bounded length."""
    printable = "".join(char if char.isprintable() else " " for char in text)
    return " ".join(unicodedata.normalize("NFC", printable).split())[:MAX_CONTEXT_LENGTH]


def validate_word(word: str, language: Language) -> str | None:
    """Return a short hint for the user when the word is unusable, or ``None`` when it is fine."""
    if not word:
        return "Введите слово."
    if len(word) > MAX_WORD_LENGTH:
        return f"Слишком длинно: не больше {MAX_WORD_LENGTH} символов."
    return _validate_script(word, language)


def _validate_script(word: str, language: Language) -> str | None:
    allowed = _ALLOWED_SCRIPTS[language.script]
    seen: set[str] = set()
    for char in word:
        script = _letter_script(char)
        if script is None:
            if char in _EXTRA_WORD_CHARS:
                continue
            return _script_hint(language) if char.isalpha() else _NON_LETTER_HINT
        if script not in allowed:
            return _script_hint(language)
        seen.add(script)
    if not seen:
        return "Введите слово."
    if len(seen) > 1:
        return "Не смешивайте латиницу и кириллицу в одном слове."
    return None


def _letter_script(char: str) -> str | None:
    name = unicodedata.name(char, "")
    if name.startswith("LATIN "):
        return LATIN
    if name.startswith("CYRILLIC "):
        return CYRILLIC
    return None


def _script_hint(language: Language) -> str:
    return f"Для «{language.name}» нужна {_SCRIPT_HINT[language.script]}."


def unknown_language_hint(code: str) -> str:
    return f"Неизвестный язык «{code}» — выберите язык из списка."
