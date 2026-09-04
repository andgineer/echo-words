import pytest

from echo_words.language_catalog import (
    BY_CODE,
    CATALOG,
    UNMEASURED,
    UNRELIABLE,
    VOUCHED,
    catalog_language,
)
from echo_words.languages import _ALLOWED_SCRIPTS, _BEYOND_LATIN, _CODE_PATTERN, _alphabet


def test_every_code_is_one_the_editor_would_accept():
    for entry in CATALOG:
        assert _CODE_PATTERN.match(entry.code), entry.code


def test_every_script_is_one_the_input_validator_can_check():
    """A language whose writing it cannot read would refuse every word submitted."""
    for entry in CATALOG:
        assert entry.script in _ALLOWED_SCRIPTS, entry.code


def test_no_code_is_listed_twice():
    codes = [entry.code for entry in CATALOG]
    assert len(codes) == len(set(codes))
    assert len(BY_CODE) == len(CATALOG)


def test_every_entry_is_named_in_all_three_ways():
    for entry in CATALOG:
        assert entry.name.strip()
        assert entry.english.strip()
        assert entry.russian.strip()


@pytest.mark.parametrize(
    ("code", "name", "deck"),
    [
        ("en", "English", "EchoWords: English"),
        ("de", "Deutsch", "EchoWords: German"),
        ("sr", "Српски", "EchoWords: Serbian"),
    ],
)
def test_the_shipped_languages_keep_the_names_and_decks_already_in_use(code, name, deck):
    """The name is what the prompt calls the source language, so the directory
    holding a different one for a configured language would change what is asked."""
    entry = catalog_language(code)
    assert entry is not None
    assert entry.name == name
    assert entry.deck == deck


@pytest.mark.parametrize("code", ["sr", "hr"])
def test_the_south_slavic_pair_is_marked_as_having_no_usable_piper_voice(code):
    """Piper's `sr` model is Lower Sorbian and it has no Croatian at all
    (spec/decision-tts.md), so neither may be offered the engine."""
    assert catalog_language(code).piper_unusable is True
    assert catalog_language("de").piper_unusable is False


def test_an_unlisted_code_is_simply_absent():
    assert catalog_language("xx") is None


def test_every_language_records_the_letters_it_writes():
    """A language whose alphabet nobody recorded cannot be told from the target by its
    letters, so the directory is the list that has to stay complete."""
    for entry in CATALOG:
        assert entry.code in _BEYOND_LATIN, entry.code
        letters = _alphabet(entry)
        assert letters, entry.code
        assert all(char.isalpha() and char == char.casefold() for char in letters), entry.code


def test_the_directory_carries_what_the_bench_measured_of_each_language():
    """Only what a decision spec records may be claimed here: the three the bench is
    built on are vouched for, the Cyrillic pair was measured and its answers refused,
    and every other row is nobody having looked (spec/decision-llm-backend.md)."""
    by_answers = {entry.code: entry.answers for entry in CATALOG}

    assert [code for code, answers in by_answers.items() if answers == VOUCHED] == [
        "en",
        "de",
        "sr",
    ]
    assert [code for code, answers in by_answers.items() if answers == UNRELIABLE] == [
        "bg",
        "uk",
    ]
    assert by_answers["pl"] == UNMEASURED
