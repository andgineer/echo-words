from pathlib import Path

import pytest

from echo_words.languages import (
    MAX_CONTEXT_LENGTH,
    MAX_WORD_LENGTH,
    Language,
    LanguagesConfigError,
    load_languages,
    normalize_submission,
    sanitize_context,
    unknown_language_hint,
    validate_word,
)


def test_load_languages_indexes_by_code(languages_file: Path):
    languages = load_languages(languages_file)
    assert set(languages) == {"en", "de", "sr"}
    assert languages["en"].code == "en"
    assert languages["en"].name == "English"
    assert languages["en"].deck == "English::Vocabulary"
    assert languages["sr"].name == "Српски"


def test_load_languages_keeps_optional_fields(languages_file: Path):
    languages = load_languages(languages_file)
    assert languages["en"].dict_api == "en"
    assert languages["en"].accent == "us"
    assert languages["sr"].dict_api is None
    assert languages["sr"].api_model == "gpt-fast"
    assert languages["sr"].edge_tts_voice == "sr-RS-SophieNeural"
    assert languages["sr"].prompt_hints == "for nouns give gender and plural"
    assert languages["de"].prompt_hints is None


def test_load_languages_ignores_unknown_keys(tmp_path: Path):
    path = tmp_path / "languages.toml"
    path.write_text(
        '[languages.en]\nname="English"\ndeck="D"\nscript="latin"\nfuture_key="x"\n',
        encoding="utf-8",
    )
    assert load_languages(path)["en"].name == "English"


def test_missing_file_is_a_config_error(tmp_path: Path):
    with pytest.raises(LanguagesConfigError, match="not readable"):
        load_languages(tmp_path / "absent.toml")


def test_broken_toml_is_a_config_error(tmp_path: Path):
    path = tmp_path / "languages.toml"
    path.write_text("[languages.en\nname =", encoding="utf-8")
    with pytest.raises(LanguagesConfigError, match="not valid TOML"):
        load_languages(path)


def test_table_without_languages_is_a_config_error(tmp_path: Path):
    path = tmp_path / "languages.toml"
    path.write_text('title = "nothing here"', encoding="utf-8")
    with pytest.raises(LanguagesConfigError, match="no \\[languages"):
        load_languages(path)


def test_missing_required_field_is_a_config_error(tmp_path: Path):
    path = tmp_path / "languages.toml"
    path.write_text('[languages.en]\nname = "English"\n', encoding="utf-8")
    with pytest.raises(LanguagesConfigError, match="missing: deck, script"):
        load_languages(path)


def test_unknown_script_is_a_config_error(tmp_path: Path):
    path = tmp_path / "languages.toml"
    path.write_text(
        '[languages.el]\nname="Greek"\ndeck="D"\nscript="greek"\n',
        encoding="utf-8",
    )
    with pytest.raises(LanguagesConfigError, match="unknown script"):
        load_languages(path)


@pytest.mark.parametrize(
    ("text", "flag", "expected"),
    [
        ("word", False, ("word", False)),
        ("  word  ", False, ("word", False)),
        ("?word", False, ("word", True)),
        ("? word", False, ("word", True)),
        ("  ?  word ", False, ("word", True)),
        ("word", True, ("word", True)),
        ("?word", True, ("word", True)),
    ],
)
def test_normalize_submission_strips_the_lookup_shortcut(text, flag, expected):
    assert normalize_submission(text, flag) == expected


def test_normalize_submission_composes_accents():
    assert normalize_submission("café")[0] == "café"


def test_sanitize_context_collapses_whitespace_and_control_chars():
    assert sanitize_context("  a\tphrase\nwith\x00junk  ") == "a phrase with junk"


def test_sanitize_context_is_capped():
    assert len(sanitize_context("x" * (MAX_CONTEXT_LENGTH + 100))) == MAX_CONTEXT_LENGTH


@pytest.fixture
def languages(languages_file: Path) -> dict[str, Language]:
    return load_languages(languages_file)


@pytest.mark.parametrize(
    ("code", "word"),
    [
        ("en", "receive"),
        ("en", "café"),
        ("en", "naïve"),
        ("en", "kick the bucket"),
        ("en", "mother-in-law"),
        ("en", "don't"),
        ("de", "Straße"),
        ("de", "Fußgängerübergang"),
        ("sr", "Beograd"),
        ("sr", "Београд"),
        ("sr", "чаша воде"),
    ],
)
def test_valid_words_pass(languages, code, word):
    assert validate_word(word, languages[code]) is None


def test_cyrillic_is_rejected_for_english(languages):
    hint = validate_word("слово", languages["en"])
    assert hint == "“English” needs the Latin script."


def test_serbian_accepts_both_scripts_but_not_mixed(languages):
    assert validate_word("Beograd", languages["sr"]) is None
    assert validate_word("Београд", languages["sr"]) is None
    assert validate_word("Beoград", languages["sr"]) == "Do not mix Latin and Cyrillic in one word."


def test_digits_and_punctuation_are_rejected(languages):
    hint = "Letters, spaces, hyphens and apostrophes only."
    assert validate_word("word42", languages["en"]) == hint
    assert validate_word("word!", languages["en"]) == hint


def test_a_letter_of_another_script_names_the_script(languages):
    assert validate_word("λόγος", languages["en"]) == "“English” needs the Latin script."


def test_empty_input_is_rejected(languages):
    assert validate_word("", languages["en"]) == "Enter a word."
    assert validate_word("- -", languages["en"]) == "Enter a word."


def test_too_long_input_is_rejected(languages):
    hint = validate_word("a" * (MAX_WORD_LENGTH + 1), languages["en"])
    assert hint == f"Too long: no more than {MAX_WORD_LENGTH} characters."
    assert validate_word("a" * MAX_WORD_LENGTH, languages["en"]) is None


def test_unknown_language_hint_names_the_code():
    assert "“fr”" in unknown_language_hint("fr")
    assert "«fr»" in unknown_language_hint("fr", "ru")


def test_every_hint_has_a_russian_wording(languages):
    assert validate_word("", languages["en"], "ru") == "Введите слово."
    assert validate_word("word!", languages["en"], "ru") == (
        "Только буквы, пробел, дефис и апостроф."
    )
    assert validate_word("λόγος", languages["en"], "ru") == "Для «English» нужна латиница."
    assert validate_word("сloud", languages["en"], "ru") == "Для «English» нужна латиница."
    assert validate_word("Beogradу", languages["sr"], "ru") == (
        "Не смешивайте латиницу и кириллицу в одном слове."
    )
    assert validate_word("a" * (MAX_WORD_LENGTH + 1), languages["en"], "ru") == (
        f"Слишком длинно: не больше {MAX_WORD_LENGTH} символов."
    )
