import asyncio
import json
from collections.abc import AsyncIterator, Iterable

from fakes import FakeDirectClient, FakeHandle, fake_cascade

from echo_words import pipeline as pipeline_module
from echo_words.anki import Added, MisconfiguredNoteTypeError
from echo_words.broker import BackendError
from echo_words.events import Event, EventHub
from echo_words.pipeline import (
    ADDED_STATUS,
    ANALYSIS_FAILED_CODE,
    CARD_FAILED_STATUS,
    LOOKUP_ONLY_STATUS,
    TEXT_STATUS,
    WordPipeline,
)
from echo_words.prompt import MAX_COMPLETE_ANSWER_CHARS

pytest = __import__("pytest")
pytestmark = pytest.mark.anyio


class Completion:
    def __init__(  # noqa: PLR0913 - stream timing controls keep race tests explicit.
        self,
        deltas: Iterable[str],
        *,
        error: Exception | None = None,
        gate: asyncio.Event | None = None,
        started: asyncio.Event | None = None,
        reset_after: int | None = None,
        gate_after: int | None = None,
    ) -> None:
        self.deltas = list(deltas)
        self.error = error
        self.gate = gate
        self.started = started
        self.reset_after = reset_after
        self.gate_after = gate_after
        self.on_reset = None
        self.closed = False
        self.scores: list[float] = []

    def __aiter__(self) -> AsyncIterator[str]:
        return self.stream()

    async def stream(self) -> AsyncIterator[str]:
        if self.started is not None:
            self.started.set()
        for index, delta in enumerate(self.deltas, start=1):
            yield delta
            if index == self.reset_after:
                await self.on_reset()
            if self.gate is not None and index == self.gate_after:
                await self.gate.wait()
        if self.gate is not None and self.gate_after is None:
            await self.gate.wait()
        if self.error is not None:
            raise self.error

    async def aclose(self) -> None:
        self.closed = True

    async def record_quality(self, score: float) -> None:
        self.scores.append(score)


class ScriptedCascade:
    def __init__(self, completions: Iterable[Completion], *, refusal: str | None = None) -> None:
        self.completions = list(completions)
        self.calls: list[str] = []
        self.prompts: list[str] = []
        self.trace_ids: list[str | None] = []
        self.active = 0
        self.max_active = 0
        self.refusal = refusal
        self.paid_calls = 0
        self.usable_checks: list[object] = []

    def stream_completion(self, prompt, language, *, trace_id=None, on_reset=None, usable=None):
        self.calls.append(language.code)
        self.prompts.append(prompt)
        self.trace_ids.append(trace_id)
        self.usable_checks.append(usable)
        completion = self.completions.pop(0)
        completion.on_reset = on_reset
        original = completion.stream

        async def tracked():
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            try:
                async for delta in original():
                    yield delta
            finally:
                self.active -= 1

        completion.stream = tracked
        return completion

    def stream_paid(self, prompt, language, *, trace_id=None):
        if self.refusal is not None:
            raise BackendError(self.refusal)
        self.paid_calls += 1
        return self.stream_completion(prompt, language, trace_id=trace_id)

    def paid_refusal(self, _language):
        return self.refusal

    async def refresh_paid_availability(self, _language):
        return self.refusal


def drain(queue: asyncio.Queue[Event]) -> list[Event]:
    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    return events


async def test_deltas_are_throttled_cut_sanitized_and_finished(languages):
    times = iter([0.0, 0.1, 0.2, 0.3, 0.4])
    cascade = ScriptedCascade(
        [Completion(["<b>W", "ord</b> & meaning", "===CA", "RD===", '{"word":"Word"}'])],
    )
    hub = EventHub()
    pipeline = WordPipeline(cascade, target_lang="ru", events=hub, clock=lambda: next(times))
    pipeline.start()
    try:
        async with hub.subscribe() as subscriber:
            entry = await pipeline.enqueue(languages["en"], "Word", False)
            await pipeline.join()
            events = drain(subscriber)
        updates = [event.data["text"] for event in events if event.name == "update"]
        assert updates == ["<b>W</b>", "<b>Word</b> &amp; meaning"]
        assert events[-1] == Event(
            "done",
            {
                "entry_id": entry.entry_id,
                "text": "<b>Word</b> &amp; meaning",
                "suggestion": None,
                "shown_spelling": "Word",
                "card_status": CARD_FAILED_STATUS,
                "card_kinds": [],
                "card_error": None,
                "no_audio": True,
                "no_card_audio": False,
                "segments": [],
                "segment_kind": None,
                "shape": None,
                "audio_url": None,
                "context_audio_url": None,
                "model": None,
                "detail_available": False,
                "correction_reversed": False,
            },
        )
    finally:
        await pipeline.close()


async def test_a_backend_error_keeps_partial_text_and_publishes_a_safe_hint(languages):
    cascade = ScriptedCascade([Completion(["partial"], error=BackendError("secret"))])
    hub = EventHub()
    pipeline = WordPipeline(cascade, target_lang="ru", events=hub)
    pipeline.start()
    try:
        async with hub.subscribe() as subscriber:
            entry = await pipeline.enqueue(languages["en"], "word", False)
            await pipeline.join()
            events = drain(subscriber)
        assert entry.text == "partial"
        assert entry.status == "error"
        assert events[-1] == Event(
            "error",
            {"entry_id": entry.entry_id, "code": ANALYSIS_FAILED_CODE},
        )
    finally:
        await pipeline.close()


async def test_card_parse_quality_and_suggestion_are_published_after_completion(languages):
    completion = Completion(
        [
            "analysis===CARD===",
            '{"kind":"unit","word":"recieve","word_relation":"typo",',
            '"suggestion":"receive","meanings":',
            '[{"label":"","translations":["получать"],"examples":',
            '[{"text":"I recieve it.","translation":"Я получаю это.",',
            '"highlighted":"I <b>recieve</b> it.","gapped":"I ___ it."}]}],"segments":[]}',
        ],
    )
    cascade = ScriptedCascade([completion])
    hub = EventHub()
    pipeline = WordPipeline(cascade, target_lang="ru", events=hub)
    pipeline.start()
    try:
        async with hub.subscribe() as subscriber:
            entry = await pipeline.enqueue(languages["en"], "recieve", False)
            await pipeline.join()
            events = drain(subscriber)
        assert completion.scores == [1.0]
        assert events[-1] == Event(
            "done",
            {
                "entry_id": entry.entry_id,
                "text": "analysis",
                "suggestion": "receive",
                "shown_spelling": "recieve",
                "card_status": CARD_FAILED_STATUS,
                "card_kinds": [],
                "card_error": None,
                "no_audio": True,
                "no_card_audio": False,
                "segments": [
                    {
                        "label": "recieve",
                        "reason": "получать",
                        "context": "I recieve it.",
                    },
                ],
                "segment_kind": "senses",
                "shape": "unit",
                "audio_url": None,
                "context_audio_url": None,
                "model": None,
                "detail_available": True,
                "correction_reversed": False,
            },
        )
    finally:
        await pipeline.close()


async def test_card_without_examples_is_rated_as_a_failure_without_losing_analysis(languages):
    completion = Completion(
        [
            "analysis===CARD===",
            '{"kind":"unit","word":"word","word_relation":"same",',
            '"suggestion":"","meanings":[{"label":"",',
            '"translations":["слово"],"examples":[]}],"segments":[]}',
        ],
    )
    cascade = ScriptedCascade([completion])
    hub = EventHub()
    pipeline = WordPipeline(cascade, target_lang="ru", events=hub)
    pipeline.start()
    try:
        async with hub.subscribe() as subscriber:
            entry = await pipeline.enqueue(languages["en"], "word", False)
            await pipeline.join()
            events = drain(subscriber)
        assert completion.scores == [0.0]
        assert entry.status == "done"
        assert events[-1] == Event(
            "done",
            {
                "entry_id": entry.entry_id,
                "text": "analysis",
                "suggestion": None,
                "shown_spelling": "word",
                "card_status": CARD_FAILED_STATUS,
                "card_kinds": [],
                "card_error": None,
                "no_audio": True,
                "no_card_audio": False,
                "segments": [],
                "segment_kind": None,
                "shape": None,
                "audio_url": None,
                "context_audio_url": None,
                "model": None,
                "detail_available": False,
                "correction_reversed": False,
            },
        )
    finally:
        await pipeline.close()


class RecordingAnki:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def add_note(self, note, deck, audio_path=None):
        self.calls.append((note, deck, audio_path))
        return self.result

    async def remove_note(self, _note_id, _media_filename=None):
        return None


def example(word, *, translation="Перевод."):
    return {
        "text": f"Use {word} now.",
        "translation": translation,
        "highlighted": f"Use <b>{word}</b> now.",
        "gapped": "Use ___ now.",
    }


def valid_card(word, *, segments=None, context=None, word_relation="same"):
    meanings = None
    if context is not None:
        meanings = [
            {
                "label": "",
                "translations": ["перевод"],
                "examples": [
                    {
                        "text": context,
                        "translation": "Перевод.",
                        "highlighted": _highlighted_context(word, context),
                        "gapped": _gapped_context(word, context),
                    },
                ],
            },
        ]
    return card_with(
        word,
        meanings=meanings,
        segments=segments or [],
        word_relation=word_relation,
    )


