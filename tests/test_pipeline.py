import asyncio
from collections.abc import AsyncIterator, Iterable

from fakes import FakeDirectClient, FakeHandle, fake_cascade

from echo_words.anki import Added, MisconfiguredNoteTypeError
from echo_words.broker import BackendError
from echo_words.events import Event, EventHub
from echo_words.pipeline import (
    ADDED_STATUS,
    ANALYSIS_FAILED_CODE,
    CARD_FAILED_STATUS,
    FRAGMENT_STATUS,
    LOOKUP_ONLY_STATUS,
    TEXT_STATUS,
    WordPipeline,
)

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
                "context_dropped": False,
                "no_audio": True,
                "segments": [],
                "segments_are_senses": False,
                "audio_url": None,
                "context_audio_url": None,
                "model": None,
                "detail_available": True,
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
            '{"word":"recieve","suggestion":"receive","meanings":',
            '[{"label":"","translations":["получать"],"examples":',
            '[{"text":"I recieve it.","translation":"Я получаю это."}]}]}',
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
                "context_dropped": False,
                "no_audio": True,
                "segments": [],
                "segments_are_senses": False,
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
            '{"word":"word","meanings":[{"label":"","translations":["слово"],',
            '"examples":[]}]}',
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
                "context_dropped": False,
                "no_audio": True,
                "segments": [],
                "segments_are_senses": False,
                "audio_url": None,
                "context_audio_url": None,
                "model": None,
                "detail_available": True,
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


def valid_card(word):
    return (
        f'analysis===CARD==={{"word":"{word}","meanings":[{{'
        '"label":"","translations":["перевод"],"examples":'
        f'[{{"text":"Use {word} now.","translation":"Перевод."}}]}}]}}'
    )


TWO_MEANINGS = (
    '{"label":"учреждение","translations":["банк"],'
    '"examples":[{"text":"The bank opens at nine.","translation":"Банк открывается в девять."}]},'
    '{"label":"берег","translations":["берег"],'
    '"examples":[{"text":"We sat on the bank.","translation":"Мы сидели на берегу."}]}'
)


def card_with(word, meanings=None, **fields):
    blocks = meanings or (
        '{"label":"","translations":["перевод"],'
        f'"examples":[{{"text":"Use {word} now.","translation":"Перевод."}}]}}'
    )
    named = "".join(f'"{name}":{value},' for name, value in fields.items())
    return f'analysis===CARD==={{"word":"{word}",{named}"meanings":[{blocks}]}}'


async def stored_note(languages, answer, anki, **submission):
    pipeline = WordPipeline(ScriptedCascade([Completion([answer])]), target_lang="ru", anki=anki)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "bank", False, **submission)
        await pipeline.join()
    finally:
        await pipeline.close()
    return entry


async def test_a_sense_index_without_a_context_leaves_the_note_bare(languages):
    anki = RecordingAnki(Added(1, None, ("Recognition", "SenseRecall1", "SenseRecall2")))
    answer = card_with("bank", meanings=TWO_MEANINGS, context_sense=1)

    entry = await stored_note(languages, answer, anki)

    note = anki.calls[0][0]
    assert note.word == "bank"
    assert note.context == ""
    assert note.context_sense is None
    assert entry.context_dropped is False


async def test_a_context_equal_to_the_word_narrows_nothing(languages):
    anki = RecordingAnki(Added(1, None, ("Recognition", "SenseRecall1", "SenseRecall2")))
    answer = card_with("bank", meanings=TWO_MEANINGS, context_sense=1)

    await stored_note(languages, answer, anki, context="bank")

    assert anki.calls[0][0].context_sense is None


async def test_several_meanings_card_the_context_under_the_sense_it_uses(languages):
    anki = RecordingAnki(Added(1, None, ("ContextRecognition", "ContextProduction")))
    answer = card_with("bank", meanings=TWO_MEANINGS, context_sense=1)

    entry = await stored_note(languages, answer, anki, context="We sat on the bank.")

    note = anki.calls[0][0]
    assert note.context == "We sat on the bank."
    assert note.context_sense == 1
    assert entry.context_dropped is False


async def test_one_meaning_drops_the_context_and_says_so(languages):
    """The context narrows nothing, and the app decided that on the user's behalf."""
    anki = RecordingAnki(Added(1, None, ("Recognition", "Recall")))
    answer = card_with("bank", context_sense=0)

    entry = await stored_note(languages, answer, anki, context="The bank opens at nine.")

    note = anki.calls[0][0]
    assert note.context == ""
    assert note.context_sense is None
    assert entry.card_status == ADDED_STATUS
    assert entry.context_dropped is True


async def test_an_unusable_sense_index_falls_through_to_the_bare_note(languages):
    anki = RecordingAnki(Added(1, None, ("Recognition", "SenseRecall1", "SenseRecall2")))
    answer = card_with("bank", meanings=TWO_MEANINGS, context_sense=7)

    entry = await stored_note(languages, answer, anki, context="We sat on the bank.")

    assert anki.calls[0][0].context == ""
    assert entry.context_dropped is True


