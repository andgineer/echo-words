import pytest
import tier_screen as screen

from echo_words.prompt import CARD_DELIMITER


def _record(arm: str, *, prompt: int, completion: int, tier: str | None = None) -> dict:
    return {
        "arm": arm,
        "fixture": "en-reluctant",
        "usage": {"prompt_tokens": prompt, "completion_tokens": completion},
        "service_tier": tier,
        "text": "",
    }


def test_every_arm_is_priced_at_the_tier_it_asks_for():
    for arm in screen.ARMS:
        assert (arm.model, arm.tier) in screen.PRICES


def test_a_call_is_priced_at_the_tier_the_provider_granted():
    # Asked for priority and served standard, a call is billed at the standard rate.
    granted = screen._cost(
        _record("sol-none-prio", prompt=1_000_000, completion=0, tier="priority")
    )
    refused = screen._cost(_record("sol-none-prio", prompt=1_000_000, completion=0, tier="default"))
    assert (granted, refused) == (8.00, 4.00)


def test_reasoning_tokens_are_read_from_the_completion_details():
    usage = {
        "prompt_tokens": 300,
        "completion_tokens": 1800,
        "completion_tokens_details": {"reasoning_tokens": 1000},
    }
    assert screen._tokens(usage) == (300, 1800, 1000)
    assert screen._tokens(None) == (0, 0, 0)


def test_the_p90_is_read_off_the_sorted_values():
    assert screen._q([5.0, 1.0, 3.0, 2.0, 4.0, 6.0, 7.0, 8.0, 9.0, 10.0], 0.9) == 10.0


def test_the_detail_job_asks_the_production_deeper_article_prompt():
    fixture = screen.DETAIL_FIXTURES[0]
    assert "Analyse it in depth: reluctant" in screen.prompt_for("detail", fixture)


@pytest.mark.parametrize("fixture", screen.CARD_FIXTURES, ids=lambda fixture: fixture.id)
def test_the_card_job_asks_the_production_card_prompt(fixture):
    assert CARD_DELIMITER in screen.prompt_for("card", fixture)


def test_an_answer_without_a_payload_is_not_a_usable_card():
    record = {"arm": "haiku", "fixture": "card-en-reluctant", "text": "no payload here"}
    assert screen._card_usable(record) is False