def _highlighted_context(word, context):
    if "steht" in context and "auf" in context and word == "aufstehen":
        return context.replace("steht", "<b>steht</b>").replace("auf.", "<b>auf</b>.")
    surface = "gave up" if word == "give up" and "gave up" in context else word
    return context.replace(surface, f"<b>{surface}</b>")


def _gapped_context(word, context):
    if "steht" in context and "auf" in context and word == "aufstehen":
        return context.replace("steht", "___").replace("auf.", "___.")
    surface = "gave up" if word == "give up" and "gave up" in context else word
    return context.replace(surface, "___")


TWO_MEANINGS = [
    {
        "label": "учреждение",
        "translations": ["банк"],
        "examples": [
            {
                "text": "The bank opens at nine.",
                "translation": "Банк открывается в девять.",
                "highlighted": "The <b>bank</b> opens at nine.",
                "gapped": "The ___ opens at nine.",
            },
        ],
    },
    {
        "label": "берег",
        "translations": ["берег"],
        "examples": [
            {
                "text": "We sat on the bank.",
                "translation": "Мы сидели на берегу.",
                "highlighted": "We sat on the <b>bank</b>.",
                "gapped": "We sat on the ___.",
            },
        ],
    },
]


def card_with(word, meanings=None, **fields):
    answer = {
        "kind": "unit",
        "word": word,
        "word_relation": "same",
        "suggestion": "",
        "meanings": meanings
        or [
            {
                "label": "",
                "translations": ["перевод"],
                "examples": [example(word)],
            },
        ],
        "segments": [],
        **fields,
    }
    return f"analysis===CARD==={json.dumps(answer, ensure_ascii=False)}"


async def stored_note(languages, answer, anki, **submission):
    pipeline = WordPipeline(ScriptedCascade([Completion([answer])]), target_lang="ru", anki=anki)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "bank", False, **submission)
        await pipeline.join()
    finally:
        await pipeline.close()
    return entry


async def test_context_sense_selects_one_note_and_every_sense_stays_a_chip(languages):
    kinds = ("Recognition", "Recall", "ContextRecognition", "ContextProduction")
    anki = RecordingAnki(Added(1, None, kinds))
    answer = card_with("bank", meanings=TWO_MEANINGS, context_sense=1)

    entry = await stored_note(
        languages,
        answer,
        anki,
        context="We sat on the bank.",
        intent="unit",
    )

    note = anki.calls[0][0]
    assert note.word == "bank"
    assert note.sense == 1
    assert note.meaning.translations == ["берег"]
    assert entry.segment_kind == "senses"
    assert entry.segments == [
        {
            "label": "bank",
            "reason": "банк",
            "context": "The bank opens at nine.",
        },
        {
            "label": "bank",
            "reason": "берег",
            "context": "We sat on the bank.",
        },
    ]


async def test_one_meaning_keeps_the_context_example_and_all_four_cards(languages):
    kinds = ("Recognition", "Recall", "ContextRecognition", "ContextProduction")
    anki = RecordingAnki(Added(1, None, kinds))
    context_example = {
        "text": "The bank opens at nine.",
        "translation": "Банк открывается в девять.",
        "highlighted": "The <b>bank</b> opens at nine.",
        "gapped": "The ___ opens at nine.",
    }
    answer = card_with(
        "bank",
        meanings=[{"label": "", "translations": ["банк"], "examples": [context_example]}],
        context_sense=0,
    )

    entry = await stored_note(
        languages,
        answer,
        anki,
        context="The bank opens at nine.",
        intent="unit",
    )

    assert anki.calls[0][0].meaning.examples[0].text == "The bank opens at nine."
    assert entry.card_status == ADDED_STATUS
    assert entry.card_kinds == list(kinds)


async def test_an_unusable_context_sense_falls_back_to_the_first(languages):
    anki = RecordingAnki(Added(1, None))
    answer = card_with("bank", meanings=TWO_MEANINGS, context_sense=7)

    await stored_note(
        languages,
        answer,
        anki,
        context="The bank opens at nine.",
        intent="unit",
    )

    assert anki.calls[0][0].sense == 0


async def test_a_sense_sentence_within_the_context_bound_is_kept_exactly(languages):
    long_example = "The bank opens at nine " + " ".join(["and closes at five"] * 10)
    meanings = [
        {
            "label": "учреждение",
            "translations": ["банк"],
            "examples": [
                {
                    "text": long_example,
                    "translation": "Банк.",
                    "highlighted": long_example.replace("bank", "<b>bank</b>", 1),
                    "gapped": long_example.replace("bank", "___", 1),
                },
            ],
        },
        TWO_MEANINGS[1],
    ]
    anki = RecordingAnki(Added(1, None))
    answer = card_with("bank", meanings=meanings, context_sense=1)

    entry = await stored_note(languages, answer, anki, intent="unit")

    assert 120 < len(long_example) <= 500
    assert entry.segments[0]["context"] == long_example
    assert entry.segments[1]["context"] == "We sat on the bank."


async def test_a_sense_sentence_beyond_the_context_bound_falls_back_to_bare_lookup(
    languages,
):
    long_example = "The bank " + "stays open " * 50
    answer = card_with(
        "bank",
        meanings=[
            {
                "label": "",
                "translations": ["банк"],
                "examples": [
                    {
                        "text": long_example,
                        "translation": "Банк.",
                        "highlighted": long_example.replace("bank", "<b>bank</b>", 1),
                        "gapped": long_example.replace("bank", "___", 1),
                    },
                ],
            },
        ],
    )

    entry = await stored_note(
        languages,
        answer,
        RecordingAnki(Added(1, None)),
        intent="unit",
    )

    assert len(long_example) > 500
    assert entry.segments[0]["context"] == ""


async def test_the_status_names_all_four_kinds_the_collection_made(languages):
    kinds = ("Recognition", "Recall", "ContextRecognition", "ContextProduction")
    anki = RecordingAnki(Added(1, None, kinds))
    hub = EventHub()
    pipeline = WordPipeline(
        ScriptedCascade([Completion([card_with("bank", meanings=TWO_MEANINGS)])]),
        target_lang="ru",
        events=hub,
        anki=anki,
    )
    pipeline.start()
    try:
        async with hub.subscribe() as subscriber:
            entry = await pipeline.enqueue(languages["en"], "bank", False, intent="unit")
            await pipeline.join()
            events = drain(subscriber)
    finally:
        await pipeline.close()

    done = [event for event in events if event.name == "done"][-1]
    assert done.data["card_status"] == "added"
    assert done.data["card_kinds"] == list(kinds)
    assert entry.card_kinds == list(kinds)
    assert entry.public()["card_kinds"] == list(kinds)


async def test_a_rebuild_retains_unit_intent_and_replaces_with_the_returned_headword(languages):
    kinds = ("Recognition", "Recall", "ContextRecognition", "ContextProduction")
    anki = MutableAnki([Added(1, None, kinds), Added(2, None, kinds)])
    cascade = ScriptedCascade(
        [
            Completion(
                [
                    valid_card(
                        "give up",
                        context="She gave up yesterday.",
                        word_relation="morphology",
                    ),
                ],
            ),
            Completion(
                [
                    valid_card(
                        "give up",
                        context="She gave up yesterday.",
                        word_relation="morphology",
                    ),
                ],
            ),
        ],
    )
    pipeline = WordPipeline(cascade, target_lang="ru", anki=anki)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(
            languages["en"],
            "gave up",
            False,
            intent="unit",
            context="She gave up yesterday.",
        )
        await pipeline.join()
        await pipeline.request_rebuild(entry.entry_id)
        await pipeline.join()
    finally:
        await pipeline.close()

    assert "kind must be unit" in cascade.prompts[0]
    assert "kind must be unit" in cascade.prompts[1]
    assert anki.calls[0][0].word == "give up"
    assert anki.replaced[0][1].word == "give up"
    assert entry.word == "gave up"


async def test_a_set_expression_makes_one_note_and_offers_its_component_words(languages):
    anki = RecordingAnki(Added(1, None))
    answer = valid_card(
        "kick the bucket",
        segments=[
            {"label": "kick", "surface": "kick", "why": "глагол"},
            {"label": "the", "surface": "the", "why": "артикль"},
            {"label": "bucket", "surface": "bucket", "why": "существительное"},
        ],
    )
    pipeline = WordPipeline(ScriptedCascade([Completion([answer])]), target_lang="ru", anki=anki)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "kick the bucket", False)
        await pipeline.join()
    finally:
        await pipeline.close()

    assert len(anki.calls) == 1
    assert entry.segment_kind == "expression"
    assert [segment["label"] for segment in entry.segments] == ["kick", "the", "bucket"]
    assert {segment["context"] for segment in entry.segments} == {"Use kick the bucket now."}


async def test_an_inflected_single_word_uses_the_returned_dictionary_headword(languages):
    anki = RecordingAnki(Added(1, None))
    pipeline = WordPipeline(
        ScriptedCascade(
            [Completion([valid_card("одржавати", word_relation="morphology")])],
        ),
        target_lang="ru",
        anki=anki,
    )
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["sr"], "одржава", False, intent="unit")
        await pipeline.join()
    finally:
        await pipeline.close()

    assert [note.word for note, *_ in anki.calls] == ["одржавати"]
    assert entry.word == "одржава"
    assert entry.card_status == ADDED_STATUS
    assert entry.segment_kind == "senses"


