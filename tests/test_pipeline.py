import asyncio
import json
import logging
from collections.abc import AsyncIterator, Iterable
from dataclasses import replace

from fakes import FakeDirectClient, FakeHandle, fake_cascade
from llmbroker import NoLLMAvailableError

from echo_words import pipeline as pipeline_module
from echo_words.anki import Added, MisconfiguredNoteTypeError
from echo_words.broker import BackendError
from echo_words.events import Event, EventHub
from echo_words.history import Entry
from echo_words.lexicon import Usage
from echo_words.pipeline import (
    ADDED_STATUS,
    ANALYSIS_FAILED_CODE,
    CARD_FAILED_STATUS,
    DELETED_STATUS,
    FOREIGN_STATUS,
    LOOKUP_ONLY_STATUS,
    MISSPELLED_STATUS,
    REVERSE_NOT_A_WORD_STATUS,
    TEXT_STATUS,
    UNATTESTED_STATUS,
    DetailSubject,
    WordPipeline,
)
from echo_words.prompt import MAX_COMPLETE_ANSWER_CHARS, build_extended_prompt

POOL_MISSED = NoLLMAvailableError("pool exhausted", reason="timeout")

pytest = __import__("pytest")
pytestmark = pytest.mark.anyio


class Completion:
    def __init__(
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
    ATTESTATION_MARK = "You judge whether a wording is actually used"
    VOUCHED = '{"used": true, "where": "everyday"}'

    def __init__(
        self,
        completions: Iterable[Completion],
        *,
        refusal: str | None = None,
        paid: Iterable[Completion] = (),
        attestations: Iterable[str] = (),
    ) -> None:
        self.completions = list(completions)
        # The parallel attestation call is answered from its own script, so a test that
        # cares about the article does not have to know the topology of the pipeline.
        self.attestations = list(attestations)
        self.attested: list[str] = []
        self.reported: list[bool] = []
        # What the paid model answers when the cascade steps up. Scripting none is
        # scripting a cascade with nothing to step up to, which is what most of these
        # tests are: the pool answers and its answer stands.
        self.paid_answers = list(paid)
        self.calls: list[str] = []
        self.paid_jobs: list[str] = []
        self.refreshed_for: list[str] = []
        self.prompts: list[str] = []
        self.trace_ids: list[str | None] = []
        self.active = 0
        self.max_active = 0
        self.refusal = refusal
        self.paid_calls = 0
        self.usable_checks: list[object] = []
        self.stepped_up: list[str] = []

    def stream_completion(
        self,
        prompt,
        language,
        *,
        trace_id=None,
        on_reset=None,
        usable=None,
        hand_over=None,
        pool_only=False,
        reported=True,
    ):
        self.reported.append(reported)
        if self.ATTESTATION_MARK in prompt:
            self.attested.append(prompt)
            answer = self.attestations.pop(0) if self.attestations else self.VOUCHED
            # A scripted Completion is used as it is, so a test can make the judgement
            # land late — the case where reading it once would call it absent.
            return answer if isinstance(answer, Completion) else Completion([answer])
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
                answer = ""
                async for delta in original():
                    answer += delta
                    yield delta
                # The cascade's own rule, so a test asserts on the step-up instead of
                # on the closure.
                if not self._steps_up(answer, usable, hand_over) or not self.paid_answers:
                    return
                self.stepped_up.append(answer)
                if self.refusal is not None:
                    return
                self.paid_calls += 1
                if on_reset is not None:
                    await on_reset()
                async for delta in self.paid_answers.pop(0).stream():
                    yield delta
            finally:
                self.active -= 1

        completion.stream = tracked
        return completion

    @staticmethod
    def _steps_up(answer, usable, hand_over):
        if usable is not None and not usable(answer):
            return True
        return hand_over is not None and hand_over(answer)

    def stream_paid(self, prompt, language, *, trace_id=None, detail=False):
        if self.refusal is not None:
            raise BackendError(self.refusal)
        self.paid_calls += 1
        self.paid_jobs.append("detail" if detail else "rebuild")
        return self.stream_completion(prompt, language, trace_id=trace_id)

    def paid_refusal(self, _language, *, detail=False):
        return self.refusal

    async def refresh_paid_availability(self, _language, *, detail=False):
        self.refreshed_for.append("detail" if detail else "card")
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
                "card_kept": False,
                "analysed_as": None,
                "typo_suspected": False,
                "showing_other_spelling": False,
                "segments": [],
                "segment_kind": None,
                "carded_sense": None,
                "shape": None,
                "audio_url": None,
                "context_audio_url": None,
                "model": None,
                "detail_available": False,
                "detail_word": None,
                "paid_answer_available": True,
                "reverse_offered": False,
                "foreign_language": None,
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
                "card_kept": False,
                "analysed_as": None,
                "typo_suspected": True,
                "showing_other_spelling": False,
                "segments": [
                    {
                        "label": "recieve",
                        "reason": "получать",
                        "context": "I recieve it.",
                        "surface": "",
                    },
                ],
                "segment_kind": "senses",
                "carded_sense": None,
                "shape": "unit",
                "audio_url": None,
                "context_audio_url": None,
                "model": None,
                "detail_available": True,
                "detail_word": "recieve",
                "paid_answer_available": True,
                "reverse_offered": False,
                "foreign_language": None,
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
                "card_kept": False,
                "analysed_as": None,
                "typo_suspected": False,
                "showing_other_spelling": False,
                "segments": [],
                "segment_kind": None,
                "carded_sense": None,
                "shape": None,
                "audio_url": None,
                "context_audio_url": None,
                "model": None,
                "detail_available": False,
                "detail_word": None,
                "paid_answer_available": True,
                "reverse_offered": False,
                "foreign_language": None,
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
    extra = (
        {
            "context_sense": 0,
            "context_translation": "Перевод.",
            # How the unit stands in this sentence: neither a separable verb nor a
            # past tense is its lemma, and only the answer knows which words it is.
            "context_surface": _context_surface(word, context),
        }
        if context is not None
        else {}
    )
    return card_with(
        word,
        meanings=meanings,
        segments=segments or [],
        word_relation=word_relation,
        **extra,
    )


def _context_surface(word, context):
    if word == "aufstehen":
        return "steht auf"
    return "gave up" if word == "give up" and "gave up" in context else word


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
    # An answer that names a contextual sense also translates that sentence: the backend
    # builds the context example out of the two, and carries neither on its own.
    if "context_sense" in answer:
        answer.setdefault("context_translation", "Перевод контекста.")
    return f"analysis===CARD==={json.dumps(answer, ensure_ascii=False)}"


REFUSED = '{"used": false, "where": ""}'


async def test_a_refused_judgement_stores_nothing_and_shows_nothing(languages):
    """A string the judgement will not vouch for gets no card and no article, however
    complete the article call's own answer was: an article about it is exactly the
    fabrication a learner would drill for months."""
    anki = RecordingAnki(Added(1, None, ("Recognition",)))
    cascade = ScriptedCascade(
        [Completion([valid_card("blorptium")])],
        attestations=[REFUSED],
    )
    pipeline = WordPipeline(cascade, target_lang="ru", anki=anki)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "blorptium", False, intent="unit")
        await pipeline.join()

        assert (entry.card_status, entry.action) == (UNATTESTED_STATUS, "unattested")
        assert entry.text == ""
        assert entry.segments == []
        assert anki.calls == []
    finally:
        await pipeline.close()


async def test_a_refusal_is_never_handed_to_the_paid_model(languages):
    """Sending a refusal up would overturn the very judgement it is made of: the paid
    models were measured to withhold fewer coinages than the pool, so the one asked to
    review the refusal is the one more likely to write the article anyway."""
    anki = RecordingAnki(Added(1, None, ("Recognition",)))
    cascade = ScriptedCascade(
        [Completion([valid_card("blorptium")])],
        paid=[Completion([valid_card("blorptium")])],
        attestations=[REFUSED],
    )
    pipeline = WordPipeline(cascade, target_lang="ru", anki=anki)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "blorptium", False, intent="unit")
        await pipeline.join()

        assert cascade.stepped_up == []
        assert cascade.paid_calls == 0
        assert entry.card_status == UNATTESTED_STATUS
        assert anki.calls == []
    finally:
        await pipeline.close()


async def test_a_declared_misspelling_is_handed_to_the_paid_model(languages):
    """The one thing the paid models are measurably better at: six of six registered
    misspellings corrected, against the pool's four."""
    anki = RecordingAnki(Added(1, None, ("Recognition",)))
    cascade = ScriptedCascade(
        [Completion([corrected_card("envi", "envy")])],
        paid=[Completion([typo_card("envy")])],
    )
    pipeline = WordPipeline(cascade, target_lang="ru", anki=anki)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "envi", False)
        await pipeline.join()

        assert cascade.paid_calls == 1
        assert entry.card_status == ADDED_STATUS
        assert entry.analysed_as == "envy"
        assert [note.word for note, _deck, _audio in anki.calls] == ["envy"]
    finally:
        await pipeline.close()


async def test_a_correction_the_judgement_refuses_too_cards_nothing(languages):
    """The judgement refused the submission and the answer replaced it with a second
    invention. Overruling the refusal on the word `typo` alone cards a coinage under a
    headword nothing ever vouched for, and tells the reader they misspelled it."""
    anki = RecordingAnki(Added(1, None, ("Recognition",)))
    cascade = ScriptedCascade(
        [Completion([typo_card("сумралица")])],
        attestations=[REFUSED, REFUSED],
    )
    pipeline = WordPipeline(cascade, target_lang="ru", anki=anki)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["sr"], "змркалица", False, intent="unit")
        await pipeline.join()

        assert (entry.card_status, entry.action) == (UNATTESTED_STATUS, "unattested")
        assert entry.text == ""
        assert anki.calls == []
        # Asked about the correction, not about the wording it replaced.
        assert "сумралица" in cascade.attested[-1]
    finally:
        await pipeline.close()


async def test_a_correction_the_judgement_vouches_for_still_cards(languages):
    """A misspelling is unused wording — that is what being one means — so the refusal
    of the submission must not withhold the correction the answer is actually about."""
    anki = RecordingAnki(Added(1, None, ("Recognition",)))
    cascade = ScriptedCascade(
        [Completion([typo_card("receive")])],
        attestations=[REFUSED, '{"used": true, "where": "everyday"}'],
    )
    pipeline = WordPipeline(cascade, target_lang="ru", anki=anki)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "recieve", False, intent="unit")
        await pipeline.join()

        assert entry.card_status == ADDED_STATUS
        assert [note.word for note, _deck, _audio in anki.calls] == ["receive"]
        assert len(cascade.attested) == 2
    finally:
        await pipeline.close()


async def test_a_vouched_submission_is_never_asked_about_twice(languages):
    """The second question exists only where the first one refused. Asking it beside
    every corrected spelling would spend a pool call on wording nothing objected to."""
    anki = RecordingAnki(Added(1, None, ("Recognition",)))
    cascade = ScriptedCascade([Completion([typo_card("receive")])], paid=[])
    pipeline = WordPipeline(cascade, target_lang="ru", anki=anki)
    pipeline.start()
    try:
        await pipeline.enqueue(languages["en"], "recieve", False, intent="unit")
        await pipeline.join()

        assert len(cascade.attested) == 1
    finally:
        await pipeline.close()


async def test_a_correction_that_repeats_the_submission_is_not_asked_about_again(languages):
    """The answer declared a misspelling and still headed itself with the submission,
    so it named no second wording. Asking the same question again would let a re-roll
    of it overturn the refusal the first call already gave."""
    anki = RecordingAnki(Added(1, None, ("Recognition",)))
    cascade = ScriptedCascade(
        [Completion([corrected_card("recieve", "receive")])],
        attestations=[REFUSED],
    )
    pipeline = WordPipeline(cascade, target_lang="ru", anki=anki)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "recieve", False, intent="unit")
        await pipeline.join()

        assert len(cascade.attested) == 1
        assert (entry.card_status, entry.action) == (MISSPELLED_STATUS, "misspelled")
        assert entry.suggestion == "receive"
    finally:
        await pipeline.close()


async def test_an_answer_that_kept_the_misspelling_it_declared_cards_nothing(languages):
    """The answer called the submission misspelled and still headed itself with it.
    Its card would teach the spelling the same answer calls wrong, so there is none —
    and the correction stays on offer beside the entry."""
    anki = RecordingAnki(Added(1, None, ("Recognition",)))
    cascade = ScriptedCascade([Completion([corrected_card("recieve", "receive")])])
    pipeline = WordPipeline(cascade, target_lang="ru", anki=anki)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "recieve", False)
        await pipeline.join()

        assert (entry.card_status, entry.action) == (MISSPELLED_STATUS, "misspelled")
        assert anki.calls == []
        assert entry.suggestion == "receive"
        assert entry.analysed_as is None
    finally:
        await pipeline.close()


