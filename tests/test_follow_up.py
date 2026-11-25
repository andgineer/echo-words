import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fakes import FakeBroker, FakeHandle, fake_cascade, lost_the_race
from fastapi.testclient import TestClient
from llmbroker import InvalidProviderResponseError, NoLLMAvailableError

from echo_words.api import create_app
from echo_words.config import Settings
from echo_words.follow_up import (
    MAX_FOLLOW_UP_PROMPT_CHARS,
    MAX_QUESTION_CHARS,
    FollowUpRefusedError,
    ReplyPump,
    follow_up_material,
    follow_up_prompt,
    reading_text,
    reply_events,
)
from echo_words.i18n import message
from echo_words.languages import Language
from echo_words.prompt import MAX_COMPLETE_ANSWER_CHARS, Chip, Exchange

RECORDED = json.loads(
    (Path(__file__).parent / "data" / "follow_up_recorded.json").read_text(encoding="utf-8"),
)
RELUCTANT = RECORDED["entries"]["en-reluctant"]
AUFHEBEN = RECORDED["entries"]["de-aufheben"]
DRZATI_REC = RECORDED["entries"]["sr-drzati-rec"]


def _material(entry: dict, question: str = "Что это значит?", exchanges=()):
    return follow_up_material(
        submitted=entry["word"],
        question=question,
        analysis_html=entry["analysis"],
        analysed_as=entry["analysed_as"],
        context=entry["context"],
        chips=[Chip(chip["label"], chip["note"]) for chip in entry["chips"]],
        detail_html=entry["detail"],
        exchanges=exchanges,
    )


def _body(entry: dict, question: str = "Что это значит?", **extra) -> dict:
    """What the page sends for an entry: everything the reader can see on it."""
    return {
        "lang": entry["lang"],
        "word": entry["word"],
        "analysed_as": entry["analysed_as"],
        "context": entry["context"],
        "analysis": entry["analysis"],
        "chips": entry["chips"],
        "detail": entry["detail"],
        "question": question,
        **extra,
    }