async def test_lookup_only_skips_anki_and_reports_it_in_done(languages):
    anki = RecordingAnki(Added(1, None))
    hub = EventHub()
    pipeline = WordPipeline(
        ScriptedCascade(
            [Completion([valid_card("word", word_relation="morphology")])],
        ),
        target_lang="ru",
        events=hub,
        anki=anki,
    )
    pipeline.start()
    try:
        async with hub.subscribe() as subscriber:
            entry = await pipeline.enqueue(languages["en"], "word", True)
            await pipeline.join()
            events = drain(subscriber)
        assert anki.calls == []
        assert entry.card_status == LOOKUP_ONLY_STATUS
        assert entry.no_audio is True
        assert events[-1].data["card_status"] == LOOKUP_ONLY_STATUS
        assert events[-1].data["no_audio"] is True
        assert events[-1].data["no_card_audio"] is False
    finally:
        await pipeline.close()


async def test_lookup_only_unit_has_detail_but_no_card_to_rebuild(languages):
    pipeline = WordPipeline(
        ScriptedCascade([Completion([valid_card("word")])]),
        target_lang="ru",
    )
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "word", True)
        await pipeline.join()

        assert entry.detail_available is True
        with pytest.raises(BackendError, match="no card to rebuild"):
            await pipeline.request_rebuild(entry.entry_id)
    finally:
        await pipeline.close()


async def test_an_added_note_becomes_the_done_status(languages):
    anki = RecordingAnki(Added(10, None))
    hub = EventHub()
    pipeline = WordPipeline(
        ScriptedCascade([Completion([valid_card("word")])]),
        target_lang="ru",
        events=hub,
        anki=anki,
    )
    pipeline.start()
    try:
        async with hub.subscribe() as subscriber:
            entry = await pipeline.enqueue(languages["en"], "word", False)
            await pipeline.join()
            events = drain(subscriber)
        assert len(anki.calls) == 1
        assert anki.calls[0][1] == "English::Vocabulary"
        assert entry.card_status == ADDED_STATUS
        assert entry.no_audio is True
        assert events[-1].data["card_status"] == ADDED_STATUS
        assert events[-1].data["no_audio"] is True
    finally:
        await pipeline.close()


async def test_audio_is_speculative_used_once_and_attached_to_the_note(languages, tmp_path):
    release_completion = asyncio.Event()
    completion_started = asyncio.Event()
    audio_started = asyncio.Event()
    audio_calls = []
    audio_path = tmp_path / "pronunciation-aabbccddeeff00112233.mp3"
    audio_path.write_bytes(b"audio")

    async def fetch_audio(word, language):
        audio_calls.append((word, language.code))
        audio_started.set()
        return audio_path

    anki = RecordingAnki(Added(10, "media.mp3"))
    hub = EventHub()
    pipeline = WordPipeline(
        ScriptedCascade(
            [
                Completion(
                    [valid_card("word")],
                    gate=release_completion,
                    started=completion_started,
                ),
            ],
        ),
        target_lang="ru",
        events=hub,
        anki=anki,
        audio=fetch_audio,
    )
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "word", False)
        await completion_started.wait()
        await audio_started.wait()
        release_completion.set()
        await pipeline.join()

        assert audio_calls == [("word", "en")]
        assert anki.calls[0][2] == audio_path
        assert entry.audio_url == f"/api/audio/{audio_path.name}"
        assert entry.card_status == ADDED_STATUS
    finally:
        await pipeline.close()


async def test_card_audio_uses_the_returned_headword_without_replacing_pwa_audio(
    languages,
    tmp_path,
):
    submitted_audio = tmp_path / "submitted.mp3"
    context_audio = tmp_path / "context.mp3"
    card_audio = tmp_path / "card.mp3"
    for path in (submitted_audio, context_audio, card_audio):
        path.write_bytes(b"audio")
    paths = {
        "gave up": submitted_audio,
        "She gave up yesterday.": context_audio,
        "give up": card_audio,
    }
    audio_calls = []

    async def fetch_audio(text, _language):
        audio_calls.append(text)
        return paths[text]

    anki = RecordingAnki(Added(10, "media.mp3"))
    pipeline = WordPipeline(
        ScriptedCascade(
            [
                Completion(
                    [
                        valid_card(
                            "give up",
                            context="She gave up yesterday.",
                            word_relation="morphology",
                        ),
                    ],
                ),
            ],
        ),
        target_lang="ru",
        anki=anki,
        audio=fetch_audio,
    )
    pipeline.start()
    try:
        entry = await pipeline.enqueue(
            languages["en"],
            "gave up",
            False,
            intent="unit",
            context="She gave up yesterday.",
        )
        await pipeline.join()
    finally:
        await pipeline.close()

    assert sorted(audio_calls) == sorted(paths)
    assert entry.word == "gave up"
    assert entry.audio_url == f"/api/audio/{submitted_audio.name}"
    assert entry.context_audio_url == f"/api/audio/{context_audio.name}"
    note, _deck, stored_audio = anki.calls[0]
    assert note.word == "give up"
    assert stored_audio == card_audio
    assert entry.no_audio is False
    assert entry.no_card_audio is False


async def test_three_hanging_audio_roles_use_one_shared_wait_budget(  # noqa: PLR0915
    languages,
    monkeypatch,
    caplog,
):
    context = "She gave up yesterday."
    started = []
    cancelled = []
    blocked = asyncio.Event()
    release = asyncio.Event()
    finished = asyncio.Event()
    finished_count = 0
    waits = []

    async def fetch_audio(text, _language):
        nonlocal finished_count
        started.append(text)
        try:
            await blocked.wait()
        except asyncio.CancelledError:
            cancelled.append(text)
            await release.wait()
            raise RuntimeError(f"late audio failure: {text}") from None
        finally:
            finished_count += 1
            if finished_count == 3:
                finished.set()

    async def record_wait(tasks, *, timeout):
        pending = set(tasks)
        while len(started) < len(pending):
            await asyncio.sleep(0)
        waits.append((sorted(task.get_name() for task in pending), timeout))
        return set(), pending

    monkeypatch.setattr(pipeline_module.asyncio, "wait", record_wait)
    anki = RecordingAnki(Added(10, None))
    pipeline = WordPipeline(
        ScriptedCascade(
            [
                Completion(
                    [
                        valid_card(
                            "give up",
                            context=context,
                            word_relation="morphology",
                        ),
                    ],
                ),
            ],
        ),
        target_lang="ru",
        anki=anki,
        audio=fetch_audio,
        audio_timeout=4.25,
    )
    pipeline.start()
    try:
        entry = await pipeline.enqueue(
            languages["en"],
            "gave up",
            False,
            intent="unit",
            context=context,
        )
        await pipeline.join()
        release.set()
        await finished.wait()
        await asyncio.sleep(0)
    finally:
        release.set()
        await pipeline.close()

    assert sorted(started) == sorted(["gave up", context, "give up"])
    assert sorted(cancelled) == sorted(started)
    assert len(waits) == 1
    names, timeout = waits[0]
    assert len(names) == 3
    assert any(name.startswith("echo-words-audio-") for name in names)
    assert any(name.startswith("echo-words-context-audio-") for name in names)
    assert any(name.startswith("echo-words-card-audio-") for name in names)
    assert timeout == 4.25
    assert entry.status == "done"
    assert entry.no_audio is True
    assert entry.no_card_audio is True
    assert anki.calls[0][2] is None
    consumed = [
        record
        for record in caplog.records
        if record.getMessage() == "abandoned pronunciation task failed"
    ]
    assert len(consumed) == 3
    assert all(
        record.exc_info is not None and str(record.exc_info[1]).startswith("late audio failure:")
        for record in consumed
    )


async def test_an_nfc_equivalent_headword_reuses_submitted_audio(languages, tmp_path):
    decomposed = "cafe\N{COMBINING ACUTE ACCENT}"
    composed = "caf\N{LATIN SMALL LETTER E WITH ACUTE}"
    submitted_audio = tmp_path / "submitted.mp3"
    submitted_audio.write_bytes(b"audio")
    audio_calls = []

    async def fetch_audio(text, _language):
        audio_calls.append(text)
        return submitted_audio

    anki = RecordingAnki(Added(10, "media.mp3"))
    pipeline = WordPipeline(
        ScriptedCascade([Completion([valid_card(composed)])]),
        target_lang="ru",
        anki=anki,
        audio=fetch_audio,
    )
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], decomposed, False, intent="unit")
        await pipeline.join()
    finally:
        await pipeline.close()

    assert audio_calls == [decomposed]
    assert entry.audio_url == f"/api/audio/{submitted_audio.name}"
    note, _deck, stored_audio = anki.calls[0]
    assert note.word == composed
    assert stored_audio == submitted_audio