async def test_a_parallel_refusal_stops_an_article_the_other_call_wrote(languages):
    """The judgement is asked on its own because a model already writing a dictionary
    entry keeps producing one: measured on the free pool, the standalone question
    withholds four to six coinages of six against the leading verdict's two. So the
    article call may vouch for the wording and still be overruled."""
    hub = EventHub()
    anki = RecordingAnki(Added(1, None, ("Recognition",)))
    cascade = ScriptedCascade(
        [Completion([valid_card("Fahrradsuppe")])],
        attestations=['{"used": false, "where": ""}'],
    )
    pipeline = WordPipeline(cascade, target_lang="ru", anki=anki, events=hub)
    pipeline.start()
    try:
        async with hub.subscribe() as subscriber:
            entry = await pipeline.enqueue(languages["de"], "Fahrradsuppe", False, intent="unit")
            await pipeline.join()
            published = drain(subscriber)

        assert entry.card_status == UNATTESTED_STATUS
        assert entry.text == ""
        assert anki.calls == []
        assert all("Fahrradsuppe</b>" not in str(event.data) for event in published)
        # The senses are the same invention one tap away, and a deeper analysis is the
        # withheld article again — bought from the paid model.
        assert entry.segments == []
        assert entry.shape is None
        assert entry.detail_available is False
    finally:
        await pipeline.close()


async def test_a_correction_stands_over_a_refusal_of_the_misspelling(languages):
    """The standalone question refuses four of six registered misspellings — of course
    it does, being unused is what a misspelling is. Letting that refusal win would
    answer every typo with "no such word" instead of the correction."""
    anki = RecordingAnki(Added(1, None, ("Recognition",)))
    cascade = ScriptedCascade(
        [Completion([typo_card("receive")])],
        attestations=['{"used": false, "where": ""}'],
    )
    pipeline = WordPipeline(cascade, target_lang="ru", anki=anki)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "recieve", False, intent="unit")
        await pipeline.join()

        assert entry.card_status == ADDED_STATUS
        assert entry.analysed_as == "receive"
        assert [note.word for note, _deck, _audio in anki.calls] == ["receive"]
    finally:
        await pipeline.close()


async def test_a_kept_misspelling_keeps_its_article_over_a_refusal(languages):
    """The answer declared a misspelling and named the correction, so it pointed at a
    real word: the judgement about the wrong spelling is beside the point. Refusing
    here would answer a plain typo with "no such word" and destroy the article."""
    anki = RecordingAnki(Added(1, None, ("Recognition",)))
    cascade = ScriptedCascade(
        [Completion([corrected_card("recieve", "receive")])],
        attestations=['{"used": false, "where": ""}'],
    )
    pipeline = WordPipeline(cascade, target_lang="ru", anki=anki)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "recieve", False, intent="unit")
        await pipeline.join()

        assert entry.card_status == MISSPELLED_STATUS
        assert entry.text
        assert entry.suggestion == "receive"
        assert anki.calls == []
    finally:
        await pipeline.close()


async def test_normalizing_a_coinage_does_not_disarm_the_refusal(languages):
    """A dictionary form of an unattested compound is that compound, and a plural of a
    coinage is a coinage. Only a declared correction names another word."""
    anki = RecordingAnki(Added(1, None, ("Recognition",)))
    cascade = ScriptedCascade(
        [
            Completion(
                [valid_card("Fahrradsuppe", word_relation="morphology")],
            ),
        ],
        attestations=['{"used": false, "where": ""}'],
    )
    pipeline = WordPipeline(cascade, target_lang="ru", anki=anki)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["de"], "Fahrradsuppen", False, intent="unit")
        await pipeline.join()

        assert entry.card_status == UNATTESTED_STATUS
        assert anki.calls == []
    finally:
        await pipeline.close()


async def test_a_refusal_stands_when_the_answer_kept_the_wording_submitted(languages):
    """The other side of the same rule: an answer that analysed the very wording the
    judgement refused has nothing to overrule it with."""
    anki = RecordingAnki(Added(1, None, ("Recognition",)))
    cascade = ScriptedCascade(
        [Completion([valid_card("vieleicht")])],
        attestations=['{"used": false, "where": ""}'],
    )
    pipeline = WordPipeline(cascade, target_lang="ru", anki=anki)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["de"], "vieleicht", False, intent="unit")
        await pipeline.join()

        assert entry.card_status == UNATTESTED_STATUS
        assert anki.calls == []
    finally:
        await pipeline.close()


async def test_a_refusal_that_lands_after_the_first_paint_still_withholds(
    languages,
    monkeypatch,
):
    """The judgement decides the answer whenever it arrives. Reading it once, on the
    first delta, and calling a slow one absent would card the coinage the moment the
    article happened to be longer than the wait."""
    # The waits are cut to nothing so the judgement lands after both of them and while
    # the article is still streaming — the case where reading it once discards it.
    monkeypatch.setattr(pipeline_module, "FIRST_PAINT_SECONDS", 0.01)
    monkeypatch.setattr(pipeline_module, "ATTESTATION_GRACE_SECONDS", 0.01)
    hub = EventHub()
    anki = RecordingAnki(Added(1, None, ("Recognition",)))
    late, more = asyncio.Event(), asyncio.Event()
    loop = asyncio.get_running_loop()
    loop.call_later(0.05, late.set)
    loop.call_later(0.10, more.set)
    cascade = ScriptedCascade(
        [
            Completion(
                [
                    "<b>Fahrradsuppe</b> — суп из велосипеда.",
                    valid_card("Fahrradsuppe"),
                ],
                gate=more,
                gate_after=1,
            ),
        ],
        attestations=[Completion(['{"used": false, "where": ""}'], gate=late)],
    )
    pipeline = WordPipeline(cascade, target_lang="ru", anki=anki, events=hub)
    pipeline.start()
    try:
        async with hub.subscribe() as subscriber:
            entry = await pipeline.enqueue(languages["de"], "Fahrradsuppe", False, intent="unit")
            await pipeline.join()
            published = drain(subscriber)

        assert entry.card_status == UNATTESTED_STATUS
        assert entry.text == ""
        assert anki.calls == []
        assert all("велосипеда" not in str(event.data) for event in published)
    finally:
        await pipeline.close()


async def test_a_vouched_wording_is_shown_and_carded_as_usual(languages):
    cascade = ScriptedCascade([Completion([valid_card("Katze")])])
    anki = RecordingAnki(Added(1, None, ("Recognition",)))
    pipeline = WordPipeline(cascade, target_lang="ru", anki=anki)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["de"], "Katze", False, intent="unit")
        await pipeline.join()

        assert entry.card_status == ADDED_STATUS
        assert entry.text
        assert len(cascade.attested) == 1
    finally:
        await pipeline.close()


async def test_an_attestation_that_never_answers_is_not_an_objection(languages):
    """Closing on the pool's silence would withhold real words, which is the worse
    error — the same rule the article's own missing verdict follows."""
    cascade = ScriptedCascade(
        [Completion([valid_card("Katze")])],
        attestations=["nothing that parses"],
    )
    anki = RecordingAnki(Added(1, None, ("Recognition",)))
    pipeline = WordPipeline(cascade, target_lang="ru", anki=anki)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["de"], "Katze", False, intent="unit")
        await pipeline.join()

        assert entry.card_status == ADDED_STATUS
        assert entry.text
    finally:
        await pipeline.close()


async def test_a_judgement_past_its_grace_is_ended_rather_than_left_running(
    languages,
    monkeypatch,
):
    """A judgement read past its grace is still streaming, and nothing awaits it any
    more: left alone it holds a pool slot for the rest of the provider's timeout."""
    monkeypatch.setattr(pipeline_module, "FIRST_PAINT_SECONDS", 0.01)
    monkeypatch.setattr(pipeline_module, "ATTESTATION_GRACE_SECONDS", 0.01)
    never = asyncio.Event()
    hanging = Completion(['{"used": true, "where": "everyday"}'], gate=never)
    cascade = ScriptedCascade(
        [Completion([valid_card("Katze")])],
        attestations=[hanging],
    )
    anki = RecordingAnki(Added(1, None, ("Recognition",)))
    pipeline = WordPipeline(cascade, target_lang="ru", anki=anki)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["de"], "Katze", False, intent="unit")
        await pipeline.join()

        assert entry.card_status == ADDED_STATUS
        assert hanging.closed is True
    finally:
        await pipeline.close()


async def test_a_cancellation_during_the_paint_wait_is_not_swallowed():
    """The wait shields the judgement, never the waiter: a cancellation eaten here
    leaves close() awaiting a worker that has already gone back to its queue."""
    never = asyncio.Event()

    async def forever():
        await never.wait()

    task = asyncio.create_task(forever())
    attestation = pipeline_module._Attestation(task)
    waiter = asyncio.create_task(attestation.lands_within(10))
    await asyncio.sleep(0)
    waiter.cancel()

    with pytest.raises(asyncio.CancelledError):
        await waiter
    # The judgement itself survives the waiter, for its owner to end.
    assert task.done() is False
    attestation.cancel()


async def test_a_refused_wording_keeps_no_card_recording_in_the_entry_state(
    languages,
    tmp_path,
):
    """A recording of a string the answer would not vouch for must not survive as the
    entry's card audio: a later job reading that state would attach it to a card."""

    async def fetch(word, _language):
        path = tmp_path / f"pronunciation-{word}.mp3"
        path.write_bytes(b"audio")
        return path

    cascade = ScriptedCascade(
        # The headword differs from the submission, so a card recording is made for it
        # before the standalone judgement refuses the wording it was made from.
        [Completion([valid_card("Fahrradsuppen")])],
        attestations=['{"used": false, "where": ""}'],
    )
    pipeline = WordPipeline(
        cascade,
        target_lang="ru",
        anki=RecordingAnki(Added(1, None, ("Recognition",))),
        audio=fetch,
    )
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["de"], "Fahrradsuppe", False, intent="unit")
        await pipeline.join()

        assert entry.card_status == UNATTESTED_STATUS
        assert pipeline.history.undo["de"].card_audio_file is None
    finally:
        await pipeline.close()


async def test_the_judgement_is_not_reported_as_the_language_last_call(languages):
    """`/api/status` answers with the analysis the reader waited for. The judgement
    asked beside it settles after it as often as not, and would overwrite it."""
    cascade = ScriptedCascade(
        [Completion([valid_card("Katze")])],
    )
    anki = RecordingAnki(Added(1, None, ("Recognition",)))
    pipeline = WordPipeline(cascade, target_lang="ru", anki=anki)
    pipeline.start()
    try:
        await pipeline.enqueue(languages["de"], "Katze", False, intent="unit")
        await pipeline.join()

        assert cascade.reported.count(False) == 1
        assert cascade.reported.count(True) == 1
    finally:
        await pipeline.close()


async def test_a_more_usual_spelling_beside_a_vouched_word_cards_the_learners_own(languages):
    """The answer analysed exactly what was typed and merely names a commoner spelling.
    That is advice, not a correction: the card is the learner's, with the offer beside
    it (spec/functional-description.md)."""
    cascade = ScriptedCascade(
        [
            Completion(
                [
                    card_with("colour", word_relation="same", suggestion="color"),
                ],
            ),
        ],
    )
    anki = RecordingAnki(Added(1, None, ("Recognition",)))
    pipeline = WordPipeline(cascade, target_lang="ru", anki=anki)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "colour", False, intent="unit")
        await pipeline.join()

        assert entry.card_status == ADDED_STATUS
        assert entry.suggestion == "color"
        assert entry.typo_suspected is False
    finally:
        await pipeline.close()


async def test_a_paid_rebuild_is_never_asked_for_an_attestation(languages):
    """A rebuild is about a wording already carded and already judged once. Asking
    again would spend a pool call to re-litigate a note the reader chose to keep."""
    cascade = ScriptedCascade(
        [
            Completion([valid_card("Katze")]),
            Completion([valid_card("Katze")]),
        ],
    )
    anki = MutableAnki([Added(1, "one.mp3"), Added(2, "two.mp3")])
    pipeline = WordPipeline(cascade, target_lang="ru", anki=anki)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["de"], "Katze", False, intent="unit")
        await pipeline.join()
        asked_once = len(cascade.attested)

        await pipeline.request_rebuild(entry.entry_id)
        await pipeline.join()

        assert entry.card_status == ADDED_STATUS
        assert len(cascade.attested) == asked_once == 1
        # A rebuild writes a card, so it keeps the card's paid model and not the article's.
        assert cascade.paid_jobs == ["rebuild"]
    finally:
        await pipeline.close()


async def test_a_running_text_is_never_asked_for_an_attestation(languages):
    """The question is about one wording. A sentence has none to judge, and asking
    would spend a pool call on every sentence submitted."""
    answer = 'Он встаёт каждое утро в шесть.===CARD==={"kind":"text","combinations":[]}'
    cascade = ScriptedCascade([Completion([answer])])
    pipeline = WordPipeline(cascade, target_lang="ru", anki=RecordingAnki(Added(1, None, ())))
    pipeline.start()
    try:
        await pipeline.enqueue(languages["de"], "Er steht jeden Morgen um sechs auf.", False)
        await pipeline.join()

        assert cascade.attested == []
    finally:
        await pipeline.close()


