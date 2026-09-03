"""The source-language table (``languages.toml``) and per-language input validation."""

import os
import re
import tempfile
import tomllib
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, fields
from pathlib import Path

import tomli_w

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

TTS_ENGINES = ("piper", "edge")
_CODE_PATTERN = re.compile(r"^[a-z]{2,8}$")
# The two fields the editor never writes: both reach machinery it can neither show
# nor check. `prompt_hints` is interpolated into the prompt, and a bad hint degrades
# every future answer silently; `api_model` builds the broker's direct map at
# startup, so a change to it would need the broker rebuilt underneath a live app.
FILE_ONLY_FIELDS = ("api_model", "prompt_hints")


class LanguagesConfigError(RuntimeError):
    """The languages table is missing or unusable — a startup config error."""


class LanguageValidationError(ValueError):
    """A submitted language entry is unusable, with a hint for the person who sent it."""


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


def _optional(value: object) -> str | None:
    """An empty box means the key is absent; only a real value is written."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def validated_language(
    code: str,
    submitted: Mapping[str, object],
    existing: "Language | None" = None,
    locale: str = DEFAULT_LOCALE,
) -> Language:
    """Build a `Language` from an editor submission, or refuse it with a hint.

    The two file-only fields are carried over from `existing` untouched: saving a
    voice must never drop a prompt hint the editor cannot see.
    """
    if not _CODE_PATTERN.match(code):
        raise LanguageValidationError(message("language.bad_code", locale, code=code))
    required = {field: _optional(submitted.get(field)) for field in _REQUIRED_FIELDS}
    missing = [field for field, value in required.items() if value is None]
    if missing:
        raise LanguageValidationError(
            message("language.missing", locale, fields=", ".join(missing)),
        )
    script = required["script"]
    if script not in _ALLOWED_SCRIPTS:
        raise LanguageValidationError(
            message(
                "language.bad_script",
                locale,
                script=script,
                allowed=", ".join(sorted(_ALLOWED_SCRIPTS)),
            ),
        )
    tts = _optional(submitted.get("tts"))
    if tts is not None and tts not in TTS_ENGINES:
        raise LanguageValidationError(
            message("language.bad_tts", locale, tts=tts, allowed=", ".join(TTS_ENGINES)),
        )
    return Language(
        code=code,
        name=required["name"] or "",
        deck=required["deck"] or "",
        script=script or "",
        dict_api=_optional(submitted.get("dict_api")),
        tts=tts,
        tts_voice=_optional(submitted.get("tts_voice")),
        edge_tts_voice=_optional(submitted.get("edge_tts_voice")),
        accent=_optional(submitted.get("accent")),
        **{field: getattr(existing, field, None) for field in FILE_ONLY_FIELDS},
    )


def save_languages(path: Path, table: dict[str, Language]) -> None:
    """Replace the whole table on disk, atomically.

    Written beside the target and renamed over it: a crash halfway through would
    otherwise leave the app with no readable config at all.
    """
    if not table:
        raise LanguageValidationError(message("language.last"))
    document = tomli_w.dumps(
        {
            "languages": {
                code: {
                    field.name: getattr(language, field.name)
                    for field in fields(Language)
                    if field.name != "code" and getattr(language, field.name) is not None
                }
                for code, language in table.items()
            },
        },
    )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(  # noqa: SIM115 - replaced onto the target below
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=".languages-",
        suffix=".toml",
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(document)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


def normalize_submission(text: str, lookup_only: bool = False) -> tuple[str, bool]:
    """Strip the leading ``?`` lookup-only shortcut; return the text and the resulting flag."""
    normalized = unicodedata.normalize("NFC", text).strip()
    if normalized.startswith("?"):
        return normalized[1:].strip(), True
    return normalized, lookup_only


# Serbian is written in both scripts, so a model answer may come back transliterated
# while the submitted text stays in the other script. Matching folds one onto the other.
_SERBIAN_LATIN = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "ђ": "đ",
    "е": "e",
    "ж": "ž",
    "з": "z",
    "и": "i",
    "ј": "j",
    "к": "k",
    "л": "l",
    "љ": "lj",
    "м": "m",
    "н": "n",
    "њ": "nj",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "ћ": "ć",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "c",
    "ч": "č",
    "џ": "dž",
    "ш": "š",
}


# Closed-class material a dictionary unit never carries, and the reflexive marker a
# unit's dictionary form names. Serbian is listed in Latin only: `fold_for_match`
# folds its Cyrillic onto Latin before any of these are consulted. A language absent
# here gets no repair, which is why an operator may add one without touching this.
_UNIT_EXCLUDED = {
    "en": frozenset({"not", "never", "is", "are", "was", "were", "am", "be", "been", "being"}),
    "de": frozenset({"nicht", "nie", "niemals"}),
    "sr": frozenset({"ne", "nije", "da"}),
}
_REFLEXIVE_FORMS = {
    "de": frozenset({"mich", "dich", "sich", "uns", "euch"}),
    "sr": frozenset({"se"}),
}
_REFLEXIVE_MARKERS = {
    "de": frozenset({"sich"}),
    "sr": frozenset({"se"}),
}


def unit_excluded_words(language: Language) -> frozenset[str]:
    """Folded words a dictionary unit does not carry: negation, subordinators, copulas."""
    return _UNIT_EXCLUDED.get(language.code, frozenset())


def reflexive_forms(language: Language) -> frozenset[str]:
    """Folded reflexive pronouns as running text spells them."""
    return _REFLEXIVE_FORMS.get(language.code, frozenset())


def reflexive_markers(language: Language) -> frozenset[str]:
    """Folded reflexive markers as a dictionary form spells them."""
    return _REFLEXIVE_MARKERS.get(language.code, frozenset())


# Letters that cannot occur in a source language, used to tell its sentences from
# sentences in the target one. Serbian is the awkward case: it shares Cyrillic with
# Russian, so only the letters Russian has and Serbian does not can separate them.
# The Serbian Cyrillic alphabet has none of these; Russian has all of them.
_RUSSIAN_ONLY = frozenset("ёйщъыьэюя")
_CYRILLIC = frozenset("абвгдежзийклмнопрстуфхцчшщъыьэюяђјљњћџѐѝ")


def sentence_is_source_language(text: str, language: Language) -> bool:
    """Whether a card sentence is written in the source language rather than the target.

    A card example is the front of a card, so a target-language sentence with the
    source word wedged into it teaches nothing and is rejected outright.
    """
    letters = {char for char in unicodedata.normalize("NFC", text).casefold() if char.isalpha()}
    foreign = _RUSSIAN_ONLY if language.script == "latin+cyrillic" else _CYRILLIC
    return not (letters & foreign)


def fold_for_match(text: str, language: Language) -> str:
    """Fold a string for comparison against another spelling of the same language."""
    folded = unicodedata.normalize("NFC", text).casefold()
    if language.script != "latin+cyrillic":
        return folded
    return "".join(_SERBIAN_LATIN.get(char, char) for char in folded)


# The inverse of the fold, longest first so a digraph is not read as two letters.
_SERBIAN_CYRILLIC = sorted(
    ((latin, cyrillic) for cyrillic, latin in _SERBIAN_LATIN.items()),
    key=lambda pair: -len(pair[0]),
)


def other_script(text: str, language: Language) -> str:
    """The same wording in the language's other script, or empty where it has one.

    Serbian is written in both, and a count of occurrences is per exact string, so
    one script alone counts a fraction of what a wording is used in.
    """
    if language.script != "latin+cyrillic":
        return ""
    normalized = unicodedata.normalize("NFC", text)
    if any(char.casefold() in _SERBIAN_LATIN for char in normalized):
        return "".join(_SERBIAN_LATIN.get(char.casefold(), char) for char in normalized)
    lowered = normalized.casefold()
    for latin, cyrillic in _SERBIAN_CYRILLIC:
        lowered = lowered.replace(latin, cyrillic)
    return lowered


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