async def test_a_case_changed_headword_fetches_distinct_card_audio(languages, tmp_path):
    submitted_audio = tmp_path / "submitted.mp3"
    card_audio = tmp_path / "card.mp3"
    for path in (submitted_audio, card_audio):
        path.write_bytes(b"audio")
    paths = {"Word": submitted_audio, "word": card_audio}
    audio_calls = []

    async def fetch_audio(text, _language):
        audio_calls.append(text)
        return paths[text]

    anki = RecordingAnki(Added(10, "media.mp3"))
    pipeline = WordPipeline(
        ScriptedCascade(
            [Completion([valid_card("word", word_relation="morphology")])],
        ),
        target_lang="ru",
        anki=anki,
        audio=fetch_audio,
    )
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "Word", False, intent="unit")
        await pipeline.join()
    finally:
        await pipeline.close()

    assert sorted(audio_calls) == ["Word", "word"]
    assert entry.audio_url == f"/api/audio/{submitted_audio.name}"
    assert anki.calls[0][2] == card_audio


async def test_returned_headword_audio_failure_is_distinct_from_submitted_audio_success(
    languages,
    tmp_path,
):
    submitted_audio = tmp_path / "submitted.mp3"
    submitted_audio.write_bytes(b"audio")

    async def fetch_audio(text, _language):
        return submitted_audio if text == "gave up" else None

    anki = RecordingAnki(Added(10, None))
    pipeline = WordPipeline(
        ScriptedCascade(
            [Completion([valid_card("give up", word_relation="morphology")])],
        ),
        target_lang="ru",
        anki=anki,
        audio=fetch_audio,
    )
    pipeline.start()
    try:
        entry = await pipeline.enqueue(
            languages["en"],
            "gave up",
            False,
            intent="unit",
        )
        await pipeline.join()
    finally:
        await pipeline.close()

    assert entry.audio_url == f"/api/audio/{submitted_audio.name}"
    assert entry.no_audio is False
    assert entry.no_card_audio is True
    assert anki.calls[0][2] is None


async def test_delayed_headword_audio_cannot_hold_card_storage_or_done(languages, tmp_path):
    submitted_audio = tmp_path / "submitted.mp3"
    submitted_audio.write_bytes(b"audio")
    card_cancelled = asyncio.Event()

    async def fetch_audio(text, _language):
        if text == "gave up":
            return submitted_audio
        try:
            await asyncio.Event().wait()
        finally:
            card_cancelled.set()

    anki = RecordingAnki(Added(10, None))
    pipeline = WordPipeline(
        ScriptedCascade(
            [Completion([valid_card("give up", word_relation="morphology")])],
        ),
        target_lang="ru",
        anki=anki,
        audio=fetch_audio,
        audio_timeout=0.01,
    )
    pipeline.start()
    try:
        entry = await pipeline.enqueue(
            languages["en"],
            "gave up",
            False,
            intent="unit",
        )
        await asyncio.wait_for(pipeline.join(), timeout=0.2)
    finally:
        await pipeline.close()

    assert card_cancelled.is_set()
    assert entry.status == "done"
    assert entry.card_status == ADDED_STATUS
    assert entry.no_audio is False
    assert entry.no_card_audio is True
    assert anki.calls[0][2] is None


async def test_failing_headword_tts_still_stores_and_finishes(languages, tmp_path):
    submitted_audio = tmp_path / "submitted.mp3"
    submitted_audio.write_bytes(b"audio")

    async def fetch_audio(text, _language):
        if text == "gave up":
            return submitted_audio
        raise RuntimeError("tts failed")

    anki = RecordingAnki(Added(10, None))
    pipeline = WordPipeline(
        ScriptedCascade(
            [Completion([valid_card("give up", word_relation="morphology")])],
        ),
        target_lang="ru",
        anki=anki,
        audio=fetch_audio,
    )
    pipeline.start()
    try:
        entry = await pipeline.enqueue(
            languages["en"],
            "gave up",
            False,
            intent="unit",
        )
        await asyncio.wait_for(pipeline.join(), timeout=0.2)
    finally:
        await pipeline.close()

    assert entry.status == "done"
    assert entry.card_status == ADDED_STATUS
    assert entry.no_card_audio is True
    assert anki.calls[0][2] is None


async def test_audio_deadline_cancels_a_wedged_task_and_does_not_stall_done(languages):
    cancelled = asyncio.Event()
    release = asyncio.Event()
    exited = asyncio.Event()

    async def wedged_audio(_word, _language):
        try:
            while not release.is_set():
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    cancelled.set()
        finally:
            exited.set()

    hub = EventHub()
    pipeline = WordPipeline(
        ScriptedCascade([Completion([valid_card("word")])]),
        target_lang="ru",
        events=hub,
        audio=wedged_audio,
        audio_timeout=0.01,
    )
    pipeline.start()
    try:
        async with hub.subscribe() as subscriber:
            entry = await pipeline.enqueue(languages["en"], "word", False)
            await asyncio.wait_for(pipeline.join(), timeout=0.2)
            events = drain(subscriber)

        assert cancelled.is_set()
        assert entry.status == "done"
        assert entry.audio_url is None
        assert entry.card_status == CARD_FAILED_STATUS
        assert entry.no_audio is True
        assert events[-1].data["audio_url"] is None
    finally:
        release.set()
        await asyncio.wait_for(exited.wait(), timeout=0.2)
        await pipeline.close()


async def test_a_misconfigured_note_type_is_a_clear_done_status_not_a_lost_answer(languages):
    class MisconfiguredAnki:
        async def add_note(self, _note, _deck, _audio_path=None):
            raise MisconfiguredNoteTypeError

    hub = EventHub()
    pipeline = WordPipeline(
        ScriptedCascade([Completion([valid_card("word")])]),
        target_lang="ru",
        events=hub,
        anki=MisconfiguredAnki(),
    )
    pipeline.start()
    try:
        async with hub.subscribe() as subscriber:
            entry = await pipeline.enqueue(languages["en"], "word", False)
            await pipeline.join()
            events = drain(subscriber)
        expected = "note type EchoWords is misconfigured — fix or delete it in Anki"
        assert entry.status == "done"
        assert entry.text == "analysis"
        assert entry.card_status == CARD_FAILED_STATUS
        assert entry.card_error == expected
        assert events[-1].data["card_status"] == CARD_FAILED_STATUS
        assert events[-1].data["card_error"] == expected
    finally:
        await pipeline.close()


async def test_a_backend_error_publishes_the_latest_throttled_partial(languages):
    cascade = ScriptedCascade(
        [Completion(["part", "ial"], error=BackendError("secret"))],
    )
    hub = EventHub()
    pipeline = WordPipeline(
        cascade,
        target_lang="ru",
        events=hub,
        clock=iter([0.0, 0.1]).__next__,
    )
    pipeline.start()
    try:
        async with hub.subscribe() as subscriber:
            entry = await pipeline.enqueue(languages["en"], "word", False)
            await pipeline.join()
            events = drain(subscriber)
        assert entry.text == "partial"
        assert [event.data["text"] for event in events if event.name == "update"] == [
            "part",
            "partial",
        ]
        assert events[-1].name == "error"
    finally:
        await pipeline.close()


async def test_a_paid_step_reset_discards_the_pool_partial_before_continuing(languages):
    cascade = ScriptedCascade([Completion(["pool half", "paid answer"], reset_after=1)])
    hub = EventHub()
    pipeline = WordPipeline(cascade, target_lang="ru", events=hub, clock=iter([0.0, 1.0]).__next__)
    pipeline.start()
    try:
        async with hub.subscribe() as subscriber:
            entry = await pipeline.enqueue(languages["en"], "word", False)
            await pipeline.join()
            events = drain(subscriber)
        assert entry.text == "paid answer"
        assert [event.name for event in events] == [
            "accepted",
            "update",
            "reset",
            "update",
            "done",
        ]
    finally:
        await pipeline.close()


async def test_two_registered_words_run_once_at_a_time_in_fifo_order(languages):
    release_first = asyncio.Event()
    first_started = asyncio.Event()
    cascade = ScriptedCascade(
        [
            Completion(["first"], gate=release_first, started=first_started),
            Completion(["second"]),
        ],
    )
    pipeline = WordPipeline(cascade, target_lang="ru")
    pipeline.start()
    try:
        first = await pipeline.enqueue(languages["en"], "first", False)
        second = await pipeline.enqueue(languages["sr"], "други", False)
        assert [item["entry_id"] for item in pipeline.recent()] == [
            second.entry_id,
            first.entry_id,
        ]
        await first_started.wait()
        await asyncio.sleep(0)
        assert cascade.calls == ["en"]
        release_first.set()
        await pipeline.join()
        assert cascade.calls == ["en", "sr"]
        assert cascade.max_active == 1
    finally:
        await pipeline.close()


async def test_history_overflow_keeps_queued_entries_and_the_worker_alive(languages):
    release_first = asyncio.Event()
    first_started = asyncio.Event()
    cascade = ScriptedCascade(
        [
            Completion(["first"], gate=release_first, started=first_started),
            Completion(["second"]),
            Completion(["third"]),
        ],
    )
    pipeline = WordPipeline(cascade, target_lang="ru", history_size=1)
    pipeline.start()
    try:
        first = await pipeline.enqueue(languages["en"], "first", False)
        await first_started.wait()
        second = await pipeline.enqueue(languages["en"], "second", False)

        assert [item["entry_id"] for item in pipeline.recent()] == [
            second.entry_id,
            first.entry_id,
        ]
        release_first.set()
        await pipeline.join()

        assert cascade.calls == ["en", "en"]
        assert second.status == "done"
        assert pipeline.recent() == [second.public()]

        third = await pipeline.enqueue(languages["en"], "third", False)
        await pipeline.join()
        assert cascade.calls == ["en", "en", "en"]
        assert third.status == "done"
        assert pipeline.recent() == [third.public()]
    finally:
        await pipeline.close()