def _events(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        name, data = block.split("\n")
        events.append((name.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return events


def _app_with(monkeypatch: pytest.MonkeyPatch, broker: FakeBroker) -> None:
    monkeypatch.setattr("echo_words.api.create_broker", lambda *_args: broker)


def test_a_table_reads_one_row_per_line_with_its_cells_side_by_side():
    text = reading_text(RELUCTANT["analysis"])

    assert (
        "нежелающий\n\n"
        "be reluctant | не хотеть\n"
        "feel reluctant | испытывать нежелание\n"
        "grow reluctant | начинать сопротивляться\n"
        "remain reluctant | оставаться непреклонным\n\n"
        "Используется"
    ) in text


def test_the_examples_keep_their_order_and_their_lines():
    text = reading_text(RELUCTANT["analysis"])

    first = text.index("The manager was reluctant to sign the new contract.\n")
    second = text.index("She is reluctant to talk about her past.\n")
    third = text.index("Even the experts were reluctant to predict the outcome.\n")
    assert first < second < third
    assert "<" not in text


def test_a_deeper_article_keeps_its_headings_and_numbered_senses_in_order():
    text = reading_text(AUFHEBEN["detail"])

    assert "\nОсновные значения\n\n1. Поднять, подобрать что-либо" in text
    senses = [text.index(f"\n{number}. ") for number in range(1, 6)]
    assert senses == sorted(senses)
    assert "4. Компенсировать, сводить на нет: одно действие" in text
    assert "\nПроисхождение и внутренняя логика\n" in text


def test_markup_the_sanitizer_refused_stays_the_text_the_reader_sees():
    text = reading_text(DRZATI_REC["analysis"])

    assert "<ul>\n  <li>Он је увек знао да држи реч у тешким тренуцима." in text
    assert "&lt;" not in text


def test_the_prompt_carries_every_part_of_the_entry_in_reading_order():
    exchanges = (
        Exchange("Как сказать «он не сдержал слово»?", "Није одржао реч."),
        Exchange("А в будущем времени?", "Неће одржати реч."),
    )
    material = _material(AUFHEBEN, "А второй ответ точно верный?", exchanges)
    language = Language(code="de", name="Deutsch", deck="d", script="latin")

    prompt = follow_up_prompt(language, "Russian", material, locale="en")

    order = [
        'The wording the learner submitted: "aufheben"',
        'The context the learner supplied with it: "Hebt die Quittung gut auf, falls ihr sie',
        "=== The analysis ===\naufheben\n",
        "=== END OF The analysis ===",
        "=== Buttons under the analysis ===\n- поднимать, подобрать\n- отменять, аннулировать\n",
        "=== The full entry ===\naufheben\n",
        "=== END OF The full entry ===",
        "Question 1: Как сказать «он не сдержал слово»?\nYour answer 1: Није одржао реч.",
        "Question 2: А в будущем времени?\nYour answer 2: Неће одржати реч.",
        "=== END OF EARLIER QUESTIONS ===",
        "=== THE LEARNER'S QUESTION NOW ===\nА второй ответ точно верный?\n",
    ]
    positions = [prompt.index(part) for part in order]
    assert positions == sorted(positions)
    assert "A learner of Deutsch" in prompt
    assert prompt.endswith(
        "WRITE YOUR ENTIRE ANSWER IN Russian. Plain text only: no Markdown, no HTML, no\nheadings.",
    )
    # The headword is the submission, so the entry is not said to be about another word.
    assert "The entry is about" not in prompt


def test_a_card_without_an_article_chips_or_turns_leaves_those_parts_out():
    material = follow_up_material(
        submitted="reluctnt",
        question="Почему так?",
        analysis_html=RELUCTANT["analysis"],
        analysed_as="reluctant",
    )
    language = Language(code="en", name="English", deck="e", script="latin")

    prompt = follow_up_prompt(language, "Russian", material, locale="en")

    assert 'The entry is about: "reluctant"' in prompt
    for absent in ("The full entry", "Buttons under", "EARLIER QUESTIONS", "context the learner"):
        assert absent not in prompt


def test_the_sections_are_named_as_the_page_in_the_readers_locale_names_them():
    material = _material(AUFHEBEN)
    language = Language(code="de", name="Deutsch", deck="d", script="latin")

    prompt = follow_up_prompt(language, "Russian", material, locale="ru")

    for name in ("Разбор", "Кнопки под разбором", "Полная статья"):
        assert f"=== {name} ===\n" in prompt
        assert f"=== END OF {name} ===" in prompt
    assert "DEEPER" not in prompt


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_the_full_article_is_named_with_the_pages_own_heading(locale: str):
    page = (Path(__file__).parents[1] / "webapp" / "src" / "i18n" / f"{locale}.js").read_text(
        encoding="utf-8",
    )

    assert f'"add.detailSection": "{message("entry.detail", locale)}",' in page


def test_a_turn_without_its_reply_never_reaches_the_prompt():
    material = _material(
        RELUCTANT,
        exchanges=[Exchange("Первый вопрос?", "Ответ."), Exchange("Оборванный?", "  ")],
    )

    assert material.exchanges == (Exchange("Первый вопрос?", "Ответ."),)


def test_an_oversized_entry_is_refused_with_its_size_and_the_limit():
    long_reply = "а" * MAX_FOLLOW_UP_PROMPT_CHARS
    material = _material(RELUCTANT, exchanges=[Exchange("Вопрос?", long_reply)])
    language = Language(code="en", name="English", deck="e", script="latin")

    with pytest.raises(FollowUpRefusedError) as refused:
        follow_up_prompt(language, "Russian", material, locale="ru")

    assert refused.value.too_large
    assert f"не больше {MAX_FOLLOW_UP_PROMPT_CHARS}" in str(refused.value)


def test_the_endpoint_asks_the_pool_the_prompt_built_from_what_the_page_sent(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    languages: dict[str, Language],
):
    broker = FakeBroker(handles=[FakeHandle(["Во втором ", "примере…"], llm_name="pool-a")])
    _app_with(monkeypatch, broker)
    earlier = [{"question": "Что значит aufheben?", "answer": "Сохранять, поднимать, отменять."}]
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/words/0123abcd/ask",
            json=_body(AUFHEBEN, "А четвёртое значение?", exchanges=earlier),
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert _events(response.text) == [
        ("delta", {"text": "Во втором "}),
        ("delta", {"text": "примере…"}),
        ("done", {"model": "pool-a", "complete": True}),
    ]
    (call,) = broker.stream_calls
    material = _material(
        AUFHEBEN,
        "А четвёртое значение?",
        [Exchange("Что значит aufheben?", "Сохранять, поднимать, отменять.")],
    )
    assert call["prompt"] == follow_up_prompt(languages["de"], "Russian", material, locale="en")
    assert (call["operation"], call["trace_id"]) == ("vocab-de", "0123abcd-ask")
    assert broker.handles == []


def test_a_card_restored_after_a_restart_is_asked_about_without_the_server_knowing_it(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
):
    broker = FakeBroker(handles=[FakeHandle(["Ответ."])])
    _app_with(monkeypatch, broker)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/words/recent").json() == []
        response = client.post("/api/words/never-seen-here/ask", json=_body(RELUCTANT))

    assert response.status_code == 200
    assert _events(response.text)[-1][0] == "done"


def test_an_exhausted_pool_is_a_retryable_failure_and_never_a_paid_call(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
):
    exhausted = NoLLMAvailableError("every provider is out of quota", reason="quota")
    broker = FakeBroker(handles=[FakeHandle([], error=exhausted)])
    _app_with(monkeypatch, broker)
    with TestClient(create_app(settings)) as client:
        assert client.app.state.cascade.paid_refusal(client.app.state.languages["en"]) is None
        response = client.post(
            "/api/words/e1/ask",
            json=_body(RELUCTANT),
            headers={"Accept-Language": "ru"},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Сейчас ни одна модель не ответила. Спросите ещё раз через минуту."
    )
    assert broker.direct_calls == []


def test_a_pool_missing_its_budget_is_not_stepped_up_either(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
):
    missed = NoLLMAvailableError("nothing answered in time", reason="timeout")
    broker = FakeBroker(handles=[FakeHandle([], error=missed)])
    _app_with(monkeypatch, broker)
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/words/e1/ask", json=_body(RELUCTANT))

    assert response.status_code == 503
    assert broker.direct_calls == []


def test_a_reply_that_breaks_off_keeps_its_text_and_ends_in_a_retryable_error(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
):
    cut = InvalidProviderResponseError("the stream ended mid-answer", model="pool-a")
    broker = FakeBroker(handles=[FakeHandle(["Во втором примере ", "речь"], error=cut)])
    _app_with(monkeypatch, broker)
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/words/e1/ask", json=_body(RELUCTANT))

    assert response.status_code == 200
    assert _events(response.text) == [
        ("delta", {"text": "Во втором примере "}),
        ("delta", {"text": "речь"}),
        (
            "error",
            {
                "detail": "The reply broke off before it was finished. Ask again.",
                "retryable": True,
            },
        ),
    ]
    assert broker.direct_calls == []


def test_text_a_whole_answer_beat_is_withdrawn_before_that_answer_arrives(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
):
    won = lost_the_race("Целый ответ.", winner="pool-b", streamed="pool-a")
    broker = FakeBroker(handles=[FakeHandle(["Нача"], error=won, llm_name="pool-a")])
    _app_with(monkeypatch, broker)
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/words/e1/ask", json=_body(RELUCTANT))

    assert _events(response.text) == [
        ("delta", {"text": "Нача"}),
        ("reset", {}),
        ("delta", {"text": "Целый ответ."}),
        ("done", {"model": "pool-b", "complete": True}),
    ]


@pytest.mark.parametrize(
    ("question", "detail"),
    [
        ("   ", "Type a question."),
        ("?" * (MAX_QUESTION_CHARS + 1), f"no more than {MAX_QUESTION_CHARS} characters"),
    ],
)
def test_a_question_that_cannot_be_asked_is_refused_before_any_model_is(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    question: str,
    detail: str,
):
    broker = FakeBroker()
    _app_with(monkeypatch, broker)
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/words/e1/ask", json=_body(RELUCTANT, question))

    assert response.status_code == 400
    assert detail in response.json()["detail"]
    assert broker.stream_calls == []


@pytest.mark.parametrize("locale", ["en", "ru"])
def test_a_question_of_any_length_over_the_limit_gets_the_localized_refusal(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    locale: str,
):
    broker = FakeBroker()
    _app_with(monkeypatch, broker)
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/words/e1/ask",
            json=_body(RELUCTANT, "?" * (MAX_QUESTION_CHARS * 5)),
            headers={"Accept-Language": locale},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == message(
        "question.too_long",
        locale,
        limit=MAX_QUESTION_CHARS,
    )
    assert broker.stream_calls == []


def test_an_entry_too_long_to_ask_about_is_explained_before_any_model_is_asked(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
):
    broker = FakeBroker()
    _app_with(monkeypatch, broker)
    turns = [{"question": f"Вопрос {n}?", "answer": "ответ " * 1500} for n in range(5)]
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/words/e1/ask", json=_body(RELUCTANT, exchanges=turns))

    assert response.status_code == 413
    assert response.json()["detail"].startswith("This entry and its conversation are too long")
    assert f"no more than {MAX_FOLLOW_UP_PROMPT_CHARS}" in response.json()["detail"]
    assert broker.stream_calls == []


def test_a_language_the_server_does_not_have_is_refused(client: TestClient):
    response = client.post("/api/words/e1/ask", json=_body({**RELUCTANT, "lang": "fr"}))

    assert response.status_code == 400
    assert response.json()["detail"] == "Unknown language “fr” — pick one from the list."


def test_without_a_backend_the_question_is_a_retryable_failure(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
):
    def broken(*_args: object) -> object:
        raise RuntimeError("no keys")

    monkeypatch.setattr("echo_words.api.create_broker", broken)
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/words/e1/ask", json=_body(RELUCTANT))

    assert response.status_code == 503


def test_asking_touches_no_history_card_audio_article_or_status(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
):
    broker = FakeBroker(handles=[FakeHandle(["Ответ."])])
    _app_with(monkeypatch, broker)
    touched: list[str] = []

    async def boundary(*_args: object, **_kwargs: object) -> None:
        touched.append("reached")

    monkeypatch.setattr("echo_words.api.fetch_pronunciation", boundary)
    monkeypatch.setattr("echo_words.api.Wiktionary", lambda: SimpleNamespace(documents=boundary))
    monkeypatch.setattr("echo_words.api.Wikipedia", lambda: SimpleNamespace(usage=boundary))
    with TestClient(create_app(settings)) as client:
        anki = client.app.state.anki
        monkeypatch.setattr(anki, "add_note", boundary)
        monkeypatch.setattr(anki, "replace_note", boundary)
        monkeypatch.setattr(anki, "remove_note", boundary)
        events = []
        client.app.state.events.publish = lambda *args, **kwargs: events.append(args)
        response = client.post("/api/words/e1/ask", json=_body(AUFHEBEN))
        recent = client.get("/api/words/recent").json()
        cascade = client.app.state.cascade

    assert _events(response.text)[-1][0] == "done"
    assert touched == []
    assert events == []
    assert recent == []
    assert cascade.last_calls == {}
    assert cascade.calls_today == 0
    assert broker.direct_calls == []
    assert broker.attestation_calls == []


@pytest.mark.anyio
async def test_a_finished_reply_rates_the_pool_call_that_wrote_it(
    settings: Settings,
    languages: dict[str, Language],
):
    handle = FakeHandle(["Ответ."])
    cascade = fake_cascade(settings, handles=[handle])

    events = [
        event
        async for event in reply_events(
            cascade,
            "prompt",
            languages["en"],
            trace_id="e1-ask",
            locale="en",
        )
    ]

    assert [event.name for event in events] == ["delta", "done"]
    assert handle.scores == [1.0]


@pytest.mark.anyio
async def test_an_oversized_reply_is_cut_at_the_bound_and_said_to_be_incomplete(
    settings: Settings,
    languages: dict[str, Language],
):
    handle = FakeHandle(["а" * (MAX_COMPLETE_ANSWER_CHARS + 10)])
    cascade = fake_cascade(settings, handles=[handle])

    events = [
        event
        async for event in reply_events(
            cascade,
            "prompt",
            languages["en"],
            trace_id="e1-ask",
            locale="en",
        )
    ]

    assert sum(len(str(event.data.get("text", ""))) for event in events) == (
        MAX_COMPLETE_ANSWER_CHARS
    )
    assert events[-1].data == {"model": "pool-model", "complete": False}
    assert handle.scores == [0.0]


@pytest.mark.anyio
async def test_a_reader_who_leaves_mid_reply_frees_the_pool_stream(
    settings: Settings,
    languages: dict[str, Language],
):
    never = asyncio.Event()
    handle = FakeHandle(["Начало"], hold=never.wait)
    cascade = fake_cascade(settings, handles=[handle])
    pump = ReplyPump(
        reply_events(cascade, "prompt", languages["en"], trace_id="e1-ask", locale="en"),
    )

    first = await pump.next()
    await pump.aclose()

    assert first is not None
    assert first.data == {"text": "Начало"}
    assert handle.closed


REPLIES = RECORDED["replies"]


def _deltas(text: str, size: int = 37) -> list[str]:
    return [text[start : start + size] for start in range(0, len(text), size)]


@pytest.mark.parametrize(
    "fixture",
    [
        "follow-up-deeper-de-aufheben",
        "follow-up-ambiguous-en-reluctant",
        "follow-up-deeper-de-aufheben@run2",
        # The pool stopped after three tokens; the reader still gets exactly that.
        "follow-up-base-en-reluctant@run2",
    ],
)
def test_a_recorded_reply_reaches_the_page_exactly_as_the_pool_wrote_it(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    fixture: str,
):
    recorded = REPLIES[fixture]
    broker = FakeBroker(handles=[FakeHandle(_deltas(recorded["reply"]), llm_name="pool-a")])
    _app_with(monkeypatch, broker)
    entry = RECORDED["entries"][recorded["entry"]]
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/words/e1/ask", json=_body(entry, recorded["question"]))

    events = _events(response.text)
    assert (
        "".join(str(data["text"]) for name, data in events if name == "delta")
        == (recorded["reply"])
    )
    assert events[-1] == ("done", {"model": "pool-a", "complete": True})


@pytest.mark.parametrize("run", ["", "@run2"])
def test_a_second_turn_is_asked_with_the_recorded_first_reply_verbatim(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    run: str,
):
    first = REPLIES[f"follow-up-turn1-sr-drzati-rec{run}"]
    second = REPLIES[f"follow-up-turn2-sr-drzati-rec{run}"]
    assert second["earlier_turns"] == [{"question": first["question"], "answer": first["reply"]}]
    broker = FakeBroker(handles=[FakeHandle(_deltas(second["reply"]))])
    _app_with(monkeypatch, broker)
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/words/e1/ask",
            json=_body(DRZATI_REC, second["question"], exchanges=second["earlier_turns"]),
        )

    assert _events(response.text)[-1][0] == "done"
    (call,) = broker.stream_calls
    assert f"Question 1: {first['question']}\nYour answer 1: {first['reply']}\n" in call["prompt"]
    assert call["prompt"].index("Your answer 1:") < call["prompt"].index(second["question"])