async def test_a_refused_word_is_not_spoken_but_its_file_survives(languages, tmp_path):
    """Pronouncing a string the answer would not vouch for tells the reader it is a
    word. The recording is only detached: one cached file is addressed by its text,
    so deleting it would silence every other entry voicing the same words."""
    audio = tmp_path / "pronunciation-aabbccddeeff00112233.mp3"

    async def fetch(_word, _language):
        audio.write_bytes(b"audio")
        return audio

    pipeline = WordPipeline(
        ScriptedCascade([Completion([valid_card("blorptium")])], attestations=[REFUSED]),
        target_lang="ru",
        anki=RecordingAnki(Added(1, None, ())),
        audio=fetch,
    )
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "blorptium", False, intent="unit")
        await pipeline.join()

        assert entry.card_status == UNATTESTED_STATUS
        assert entry.audio_file is None
        assert entry.no_audio is False
        assert audio.exists()
    finally:
        await pipeline.close()


async def test_a_refusal_hides_the_article_the_other_call_is_writing(languages):
    """The article call knows nothing of the judgement and keeps writing. The
    withholding has to happen as the answer streams: blanking it at the end still shows
    the fabrication, one delta at a time, to a reader who is watching it arrive."""
    hub = EventHub()
    pipeline = WordPipeline(
        ScriptedCascade(
            [
                Completion(
                    [
                        "<b>blorptium</b> — вымышленный ",
                        "сверхтяжёлый металл.",
                        valid_card("blorptium"),
                    ],
                ),
            ],
            attestations=[REFUSED],
        ),
        target_lang="ru",
        anki=RecordingAnki(Added(1, None, ())),
        events=hub,
    )
    pipeline.start()
    try:
        async with hub.subscribe() as subscriber:
            entry = await pipeline.enqueue(languages["en"], "blorptium", False, intent="unit")
            await pipeline.join()
            published = drain(subscriber)

        assert entry.card_status == UNATTESTED_STATUS
        assert entry.text == ""
        assert all("металл" not in str(event.data) for event in published)
        assert all("<b>" not in str(event.data) for event in published)
    finally:
        await pipeline.close()


async def test_a_refused_lookup_is_still_counted_as_a_lookup(languages):
    pipeline = WordPipeline(
        ScriptedCascade([Completion([valid_card("blorptium")])], attestations=[REFUSED]),
        target_lang="ru",
        anki=RecordingAnki(Added(1, None, ())),
    )
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "blorptium", True, intent="unit")
        await pipeline.join()

        assert entry.card_status == UNATTESTED_STATUS
        assert pipeline.history.counts("en") == {"lookup_only": 1}
    finally:
        await pipeline.close()


@pytest.mark.parametrize(
    ("lang", "submitted", "headword", "suggestion"),
    [("de", "strase", "Strase", "Straße"), ("sr", "mozda", "мозда", "можда")],
)
async def test_a_kept_misspelling_is_caught_however_its_case_or_script_is_written(
    languages,
    lang,
    submitted,
    headword,
    suggestion,
):
    """The guard folds exactly as the relation itself was decided. Comparing the two
    spellings literally would let a capital letter or the other Serbian script carry a
    misspelling onto a card — and German nouns are always capitalized, while Serbian is
    typed in either script by design."""
    anki = RecordingAnki(Added(1, None, ("Recognition",)))
    cascade = ScriptedCascade([Completion([corrected_card(headword, suggestion)])])
    pipeline = WordPipeline(cascade, target_lang="Russian", anki=anki)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages[lang], submitted, False)
        await pipeline.join()

        assert entry.card_status == MISSPELLED_STATUS
        assert anki.calls == []
    finally:
        await pipeline.close()


async def test_a_lemma_for_an_inflected_form_is_not_called_a_typo(languages):
    """The card carries the dictionary form of what was typed, which is normalization
    and not a correction. Telling the reader their word does not exist would be a lie
    on every inflected submission, and on every Serbian word typed in Latin."""
    anki = RecordingAnki(Added(1, None, ("Recognition",)))
    pipeline = WordPipeline(
        ScriptedCascade(
            [Completion([valid_card("receive", word_relation="morphology")])],
        ),
        target_lang="ru",
        anki=anki,
    )
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "received", False)
        await pipeline.join()

        assert entry.card_status == ADDED_STATUS
        assert [note.word for note, _deck, _audio in anki.calls] == ["receive"]
        # Named, because the card is not about the wording that was typed — but not
        # named as a misspelling, which is the lie this test exists to prevent.
        # A lemma given for an inflected form is the answer doing its job, not an event
        # to announce: nothing is said above the analysis about it.
        assert entry.analysed_as is None
        assert entry.typo_suspected is False
    finally:
        await pipeline.close()


async def test_a_corrected_misspelling_names_the_word_the_card_is_for(languages):
    anki = RecordingAnki(Added(1, None, ("Recognition",)))
    pipeline = WordPipeline(
        ScriptedCascade([Completion([typo_card("envy")])]),
        target_lang="ru",
        anki=anki,
    )
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "envi", False)
        await pipeline.join()

        assert entry.card_status == ADDED_STATUS
        assert entry.analysed_as == "envy"
        assert [note.word for note, _deck, _audio in anki.calls] == ["envy"]
    finally:
        await pipeline.close()


async def test_a_wording_no_reference_work_has_is_said_and_still_carded(languages):
    """The reader is told, not overruled: a wording absent from the wikis that the
    encyclopedia also never writes is what every measured coinage looks like."""
    anki = RecordingAnki(Added(1, None, ("Recognition",)))
    asked = []

    async def dictionary(word, language):
        asked.append((word, language.code))
        return False

    cascade = ScriptedCascade([Completion([valid_card("bookshelfy")])])
    pipeline = WordPipeline(
        cascade,
        target_lang="ru",
        anki=anki,
        dictionary=dictionary,
        usage=_usage(hits=0),
    )
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "bookshelfy", False, intent="unit")
        await pipeline.join()

        assert entry.not_in_references is True
        assert entry.usage_search_url == "https://example.invalid/search"
        assert entry.card_status == ADDED_STATUS
        assert asked == [("bookshelfy", "en")]
    finally:
        await pipeline.close()


async def test_a_set_expression_the_encyclopedia_writes_is_not_accused(languages):
    """No wiki carries `у реду`, and the encyclopedia writes it more than a thousand
    times. A dictionary alone would call the commonest Serbian phrase no word at all."""
    anki = RecordingAnki(Added(1, None, ("Recognition",)))

    async def dictionary(_word, _language):
        return False

    cascade = ScriptedCascade([Completion([valid_card("у реду")])])
    pipeline = WordPipeline(
        cascade,
        target_lang="ru",
        anki=anki,
        dictionary=dictionary,
        usage=_usage(hits=1183),
    )
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["sr"], "у реду", False, intent="unit")
        await pipeline.join()

        assert entry.not_in_references is False
        assert entry.usage_search_url is None
    finally:
        await pipeline.close()


async def test_an_unreachable_usage_search_does_not_confirm_a_dictionary_miss(languages):
    """Nought occurrences is evidence about a wording; a search that never answered is
    not, and accusing a word on our own outage is the error the second source removes."""
    anki = RecordingAnki(Added(1, None, ("Recognition",)))

    async def dictionary(_word, _language):
        return False

    async def unavailable(_word, _language):
        return None

    cascade = ScriptedCascade([Completion([valid_card("bookshelfy")])])
    pipeline = WordPipeline(
        cascade,
        target_lang="ru",
        anki=anki,
        dictionary=dictionary,
        usage=unavailable,
    )
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "bookshelfy", False, intent="unit")
        await pipeline.join()

        assert entry.not_in_references is False
    finally:
        await pipeline.close()


async def test_the_dictionary_is_asked_about_the_wording_the_note_carries(languages):
    """The note teaches the headword, so that is what has to be in a dictionary — not
    the spelling the reader typed and the answer corrected away. A wording the
    dictionary has raises no question, so the encyclopedia is not asked about it."""
    anki = RecordingAnki(Added(1, None, ("Recognition",)))
    asked = []
    searched = []

    async def dictionary(word, _language):
        asked.append(word)
        return True

    async def usage(word, _language):
        searched.append(word)

    cascade = ScriptedCascade(
        [Completion([typo_card("receive")])],
        attestations=[REFUSED, '{"used": true, "where": "everyday"}'],
    )
    pipeline = WordPipeline(
        cascade,
        target_lang="ru",
        anki=anki,
        dictionary=dictionary,
        usage=usage,
    )
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "recieve", False, intent="unit")
        await pipeline.join()

        assert asked == ["receive"]
        assert searched == []
        assert entry.not_in_references is False
    finally:
        await pipeline.close()


async def test_an_unreachable_dictionary_says_nothing_about_the_word(languages):
    """A service that did not answer is not a dictionary that lacks the word, and
    telling the reader otherwise would accuse their real word on our own outage."""
    anki = RecordingAnki(Added(1, None, ("Recognition",)))

    async def dictionary(_word, _language):
        return None

    cascade = ScriptedCascade([Completion([valid_card("petrichor")])])
    pipeline = WordPipeline(
        cascade,
        target_lang="ru",
        anki=anki,
        dictionary=dictionary,
        usage=_usage(hits=0),
    )
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "petrichor", False, intent="unit")
        await pipeline.join()

        assert entry.not_in_references is False
    finally:
        await pipeline.close()


async def test_a_text_answer_is_never_asked_about_in_a_dictionary(languages):
    """Text teaches no single wording, so there is nothing to look up and no lookup
    to spend."""
    asked = []

    async def dictionary(word, _language):
        asked.append(word)
        return False

    cascade = ScriptedCascade(
        [Completion(['translation===CARD==={"kind":"text","combinations":[]}'])],
    )
    pipeline = WordPipeline(cascade, target_lang="ru", dictionary=dictionary)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["de"], "Ampel links", False)
        await pipeline.join()

        assert asked == []
        assert entry.not_in_references is False
    finally:
        await pipeline.close()


def _usage(*, hits: int):
    async def usage(_word, _language):
        return Usage(hits=hits, examples=[], search_url="https://example.invalid/search")

    return usage


async def test_a_vouched_word_keeps_the_article_it_was_given(languages):
    anki = RecordingAnki(Added(2, None, ("Recognition",)))
    cascade = ScriptedCascade([Completion([valid_card("petrichor")])])
    pipeline = WordPipeline(cascade, target_lang="ru", anki=anki)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "petrichor", False, intent="unit")
        await pipeline.join()

        assert entry.card_status == ADDED_STATUS
        assert "analysis" in entry.text
        assert [note.word for note, _deck, _audio in anki.calls] == ["petrichor"]
    finally:
        await pipeline.close()


def typo_card(corrected):
    """The production shape of a suspected typo: the model corrects the spelling in
    ``word`` and its examples are about the corrected word, not the submitted one."""
    return card_with(
        corrected,
        meanings=[
            {
                "label": "",
                "translations": ["перевод"],
                "examples": [example(corrected)],
            },
        ],
        word_relation="typo",
        suggestion=corrected,
    )


async def stored_note(languages, answer, anki, **submission):
    pipeline = WordPipeline(ScriptedCascade([Completion([answer])]), target_lang="ru", anki=anki)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "bank", False, **submission)
        await pipeline.join()
    finally:
        await pipeline.close()
    return entry