async def test_reuse_updates_the_existing_entry_without_creating_another(languages):
    cascade = ScriptedCascade([Completion(["old"]), Completion(["new"])])
    pipeline = WordPipeline(cascade, target_lang="ru")
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "old", False)
        await pipeline.join()
        reused = await pipeline.enqueue(
            languages["en"],
            "new",
            True,
            reuse_entry=entry.entry_id,
        )
        await pipeline.join()
        assert reused is entry
        assert pipeline.recent() == [entry.public()]
        assert entry.word == "new"
        assert entry.text == "new"
    finally:
        await pipeline.close()


async def test_reuse_supersedes_a_prior_job_while_it_is_still_queued(languages):
    cascade = ScriptedCascade([Completion(["replacement answer"])])
    pipeline = WordPipeline(cascade, target_lang="Russian")
    entry = await pipeline.enqueue(languages["en"], "old", False)
    reused = await pipeline.enqueue(
        languages["en"],
        "replacement",
        False,
        reuse_entry=entry.entry_id,
    )
    pipeline.start()
    try:
        await pipeline.join()
        assert reused is entry
        assert cascade.calls == ["en"]
        assert "replacement" in cascade.prompts[0]
        assert entry.word == "replacement"
        assert entry.text == "replacement answer"
        assert entry.status == "done"
    finally:
        await pipeline.close()


async def test_reuse_stops_an_active_prior_job_from_publishing_stale_results(languages):
    release_old = asyncio.Event()
    old_started = asyncio.Event()
    cascade = ScriptedCascade(
        [
            Completion(["old partial"], gate=release_old, started=old_started),
            Completion(["replacement answer"]),
        ],
    )
    hub = EventHub()
    pipeline = WordPipeline(cascade, target_lang="Russian", events=hub)
    pipeline.start()
    try:
        async with hub.subscribe() as subscriber:
            entry = await pipeline.enqueue(languages["en"], "old", False)
            await old_started.wait()
            while entry.text != "old partial":
                await asyncio.sleep(0)
            drain(subscriber)

            await pipeline.enqueue(
                languages["en"],
                "replacement",
                False,
                reuse_entry=entry.entry_id,
            )
            release_old.set()
            await pipeline.join()
            events = drain(subscriber)

        assert entry.word == "replacement"
        assert entry.text == "replacement answer"
        assert entry.status == "done"
        assert [event.name for event in events] == ["reset", "accepted", "update", "done"]
        assert all(event.data.get("text") != "old partial" for event in events)
        assert cascade.calls == ["en", "en"]
    finally:
        await pipeline.close()


class MutableAnki:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []
        self.removed = []
        self.replaced = []

    async def add_note(self, note, deck, audio_path=None):
        self.calls.append((note, deck, audio_path))
        return self.results.pop(0)

    async def remove_note(self, note_id, media_filename=None):
        self.removed.append((note_id, media_filename))

    async def replace_note(
        self,
        note_id,
        note,
        deck,
        audio_path=None,
        old_media_filename=None,
    ):
        self.replaced.append((note_id, note, deck, audio_path, old_media_filename))
        self.calls.append((note, deck, audio_path))
        return self.results.pop(0)


def corrected_card(word, suggestion="", *, context=None, word_relation="same"):
    value = valid_card(
        word,
        context=context,
        word_relation="typo" if suggestion else word_relation,
    )
    if suggestion:
        value = value.replace('"suggestion": ""', f'"suggestion": "{suggestion}"', 1)
    return value.replace("analysis", f"analysis for {word}", 1)


async def test_a_rebuild_keeps_the_audio_of_the_unit_and_of_its_text(languages, tmp_path):
    audio_calls = []
    unit_audio = tmp_path / "pronunciation-aabbccddeeff00112233.mp3"
    text_audio = tmp_path / "pronunciation-1122334455667788990a.mp3"
    for path in (unit_audio, text_audio):
        path.write_bytes(b"audio")

    async def fetch(word, _language):
        audio_calls.append(word)
        return unit_audio if word == "aufstehen" else text_audio

    cascade = ScriptedCascade(
        [
            Completion([valid_card("aufstehen", context=SENTENCE)]),
            Completion([corrected_card("aufstehen", context=SENTENCE)]),
        ],
    )
    pipeline = WordPipeline(
        cascade,
        target_lang="ru",
        anki=MutableAnki([Added(1, "old.mp3"), Added(2, "new.mp3")]),
        audio=fetch,
    )
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["de"], "aufstehen", False, context=SENTENCE)
        await pipeline.join()
        await pipeline.request_rebuild(entry.entry_id)
        await pipeline.join()

        assert sorted(audio_calls) == sorted(["aufstehen", SENTENCE])
        assert entry.audio_url == f"/api/audio/{unit_audio.name}"
        assert entry.context_audio_url == f"/api/audio/{text_audio.name}"
    finally:
        await pipeline.close()


async def test_rebuild_replaces_the_note_keeps_audio_and_reuses_the_entry(languages, tmp_path):
    audio = tmp_path / "pronunciation-aabbccddeeff00112233.mp3"
    audio.write_bytes(b"audio")
    audio_calls = []

    async def fetch(word, _language):
        audio_calls.append(word)
        return audio

    anki = MutableAnki([Added(1, "old.mp3"), Added(2, "new.mp3")])
    cascade = ScriptedCascade(
        [Completion([valid_card("word")]), Completion([corrected_card("word")])],
    )
    pipeline = WordPipeline(cascade, target_lang="Russian", anki=anki, audio=fetch)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "word", False)
        await pipeline.join()
        await pipeline.request_rebuild(entry.entry_id)
        await pipeline.join()

        assert anki.removed == []
        assert [(call[0], call[4]) for call in anki.replaced] == [(1, "old.mp3")]
        assert [call[2] for call in anki.calls] == [audio, audio]
        assert audio_calls == ["word"]
        assert pipeline.recent()[0]["entry_id"] == entry.entry_id
        assert entry.text == "analysis for word"
        assert cascade.paid_calls == 1
    finally:
        await pipeline.close()


async def test_rebuild_fetches_new_card_audio_when_headword_case_changes(languages, tmp_path):
    original_audio = tmp_path / "original.mp3"
    rebuilt_audio = tmp_path / "rebuilt.mp3"
    for path in (original_audio, rebuilt_audio):
        path.write_bytes(b"audio")
    audio_calls = []

    async def fetch(word, _language):
        audio_calls.append(word)
        return original_audio if word == "Word" else rebuilt_audio

    anki = MutableAnki([Added(1, "old.mp3"), Added(2, "new.mp3")])
    cascade = ScriptedCascade(
        [
            Completion([valid_card("Word")]),
            Completion([corrected_card("word", word_relation="morphology")]),
        ],
    )
    pipeline = WordPipeline(cascade, target_lang="Russian", anki=anki, audio=fetch)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "Word", False, intent="unit")
        await pipeline.join()
        await pipeline.request_rebuild(entry.entry_id)
        await pipeline.join()
    finally:
        await pipeline.close()

    assert audio_calls == ["Word", "word"]
    assert [call[2] for call in anki.calls] == [original_audio, rebuilt_audio]
    assert anki.replaced[0][1].word == "word"


async def test_rebuild_refused_by_the_cap_changes_nothing(languages):
    cascade = ScriptedCascade([Completion([valid_card("word")])])
    pipeline = WordPipeline(
        cascade,
        target_lang="Russian",
        anki=RecordingAnki(Added(1, None)),
    )
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "word", False)
        await pipeline.join()
        before = entry.public()
        cascade.refusal = "the daily paid-call cap is spent"

        with pytest.raises(BackendError, match="cap"):
            await pipeline.request_rebuild(entry.entry_id)

        assert entry.public() == before
        assert cascade.paid_calls == 0
    finally:
        await pipeline.close()


async def test_detail_appends_is_cached_and_cuts_a_stray_card_block(languages):
    cascade = ScriptedCascade(
        [
            Completion([valid_card("word")]),
            Completion(["<b>Deep</b><script>x</script>", "===CARD===discarded"]),
        ],
    )
    pipeline = WordPipeline(cascade, target_lang="Russian")
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "word", False)
        await pipeline.join()
        analysis = entry.text
        audio = entry.audio_url
        await pipeline.request_detail(entry.entry_id)
        await pipeline.join()

        assert entry.text == analysis
        assert entry.audio_url == audio
        assert entry.detail_html == "<b>Deep</b>&lt;script&gt;x&lt;/script&gt;"
        cached = await pipeline.request_detail(entry.entry_id)
        assert cached["cached"] is True
        assert cascade.paid_calls == 1
    finally:
        await pipeline.close()