async def test_the_senses_the_context_did_not_use_are_offered_as_chips(languages):
    anki = RecordingAnki(Added(1, None, ("ContextRecognition", "ContextProduction")))
    answer = card_with("bank", meanings=TWO_MEANINGS, context_sense=1)

    entry = await stored_note(languages, answer, anki, context="We sat on the bank.")

    assert entry.segments == [
        {
            "label": "bank",
            "surface": "The bank opens at nine.",
            "reason": "банк",
        },
    ]
    assert entry.segments_are_senses is True


async def test_a_sense_sentence_too_long_for_a_context_is_left_off_its_chip(languages):
    """Cutting it to length would card a mangled sentence; without one the tap is an
    ordinary bare send of the word, which still brings that sense into the deck."""
    long_example = "The bank opens at nine " + "and closes at five " * 10
    meanings = (
        '{"label":"учреждение","translations":["банк"],'
        f'"examples":[{{"text":"{long_example}","translation":"Банк."}}]}},'
        '{"label":"берег","translations":["берег"],'
        '"examples":[{"text":"We sat on the bank.","translation":"Мы сидели на берегу."}]}'
    )
    anki = RecordingAnki(Added(1, None, ("ContextRecognition", "ContextProduction")))
    answer = card_with("bank", meanings=meanings, context_sense=1)

    entry = await stored_note(languages, answer, anki, context="We sat on the bank.")

    assert entry.segments == [{"label": "bank", "surface": "", "reason": "банк"}]


async def test_a_context_that_narrowed_nothing_offers_no_chips(languages):
    anki = RecordingAnki(Added(1, None, ("Recognition", "Recall")))
    answer = card_with("bank", context_sense=0)

    entry = await stored_note(languages, answer, anki, context="The bank opens at nine.")

    assert entry.segments == []


async def test_the_status_names_the_kinds_the_collection_actually_made(languages):
    kinds = ("ContextRecognition", "ContextProduction")
    anki = RecordingAnki(Added(1, None, kinds))
    hub = EventHub()
    pipeline = WordPipeline(
        ScriptedCascade(
            [Completion([card_with("bank", meanings=TWO_MEANINGS, context_sense=0)])],
        ),
        target_lang="ru",
        events=hub,
        anki=anki,
    )
    pipeline.start()
    try:
        async with hub.subscribe() as subscriber:
            entry = await pipeline.enqueue(
                languages["en"],
                "bank",
                False,
                context="The bank opens at nine.",
            )
            await pipeline.join()
            events = drain(subscriber)
    finally:
        await pipeline.close()

    done = [event for event in events if event.name == "done"][-1]
    assert done.data["card_status"] == "added"
    assert done.data["card_kinds"] == list(kinds)
    assert done.data["context_dropped"] is False
    assert entry.card_kinds == list(kinds)
    assert entry.public()["card_kinds"] == list(kinds)


async def test_a_rebuild_carries_the_card_set_into_the_replacement(languages):
    replaced_kinds = ("ContextRecognition", "ContextProduction")
    anki = MutableAnki(
        [Added(1, None, ("Recognition", "Recall")), Added(2, None, replaced_kinds)],
    )
    cascade = ScriptedCascade(
        [
            Completion([valid_card("bank")]),
            Completion([card_with("bank", meanings=TWO_MEANINGS, context_sense=0)]),
        ],
    )
    hub = EventHub()
    pipeline = WordPipeline(
        cascade,
        target_lang="ru",
        events=hub,
        anki=anki,
    )
    pipeline.start()
    try:
        async with hub.subscribe() as subscriber:
            entry = await pipeline.enqueue(
                languages["en"],
                "bank",
                False,
                context="The bank opens at nine.",
            )
            await pipeline.join()
            await pipeline.request_rebuild(entry.entry_id)
            await pipeline.join()
            events = drain(subscriber)
    finally:
        await pipeline.close()

    _note_id, note, _deck, _audio_path, _media = anki.replaced[0]
    assert note.context == "The bank opens at nine."
    assert note.context_sense == 0
    done = [event for event in events if event.name == "done"][-1]
    assert done.data["card_kinds"] == list(replaced_kinds)
    assert entry.card_kinds == list(replaced_kinds)


async def test_a_fragment_makes_no_note_and_offers_the_unit_it_is_about(languages):
    # The submitted text was a use of a unit, so its front would be unreviewable;
    # the unit is offered instead and one tap on it makes the note.
    anki = RecordingAnki(Added(1, None))
    hub = EventHub()
    answer = (
        'analysis===CARD==={"word":"allein","candidates":["allein","einsam"],"meanings":[{'
        '"label":"","translations":["один"],"examples":'
        '[{"text":"Er ist allein.","translation":"Он один."}]}]}'
    )
    pipeline = WordPipeline(
        ScriptedCascade([Completion([answer])]),
        target_lang="ru",
        events=hub,
        anki=anki,
    )
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["de"], "ist allein im Restaurant", False)
        await pipeline.join()
        assert anki.calls == []
        assert entry.card_status == FRAGMENT_STATUS
        assert [segment["label"] for segment in entry.segments] == ["allein", "einsam"]
    finally:
        await pipeline.close()