async def test_context_sense_identifies_the_carded_chip_for_display(languages):
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
    assert entry.carded_sense == 1
    assert entry.public()["carded_sense"] == 1
    assert entry.segments == [
        {
            "label": "bank",
            "reason": "банк",
            "context": "The bank opens at nine.",
            "surface": "",
        },
        {
            "label": "bank",
            "reason": "берег",
            "context": "We sat on the bank.",
            "surface": "",
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
    assert entry.carded_sense == 0


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

    assert all("The learner selected this unit" in prompt for prompt in cascade.prompts)
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


async def test_three_hanging_audio_roles_use_one_shared_wait_budget(
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
        assert entry.carded_sense is None
        assert len(entry.segments) == 1
        assert events[-1].data["card_status"] == CARD_FAILED_STATUS
        assert events[-1].data["card_error"] == expected
        assert events[-1].data["carded_sense"] is None
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
        assert pipeline.recent() == [{**second.public(), "detail_pending": False}]

        third = await pipeline.enqueue(languages["en"], "third", False)
        await pipeline.join()
        assert cascade.calls == ["en", "en", "en"]
        assert third.status == "done"
        assert pipeline.recent() == [{**third.public(), "detail_pending": False}]
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
        assert pipeline.recent() == [{**entry.public(), "detail_pending": False}]
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


async def test_the_deeper_article_is_signed_by_the_model_that_wrote_it(settings, languages):
    """The analysis and the deeper article come from two different models, and the name
    over the entry belongs to the first. Signing the second with it tells the reader the
    free model wrote what the paid one did."""
    cascade = fake_cascade(
        settings,
        handles=[FakeHandle([valid_card("word")])],
        client=FakeDirectClient(["<b>Deep</b>"]),
    )
    pipeline = WordPipeline(cascade, target_lang="Russian", anki=RecordingAnki(Added(7, None)))
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "word", False)
        await pipeline.join()
        assert entry.model == "pool-model"
        assert entry.detail_model is None

        await pipeline.request_detail(entry.entry_id)
        await pipeline.join()
    finally:
        await pipeline.close()

    assert entry.detail_html == "<b>Deep</b>"
    assert entry.detail_model == "gpt"
    # The analysis above it was not written by the paid model and does not claim to be.
    assert entry.model == "pool-model"


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
        # The deeper article is its own job: its model and parameters, not the card's.
        assert cascade.paid_jobs == ["detail"]
        assert cascade.refreshed_for.count("detail") == 1
    finally:
        await pipeline.close()


async def test_a_streamed_article_says_it_is_running_until_the_last_piece(languages):
    """The strip and the live dot are what the reader has for ten seconds, so only the
    end of the call may take them away — not its first piece."""
    hub = EventHub()
    cascade = ScriptedCascade(
        [
            Completion([valid_card("word")]),
            Completion(["Half an ", "article"]),
        ],
    )
    pipeline = WordPipeline(cascade, target_lang="Russian", events=hub)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "word", False)
        await pipeline.join()

        async with hub.subscribe() as subscriber:
            await pipeline.request_detail(entry.entry_id)
            await pipeline.join()
            events = [event for event in drain(subscriber) if event.name == "detail"]

        assert [event.data.get("streaming") for event in events] == [True, True, None]
        assert events[-1].data["text"] == "Half an article"
    finally:
        await pipeline.close()


async def test_an_article_that_fails_unexpectedly_still_ends_its_progress_strip(languages):
    """Not every failure is the backend's own, and the strip and the live dot are ended
    by an event: without one the reader watches a call that stopped running."""
    hub = EventHub()

    class BrokenStream(ScriptedCascade):
        def stream_paid(self, *_args, **_kwargs):
            async def broken():
                yield "half an "
                raise RuntimeError("the stream broke")

            self.paid_calls += 1
            return broken()

    cascade = BrokenStream([Completion([valid_card("word")])])
    pipeline = WordPipeline(cascade, target_lang="Russian", events=hub)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "word", False)
        await pipeline.join()

        async with hub.subscribe() as subscriber:
            await pipeline.request_detail(entry.entry_id)
            await pipeline.join()
            events = [event for event in drain(subscriber) if event.name == "detail"]

        assert events[-1].data == {"entry_id": entry.entry_id, "error": "detail_failed"}
        assert pipeline.recent()[0]["detail_pending"] is False
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


async def test_a_restarted_server_writes_the_deeper_article_from_the_pages_copy(languages):
    """The browser keeps its history through a restart and the process does not, so a
    press on an entry the process never saw is answered from what the page sent."""
    hub = EventHub()
    cascade = ScriptedCascade([Completion(["<b>Deep</b>"])])
    pipeline = WordPipeline(cascade, target_lang="Russian", events=hub)
    subject = DetailSubject(languages["en"], "house", "two houses")
    pipeline.start()
    try:
        async with hub.subscribe() as subscriber:
            queued = await pipeline.request_detail("e1", restored=subject)
            await pipeline.join()
            events = [event for event in drain(subscriber) if event.name == "detail"]

        assert queued == {"entry_id": "e1", "queued": True}
        assert cascade.prompts == [
            build_extended_prompt(languages["en"], "house", "Russian", context="two houses"),
        ]
        assert events[-1].data == {"entry_id": "e1", "text": "<b>Deep</b>", "model": None}
        cached = await pipeline.request_detail("e1", restored=subject)
        assert cached == {"entry_id": "e1", "detail_html": "<b>Deep</b>", "cached": True}
        assert cascade.paid_calls == 1
        # Nothing it carries could change a card: those controls still find nothing.
        for control in (pipeline.request_switch, pipeline.request_rebuild, pipeline.delete_card):
            with pytest.raises(KeyError, match="request expired"):
                await control("e1")
    finally:
        await pipeline.close()


async def test_the_pages_copy_never_outranks_what_the_process_holds(languages):
    cascade = ScriptedCascade([Completion([valid_card("word")]), Completion(["<b>Deep</b>"])])
    pipeline = WordPipeline(cascade, target_lang="Russian")
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "word", False)
        await pipeline.join()
        await pipeline.request_detail(
            entry.entry_id,
            restored=DetailSubject(languages["de"], "Wort", "ein Wort"),
        )
        await pipeline.join()

        assert cascade.prompts[-1] == build_extended_prompt(languages["en"], "word", "Russian")
        assert entry.lang == "en"
    finally:
        await pipeline.close()


async def test_a_press_without_the_pages_copy_still_expires_on_an_unknown_entry(languages):
    pipeline = WordPipeline(ScriptedCascade([]), target_lang="Russian")
    with pytest.raises(KeyError, match="request expired"):
        await pipeline.request_detail("gone")


async def test_a_finished_answer_tells_the_page_what_its_deeper_article_asks_about(languages):
    hub = EventHub()
    cascade = ScriptedCascade([Completion([valid_card("word")])])
    pipeline = WordPipeline(cascade, target_lang="Russian", events=hub)
    pipeline.start()
    try:
        async with hub.subscribe() as subscriber:
            entry = await pipeline.enqueue(languages["en"], "word", False)
            await pipeline.join()
            done = next(event for event in drain(subscriber) if event.name == "done")

        assert entry.detail_word == "word"
        assert done.data["detail_word"] == "word"
    finally:
        await pipeline.close()


async def test_a_running_paid_call_is_still_running_after_a_reload(languages):
    """The strip and the live dot come back with the page: a reload, or a trip to
    another screen, must not lose a call the pipeline is still making."""
    cascade = ScriptedCascade([Completion([valid_card("word")])])
    pipeline = WordPipeline(cascade, target_lang="Russian")
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "word", False)
        await pipeline.join()
        assert pipeline.recent()[0]["detail_pending"] is False

        await pipeline.close()
        await pipeline.request_detail(entry.entry_id)

        assert pipeline.recent()[0]["detail_pending"] is True

        pipeline.start()
        await pipeline.join()
        assert pipeline.recent()[0]["detail_pending"] is False
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
    named_other = card_with("Straße", word_relation="typo", suggestion="Strasse")
    cascade = ScriptedCascade(
        [
            Completion([named_other]),
            Completion([corrected_card("Strasse")]),
            Completion([named_other]),
        ],
    )
    pipeline = WordPipeline(cascade, target_lang="Russian", anki=anki, audio=fetch)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["de"], "Strase", False)
        await pipeline.join()
        # The answer carded the spelling it analysed and named another one beside it,
        # so the switch is an offer rather than a question to answer first.
        assert (entry.card_status, entry.suggestion) == (ADDED_STATUS, "Strasse")
        assert entry.carded_sense == 0
        entry.detail_html = "details for the carded spelling"
        await pipeline.request_switch(entry.entry_id)
        await pipeline.join()

        assert entry.word == "Strasse"
        assert entry.suggestion == "Strase"
        assert entry.detail_html == ""
        assert pipeline.history.undo["de"].note_id == 2
        assert pipeline.recent()[0]["entry_id"] == entry.entry_id

        await pipeline.request_switch(entry.entry_id)
        await pipeline.join()
        assert entry.word == "Strase"
        assert entry.suggestion == "Strasse"
        assert anki.removed == []
        assert [(call[0], call[4]) for call in anki.replaced] == [
            (1, "one.mp3"),
            (2, "two.mp3"),
        ]
        assert pipeline.history.undo["de"].note_id == 3
        # The recording of the spelling switched away from stays in the cache, where
        # the next send of that word finds it.
        assert paths["Strasse"].exists()
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


async def test_a_switch_that_stores_nothing_keeps_the_note_and_the_audio_it_had(
    languages,
    tmp_path,
):
    """A replacement that never happened leaves the previous note and its media exactly
    as they were, and says so: the reader still has the card they had."""
    audio = tmp_path / "pronunciation-aabbccddeeff00112233.mp3"
    audio.write_bytes(b"audio")

    async def fetch(_word, _language):
        return audio

    anki = MutableAnki([Added(7, "media.mp3")])
    cascade = ScriptedCascade(
        [
            Completion([card_with("Straße", word_relation="typo", suggestion="Strasse")]),
            Completion(["no answer block at all"]),
        ],
    )
    pipeline = WordPipeline(
        cascade,
        target_lang="Russian",
        anki=anki,
        audio=fetch,
    )
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["de"], "Strase", False)
        await pipeline.join()
        assert (entry.card_status, entry.suggestion) == (ADDED_STATUS, "Strasse")

        await pipeline.request_switch(entry.entry_id)
        await pipeline.join()

        assert entry.card_status == CARD_FAILED_STATUS
        assert entry.card_kept is True
        assert entry.carded_sense is None
        assert anki.removed == []
        assert entry.audio_file == audio.name
        assert audio.exists()
    finally:
        await pipeline.close()


async def test_a_switch_over_an_uncarded_answer_records_the_first_undo_state(languages):
    """The misspelling was left uncarded, so the switch that cards the correction is
    the first note this entry ever stored — and undo has to know it exists."""
    anki = MutableAnki([Added(7, "media.mp3")])
    cascade = ScriptedCascade(
        [
            Completion([corrected_card("recieve", "receive")]),
            Completion([valid_card("receive")]),
        ],
    )
    pipeline = WordPipeline(cascade, target_lang="Russian", anki=anki)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "recieve", False)
        await pipeline.join()
        assert entry.card_status == MISSPELLED_STATUS

        await pipeline.request_switch(entry.entry_id)
        await pipeline.join()

        assert entry.card_status == ADDED_STATUS
        assert await pipeline.undo(languages["en"]) == "receive"
        assert anki.removed == [(7, "media.mp3")]
    finally:
        await pipeline.close()


async def test_a_corrected_lookup_still_says_which_word_it_analysed(languages):
    """A lookup stores nothing, but the reader typed one word and is reading about
    another, and that is said above the analysis either way."""
    cascade = ScriptedCascade([Completion([typo_card("receive")])])
    pipeline = WordPipeline(cascade, target_lang="Russian", anki=MutableAnki([]))
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "recieve", True)
        await pipeline.join()

        assert entry.card_status == LOOKUP_ONLY_STATUS
        assert entry.analysed_as == "receive"
    finally:
        await pipeline.close()


async def test_undo_removes_the_note_and_its_media_per_language(languages, tmp_path):
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
    )
    pipeline.start()
    try:
        await pipeline.enqueue(languages["en"], "word", False)
        await pipeline.join()
        assert await pipeline.undo(languages["de"]) is None
        assert await pipeline.undo(languages["en"]) == "word"
        assert anki.removed == [(7, "media.mp3")]
        assert audio.exists()
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


async def test_delete_card_removes_the_note_and_its_media_and_keeps_the_recording(
    languages,
    tmp_path,
):
    """The cards go and the analysis stays, recording included: a cached file is
    addressed by its text and shared with every other entry for the same word, so it
    belongs to the cache rather than to the note that happened to use it."""
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
    )
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "gave up", False, intent="unit")
        await pipeline.join()

        assert await pipeline.delete_card(entry.entry_id) == "give up"

        assert anki.removed == [(7, "media.mp3")]
        assert submitted.exists()
        assert headword.exists()
        assert pipeline.history.entries[entry.entry_id].card_status == DELETED_STATUS
        # The word is still on the screen, so it is still readable and still audible.
        assert pipeline.history.entries[entry.entry_id].audio_file == submitted.name
        # The control kept nothing to delete a second time, and says so rather than
        # answering a confirmed deletion with silence.
        with pytest.raises(BackendError, match="nothing to delete"):
            await pipeline.delete_card(entry.entry_id)
        assert anki.removed == [(7, "media.mp3")]
    finally:
        await pipeline.close()


async def test_a_corrected_misspelling_is_spoken_as_the_headword(languages, tmp_path):
    """The note is about the correction, so the player says the correction. Speaking the
    submitted slip instead teaches a pronunciation of a word nobody writes: `uber` read
    by a German voice is not `über`."""
    submitted = tmp_path / "pronunciation-00112233445566778899.mp3"
    headword = tmp_path / "pronunciation-99887766554433221100.mp3"
    for path in (submitted, headword):
        path.write_bytes(b"audio")

    async def fetch(word, _language):
        return headword if word == "über" else submitted

    anki = MutableAnki([Added(7, "media.mp3")])
    pipeline = WordPipeline(
        ScriptedCascade([Completion([typo_card("über")])]),
        target_lang="Russian",
        anki=anki,
        audio=fetch,
    )
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["de"], "uber", False, intent="unit")
        await pipeline.join()

        assert entry.analysed_as == "über"
        assert entry.audio_file == headword.name
        assert pipeline.history.entries[entry.entry_id].audio_file == headword.name
    finally:
        await pipeline.close()