async def test_detail_is_refused_when_a_completed_entry_has_no_parsed_shape(languages):
    cascade = ScriptedCascade(
        [
            Completion(
                [
                    (
                        "analysis===CARD==="
                        '{"kind":"unit","word":"word","word_relation":"same",'
                        '"suggestion":"","meanings":'
                        '[{"label":"","translations":["слово"],"examples":[]}]}'
                    ),
                ],
            ),
        ],
    )
    pipeline = WordPipeline(cascade, target_lang="Russian")
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "word", False)
        await pipeline.join()

        assert entry.shape is None
        with pytest.raises(BackendError, match="not for running text"):
            await pipeline.request_detail(entry.entry_id)
        assert cascade.paid_calls == 0
    finally:
        await pipeline.close()


async def test_detail_refusal_leaves_the_entry_unchanged(languages):
    cascade = ScriptedCascade([Completion([valid_card("word")])])
    pipeline = WordPipeline(cascade, target_lang="Russian")
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "word", False)
        await pipeline.join()
        before = entry.public()
        cascade.refusal = "no paid model is configured"
        with pytest.raises(BackendError, match="no paid"):
            await pipeline.request_detail(entry.entry_id)
        assert entry.public() == before
    finally:
        await pipeline.close()


async def test_queued_detail_refusal_reports_the_exact_reason_without_changing_entry(languages):
    cascade = ScriptedCascade([Completion([valid_card("word")])])
    hub = EventHub()
    pipeline = WordPipeline(cascade, target_lang="Russian", events=hub)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "word", False)
        await pipeline.join()
        before = entry.public()

        await pipeline.close()
        async with hub.subscribe() as subscriber:
            await pipeline.request_detail(entry.entry_id)
            cascade.refusal = "the daily paid-call cap is spent"
            pipeline.start()
            await pipeline.join()
            events = drain(subscriber)

        assert entry.public() == before
        assert cascade.paid_calls == 0
        assert events[-1] == Event(
            "detail",
            {
                "entry_id": entry.entry_id,
                "error": "the daily paid-call cap is spent",
            },
        )
    finally:
        await pipeline.close()


async def test_correction_switch_is_reversible_replaces_notes_and_updates_undo(
    languages,
    tmp_path,
):
    paths = {}

    async def fetch(word, _language):
        path = tmp_path / f"pronunciation-{word}-aabbccddeeff0011.mp3"
        path.write_bytes(word.encode())
        paths[word] = path
        return path

    anki = MutableAnki(
        [Added(1, "one.mp3"), Added(2, "two.mp3"), Added(3, "three.mp3")],
    )
    cascade = ScriptedCascade(
        [
            Completion([corrected_card("recieve", "receive")]),
            Completion([corrected_card("receive")]),
            Completion([corrected_card("recieve", "receive")]),
        ],
    )
    pipeline = WordPipeline(cascade, target_lang="Russian", anki=anki, audio=fetch)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "recieve", False)
        await pipeline.join()
        entry.detail_html = "details for the misspelling"
        await pipeline.request_switch(entry.entry_id)
        await pipeline.join()

        assert entry.word == "receive"
        assert entry.suggestion == "recieve"
        assert entry.correction_reversed is True
        assert entry.detail_html == ""
        assert pipeline.history.undo["en"].note_id == 2
        assert pipeline.recent()[0]["entry_id"] == entry.entry_id

        await pipeline.request_switch(entry.entry_id)
        await pipeline.join()
        assert entry.word == "recieve"
        assert entry.suggestion == "receive"
        assert entry.correction_reversed is False
        assert anki.removed == []
        assert [(call[0], call[4]) for call in anki.replaced] == [
            (1, "one.mp3"),
            (2, "two.mp3"),
        ]
        assert pipeline.history.undo["en"].note_id == 3
        assert not paths["receive"].exists()
    finally:
        await pipeline.close()


async def test_queued_rebuild_refused_at_processing_time_changes_nothing(languages):
    cascade = ScriptedCascade(
        [Completion([valid_card("word")]), Completion([corrected_card("word")])],
    )
    anki = MutableAnki([Added(1, "old.mp3"), Added(2, "new.mp3")])
    hub = EventHub()
    pipeline = WordPipeline(cascade, target_lang="Russian", anki=anki, events=hub)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "word", False)
        await pipeline.join()
        before = entry.public()

        await pipeline.close()
        async with hub.subscribe() as subscriber:
            await pipeline.request_rebuild(entry.entry_id)
            cascade.refusal = "the daily paid-call cap is spent"
            pipeline.start()
            await pipeline.join()
            events = drain(subscriber)

        assert entry.public() == before
        assert anki.replaced == []
        assert events[-1] == Event(
            "control_error",
            {
                "entry_id": entry.entry_id,
                "message": "the daily paid-call cap is spent",
            },
        )
    finally:
        await pipeline.close()


async def test_switch_cancels_in_flight_detail_before_it_can_repopulate_the_entry(languages):
    release_detail = asyncio.Event()
    detail_started = asyncio.Event()
    cascade = ScriptedCascade(
        [
            Completion([corrected_card("recieve", "receive")]),
            Completion(
                ["old spelling detail", " stale suffix"],
                gate=release_detail,
                gate_after=1,
                started=detail_started,
            ),
            Completion([corrected_card("receive")]),
        ],
    )
    hub = EventHub()
    pipeline = WordPipeline(cascade, target_lang="Russian", events=hub)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "recieve", True)
        await pipeline.join()
        async with hub.subscribe() as subscriber:
            await pipeline.request_detail(entry.entry_id)
            await detail_started.wait()
            while entry.detail_html != "old spelling detail":
                await asyncio.sleep(0)
            drain(subscriber)

            await pipeline.request_switch(entry.entry_id)
            release_detail.set()
            await pipeline.join()
            events = drain(subscriber)

        assert entry.word == "receive"
        assert entry.detail_html == ""
        reset_index = next(index for index, event in enumerate(events) if event.name == "reset")
        assert all(event.name != "detail" for event in events[reset_index + 1 :])
    finally:
        await pipeline.close()


async def test_lookup_switch_stays_cardless(languages):
    cascade = ScriptedCascade(
        [Completion([corrected_card("recieve", "receive")]), Completion([valid_card("receive")])],
    )
    anki = MutableAnki([])
    pipeline = WordPipeline(cascade, target_lang="Russian", anki=anki)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "recieve", True)
        await pipeline.join()
        await pipeline.request_switch(entry.entry_id)
        await pipeline.join()
        assert entry.lookup_only is True
        assert entry.card_status.startswith(LOOKUP_ONLY_STATUS)
        assert anki.calls == []
    finally:
        await pipeline.close()


async def test_undo_removes_the_note_media_and_cached_audio_per_language(languages, tmp_path):
    audio = tmp_path / "pronunciation-aabbccddeeff00112233.mp3"
    audio.write_bytes(b"audio")

    async def fetch(_word, _language):
        return audio

    anki = MutableAnki([Added(7, "media.mp3")])
    pipeline = WordPipeline(
        ScriptedCascade([Completion([valid_card("word")])]),
        target_lang="Russian",
        anki=anki,
        audio=fetch,
        audio_dir=tmp_path,
    )
    pipeline.start()
    try:
        await pipeline.enqueue(languages["en"], "word", False)
        await pipeline.join()
        assert await pipeline.undo(languages["de"]) is None
        assert await pipeline.undo(languages["en"]) == "word"
        assert anki.removed == [(7, "media.mp3")]
        assert not audio.exists()
        assert await pipeline.undo(languages["en"]) is None
    finally:
        await pipeline.close()


async def test_undo_after_a_lookup_only_send_is_a_noop(languages):
    anki = MutableAnki([])
    pipeline = WordPipeline(
        ScriptedCascade([Completion([valid_card("word")])]),
        target_lang="Russian",
        anki=anki,
    )
    pipeline.start()
    try:
        await pipeline.enqueue(languages["en"], "word", True)
        await pipeline.join()
        assert await pipeline.undo(languages["en"]) is None
        assert anki.removed == []
    finally:
        await pipeline.close()


async def test_pending_latest_send_never_reexposes_the_previous_card_to_undo(languages):
    release_first = asyncio.Event()
    release_latest = asyncio.Event()
    latest_started = asyncio.Event()
    anki = MutableAnki([Added(1, "first.mp3")])
    pipeline = WordPipeline(
        ScriptedCascade(
            [
                Completion([valid_card("first")], gate=release_first),
                Completion(
                    [valid_card("latest")],
                    gate=release_latest,
                    started=latest_started,
                ),
            ],
        ),
        target_lang="Russian",
        anki=anki,
    )
    pipeline.start()
    try:
        await pipeline.enqueue(languages["en"], "first", False)
        await pipeline.enqueue(languages["en"], "latest", True)

        assert await pipeline.undo(languages["en"]) is None
        release_first.set()
        await latest_started.wait()
        assert await pipeline.undo(languages["en"]) is None
        release_latest.set()
        await pipeline.join()

        assert await pipeline.undo(languages["en"]) is None
        assert anki.removed == []
    finally:
        await pipeline.close()


