import pytest

from echo_words.i18n import DEFAULT_LOCALE, MESSAGES, message, pick_locale


def test_every_locale_carries_the_same_keys():
    for locale, texts in MESSAGES.items():
        assert set(texts) == set(MESSAGES[DEFAULT_LOCALE]), locale


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (None, "en"),
        ("", "en"),
        ("ru", "ru"),
        ("ru-RU,ru;q=0.9", "ru"),
        ("RU", "ru"),
        ("fr-FR,fr;q=0.9", "en"),
        ("fr;q=0.9,ru;q=0.8", "ru"),
        ("en;q=0.4,ru;q=0.8", "ru"),
        ("ru;q=0,en", "en"),
        ("ru;q=nonsense,en", "en"),
    ],
)
def test_pick_locale_reads_the_accept_language_header(header: str | None, expected: str):
    assert pick_locale(header) == expected


def test_message_interpolates_and_falls_back_to_the_default_locale():
    assert message("word.too_long", "ru", limit=50) == "Слишком длинно: не больше 50 символов."
    assert message("word.too_long", "fr", limit=50) == "Too long: no more than 50 characters."