async def test_a_switch_keeps_the_recording_a_second_entry_is_still_playing(
    languages,
    tmp_path,
):
    """A switch moves its own entry onto the corrected spelling's recording and leaves
    every other entry where it was: the same word submitted twice is one file, and the
    entry that was not switched goes on playing it."""
    misspelled = tmp_path / "pronunciation-aabbccddeeff00112233.mp3"
    corrected = tmp_path / "pronunciation-bbccddeeff0011223344.mp3"
    for path in (misspelled, corrected):
        path.write_bytes(b"audio")

    async def fetch(word, _language):
        return corrected if word == "Strasse" else misspelled

    anki = MutableAnki([Added(7, "one.mp3"), Added(8, "two.mp3"), Added(9, "three.mp3")])
    cascade = ScriptedCascade(
        [
            Completion([card_with("Strase", word_relation="typo", suggestion="Strasse")]),
            Completion([card_with("Strase", word_relation="typo", suggestion="Strasse")]),
            Completion([valid_card("Strasse")]),
        ],
    )
    pipeline = WordPipeline(
        cascade,
        target_lang="Russian",
        anki=anki,
        audio=fetch,
    )
    pipeline.start()
    try:
        first = await pipeline.enqueue(languages["de"], "Strase", False)
        second = await pipeline.enqueue(languages["de"], "Strase", False)
        await pipeline.join()

        await pipeline.request_switch(first.entry_id)
        await pipeline.join()

        assert first.audio_file == corrected.name
        assert misspelled.exists()
        assert pipeline.history.entries[second.entry_id].audio_file == misspelled.name
    finally:
        await pipeline.close()


async def test_delete_card_leaves_the_recording_a_running_answer_was_handed(
    languages,
    tmp_path,
):
    """The recording is handed to a job before the model has said a word, and a deletion
    running while that answer streams must not take it: the resubmission would finish
    with a player over a file that is no longer there."""
    shared = tmp_path / "pronunciation-aabbccddeeff00112233.mp3"
    shared.write_bytes(b"audio")
    streaming = asyncio.Event()
    finish = asyncio.Event()

    async def fetch(_word, _language):
        return shared

    anki = MutableAnki([Added(7, "one.mp3"), Added(8, "two.mp3")])
    pipeline = WordPipeline(
        ScriptedCascade(
            [
                Completion([valid_card("word")]),
                Completion([valid_card("word")], started=streaming, gate=finish),
            ],
        ),
        target_lang="Russian",
        anki=anki,
        audio=fetch,
    )
    pipeline.start()
    try:
        first = await pipeline.enqueue(languages["en"], "word", False)
        await pipeline.join()
        second = await pipeline.enqueue(languages["en"], "word", False)
        await streaming.wait()

        assert await pipeline.delete_card(first.entry_id) == "word"
        assert shared.exists()

        finish.set()
        await pipeline.join()
        assert pipeline.history.entries[second.entry_id].audio_file == shared.name
    finally:
        finish.set()
        await pipeline.close()


async def test_delete_card_leaves_undo_nothing_to_delete_twice(languages):
    anki = MutableAnki([Added(7, "media.mp3")])
    pipeline = WordPipeline(
        ScriptedCascade([Completion([valid_card("word")])]),
        target_lang="Russian",
        anki=anki,
    )
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "word", False)
        await pipeline.join()

        assert await pipeline.delete_card(entry.entry_id) == "word"
        assert await pipeline.undo(languages["en"]) is None

        assert anki.removed == [(7, "media.mp3")]
    finally:
        await pipeline.close()


async def test_delete_card_on_an_entry_that_carded_nothing_says_so(languages):
    anki = MutableAnki([])
    pipeline = WordPipeline(
        ScriptedCascade([Completion([valid_card("word")])]),
        target_lang="Russian",
        anki=anki,
    )
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "word", True)
        await pipeline.join()

        with pytest.raises(BackendError, match="nothing to delete"):
            await pipeline.delete_card(entry.entry_id)
        assert anki.removed == []
        assert pipeline.history.entries[entry.entry_id].card_status == LOOKUP_ONLY_STATUS
    finally:
        await pipeline.close()


async def test_delete_card_tells_the_open_page_the_cards_are_gone(languages):
    events = EventHub()
    anki = MutableAnki([Added(7, "media.mp3")])
    pipeline = WordPipeline(
        ScriptedCascade([Completion([valid_card("word")])]),
        target_lang="Russian",
        anki=anki,
        events=events,
    )
    pipeline.start()
    try:
        async with events.subscribe() as subscriber:
            entry = await pipeline.enqueue(languages["en"], "word", False)
            await pipeline.join()
            drain(subscriber)

            await pipeline.delete_card(entry.entry_id)
            published = drain(subscriber)

        assert [event.name for event in published] == ["done"]
        assert published[0].data["entry_id"] == entry.entry_id
        assert published[0].data["card_status"] == DELETED_STATUS
        assert published[0].data["card_kinds"] == []
        assert published[0].data["audio_url"] is None
    finally:
        await pipeline.close()


async def test_delete_card_on_a_pending_entry_raises_the_expired_error(languages):
    release = asyncio.Event()
    pipeline = WordPipeline(
        ScriptedCascade([Completion([valid_card("word")], gate=release)]),
        target_lang="Russian",
        anki=MutableAnki([Added(7, "media.mp3")]),
    )
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "word", False)

        with pytest.raises(KeyError, match="request expired"):
            await pipeline.delete_card(entry.entry_id)

        release.set()
        await pipeline.join()
    finally:
        await pipeline.close()


async def test_unknown_or_expired_entry_refuses_all_controls():
    pipeline = WordPipeline(ScriptedCascade([]), target_lang="Russian")
    for request in (
        pipeline.request_rebuild,
        pipeline.request_switch,
        pipeline.request_detail,
        pipeline.delete_card,
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
            {"label": "Er", "reason": "", "context": SENTENCE, "surface": ""},
            {
                # Named by the answer, and carrying the words it spans for whoever
                # needs to find it back in the sentence.
                "label": "aufstehen",
                "reason": "Trennbares Verb.",
                "context": SENTENCE,
                "surface": "steht auf",
            },
            {"label": "steht", "reason": "", "context": SENTENCE, "surface": ""},
            {"label": "jeden", "reason": "", "context": SENTENCE, "surface": ""},
            {"label": "Morgen", "reason": "", "context": SENTENCE, "surface": ""},
            {"label": "um", "reason": "", "context": SENTENCE, "surface": ""},
            {"label": "sechs", "reason": "", "context": SENTENCE, "surface": ""},
            {"label": "auf", "reason": "", "context": SENTENCE, "surface": ""},
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
            "јавити се",
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


async def test_an_answer_whose_card_block_is_broken_keeps_its_analysis_on_the_page(
    settings,
    languages,
):
    """The article reads; only the card behind it failed. The reader keeps what they
    were reading, the entry says the card failed, and no paid call is made on a verdict
    about the payload."""
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
    assert anki.calls == []
    assert entry.card_status == CARD_FAILED_STATUS
    assert entry.model == "pool-model"
    assert entry.text == "analysis"
    assert handle.scores == [0.0]
    assert cascade.broker.direct_calls == []
    # Nothing was cleared, because nothing replaced it.
    assert [event.name for event in events].count("reset") == 0


async def test_unit_intent_rejecting_a_text_verdict_leaves_the_card_failed(
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
    assert cascade.broker.direct_calls == []
    assert entry.card_status == CARD_FAILED_STATUS
    assert anki.calls == []


async def test_an_answer_that_ignores_the_context_in_its_examples_still_cards(
    settings,
    languages,
):
    """The answer is no longer asked to reproduce the sentence, so examples that have
    nothing to do with it are just examples. The contextual card is built from the
    reader's own sentence, and there is no comparison left to fail."""
    context = "The bank opens at nine."
    handle = FakeHandle([card_with("bank", context_sense=0)])
    cascade = fake_cascade(settings, handles=[handle], client=FakeDirectClient())
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

    assert entry.card_status == ADDED_STATUS
    assert cascade.broker.direct_calls == []
    note = anki.calls[0][0]
    assert note.meaning.examples[0].text == context
    assert note.meaning.examples[0].gapped == "The ___ opens at nine."


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


async def test_a_failed_card_offers_the_paid_answer_and_asking_for_it_makes_the_card(
    settings,
    languages,
):
    """The reader is left holding an analysis and no card. The paid answer is offered
    rather than bought for them, and taking the offer is what makes the card."""
    cascade = fake_cascade(
        settings,
        handles=[FakeHandle([BROKEN_CARD])],
        client=FakeDirectClient([valid_card("word")]),
    )
    anki = RecordingAnki(Added(7, None))
    pipeline = WordPipeline(cascade, target_lang="Russian", anki=anki)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "word", False)
        await pipeline.join()
        assert entry.card_status == CARD_FAILED_STATUS
        assert entry.paid_answer_available is True
        assert anki.calls == []

        await pipeline.request_rebuild(entry.entry_id)
        await pipeline.join()
    finally:
        await pipeline.close()

    assert cascade.broker.direct_calls == ["gpt-fast"]
    assert [note.word for note, _deck, _audio in anki.calls] == ["word"]
    assert entry.card_status == ADDED_STATUS


async def test_a_carded_entry_is_not_offered_the_paid_answer_a_failed_one_is(
    settings,
    languages,
):
    cascade = fake_cascade(settings, handles=[FakeHandle([valid_card("word")])])
    anki = RecordingAnki(Added(7, None))
    pipeline = WordPipeline(cascade, target_lang="Russian", anki=anki)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "word", False)
        await pipeline.join()
    finally:
        await pipeline.close()

    assert entry.card_status == ADDED_STATUS
    assert entry.paid_answer_available is False


async def test_a_card_block_the_paid_model_breaks_too_ends_the_request(settings, languages):
    """The pool missed its budget, so the paid model answered in its place — and broke
    the payload in turn. There is no third step: the entry keeps the analysis and says
    the card failed."""
    handle = FakeHandle(error=POOL_MISSED)
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


async def test_undo_leaves_the_recordings_of_both_spellings_in_the_cache(
    languages,
    tmp_path,
):
    """Undo answers for the note and its media in the collection; the app's own cache
    is not the note's to empty."""
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
    )
    pipeline.start()
    try:
        await pipeline.enqueue(languages["en"], "gave up", False, intent="unit")
        await pipeline.join()
        assert await pipeline.undo(languages["en"]) == "gave up"
    finally:
        await pipeline.close()

    assert submitted.exists()
    assert headword.exists()


TABLE = ("table", "The book is on the table.", "table")
DESK = ("desk", "She works at her desk.", "desk")
NOT_A_WORD = '{"verdict": "not_a_word", "read_as": "", "equivalents": []}'
REVERSE_MARK = "You are a bilingual dictionary from"


def reverse_words(*equivalents, read_as="стол"):
    return json.dumps(
        {
            "verdict": "word",
            "read_as": read_as,
            "equivalents": [
                {"word": word, "example": sentence, "form": form}
                for word, sentence, form in equivalents
            ],
        },
        ensure_ascii=False,
    )


def reverse_sentence(translation):
    return json.dumps(
        {"verdict": "sentence", "read_as": "", "equivalents": [], "translation": translation},
        ensure_ascii=False,
    )


def typed_card(word, named, **fields):
    """The answer to typed input, which also names the language the input is in."""
    return card_with(word, submission=word, submission_language=named, **fields)


def typed_text(named, translation="Перевод."):
    return (
        f'{translation}===CARD==={{"kind":"text","submission":"x",'
        f'"submission_language":"{named}","combinations":[]}}'
    )


def typed(**overrides):
    """How the API queues one typed word in an alphabet the tab and the target share."""
    return {
        "intent": "unit",
        "typed": True,
        "shared_script": True,
        "offers_reverse": True,
        **overrides,
    }


def chips(*equivalents):
    return [
        {"label": word, "reason": "", "context": sentence, "surface": ""}
        for word, sentence, _form in equivalents
    ]