async def test_a_unit_still_becomes_a_note_and_offers_nothing(languages):
    anki = RecordingAnki(Added(1, None))
    pipeline = WordPipeline(
        ScriptedCascade([Completion([valid_card("Rad fahren")])]),
        target_lang="ru",
        anki=anki,
    )
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["de"], "Rad fahren", False)
        await pipeline.join()
        assert len(anki.calls) == 1
        assert entry.card_status == ADDED_STATUS
        assert entry.segments == []
    finally:
        await pipeline.close()


async def test_an_inflected_single_word_still_becomes_a_note(languages):
    # The answer names the dictionary form of a word that was submitted inflected;
    # that is the same unit, not a unit found inside a longer input.
    anki = RecordingAnki(Added(1, None))
    pipeline = WordPipeline(
        ScriptedCascade([Completion([valid_card("одржавати")])]),
        target_lang="ru",
        anki=anki,
    )
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["sr"], "одржава", False)
        await pipeline.join()
        assert [note.word for note, *_ in anki.calls] == ["одржава"]
        assert entry.card_status == ADDED_STATUS
        assert entry.segments == []
    finally:
        await pipeline.close()


async def test_lookup_only_skips_anki_and_reports_it_in_done(languages):
    anki = RecordingAnki(Added(1, None))
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
            entry = await pipeline.enqueue(languages["en"], "word", True)
            await pipeline.join()
            events = drain(subscriber)
        assert anki.calls == []
        assert entry.card_status == LOOKUP_ONLY_STATUS
        assert entry.no_audio is True
        assert events[-1].data["card_status"] == LOOKUP_ONLY_STATUS
        assert events[-1].data["no_audio"] is True
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


def corrected_card(word, suggestion=""):
    return (
        f'analysis for {word}===CARD==={{"word":"{word}","suggestion":"{suggestion}",'
        '"meanings":[{"label":"","translations":["перевод"],"examples":'
        f'[{{"text":"Use {word} now.","translation":"Перевод."}}]}}]}}'
    )


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
        [Completion([valid_card("aufstehen")]), Completion([corrected_card("aufstehen")])],
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


async def test_rebuild_refused_by_the_cap_changes_nothing(languages):
    cascade = ScriptedCascade([Completion([valid_card("word")])])
    pipeline = WordPipeline(cascade, target_lang="Russian")
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
    return "Он встаёт каждое утро в шесть.===CARD===" + '{"segments":[' + ",".join(segments) + "]}"


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
        entry = await pipeline.enqueue(languages["de"], SENTENCE, False, shape="text")
        await pipeline.join()

        assert audio_calls == [(SENTENCE, "de")]
        assert anki.calls == []
        assert entry.card_status == TEXT_STATUS
        assert entry.no_audio is False
        assert entry.audio_url == f"/api/audio/{spoken.name}"
        assert entry.context_audio_url is None
        assert entry.lookup_only is True
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
        entry = await pipeline.enqueue(languages["de"], SENTENCE, False, shape="text")
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
        ScriptedCascade([Completion([valid_card("aufstehen")])]),
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
        ScriptedCascade([Completion([valid_card("aufstehen")])]),
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
            entry = await pipeline.enqueue(languages["de"], SENTENCE, False, shape="text")
            await pipeline.join()
            events = drain(subscriber)
        suggested = [
            {"label": "aufstehen", "surface": "steht … auf", "reason": "Trennbares Verb."},
        ]
        assert entry.segments == suggested
        assert events[-1].data["segments"] == suggested
        assert entry.public()["segments"] == suggested
        assert entry.public()["segments_are_senses"] is False
    finally:
        await pipeline.close()


async def test_a_trap_free_text_finishes_with_no_segments_and_still_rates_as_good(
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
            shape="text",
        )
        await pipeline.join()

        assert entry.segments == []
        assert entry.card_status == TEXT_STATUS
        assert completion.scores == [1.0]
    finally:
        await pipeline.close()


async def test_an_unparsable_text_payload_rates_as_a_failure_without_losing_the_answer(languages):
    completion = Completion(["<b>Разбор</b> текста.===CARD==={broken"])
    pipeline = WordPipeline(ScriptedCascade([completion]), target_lang="ru")
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["de"], SENTENCE, False, shape="text")
        await pipeline.join()

        assert entry.text == "<b>Разбор</b> текста."
        assert entry.segments == []
        assert completion.scores == [0.0]
    finally:
        await pipeline.close()


async def test_a_label_that_would_be_refused_as_input_never_becomes_a_segment(languages):
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
            shape="text",
        )
        await pipeline.join()

        assert [segment["label"] for segment in entry.segments] == ["јавити се"]
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
        entry = await pipeline.enqueue(languages["de"], SENTENCE, False, shape="text")
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
        await pipeline.enqueue(languages["de"], SENTENCE, False, shape="text")
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