async def test_unknown_or_expired_entry_refuses_all_controls():
    pipeline = WordPipeline(ScriptedCascade([]), target_lang="Russian")
    for request in (
        pipeline.request_rebuild,
        pipeline.request_switch,
        pipeline.request_detail,
    ):
        with pytest.raises(KeyError, match="request expired"):
            await request("unknown")


SENTENCE = "Er steht jeden Morgen um sechs auf."


def text_answer(*segments: str) -> str:
    return (
        "Он встаёт каждое утро в шесть.===CARD==="
        '{"kind":"text","combinations":[' + ",".join(segments) + "]}"
    )


AUFSTEHEN = '{"label":"aufstehen","surface":"steht … auf","why":"Trennbares Verb."}'


def voiced_by(directory):
    """An audio fetcher that always succeeds, one cached file per text."""
    audio = directory / "pronunciation-1122334455667788990a.mp3"
    audio.write_bytes(b"audio")

    async def fetch_audio(_word, _language):
        return audio

    return fetch_audio


async def test_running_text_is_voiced_whole_and_still_makes_no_card(languages, tmp_path):
    audio_calls = []
    spoken = tmp_path / "pronunciation-1122334455667788990a.mp3"
    spoken.write_bytes(b"audio")

    async def fetch_audio(word, language):
        audio_calls.append((word, language.code))
        return spoken

    anki = RecordingAnki(Added(1, None))
    pipeline = WordPipeline(
        ScriptedCascade([Completion([text_answer(AUFSTEHEN)])]),
        target_lang="ru",
        anki=anki,
        audio=fetch_audio,
    )
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["de"], SENTENCE, False)
        await pipeline.join()

        assert audio_calls == [(SENTENCE, "de")]
        assert anki.calls == []
        assert entry.card_status == TEXT_STATUS
        assert entry.no_audio is False
        assert entry.audio_url == f"/api/audio/{spoken.name}"
        assert entry.context_audio_url is None
        assert entry.lookup_only is False
        assert entry.detail_available is False
        assert entry.suggestion is None
    finally:
        await pipeline.close()


async def test_a_text_that_cannot_be_voiced_says_so(languages):
    pipeline = WordPipeline(
        ScriptedCascade([Completion([text_answer(AUFSTEHEN)])]),
        target_lang="ru",
    )
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["de"], SENTENCE, False)
        await pipeline.join()

        assert entry.card_status == TEXT_STATUS
        assert entry.no_audio is True
        assert entry.audio_url is None
    finally:
        await pipeline.close()


async def test_a_unit_taken_from_a_text_is_voiced_beside_the_whole_text(languages, tmp_path):
    audio_calls = []
    unit_audio = tmp_path / "pronunciation-aabbccddeeff00112233.mp3"
    text_audio = tmp_path / "pronunciation-1122334455667788990a.mp3"
    for path in (unit_audio, text_audio):
        path.write_bytes(b"audio")

    async def fetch_audio(word, language):
        audio_calls.append((word, language.code))
        return unit_audio if word == "aufstehen" else text_audio

    anki = RecordingAnki(Added(7, "media.mp3"))
    hub = EventHub()
    pipeline = WordPipeline(
        ScriptedCascade([Completion([valid_card("aufstehen", context=SENTENCE)])]),
        target_lang="ru",
        events=hub,
        anki=anki,
        audio=fetch_audio,
    )
    pipeline.start()
    try:
        async with hub.subscribe() as subscriber:
            entry = await pipeline.enqueue(
                languages["de"],
                "aufstehen",
                False,
                context=SENTENCE,
            )
            await pipeline.join()
            events = drain(subscriber)

        assert sorted(audio_calls) == sorted([("aufstehen", "de"), (SENTENCE, "de")])
        # Only the unit is carded, so only the unit's audio may reach the note.
        assert anki.calls[0][2] == unit_audio
        assert entry.audio_url == f"/api/audio/{unit_audio.name}"
        assert entry.context_audio_url == f"/api/audio/{text_audio.name}"
        assert entry.card_status == ADDED_STATUS
        assert events[-1].data["context_audio_url"] == entry.context_audio_url
        assert entry.public()["context_audio_url"] == entry.context_audio_url
    finally:
        await pipeline.close()


async def test_a_context_that_is_the_word_itself_is_not_voiced_twice(languages, tmp_path):
    audio_calls = []
    audio = tmp_path / "pronunciation-aabbccddeeff00112233.mp3"
    audio.write_bytes(b"audio")

    async def fetch_audio(word, language):
        audio_calls.append((word, language.code))
        return audio

    pipeline = WordPipeline(
        ScriptedCascade([Completion([valid_card("aufstehen", context="aufstehen")])]),
        target_lang="ru",
        anki=RecordingAnki(Added(7, "media.mp3")),
        audio=fetch_audio,
    )
    pipeline.start()
    try:
        entry = await pipeline.enqueue(
            languages["de"],
            "aufstehen",
            False,
            context="aufstehen",
        )
        await pipeline.join()

        assert audio_calls == [("aufstehen", "de")]
        assert entry.context_audio_url is None
    finally:
        await pipeline.close()


async def test_segments_reach_the_done_event_and_the_history(languages):
    hub = EventHub()
    pipeline = WordPipeline(
        ScriptedCascade([Completion([text_answer(AUFSTEHEN)])]),
        target_lang="ru",
        events=hub,
    )
    pipeline.start()
    try:
        async with hub.subscribe() as subscriber:
            entry = await pipeline.enqueue(languages["de"], SENTENCE, False)
            await pipeline.join()
            events = drain(subscriber)
        suggested = [
            {"label": "Er", "reason": "", "context": SENTENCE},
            {
                "label": "steht auf",
                "reason": "Trennbares Verb.",
                "context": SENTENCE,
            },
            {"label": "steht", "reason": "", "context": SENTENCE},
            {"label": "jeden", "reason": "", "context": SENTENCE},
            {"label": "Morgen", "reason": "", "context": SENTENCE},
            {"label": "um", "reason": "", "context": SENTENCE},
            {"label": "sechs", "reason": "", "context": SENTENCE},
            {"label": "auf", "reason": "", "context": SENTENCE},
        ]
        assert entry.segments == suggested
        assert events[-1].data["segments"] == suggested
        assert entry.public()["segments"] == suggested
        assert entry.public()["segment_kind"] == "text"
        assert entry.public()["shape"] == "text"
    finally:
        await pipeline.close()


async def test_a_trap_free_text_offers_every_word_and_still_rates_as_good(
    languages,
    tmp_path,
):
    completion = Completion([text_answer()])
    pipeline = WordPipeline(
        ScriptedCascade([completion]),
        target_lang="ru",
        audio=voiced_by(tmp_path),
    )
    pipeline.start()
    try:
        entry = await pipeline.enqueue(
            languages["de"],
            "Heute ist das Wetter schön.",
            False,
        )
        await pipeline.join()

        assert [segment["label"] for segment in entry.segments] == [
            "Heute",
            "ist",
            "das",
            "Wetter",
            "schön",
        ]
        assert entry.card_status == TEXT_STATUS
        assert completion.scores == [1.0]
    finally:
        await pipeline.close()


async def test_an_unparsable_text_payload_rates_as_a_failure_without_losing_the_answer(languages):
    completion = Completion(["<b>Разбор</b> текста.===CARD==={broken"])
    pipeline = WordPipeline(ScriptedCascade([completion]), target_lang="ru")
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["de"], SENTENCE, False)
        await pipeline.join()

        assert entry.text == "<b>Разбор</b> текста."
        assert entry.segments == []
        assert completion.scores == [0.0]
    finally:
        await pipeline.close()


async def test_an_unusable_internal_label_does_not_erase_a_surface_combination(languages):
    completion = Completion(
        [
            text_answer(
                '{"label":"vratiti се","surface":"се … вратио","why":"Повратна речца."}',
                '{"label":"јавити се","surface":"ми се … јавио","why":"Повратни глагол."}',
            ),
        ],
    )
    pipeline = WordPipeline(ScriptedCascade([completion]), target_lang="ru")
    pipeline.start()
    try:
        entry = await pipeline.enqueue(
            languages["sr"],
            "Он ми се јуче јавио телефоном.",
            False,
        )
        await pipeline.join()

        assert [segment["label"] for segment in entry.segments] == [
            "Он",
            "ми се јавио",
            "ми",
            "се",
            "јуче",
            "јавио",
            "телефоном",
        ]
    finally:
        await pipeline.close()


async def test_rebuild_and_detail_are_refused_on_a_text_entry(languages, tmp_path):
    pipeline = WordPipeline(
        ScriptedCascade([Completion([text_answer(AUFSTEHEN)])]),
        target_lang="ru",
        audio=voiced_by(tmp_path),
    )
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["de"], SENTENCE, False)
        await pipeline.join()

        with pytest.raises(BackendError, match="nothing to rebuild"):
            await pipeline.request_rebuild(entry.entry_id)
        with pytest.raises(BackendError, match="not for running text"):
            await pipeline.request_detail(entry.entry_id)
        with pytest.raises(BackendError, match="пересобирать нечего"):
            await pipeline.request_rebuild(entry.entry_id, locale="ru")
        with pytest.raises(BackendError, match="а не у текста"):
            await pipeline.request_detail(entry.entry_id, locale="ru")
        assert entry.card_status == TEXT_STATUS
    finally:
        await pipeline.close()