async def test_a_forced_reverse_cards_the_first_equivalent_and_offers_the_others(languages):
    spoken = []

    async def fetch_audio(text, _language):
        spoken.append(text)

    anki = RecordingAnki(Added(7, None, ("Recognition",)))
    reverse = Completion([reverse_words(TABLE, DESK)])
    cascade = ScriptedCascade([reverse, Completion([valid_card("table", context=TABLE[1])])])
    hub = EventHub()
    pipeline = WordPipeline(
        cascade,
        target_lang="Russian",
        events=hub,
        anki=anki,
        audio=fetch_audio,
    )
    pipeline.start()
    try:
        async with hub.subscribe() as subscriber:
            entry = await pipeline.enqueue(
                languages["en"],
                "стол",
                False,
                intent="unit",
                reverse="forced",
            )
            await pipeline.join()
            events = drain(subscriber)

        assert [event.data for event in events if event.name == "reset"] == [
            {
                "entry_id": entry.entry_id,
                "word": "table",
                "typed_word": "стол",
                "read_as": None,
                "context": TABLE[1],
                "requested_shape": "unit",
            },
        ]
        # From here the entry is the one a tap on a chip for "table" would have made.
        assert [note.word for note, _deck, _audio in anki.calls] == ["table"]
        assert (entry.word, entry.shown_spelling, entry.typed_word) == ("table", "table", "стол")
        assert (entry.card_status, entry.context) == (ADDED_STATUS, TABLE[1])
        assert (entry.segment_kind, entry.segments) == ("equivalents", chips(DESK))
        assert entry.carded_sense is None
        assert entry.detail_word == "table"
        # The typed target word is never spoken in the tab's voice.
        assert spoken == ["table", TABLE[1]]
        assert REVERSE_MARK in cascade.prompts[0]
        assert 'Wording: "стол"' in cascade.prompts[0]
        assert 'Make a card for this selected unit: "table"' in cascade.prompts[1]
        assert "submission_language" not in cascade.prompts[1]
        assert cascade.trace_ids == [f"{entry.entry_id}-reverse", entry.entry_id]
        assert reverse.scores == [1.0]
        assert await pipeline.undo(languages["en"]) == "table"
    finally:
        await pipeline.close()


async def test_a_reversal_names_the_word_the_typed_one_was_read_as(languages):
    """A slip or an inflected form is shown with the word it was taken for, so the
    reader sees whose equivalents these are."""
    cascade = ScriptedCascade(
        [
            Completion([reverse_words(TABLE, read_as="стол")]),
            Completion([valid_card("table", context=TABLE[1])]),
        ],
    )
    pipeline = WordPipeline(cascade, target_lang="Russian")
    pipeline.start()
    try:
        entry = await pipeline.enqueue(
            languages["en"],
            "Столы",
            False,
            intent="unit",
            reverse="script",
        )
        await pipeline.join()

        assert (entry.typed_word, entry.read_as, entry.word) == ("Столы", "стол", "table")
    finally:
        await pipeline.close()


async def test_a_single_equivalent_keeps_the_sense_chips_of_its_own_article(languages):
    cascade = ScriptedCascade(
        [Completion([reverse_words(TABLE)]), Completion([valid_card("table", context=TABLE[1])])],
    )
    pipeline = WordPipeline(
        cascade,
        target_lang="Russian",
        anki=RecordingAnki(Added(7, None)),
    )
    pipeline.start()
    try:
        entry = await pipeline.enqueue(
            languages["en"],
            "стол",
            False,
            intent="unit",
            reverse="forced",
        )
        await pipeline.join()

        assert entry.segment_kind == "senses"
        assert [chip["label"] for chip in entry.segments] == ["table"]
    finally:
        await pipeline.close()


async def test_a_lookup_only_reverse_finds_the_word_and_makes_no_card(languages):
    anki = RecordingAnki(Added(7, None))
    cascade = ScriptedCascade(
        [Completion([reverse_words(TABLE)]), Completion([valid_card("table", context=TABLE[1])])],
    )
    pipeline = WordPipeline(cascade, target_lang="Russian", anki=anki)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(
            languages["en"],
            "стол",
            True,
            intent="unit",
            reverse="forced",
        )
        await pipeline.join()

        assert (entry.word, entry.card_status) == ("table", LOOKUP_ONLY_STATUS)
        assert anki.calls == []
    finally:
        await pipeline.close()


async def test_a_rebuild_and_a_switch_of_a_reversed_entry_keep_the_other_equivalents(
    languages,
):
    """Each run rebuilds the chips from its own job, so without carrying them a rebuild
    or a switch would trade the other equivalents for the carded word's senses."""
    gasse = ("Gasse", "Die Gasse ist eng.", "Gasse")
    anki = MutableAnki([Added(1, None), Added(2, None), Added(3, None)])
    named_other = card_with("Straße", word_relation="typo", suggestion="Strasse")
    cascade = ScriptedCascade(
        [
            Completion([reverse_words(("Strase", "", ""), gasse, read_as="улица")]),
            Completion([named_other]),
            Completion([named_other]),
            Completion([corrected_card("Strasse")]),
        ],
    )
    pipeline = WordPipeline(cascade, target_lang="Russian", anki=anki)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(
            languages["de"],
            "улица",
            False,
            intent="unit",
            reverse="forced",
        )
        await pipeline.join()
        assert (entry.card_status, entry.suggestion) == (ADDED_STATUS, "Strasse")
        assert entry.segments == chips(gasse)

        await pipeline.request_rebuild(entry.entry_id)
        await pipeline.join()
        assert (entry.segment_kind, entry.segments) == ("equivalents", chips(gasse))

        await pipeline.request_switch(entry.entry_id)
        await pipeline.join()
        assert entry.word == "Strasse"
        assert (entry.segment_kind, entry.segments) == ("equivalents", chips(gasse))
        # What the reader typed still heads the entry after the switch.
        assert entry.typed_word == "улица"
        assert [prompt.count(REVERSE_MARK) for prompt in cascade.prompts] == [1, 0, 0, 0]
    finally:
        await pipeline.close()


async def test_an_equivalent_the_judgement_refuses_is_withheld_and_the_others_stay(languages):
    """The first equivalent goes through the judgement like any word. The others are
    kept: each is judged afresh when it is tapped."""
    anki = RecordingAnki(Added(7, None))
    cascade = ScriptedCascade(
        [
            Completion([reverse_words(TABLE, DESK)]),
            Completion([valid_card("table", context=TABLE[1])]),
        ],
        attestations=[REFUSED],
    )
    pipeline = WordPipeline(cascade, target_lang="Russian", anki=anki)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(
            languages["en"],
            "стол",
            False,
            intent="unit",
            reverse="forced",
        )
        await pipeline.join()

        assert (entry.card_status, entry.text) == (UNATTESTED_STATUS, "")
        assert (entry.segment_kind, entry.segments) == ("equivalents", chips(DESK))
        assert entry.reverse_offered is False
        assert anki.calls == []
    finally:
        await pipeline.close()


async def test_a_forced_reverse_of_no_word_says_so_and_stores_nothing(languages):
    anki = RecordingAnki(Added(7, None))
    spoken = []

    async def fetch_audio(text, _language):
        spoken.append(text)

    cascade = ScriptedCascade([Completion([NOT_A_WORD])])
    hub = EventHub()
    pipeline = WordPipeline(
        cascade,
        target_lang="Russian",
        events=hub,
        anki=anki,
        audio=fetch_audio,
    )
    pipeline.start()
    try:
        async with hub.subscribe() as subscriber:
            entry = await pipeline.enqueue(
                languages["sr"],
                "фывапр",
                False,
                intent="unit",
                reverse="forced",
                shared_script=True,
            )
            await pipeline.join()
            done = drain(subscriber)[-1]

        # A reader who asked for the target reading is not handed the tab's one instead.
        assert (done.name, done.data["card_status"]) == ("done", REVERSE_NOT_A_WORD_STATUS)
        assert (entry.action, entry.word) == (REVERSE_NOT_A_WORD_STATUS, "фывапр")
        assert (entry.status, entry.text, entry.segments) == ("done", "", [])
        assert anki.calls == []
        assert spoken == []
        assert len(cascade.prompts) == 1
        assert await pipeline.undo(languages["sr"]) is None
        assert pipeline.counters("sr") == {"lookup_only": 0}
    finally:
        await pipeline.close()


async def test_a_reversed_sentence_goes_down_the_text_path_as_its_translation(languages):
    spoken = []

    async def fetch_audio(text, _language):
        spoken.append(text)

    anki = RecordingAnki(Added(7, None))
    cascade = ScriptedCascade(
        [
            Completion([reverse_sentence("I am going home.")]),
            Completion(['Я иду домой.===CARD==={"kind":"text","combinations":[]}']),
        ],
    )
    pipeline = WordPipeline(cascade, target_lang="Russian", anki=anki, audio=fetch_audio)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["en"], "я иду домой", False, reverse="script")
        await pipeline.join()

        assert (entry.word, entry.typed_word) == ("I am going home.", "я иду домой")
        assert (entry.card_status, entry.shape, entry.segment_kind) == (TEXT_STATUS, "text", "text")
        assert [chip["label"] for chip in entry.segments] == ["I", "am", "going", "home"]
        assert 'Analyse this submitted text: "I am going home."' in cascade.prompts[1]
        assert "submission_language" not in cascade.prompts[1]
        assert spoken == ["I am going home."]
        assert anki.calls == []
        # Text is never asked about as a wording.
        assert cascade.attested == []
    finally:
        await pipeline.close()


async def test_a_reverse_answer_the_pool_cannot_make_usable_is_bought(languages):
    """Nothing is on the page yet, so the paid model is asked without the reader being
    asked first: the alternative is an entry that failed before it showed anything."""
    unusable = Completion(['{"verdict": "dog"}'])
    cascade = ScriptedCascade(
        [
            unusable,
            Completion([reverse_words(TABLE)]),
            Completion([valid_card("table", context=TABLE[1])]),
        ],
    )
    pipeline = WordPipeline(cascade, target_lang="Russian", anki=RecordingAnki(Added(7, None)))
    pipeline.start()
    try:
        entry = await pipeline.enqueue(
            languages["en"],
            "собака",
            False,
            intent="unit",
            reverse="script",
        )
        await pipeline.join()

        assert unusable.scores == [0.0]
        assert cascade.paid_calls == 1
        assert cascade.trace_ids[:2] == [
            f"{entry.entry_id}-reverse",
            f"{entry.entry_id}-reverse-paid",
        ]
        assert (entry.word, entry.card_status) == ("table", ADDED_STATUS)
    finally:
        await pipeline.close()


async def test_a_reverse_no_model_can_answer_fails_the_entry(languages):
    cascade = ScriptedCascade([Completion(["no json at all"])], refusal="the cap is spent")
    hub = EventHub()
    pipeline = WordPipeline(cascade, target_lang="Russian", events=hub)
    pipeline.start()
    try:
        async with hub.subscribe() as subscriber:
            entry = await pipeline.enqueue(
                languages["en"],
                "стол",
                False,
                intent="unit",
                reverse="forced",
            )
            await pipeline.join()
            last = drain(subscriber)[-1]

        assert last == Event("error", {"entry_id": entry.entry_id, "code": ANALYSIS_FAILED_CODE})
        assert (entry.status, entry.word) == ("error", "стол")
        assert cascade.paid_calls == 0
    finally:
        await pipeline.close()


async def test_a_reverse_the_pool_never_answers_fails_the_entry(languages):
    cascade = ScriptedCascade([Completion([], error=BackendError("nothing answered"))])
    pipeline = WordPipeline(cascade, target_lang="Russian")
    pipeline.start()
    try:
        entry = await pipeline.enqueue(
            languages["en"],
            "стол",
            False,
            intent="unit",
            reverse="forced",
        )
        await pipeline.join()

        # The cascade already stepped up inside that call, so there is no second purchase.
        assert entry.status == "error"
        assert cascade.paid_calls == 0
    finally:
        await pipeline.close()


async def test_a_silent_pool_is_stepped_up_inside_the_reverse_call(settings, languages):
    cascade = fake_cascade(
        settings,
        handles=[
            FakeHandle(error=POOL_MISSED),
            FakeHandle([valid_card("table", context=TABLE[1])]),
        ],
        client=FakeDirectClient([reverse_words(TABLE)]),
    )
    anki = RecordingAnki(Added(7, None))
    pipeline = WordPipeline(cascade, target_lang="Russian", anki=anki)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(
            languages["en"],
            "стол",
            False,
            intent="unit",
            reverse="forced",
        )
        await pipeline.join()
    finally:
        await pipeline.close()

    assert cascade.broker.direct_calls == ["gpt-fast"]
    assert cascade.calls_today == 1
    assert (entry.word, entry.card_status) == ("table", ADDED_STATUS)


async def test_a_paid_reverse_nobody_can_read_is_not_bought_a_second_time(settings, languages):
    cascade = fake_cascade(
        settings,
        handles=[FakeHandle(error=POOL_MISSED)],
        client=FakeDirectClient(['{"verdict": "dog"}']),
    )
    pipeline = WordPipeline(cascade, target_lang="Russian")
    pipeline.start()
    try:
        entry = await pipeline.enqueue(
            languages["en"],
            "стол",
            False,
            intent="unit",
            reverse="forced",
        )
        await pipeline.join()
    finally:
        await pipeline.close()

    assert cascade.broker.direct_calls == ["gpt-fast"]
    assert (entry.status, entry.word) == ("error", "стол")


async def test_an_unreadable_pool_reverse_is_rated_down_and_replaced_by_a_paid_one(
    settings,
    languages,
):
    unreadable = FakeHandle(['{"verdict": "dog"}'])
    cascade = fake_cascade(
        settings,
        handles=[unreadable, FakeHandle([valid_card("table", context=TABLE[1])])],
        client=FakeDirectClient([reverse_words(TABLE)]),
    )
    pipeline = WordPipeline(cascade, target_lang="Russian", anki=RecordingAnki(Added(7, None)))
    pipeline.start()
    try:
        entry = await pipeline.enqueue(
            languages["en"],
            "стол",
            False,
            intent="unit",
            reverse="forced",
        )
        await pipeline.join()
    finally:
        await pipeline.close()

    assert unreadable.scores == [0.0]
    assert cascade.broker.direct_calls == ["gpt-fast"]
    assert (entry.word, entry.card_status) == ("table", ADDED_STATUS)


