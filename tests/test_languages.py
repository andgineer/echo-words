from pathlib import Path

import pytest

from echo_words.languages import (
    MAX_CONTEXT_LENGTH,
    MAX_TEXT_LENGTH,
    MAX_WORD_LENGTH,
    Language,
    LanguagesConfigError,
    LanguageValidationError,
    fold_for_match,
    load_languages,
    normalize_submission,
    plain_text,
    plain_unit,
    reflexive_forms,
    reflexive_markers,
    sanitize_context,
    save_languages,
    unit_excluded_words,
    unknown_language_hint,
    validate_text,
    validate_word,
    validated_language,
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


def test_plain_unit_drops_the_punctuation_a_shared_selection_carries():
    assert plain_unit("Straße.") == "Straße"
    assert plain_unit("Како?") == "Како"
    assert plain_unit("«Rad fahren»") == "Rad fahren"
    assert plain_unit("'(go-over)'") == "go-over"
    assert plain_unit("...") == ""


def test_plain_unit_keeps_the_punctuation_that_belongs_to_the_unit():
    assert plain_unit("don’t") == "don’t"
    assert plain_unit("ein- und aussteigen") == "ein- und aussteigen"
    assert plain_unit("word42") == "word42"


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


@pytest.mark.parametrize(
    ("code", "text"),
    [
        ("de", "Er steht jeden Morgen um sechs auf."),
        ("de", "Der Zug kommt um 7:15 an, sagt sie — hoffentlich!"),
        ("sr", "Он се синоћ вратио кући веома касно."),
        ("sr", "Sve mi se čini da nešto nije u redu."),
        ("en", "“Don’t,” he said, and left."),
    ],
)
def test_running_text_keeps_its_punctuation_and_digits(languages, code, text):
    assert validate_text(text, languages[code]) is None


def test_a_word_of_another_script_is_refused_inside_a_text(languages):
    hint = validate_text("Der Zug ist сегодня spät.", languages["de"])
    assert hint == "“Deutsch” needs the Latin script."


def test_a_hybrid_word_is_refused_inside_a_text(languages):
    # Serbian writes either script, so the rule stays per word: возiti is the real
    # hybrid the benchmark produced.
    assert validate_text("Он воли возiti bicikl.", languages["sr"]) == (
        "Do not mix Latin and Cyrillic in one word."
    )
    assert validate_text("Voli da vozi bicikl. Он воли бицикл.", languages["sr"]) is None


def test_an_over_long_text_is_refused(languages):
    hint = validate_text("wort " * (MAX_TEXT_LENGTH // 5 + 1), languages["de"])
    assert hint == f"This text is too long: no more than {MAX_TEXT_LENGTH} characters."
    assert validate_text("a" * MAX_TEXT_LENGTH, languages["de"]) is None


def test_plain_text_cleans_a_paste_without_hiding_an_over_long_one(languages):
    assert plain_text("Der Zug\u202e kommt\n\n heute  an.") == "Der Zug kommt heute an."
    too_long = plain_text("wort " * (MAX_TEXT_LENGTH // 5 + 1))
    assert validate_text(too_long, languages["de"]) == (
        f"This text is too long: no more than {MAX_TEXT_LENGTH} characters."
    )


def test_an_empty_text_is_refused(languages):
    assert validate_text("", languages["en"]) == "Enter a word."
    assert validate_text("— …", languages["en"]) == "Enter a word."


def test_the_text_hints_have_a_russian_wording(languages):
    assert validate_text("", languages["en"], "ru") == "Введите слово."
    assert validate_text("Der Zug ist сегодня spät.", languages["de"], "ru") == (
        "Для «Deutsch» нужна латиница."
    )
    assert validate_text("a" * (MAX_TEXT_LENGTH + 1), languages["de"], "ru") == (
        f"Текст слишком длинный: не больше {MAX_TEXT_LENGTH} символов."
    )


def test_serbian_folding_maps_both_scripts_onto_one_spelling(languages):
    assert fold_for_match("Њихово", languages["sr"]) == fold_for_match("njihovo", languages["sr"])
    assert fold_for_match("ЉУБАВ", languages["sr"]) == fold_for_match("ljubav", languages["sr"])


def test_folding_a_single_script_language_only_folds_case(languages):
    assert fold_for_match("Straße", languages["de"]) == fold_for_match("STRASSE", languages["de"])
    assert fold_for_match("Он", languages["en"]) == "он"


def test_serbian_closed_class_words_are_listed_once_in_the_script_matching_folds_to(languages):
    excluded = unit_excluded_words(languages["sr"])

    assert {fold_for_match(word, languages["sr"]) for word in ("не", "није", "да")} <= excluded


def test_a_language_without_closed_class_data_gets_no_boundary_repair():
    language = Language(code="fr", name="Français", deck="Deck", script="latin")

    assert unit_excluded_words(language) == frozenset()
    assert reflexive_forms(language) == frozenset()
    assert reflexive_markers(language) == frozenset()


MINIMAL = Language(code="fr", name="Français", deck="EchoWords: French", script="latin")
COMPLETE = Language(
    code="sr",
    name="Српски",
    deck="EchoWords: Serbian",
    script="latin+cyrillic",
    dict_api="sr",
    tts="edge",
    tts_voice="sr_RS-unusable-medium",
    edge_tts_voice="sr-RS-SophieNeural",
    accent="ekavian",
    api_model="gpt-fast",
    prompt_hints="for nouns give gender and plural",
)


def test_a_saved_table_reads_back_exactly_as_it_was_written(tmp_path):
    path = tmp_path / "languages.toml"

    save_languages(path, {"fr": MINIMAL, "sr": COMPLETE})

    assert load_languages(path) == {"fr": MINIMAL, "sr": COMPLETE}


def test_an_absent_optional_field_is_left_out_rather_than_written_empty(tmp_path):
    path = tmp_path / "languages.toml"

    save_languages(path, {"fr": MINIMAL})

    # `dict_api = ""` would claim the language has a dictionary code that is blank.
    assert "dict_api" not in path.read_text(encoding="utf-8")
    assert load_languages(path)["fr"].dict_api is None


def test_a_failed_write_leaves_the_previous_table_intact(tmp_path, monkeypatch):
    path = tmp_path / "languages.toml"
    save_languages(path, {"fr": MINIMAL})
    before = path.read_text(encoding="utf-8")

    def refuse(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("echo_words.languages.os.replace", refuse)
    with pytest.raises(OSError, match="disk full"):
        save_languages(path, {"sr": COMPLETE})

    assert path.read_text(encoding="utf-8") == before
    # And nothing half-written is left beside it.
    assert [child.name for child in tmp_path.iterdir()] == ["languages.toml"]


def test_saving_an_empty_table_is_refused(tmp_path):
    path = tmp_path / "languages.toml"

    with pytest.raises(LanguageValidationError, match="cannot run without one"):
        save_languages(path, {})

    assert not path.exists()


def test_a_submitted_language_is_built_from_the_fields_the_editor_shows():
    language = validated_language(
        "fr",
        {
            "name": " Français ",
            "deck": "EchoWords: French",
            "script": "latin",
            "dict_api": "  ",
            "tts": "edge",
            "edge_tts_voice": "fr-FR-DeniseNeural",
        },
    )

    assert language == Language(
        code="fr",
        name="Français",
        deck="EchoWords: French",
        script="latin",
        tts="edge",
        edge_tts_voice="fr-FR-DeniseNeural",
    )


def test_the_two_file_only_fields_survive_a_save_of_the_fields_the_editor_shows():
    """The editor cannot show a prompt hint or a paid model, so it must round-trip
    them: saving a voice would otherwise silently drop the hint."""
    language = validated_language(
        "sr",
        {"name": "Српски", "deck": "EchoWords: Serbian", "script": "cyrillic"},
        COMPLETE,
    )

    assert language.api_model == "gpt-fast"
    assert language.prompt_hints == "for nouns give gender and plural"
    assert language.script == "cyrillic"


@pytest.mark.parametrize(
    ("code", "fields", "expected"),
    [
        ("Fr", {"name": "n", "deck": "d", "script": "latin"}, "is not a language code"),
        ("f", {"name": "n", "deck": "d", "script": "latin"}, "is not a language code"),
        ("fr", {"name": "", "deck": "d", "script": "latin"}, "Fill in: name"),
        ("fr", {"name": "n", "deck": " ", "script": "latin"}, "Fill in: deck"),
        ("fr", {"name": "n", "deck": "d", "script": "runic"}, "Unknown script"),
        (
            "fr",
            {"name": "n", "deck": "d", "script": "latin", "tts": "festival"},
            "Unknown voice engine",
        ),
    ],
)
def test_an_unusable_submission_is_refused_with_a_hint(code, fields, expected):
    with pytest.raises(LanguageValidationError, match=expected):
        validated_language(code, fields)


def test_the_refusals_have_a_russian_wording():
    with pytest.raises(LanguageValidationError, match="не код языка"):
        validated_language("Fr", {"name": "n", "deck": "d", "script": "latin"}, None, "ru")