# The free pool's own failure, kept verbatim: an answer that stops escaping Cyrillic
# halfway through and leaves a payload no JSON parser will take.
BROKEN_CARD = (
    'analysis===CARD==={"word":"word","meanings":[{"label":"","pos":"\\u04гл.",'
    '"translations":["перевод"],"examples":'
    '[{"text":"Use word now.","translation":"Перевод."}]}]}'
)


async def test_an_answer_whose_card_block_is_broken_is_replaced_by_the_paid_model(
    settings,
    languages,
):
    handle = FakeHandle([BROKEN_CARD])
    cascade = fake_cascade(
        settings,
        handles=[handle],
        client=FakeDirectClient([valid_card("word")]),
    )
    anki = RecordingAnki(Added(7, None))
    hub = EventHub()
    pipeline = WordPipeline(cascade, target_lang="Russian", events=hub, anki=anki)
    pipeline.start()
    try:
        async with hub.subscribe() as subscriber:
            entry = await pipeline.enqueue(languages["en"], "word", False)
            await pipeline.join()
            events = drain(subscriber)
    finally:
        await pipeline.close()
    assert [note.word for note, _deck, _audio in anki.calls] == ["word"]
    assert entry.card_status == ADDED_STATUS
    assert entry.no_audio is True
    assert entry.model == "gpt-fast"
    assert entry.text == "analysis"
    assert handle.scores == [0.0]
    assert [event.name for event in events].count("reset") == 1


async def test_unit_intent_rejects_a_text_verdict_and_uses_the_paid_fallback(
    settings,
    languages,
):
    handle = FakeHandle([text_answer(AUFSTEHEN)])
    cascade = fake_cascade(
        settings,
        handles=[handle],
        client=FakeDirectClient([valid_card("aufstehen", context=SENTENCE)]),
    )
    anki = RecordingAnki(Added(7, None))
    pipeline = WordPipeline(cascade, target_lang="Russian", anki=anki)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(
            languages["de"],
            "aufstehen",
            False,
            intent="unit",
            context=SENTENCE,
        )
        await pipeline.join()
    finally:
        await pipeline.close()

    assert handle.scores == [0.0]
    assert cascade.broker.direct_calls == ["gpt-fast"]
    assert entry.shape == "unit"
    assert entry.card_status == ADDED_STATUS
    assert [note.word for note, _deck, _audio in anki.calls] == ["aufstehen"]


async def test_mismatched_context_example_uses_the_paid_fallback(settings, languages):
    context = "The bank opens at nine."
    wrong = valid_card("bank")
    contextual = {
        "text": context,
        "translation": "Банк открывается в девять.",
        "highlighted": "The <b>bank</b> opens at nine.",
        "gapped": "The ___ opens at nine.",
    }
    right = card_with(
        "bank",
        meanings=[{"label": "", "translations": ["банк"], "examples": [contextual]}],
        context_sense=0,
    )
    handle = FakeHandle([wrong])
    cascade = fake_cascade(
        settings,
        handles=[handle],
        client=FakeDirectClient([right]),
    )
    anki = RecordingAnki(Added(7, None))
    pipeline = WordPipeline(cascade, target_lang="Russian", anki=anki)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(
            languages["en"],
            "bank",
            False,
            intent="unit",
            context=context,
        )
        await pipeline.join()
    finally:
        await pipeline.close()

    assert handle.scores == [0.0]
    assert cascade.broker.direct_calls == ["gpt-fast"]
    assert entry.card_status == ADDED_STATUS
    assert anki.calls[0][0].meaning.examples[0].text == context


async def test_a_broken_card_block_stands_when_no_paid_model_can_replace_it(settings, languages):
    handle = FakeHandle([BROKEN_CARD])
    cascade = fake_cascade(
        settings.model_copy(update={"api_model": ""}),
        handles=[handle],
        client=FakeDirectClient(),
    )
    anki = RecordingAnki(Added(7, None))
    pipeline = WordPipeline(cascade, target_lang="Russian", anki=anki)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "word", False)
        await pipeline.join()
    finally:
        await pipeline.close()
    assert anki.calls == []
    assert cascade.broker.direct_calls == []
    assert entry.card_status == CARD_FAILED_STATUS
    assert entry.no_audio is True
    assert handle.scores == [0.0]


async def test_a_unit_answer_is_judged_by_its_card_and_a_text_answer_by_its_segments(languages):
    cascade = ScriptedCascade(
        [Completion([valid_card("word")]), Completion([text_answer(AUFSTEHEN)])],
    )
    pipeline = WordPipeline(cascade, target_lang="ru", anki=RecordingAnki(Added(1, None)))
    pipeline.start()
    try:
        await pipeline.enqueue(languages["en"], "word", False)
        await pipeline.join()
        await pipeline.enqueue(languages["de"], SENTENCE, False)
        await pipeline.join()
    finally:
        await pipeline.close()
    unit_check, text_check = cascade.usable_checks
    assert unit_check(valid_card("word")) is True
    assert unit_check("analysis with no card block") is False
    assert unit_check(BROKEN_CARD) is False
    assert text_check(text_answer(AUFSTEHEN)) is True
    assert text_check("prose with no segments block") is False


async def test_a_card_block_the_paid_model_breaks_too_ends_the_request(settings, languages):
    handle = FakeHandle([BROKEN_CARD])
    cascade = fake_cascade(
        settings,
        handles=[handle],
        client=FakeDirectClient([BROKEN_CARD]),
    )
    anki = RecordingAnki(Added(7, None))
    pipeline = WordPipeline(cascade, target_lang="Russian", anki=anki)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "word", False)
        await pipeline.join()
    finally:
        await pipeline.close()
    assert anki.calls == []
    assert cascade.broker.direct_calls == ["gpt-fast"]
    assert cascade.calls_today == 1
    assert entry.card_status == CARD_FAILED_STATUS
    assert entry.no_audio is True


async def test_an_oversized_paid_answer_cannot_card_its_bounded_prefix(settings, languages):
    bounded_prefix = valid_card("word")
    oversized = bounded_prefix + "x" * MAX_COMPLETE_ANSWER_CHARS
    cascade = fake_cascade(
        settings,
        handles=[FakeHandle([BROKEN_CARD])],
        client=FakeDirectClient([oversized]),
    )
    anki = RecordingAnki(Added(7, None))
    pipeline = WordPipeline(cascade, target_lang="Russian", anki=anki)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "word", False)
        await pipeline.join()
    finally:
        await pipeline.close()

    assert anki.calls == []
    assert len(entry.text) <= MAX_COMPLETE_ANSWER_CHARS
    assert entry.shape is None
    assert entry.card_status == CARD_FAILED_STATUS


async def test_a_rebuild_keeps_the_card_audio_of_a_headword_it_did_not_change(
    languages,
    tmp_path,
):
    submitted_audio = tmp_path / "submitted.mp3"
    headword_audio = tmp_path / "headword.mp3"
    for path in (submitted_audio, headword_audio):
        path.write_bytes(b"audio")

    async def fetch(word, _language):
        return submitted_audio if word == "gave up" else headword_audio

    anki = MutableAnki([Added(1, "old.mp3"), Added(2, "new.mp3")])
    cascade = ScriptedCascade(
        [
            Completion([corrected_card("give up", word_relation="morphology")]),
            Completion([corrected_card("give up", word_relation="morphology")]),
        ],
    )
    pipeline = WordPipeline(cascade, target_lang="Russian", anki=anki, audio=fetch)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "gave up", False, intent="unit")
        await pipeline.join()
        await pipeline.request_rebuild(entry.entry_id)
        await pipeline.join()
    finally:
        await pipeline.close()

    assert [call[2] for call in anki.calls] == [headword_audio, headword_audio]


async def test_a_running_text_entry_is_refused_as_text_not_as_a_missing_card(languages):
    pipeline = WordPipeline(
        ScriptedCascade([Completion([text_answer()])]),
        target_lang="ru",
    )
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "The book is on the table.", False)
        await pipeline.join()

        with pytest.raises(BackendError, match="Running text makes no card"):
            await pipeline.request_rebuild(entry.entry_id)
    finally:
        await pipeline.close()


async def test_undo_also_removes_the_card_audio_of_a_different_headword(
    languages,
    tmp_path,
):
    submitted = tmp_path / "pronunciation-aabbccddeeff00112233.mp3"
    headword = tmp_path / "pronunciation-1122334455667788990a.mp3"
    for path in (submitted, headword):
        path.write_bytes(b"audio")

    async def fetch(word, _language):
        return submitted if word == "gave up" else headword

    anki = MutableAnki([Added(7, "media.mp3")])
    pipeline = WordPipeline(
        ScriptedCascade([Completion([corrected_card("give up", word_relation="morphology")])]),
        target_lang="Russian",
        anki=anki,
        audio=fetch,
        audio_dir=tmp_path,
    )
    pipeline.start()
    try:
        await pipeline.enqueue(languages["en"], "gave up", False, intent="unit")
        await pipeline.join()
        assert await pipeline.undo(languages["en"]) == "gave up"
    finally:
        await pipeline.close()

    assert not submitted.exists()
    assert not headword.exists()