MAIN_MODEL = "google-gemini-3.5-flash-lite"
OTHER_MODEL = "groq-gpt-oss-120b"


def forced_reverse_pipeline(cascade, anki=None, reverse_pool_models=(MAIN_MODEL,)):
    return WordPipeline(
        cascade,
        target_lang="Russian",
        anki=anki or RecordingAnki(Added(7, None)),
        reverse_pool_models=reverse_pool_models,
    )


async def test_a_reverse_another_pool_model_answered_is_bought_from_the_paid_model(
    settings,
    languages,
    caplog,
):
    """Nothing is on the page yet, so the other model's lookup is set aside unseen and
    the paid model answers instead."""
    caplog.set_level(logging.INFO, logger="echo_words.pipeline")
    other = FakeHandle([reverse_words(DESK)], llm_name=OTHER_MODEL)
    cascade = fake_cascade(
        settings,
        handles=[other, FakeHandle([valid_card("table", context=TABLE[1])])],
        client=FakeDirectClient([reverse_words(TABLE)]),
    )
    anki = RecordingAnki(Added(7, None))
    pipeline = forced_reverse_pipeline(cascade, anki)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(
            languages["en"],
            "стол",
            False,
            intent="unit",
            reverse="forced",
        )
        await pipeline.join()
    finally:
        await pipeline.close()

    assert cascade.broker.direct_calls == ["gpt-fast"]
    assert cascade.calls_today == 1
    assert (entry.word, entry.card_status) == ("table", ADDED_STATUS)
    assert [note.word for note, _deck, _audio in anki.calls] == ["table"]
    # The rating is the language's, shared with the article, so the answer keeps it.
    assert other.scores == [1.0]
    assert (
        f"the paid model answers the reverse lookup for en: the pool answer came from {OTHER_MODEL}"
        in caplog.messages
    )
    assert not any("stands for the reverse lookup" in message for message in caplog.messages)


async def test_a_reverse_another_pool_model_answered_stands_when_the_paid_step_is_refused(
    settings,
    languages,
    caplog,
):
    caplog.set_level(logging.INFO, logger="echo_words.pipeline")
    capped = settings.model_copy(update={"api_daily_cap": 1})
    cascade = fake_cascade(
        capped,
        handles=[
            FakeHandle([reverse_words(TABLE)], llm_name=OTHER_MODEL),
            FakeHandle([valid_card("table", context=TABLE[1])]),
        ],
        client=FakeDirectClient([reverse_words(DESK)]),
    )
    cascade.spend_paid_call(languages["en"])
    pipeline = forced_reverse_pipeline(cascade)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(
            languages["en"],
            "стол",
            False,
            intent="unit",
            reverse="forced",
        )
        await pipeline.join()
    finally:
        await pipeline.close()

    assert cascade.broker.direct_calls == []
    assert (entry.word, entry.card_status) == ("table", ADDED_STATUS)
    assert not any("the paid model answers" in message for message in caplog.messages)


@pytest.mark.parametrize(
    "client",
    [FakeDirectClient(['{"verdict": "dog"}']), FakeDirectClient([])],
    ids=["unreadable", "failed"],
)
async def test_a_set_aside_reverse_stands_when_the_paid_model_gives_none(
    settings,
    languages,
    caplog,
    client,
):
    """A paid step that gives no usable lookup leaves the reader with the pool's one
    rather than with an entry that failed."""
    caplog.set_level(logging.INFO, logger="echo_words.pipeline")
    cascade = fake_cascade(
        settings,
        handles=[
            FakeHandle([reverse_words(TABLE)], llm_name=OTHER_MODEL),
            FakeHandle([valid_card("table", context=TABLE[1])]),
        ],
        client=client,
    )
    pipeline = forced_reverse_pipeline(cascade)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(
            languages["en"],
            "стол",
            False,
            intent="unit",
            reverse="forced",
        )
        await pipeline.join()
    finally:
        await pipeline.close()

    assert cascade.broker.direct_calls == ["gpt-fast"]
    assert (entry.word, entry.card_status) == ("table", ADDED_STATUS)
    assert (
        f"the pool answer from {OTHER_MODEL} stands for the reverse lookup for en:"
        " the paid model gave none"
    ) in caplog.messages
    assert not any("the paid model answers" in message for message in caplog.messages)


@pytest.mark.parametrize(
    ("model", "reverse_pool_models"),
    [(MAIN_MODEL, (MAIN_MODEL,)), (OTHER_MODEL, ())],
    ids=["main-model", "empty-setting"],
)
async def test_a_reverse_a_main_pool_model_answered_buys_nothing(
    settings,
    languages,
    model,
    reverse_pool_models,
):
    """With no model named, every pool model counts as a main one."""
    cascade = fake_cascade(
        settings,
        handles=[
            FakeHandle([reverse_words(TABLE)], llm_name=model),
            FakeHandle([valid_card("table", context=TABLE[1])]),
        ],
        client=FakeDirectClient([reverse_words(DESK)]),
    )
    pipeline = forced_reverse_pipeline(cascade, reverse_pool_models=reverse_pool_models)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(
            languages["en"],
            "стол",
            False,
            intent="unit",
            reverse="forced",
        )
        await pipeline.join()
    finally:
        await pipeline.close()

    assert cascade.broker.direct_calls == []
    assert (entry.word, entry.card_status) == ("table", ADDED_STATUS)


async def test_only_typed_input_is_asked_which_language_it_is_in(languages):
    cascade = ScriptedCascade(
        [Completion([typed_card("word", "en")]), Completion([valid_card("word")])],
    )
    pipeline = WordPipeline(cascade, target_lang="Russian", anki=RecordingAnki(Added(7, None)))
    pipeline.start()
    try:
        typed_entry = await pipeline.enqueue(languages["en"], "word", False, **typed())
        chip = await pipeline.enqueue(languages["en"], "word", False, intent="unit")
        await pipeline.join()

        assert "submission_language" in cascade.prompts[0]
        assert "submission_language" not in cascade.prompts[1]
        assert (typed_entry.card_status, chip.card_status) == (ADDED_STATUS, ADDED_STATUS)
    finally:
        await pipeline.close()


async def test_a_refused_word_the_answer_names_the_targets_is_looked_up_in_reverse(languages):
    grad = ("grad", "Ovo je lep grad.", "grad")
    anki = RecordingAnki(Added(7, None))
    hub = EventHub()
    cascade = ScriptedCascade(
        [
            Completion([typed_card("город", "ru")]),
            Completion([reverse_words(grad, read_as="город")]),
            Completion([valid_card("grad", context=grad[1])]),
        ],
        attestations=[REFUSED],
    )
    pipeline = WordPipeline(cascade, target_lang="Russian", events=hub, anki=anki)
    pipeline.start()
    try:
        async with hub.subscribe() as subscriber:
            entry = await pipeline.enqueue(languages["sr"], "город", False, **typed())
            await pipeline.join()
            events = drain(subscriber)

        assert (entry.word, entry.typed_word, entry.card_status) == ("grad", "город", ADDED_STATUS)
        assert [note.word for note, _deck, _audio in anki.calls] == ["grad"]
        assert entry.reverse_offered is False
        # The tab's own answer about «город» was withheld throughout, and dropped.
        assert [event.data["text"] for event in events if event.name == "update"] == ["analysis"]
        assert cascade.trace_ids == [entry.entry_id, f"{entry.entry_id}-reverse", entry.entry_id]
    finally:
        await pipeline.close()


async def test_a_vouched_word_stays_the_tabs_whatever_language_the_answer_names(languages):
    """The line alone takes a rare word of the tab spelled like a common target word
    for the target's (врач, a sorcerer), so the judgement has to refuse it as well."""
    anki = RecordingAnki(Added(7, None))
    cascade = ScriptedCascade([Completion([typed_card("врач", "ru")])])
    pipeline = WordPipeline(cascade, target_lang="Russian", anki=anki)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["sr"], "врач", False, **typed())
        await pipeline.join()

        assert (entry.word, entry.typed_word, entry.card_status) == ("врач", None, ADDED_STATUS)
        assert len(cascade.prompts) == 1
    finally:
        await pipeline.close()


async def test_a_target_reading_never_reverses_an_alphabet_the_target_does_not_write(
    languages,
):
    """Latin on the Serbian tab with a Russian target: nobody types Russian in Latin
    letters, so the answer's reading of it is not acted on."""
    cascade = ScriptedCascade([Completion([typed_card("grad", "ru")])], attestations=[REFUSED])
    pipeline = WordPipeline(cascade, target_lang="Russian")
    pipeline.start()
    try:
        entry = await pipeline.enqueue(
            languages["sr"],
            "grad",
            False,
            **typed(shared_script=False, offers_reverse=False),
        )
        await pipeline.join()

        assert (entry.card_status, entry.typed_word) == (UNATTESTED_STATUS, None)
        assert len(cascade.prompts) == 1
    finally:
        await pipeline.close()


async def test_text_the_answer_names_the_targets_is_translated_without_a_judgement(languages):
    """Text has no judgement to wait for: its own words say which language it is."""
    cascade = ScriptedCascade(
        [
            Completion([typed_text("ru")]),
            Completion([reverse_sentence("Idemo kući.")]),
            Completion(['Мы идём домой.===CARD==={"kind":"text","combinations":[]}']),
        ],
    )
    hub = EventHub()
    pipeline = WordPipeline(cascade, target_lang="Russian", events=hub)
    pipeline.start()
    try:
        async with hub.subscribe() as subscriber:
            entry = await pipeline.enqueue(
                languages["sr"],
                "мы идём домой",
                False,
                typed=True,
                shared_script=True,
            )
            await pipeline.join()
            events = drain(subscriber)

        assert (entry.word, entry.typed_word) == ("Idemo kući.", "мы идём домой")
        assert (entry.card_status, entry.text) == (TEXT_STATUS, "Мы идём домой.")
        assert cascade.attested == []
        resets = [event.data for event in events if event.name == "reset"]
        assert (resets[-1]["word"], resets[-1]["requested_shape"]) == ("Idemo kući.", None)
    finally:
        await pipeline.close()


async def test_a_target_reading_no_lookup_confirms_leaves_the_answer_in_hand(languages):
    """Today's outcome is the floor: «йош» is Serbian још typed on a Russian keyboard,
    and when the lookup finds no Russian word the tab's answer goes on as it would
    have, with no second article asked for."""
    anki = RecordingAnki(Added(7, None))
    corrected = card_with(
        "још",
        word_relation="typo",
        suggestion="још",
        submission="йош",
        submission_language="ru",
    )
    cascade = ScriptedCascade(
        [Completion([corrected]), Completion([NOT_A_WORD])],
        attestations=[REFUSED, ScriptedCascade.VOUCHED],
    )
    pipeline = WordPipeline(cascade, target_lang="Russian", anki=anki)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["sr"], "йош", False, **typed())
        await pipeline.join()

        assert [note.word for note, _deck, _audio in anki.calls] == ["још"]
        assert (entry.card_status, entry.typed_word) == (ADDED_STATUS, None)
        assert len(cascade.prompts) == 2
    finally:
        await pipeline.close()


async def test_a_refusal_the_lookup_already_answered_is_not_offered_the_lookup_again(languages):
    cascade = ScriptedCascade(
        [Completion([typed_card("фывапр", "ru")]), Completion([NOT_A_WORD])],
        attestations=[REFUSED],
    )
    pipeline = WordPipeline(cascade, target_lang="Russian")
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["sr"], "фывапр", False, **typed())
        await pipeline.join()

        assert entry.card_status == UNATTESTED_STATUS
        assert entry.reverse_offered is False
    finally:
        await pipeline.close()


async def test_a_lookup_the_line_asked_for_is_never_bought(settings, languages):
    """The tab's answer is in hand, so an unreadable lookup costs the reader nothing
    they had: it is not paid for, and the answer stands with the lookup on offer."""
    cascade = fake_cascade(
        settings,
        handles=[FakeHandle([typed_card("город", "ru")]), FakeHandle(['{"verdict": "dog"}'])],
        client=FakeDirectClient([reverse_words(("grad", "Ovo je lep grad.", "grad"))]),
        attestation=REFUSED,
    )
    pipeline = WordPipeline(cascade, target_lang="Russian")
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["sr"], "город", False, **typed())
        await pipeline.join()
    finally:
        await pipeline.close()

    assert cascade.broker.direct_calls == []
    assert (entry.card_status, entry.word) == (UNATTESTED_STATUS, "город")
    assert entry.reverse_offered is True


