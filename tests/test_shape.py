import pytest

from echo_words.languages import MAX_WORD_LENGTH
from echo_words.shape import classify, word_count


@pytest.mark.parametrize(
    "text",
    [
        "Straße",
        "Straße.",
        "receive",
        "кућа.",
        "mother-in-law",
        "Rad fahren",
        "voziti bicikl",
        "die Nase voll haben",
        "unter die Lupe nehmen",
        "von Zeit zu Zeit",
        "с времена на време",
    ],
)
def test_a_unit_is_analysed_whole(text: str):
    assert classify(text) == "unit"


@pytest.mark.parametrize(
    "text",
    [
        "Er steht jeden Morgen um sechs auf.",
        "Он се синоћ вратио кући.",
        "Sve mi se čini da nešto nije u redu.",
        "Wie geht es dir?",
        "Ich weiß nicht, was du meinst",
        "a" * 30 + " " + "b" * 30,
    ],
)
def test_running_text_is_explained(text: str):
    assert classify(text) == "text"


def test_a_single_word_stays_a_unit_whatever_trails_it():
    assert classify("Haus.") == "unit"
    assert classify("Како?") == "unit"
    assert classify("a" * (MAX_WORD_LENGTH + 10)) == "unit"


def test_a_five_word_expression_is_the_accepted_misroute():
    # The one benign error the decision record accepts: sentence mode still explains it
    # and offers it back as its own first suggestion, one tap from a card.
    assert classify("не пада ми на памет") == "text"


def test_word_count_drops_edge_punctuation_and_empty_tokens():
    assert word_count("“don’t,” he said — twice") == 4
    assert word_count("   ") == 0
    assert word_count("!!!") == 0
