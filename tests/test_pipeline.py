import asyncio
from collections.abc import AsyncIterator, Iterable

from echo_words.broker import BackendError
from echo_words.events import Event, EventHub
from echo_words.pipeline import ERROR_MESSAGE, WordPipeline

pytestmark = __import__("pytest").mark.anyio


class Completion:
    def __init__(
        self,
        deltas: Iterable[str],
        *,
        error: Exception | None = None,
        gate: asyncio.Event | None = None,
        started: asyncio.Event | None = None,
        reset_after: int | None = None,
    ) -> None:
        self.deltas = list(deltas)
        self.error = error
        self.gate = gate
        self.started = started
        self.reset_after = reset_after
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
        if self.gate is not None:
            await self.gate.wait()
        if self.error is not None:
            raise self.error

    async def aclose(self) -> None:
        self.closed = True

    async def record_quality(self, score: float) -> None:
        self.scores.append(score)


class ScriptedCascade:
    def __init__(self, completions: Iterable[Completion]) -> None:
        self.completions = list(completions)
        self.calls: list[str] = []
        self.prompts: list[str] = []
        self.trace_ids: list[str | None] = []
        self.active = 0
        self.max_active = 0

    def stream_completion(self, prompt, language, *, trace_id=None, on_reset=None):
        self.calls.append(language.code)
        self.prompts.append(prompt)
        self.trace_ids.append(trace_id)
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
            {"entry_id": entry.entry_id, "message": ERROR_MESSAGE},
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
            {"entry_id": entry.entry_id, "text": "analysis", "suggestion": "receive"},
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
            {"entry_id": entry.entry_id, "text": "analysis", "suggestion": None},
        )
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