async def test_a_lookup_the_line_asked_for_is_not_bought_from_a_silent_pool(settings, languages):
    """A pool that never answers steps an ordinary call up to the paid model by itself,
    which is the one purchase this lookup must not make either."""
    cascade = fake_cascade(
        settings,
        handles=[FakeHandle([typed_card("город", "ru")]), FakeHandle(error=POOL_MISSED)],
        client=FakeDirectClient([reverse_words(("grad", "Ovo je lep grad.", "grad"))]),
        attestation=REFUSED,
    )
    pipeline = WordPipeline(cascade, target_lang="Russian")
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["sr"], "город", False, **typed())
        await pipeline.join()
    finally:
        await pipeline.close()

    assert cascade.broker.direct_calls == []
    assert (entry.card_status, entry.word) == (UNATTESTED_STATUS, "город")
    assert entry.reverse_offered is True
    # The tab's own answer is the language's last call, and it was answered.
    assert cascade.last_calls["sr"].ok is True


@pytest.mark.parametrize(
    ("model", "reverse_pool_models", "reversed_"),
    [
        (OTHER_MODEL, (MAIN_MODEL,), False),
        (MAIN_MODEL, (MAIN_MODEL,), True),
        (OTHER_MODEL, (), True),
    ],
    ids=["other-model", "main-model", "empty-setting"],
)
async def test_a_last_resort_lookup_another_pool_model_answered_is_dropped(
    settings,
    languages,
    caplog,
    model,
    reverse_pool_models,
    reversed_,
):
    """The tab's own answer is in hand, so the other model's lookup is not bought over:
    it counts as none, and the reader can still ask for the lookup with one tap."""
    caplog.set_level(logging.INFO, logger="echo_words.pipeline")
    grad = ("grad", "Ovo je lep grad.", "grad")
    cascade = fake_cascade(
        settings,
        handles=[
            FakeHandle([typed_card("город", "ru")]),
            FakeHandle([reverse_words(grad, read_as="город")], llm_name=model),
            FakeHandle([valid_card("grad", context=grad[1])]),
        ],
        client=FakeDirectClient([reverse_words(("varoš", "Ovo je mala varoš.", "varoš"))]),
        attestations=[REFUSED],
    )
    pipeline = WordPipeline(
        cascade,
        target_lang="Russian",
        anki=RecordingAnki(Added(7, None)),
        reverse_pool_models=reverse_pool_models,
    )
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["sr"], "город", False, **typed())
        await pipeline.join()
    finally:
        await pipeline.close()

    dropped = f"the last-resort reverse lookup for sr is dropped: the pool answer came from {model}"
    assert cascade.broker.direct_calls == []
    if reversed_:
        assert (entry.word, entry.card_status, entry.reverse_offered) == (
            "grad",
            ADDED_STATUS,
            False,
        )
        assert dropped not in caplog.messages
    else:
        assert (entry.word, entry.card_status, entry.reverse_offered) == (
            "город",
            UNATTESTED_STATUS,
            True,
        )
        assert dropped in caplog.messages


async def test_input_in_another_of_the_readers_languages_moves_to_its_tab(languages):
    anki = RecordingAnki(Added(7, None))
    hub = EventHub()
    cascade = ScriptedCascade(
        [Completion([typed_card("Haus", "de")]), Completion([valid_card("Haus")])],
    )
    pipeline = WordPipeline(
        cascade,
        target_lang="Russian",
        languages=lambda: languages,
        events=hub,
        anki=anki,
    )
    pipeline.start()
    try:
        async with hub.subscribe() as subscriber:
            entry = await pipeline.enqueue(
                languages["en"],
                "Haus",
                False,
                **typed(shared_script=False, offers_reverse=False),
            )
            await pipeline.join()
            events = drain(subscriber)

        moved = [event.data for event in events if event.name == "moved"]
        assert moved == [{"entry_id": entry.entry_id, "lang": "de", "language": "Deutsch"}]
        assert (entry.lang, entry.language, entry.card_status) == ("de", "Deutsch", ADDED_STATUS)
        assert [(note.word, deck) for note, deck, _audio in anki.calls] == [
            ("Haus", "German::Vocabulary"),
        ]
        # Asked once: the tab it lands on answers by its own rules and is not read again.
        assert cascade.calls == ["en", "de"]
        assert "submission_language" not in cascade.prompts[1]
        assert pipeline.history.undo["de"].word == "Haus"
        assert await pipeline.undo(languages["en"]) is None
    finally:
        await pipeline.close()


async def test_a_move_leaves_undo_with_a_word_sent_to_that_tab_after_it(languages):
    """Undo follows the latest send, and an entry that arrives on a tab by being moved
    was sent before the word the reader typed there while it was still being answered."""
    cascade = ScriptedCascade(
        [
            Completion([typed_card("Haus", "de")]),
            Completion([valid_card("Haus")]),
            Completion([valid_card("Tisch")]),
        ],
    )
    pipeline = WordPipeline(
        cascade,
        target_lang="Russian",
        languages=lambda: languages,
        anki=RecordingAnki(Added(7, None)),
    )
    moved = await pipeline.enqueue(
        languages["en"],
        "Haus",
        False,
        **typed(shared_script=False, offers_reverse=False),
    )
    later = await pipeline.enqueue(languages["de"], "Tisch", False, intent="unit")
    pipeline.start()
    try:
        await pipeline.join()

        assert (moved.lang, later.lang) == ("de", "de")
        assert (moved.card_status, later.card_status) == (ADDED_STATUS, ADDED_STATUS)
        assert pipeline.history.undo["de"].word == "Tisch"
    finally:
        await pipeline.close()


async def test_croatian_named_by_the_answer_is_serbian_to_the_reader_of_a_serbian_tab(
    languages,
):
    """Both languages spell «kuća» alike and a model names it by either; to this reader
    they are one language, so it moves to the Serbian tab instead of being headed as a
    translation from a language nobody here is learning."""
    cascade = ScriptedCascade(
        [Completion([typed_card("kuća", "hr")]), Completion([valid_card("kuća")])],
    )
    pipeline = WordPipeline(
        cascade,
        target_lang="Russian",
        languages=lambda: languages,
        anki=RecordingAnki(Added(7, None)),
    )
    pipeline.start()
    try:
        entry = await pipeline.enqueue(
            languages["de"],
            "kuća",
            False,
            **typed(shared_script=False, offers_reverse=False),
        )
        await pipeline.join()

        assert (entry.lang, entry.card_status, entry.foreign_language) == ("sr", ADDED_STATUS, None)
    finally:
        await pipeline.close()


@pytest.mark.parametrize("named", ["hr", "bs", "sr", "SR"])
async def test_the_serbian_tabs_own_wording_stays_whatever_standard_it_is_named_by(
    languages,
    named,
):
    anki = RecordingAnki(Added(7, None))
    cascade = ScriptedCascade([Completion([typed_card("kuća", named)])])
    pipeline = WordPipeline(
        cascade,
        target_lang="Russian",
        languages=lambda: languages,
        anki=anki,
    )
    pipeline.start()
    try:
        entry = await pipeline.enqueue(
            languages["sr"],
            "kuća",
            False,
            **typed(shared_script=False, offers_reverse=False),
        )
        await pipeline.join()

        assert (entry.lang, entry.card_status, entry.foreign_language) == ("sr", ADDED_STATUS, None)
        assert len(cascade.prompts) == 1
    finally:
        await pipeline.close()


async def test_a_reader_with_a_croatian_tab_is_moved_there(languages):
    croatian = replace(languages["sr"], code="hr", name="Hrvatski", script="latin")
    tabs = {**languages, "hr": croatian}
    cascade = ScriptedCascade(
        [Completion([typed_card("kuća", "hr")]), Completion([valid_card("kuća")])],
    )
    pipeline = WordPipeline(cascade, target_lang="Russian", languages=lambda: tabs)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(
            languages["en"],
            "kuća",
            False,
            **typed(shared_script=False, offers_reverse=False),
        )
        await pipeline.join()

        assert entry.lang == "hr"
    finally:
        await pipeline.close()


async def test_input_a_tab_cannot_write_is_not_moved_to_it(languages):
    """The answer named a language whose tab takes another alphabet, so there is
    nothing that tab could do with these letters."""
    cyrillic_only = replace(languages["sr"], code="bg", name="Български", script="cyrillic")
    tabs = {**languages, "bg": cyrillic_only}
    cascade = ScriptedCascade([Completion([typed_card("kuka", "bg")])])
    pipeline = WordPipeline(cascade, target_lang="Russian", languages=lambda: tabs)
    pipeline.start()
    try:
        entry = await pipeline.enqueue(
            languages["en"],
            "kuka",
            False,
            **typed(shared_script=False, offers_reverse=False),
        )
        await pipeline.join()

        assert (entry.lang, len(cascade.prompts)) == ("en", 1)
    finally:
        await pipeline.close()


async def test_input_in_a_language_no_tab_teaches_is_translated_and_nothing_more(languages):
    """The reader is not learning French: the answer stays as written, with no card,
    no chips and nothing spoken in the English voice — and the English judgement,
    which rightly finds the word unused in English, withholds none of it."""
    spoken = []

    async def fetch_audio(text, _language):
        spoken.append(text)

    anki = RecordingAnki(Added(7, None))
    hub = EventHub()
    cascade = ScriptedCascade(
        [Completion([typed_card("chaussure", "fr")])],
        attestations=[REFUSED],
    )
    pipeline = WordPipeline(
        cascade,
        target_lang="Russian",
        languages=lambda: languages,
        events=hub,
        anki=anki,
        audio=fetch_audio,
    )
    pipeline.start()
    try:
        async with hub.subscribe() as subscriber:
            entry = await pipeline.enqueue(
                languages["en"],
                "chaussure",
                False,
                **typed(shared_script=False, offers_reverse=False),
            )
            await pipeline.join()
            done = drain(subscriber)[-1]

        assert (entry.card_status, entry.action) == (FOREIGN_STATUS, FOREIGN_STATUS)
        assert (entry.foreign_language, entry.text) == ("fr", "analysis")
        assert (done.data["foreign_language"], done.data["text"]) == ("fr", "analysis")
        assert (entry.segments, entry.shape, entry.suggestion) == ([], None, None)
        assert (entry.audio_url, entry.no_audio) == (None, False)
        assert (entry.detail_available, entry.paid_answer_available) == (False, False)
        assert entry.lang == "en"
        assert anki.calls == []
        assert await pipeline.undo(languages["en"]) is None
    finally:
        await pipeline.close()


@pytest.mark.parametrize(
    ("answer", "attestations", "submission", "offered"),
    [
        # One typed word the tab's language refuses may be a target word instead.
        (typed_card("книга", "sr"), [REFUSED], typed(), True),
        # A refused lookup made no card either way, and is offered the same reading.
        (typed_card("книга", "sr"), [REFUSED], typed(lookup_only=True), True),
        # A chip comes from the app's own answer, and is never offered it.
        (valid_card("книга"), [REFUSED], {"intent": "unit"}, False),
        # A word the tab's language takes needs no other reading.
        (typed_card("књига", "sr"), [], typed(), False),
    ],
)
async def test_a_typed_word_the_tab_refuses_is_offered_the_target_reading(
    languages,
    answer,
    attestations,
    submission,
    offered,
):
    hub = EventHub()
    cascade = ScriptedCascade([Completion([answer])], attestations=attestations)
    pipeline = WordPipeline(cascade, target_lang="Russian", events=hub)
    lookup_only = submission.pop("lookup_only", False)
    pipeline.start()
    try:
        async with hub.subscribe() as subscriber:
            entry = await pipeline.enqueue(languages["sr"], "книга", lookup_only, **submission)
            await pipeline.join()
            done = drain(subscriber)[-1]

        assert entry.reverse_offered is offered
        assert done.data["reverse_offered"] is offered
    finally:
        await pipeline.close()


async def test_a_misspelling_the_answer_corrects_and_cards_is_not_offered_the_lookup(languages):
    corrected = card_with(
        "књига",
        word_relation="typo",
        suggestion="књига",
        submission="кнйига",
        submission_language="sr",
    )
    cascade = ScriptedCascade(
        [Completion([corrected])],
        attestations=[REFUSED, ScriptedCascade.VOUCHED],
    )
    pipeline = WordPipeline(cascade, target_lang="Russian", anki=RecordingAnki(Added(7, None)))
    pipeline.start()
    try:
        entry = await pipeline.enqueue(languages["sr"], "кнйига", False, **typed())
        await pipeline.join()

        assert (entry.card_status, entry.reverse_offered) == (ADDED_STATUS, False)
    finally:
        await pipeline.close()


def test_a_new_run_of_an_entry_withdraws_the_offer_and_keeps_what_was_typed(languages):
    entry = Entry("one", "sr", "grad", typed_word="город", read_as="город")
    entry.reverse_offered = True
    entry.foreign_language = "fr"

    for kind in ("switch", "rebuild"):
        WordPipeline._reset_reused_entry(entry, languages["sr"], "grad", False, "", kind)

        assert (entry.reverse_offered, entry.foreign_language) == (False, None)
        assert (entry.typed_word, entry.read_as) == ("город", "город")
        entry.reverse_offered = True
