import asyncio
import hashlib
import logging
import threading
from collections import deque
from pathlib import Path

import pytest
from anki.errors import SyncError, SyncErrorKind
from anki.sync import SyncAuth
from anki.sync_pb2 import SyncCollectionResponse

from echo_words.anki import (
    FIELD_NAMES,
    NOTE_TYPE_NAME,
    SYNC_INTERVAL_SECONDS,
    TEMPLATE_NAMES,
    Added,
    AnkiStore,
    Duplicate,
    MisconfiguredNoteTypeError,
    PylibSyncBackend,
    render_meanings,
    render_translations,
)
from echo_words.card import Example, Meaning, Note
from echo_words.config import Settings

pytestmark = pytest.mark.anyio


def make_note(
    word: str = "receive",
    *,
    meanings: list[Meaning] | None = None,
) -> Note:
    return Note(
        word,
        meanings
        or [
            Meaning(
                label="",
                pos="гл.",
                translations=["получать", "принимать"],
                examples=[Example("I receive a parcel.", "Я получаю посылку.")],
            ),
        ],
    )


def local_settings(tmp_path: Path, **values: object) -> Settings:
    return Settings(_env_file=None, data_dir=tmp_path, anki_sync=False, **values)


async def test_note_type_bootstrap_creates_the_fields_and_both_card_templates(tmp_path):
    store = AnkiStore(local_settings(tmp_path))
    await store.open()
    try:
        result = await store.add_note(make_note(), "English::Vocabulary")
        assert isinstance(result, Added)
        model = store.collection.models.by_name(NOTE_TYPE_NAME)
        assert tuple(field["name"] for field in model["flds"]) == FIELD_NAMES
        assert tuple(template["name"] for template in model["tmpls"]) == TEMPLATE_NAMES
        assert model["tmpls"][0]["qfmt"] == "{{Word}} {{Audio}}"
        assert model["tmpls"][0]["afmt"] == "{{Meanings}}"
        assert model["tmpls"][1]["qfmt"] == "{{Translations}}"
        assert model["tmpls"][1]["afmt"] == "{{Word}} {{Audio}}"
        assert len(store.collection.find_cards(f"nid:{result.note_id}")) == 2
    finally:
        await store.close()


@pytest.mark.parametrize("wrong_part", ["fields", "templates"])
async def test_a_preexisting_incompatible_note_type_fails_without_adding(tmp_path, wrong_part):
    store = AnkiStore(local_settings(tmp_path))
    await store.open()
    try:
        models = store.collection.models
        model = models.new(NOTE_TYPE_NAME)
        fields = FIELD_NAMES if wrong_part == "templates" else ("Word", "Wrong")
        for name in fields:
            models.add_field(model, models.new_field(name))
        templates = TEMPLATE_NAMES if wrong_part == "fields" else ("Recognition", "Wrong")
        for index, name in enumerate(templates):
            template = models.new_template(name)
            second_field = "Wrong" if wrong_part == "fields" else "Translations"
            template["qfmt"] = "{{Word}}" if index == 0 else f"{{{{{second_field}}}}}"
            models.add_template(model, template)
        models.add(model)

        with pytest.raises(MisconfiguredNoteTypeError, match="fix or delete it in Anki"):
            await store.add_note(make_note(), "English::Vocabulary")
        assert store.collection.note_count() == 0
    finally:
        await store.close()


async def test_decks_are_created_and_duplicates_are_scoped_to_each_deck(tmp_path):
    store = AnkiStore(local_settings(tmp_path))
    await store.open()
    try:
        english = await store.add_note(make_note("Hand"), "English::Vocabulary")
        duplicate = await store.add_note(make_note("hand"), "English::Vocabulary")
        german = await store.add_note(make_note("Hand"), "German::Vocabulary")

        assert isinstance(english, Added)
        assert isinstance(duplicate, Duplicate)
        assert isinstance(german, Added)
        assert store.collection.note_count() == 2
        deck_names = {deck.name for deck in store.collection.decks.all_names_and_ids()}
        assert {"English::Vocabulary", "German::Vocabulary"} <= deck_names
    finally:
        await store.close()


async def test_single_meaning_fields_are_compact_and_unnumbered():
    note = make_note()
    assert render_translations(note) == (
        "получать, принимать<br><i>I ___ a parcel.</i> — Я получаю посылку."
    )
    assert render_meanings(note) == (
        "получать, принимать<br><i>I receive a parcel.</i> — Я получаю посылку."
    )


async def test_multiple_meanings_are_labeled_and_recognition_is_numbered():
    note = make_note(
        "bank",
        meanings=[
            Meaning("финансы", "сущ.", ["банк"], [Example("The bank opens.", "Банк открыт.")]),
            Meaning("река", "сущ.", ["берег"], [Example("A bank is wet.", "Берег мокрый.")]),
        ],
    )
    translations = render_translations(note)
    meanings = render_meanings(note)
    assert translations == (
        "<b>финансы</b><br>банк<br><i>The ___ opens.</i> — Банк открыт."
        "<br><br><b>река</b><br>берег<br><i>A ___ is wet.</i> — Берег мокрый."
    )
    assert meanings.startswith("<ol><li><b>финансы</b>")
    assert meanings.endswith("</li></ol>")
    assert meanings.count("<li>") == 2


@pytest.mark.parametrize(
    ("word", "sentence", "expected"),
    [
        ("word", "Word after word, WORD.", "___ after ___, ___."),
        ("go over", "We go over it, then GO OVER it.", "We ___ it, then ___ it."),
    ],
)
async def test_recall_masks_every_exact_whole_word_occurrence(word, sentence, expected):
    note = make_note(
        word,
        meanings=[Meaning("", "", ["перевод"], [Example(sentence, "Перевод.")])],
    )
    rendered = render_translations(note)
    assert expected in rendered
    assert sentence not in rendered


async def test_recall_falls_back_to_pos_when_only_an_inflected_form_occurs():
    note = make_note(
        "receive",
        meanings=[Meaning("", "гл.", ["получать"], [Example("She receives it.", "Она получает.")])],
    )
    rendered = render_translations(note)
    assert rendered == "получать<br><i>гл.</i>"
    assert "receives" not in rendered


async def test_recall_with_no_match_or_pos_contains_translations_alone():
    note = make_note(
        "receive",
        meanings=[Meaning("", "", ["получать"], [Example("She gets it.", "Она получает.")])],
    )
    assert render_translations(note) == "получать"


async def test_every_payload_value_is_html_escaped():
    note = make_note(
        "a&b",
        meanings=[
            Meaning(
                "<sense>",
                "noun",
                ["x < y", 'say "yes" & go'],
                [Example("Use a&b <now>.", "A & B <сейчас>.")],
            ),
            Meaning(
                "other & sense",
                "<noun>",
                ["second & value"],
                [Example("No exact headword.", "Нет & слова.")],
            ),
        ],
    )
    translations = render_translations(note)
    meanings = render_meanings(note)
    assert "<sense>" not in translations + meanings
    assert "&lt;sense&gt;" in translations + meanings
    assert "other &amp; sense" in translations + meanings
    assert "&lt;noun&gt;" in translations
    assert "x &lt; y" in translations + meanings
    assert "say &quot;yes&quot; &amp; go" in translations + meanings
    assert "Use ___ &lt;now&gt;." in translations
    assert "A &amp; B &lt;сейчас&gt;." in translations + meanings


async def test_media_name_uses_slug_hash_and_the_name_returned_by_anki(tmp_path):
    store = AnkiStore(local_settings(tmp_path))
    await store.open()
    try:
        word = "go over"
        digest = hashlib.sha1(word.encode(), usedforsecurity=False).hexdigest()[:8]
        requested = f"echo-words-go-over-{digest}.mp3"
        media_dir = Path(store.collection.media.dir())
        (media_dir / requested).write_bytes(b"old file")
        audio = tmp_path / "audio.mp3"
        audio.write_bytes(b"new audio")

        result = await store.add_note(make_note(word), "English::Vocabulary", audio)

        assert isinstance(result, Added)
        assert result.media_filename != requested
        assert result.media_filename.startswith(f"echo-words-go-over-{digest}")
        stored = store.collection.get_note(result.note_id)
        assert stored["Audio"] == f"[sound:{result.media_filename}]"
        assert (media_dir / result.media_filename).read_bytes() == b"new audio"
        assert store.last_added_by_deck["English::Vocabulary"] == result
    finally:
        await store.close()


async def test_equal_slugs_get_distinct_hashes_in_their_media_names(tmp_path):
    store = AnkiStore(local_settings(tmp_path))
    await store.open()
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"audio")
    try:
        spaced = await store.add_note(make_note("go over"), "English::Vocabulary", audio)
        hyphenated = await store.add_note(make_note("go-over"), "English::Vocabulary", audio)
        assert isinstance(spaced, Added)
        assert isinstance(hyphenated, Added)
        assert spaced.media_filename != hyphenated.media_filename
        assert spaced.media_filename.startswith("echo-words-go-over-")
        assert hyphenated.media_filename.startswith("echo-words-go-over-")
    finally:
        await store.close()


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.delays: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, delay: float) -> None:
        self.delays.append(delay)
        self.now += delay
        await asyncio.sleep(0)


class FakeSyncBackend:
    def __init__(
        self,
        required: list[int | Exception],
        *,
        full_download_error: Exception | None = None,
    ) -> None:
        self.required = deque(required)
        self.full_download_error = full_download_error
        self.login_calls: list[tuple[str, str, str | None]] = []
        self.auths: list[SyncAuth] = []
        self.full_downloads: list[tuple[str, int]] = []

    def login(self, _collection, username, password, endpoint):
        self.login_calls.append((username, password, endpoint))
        return SyncAuth(hkey="persisted-key", endpoint=endpoint or "https://login/")

    def sync_collection(self, _collection, auth):
        self.auths.append(auth)
        required = self.required.popleft() if self.required else SyncCollectionResponse.NO_CHANGES
        if isinstance(required, Exception):
            raise required
        return SyncCollectionResponse(
            required=required,
            new_endpoint="https://shard/",
            server_media_usn=42,
        )

    def full_download(self, _collection, auth, server_usn):
        self.full_downloads.append((auth.endpoint, server_usn))
        if self.full_download_error is not None:
            error, self.full_download_error = self.full_download_error, None
            raise error


def synced_settings(tmp_path: Path, **values: object) -> Settings:
    defaults = {
        "data_dir": tmp_path,
        "anki_sync": True,
        "ankiweb_user": "owner@example.com",
        "ankiweb_password": "secret",  # noqa: S105 - explicit fake test credential
    }
    defaults.update(values)
    return Settings(
        _env_file=None,
        **defaults,
    )


async def test_fresh_collection_bootstraps_by_download_and_follows_the_shard(tmp_path):
    backend = FakeSyncBackend([SyncCollectionResponse.FULL_SYNC])
    store = AnkiStore(synced_settings(tmp_path), sync_backend=backend)
    await store.open()
    try:
        assert backend.login_calls == [("owner@example.com", "secret", None)]
        assert backend.full_downloads == [("https://shard/", 42)]
        persisted = store.auth_path.read_text(encoding="utf-8")
        assert "persisted-key" in persisted
        assert "https://shard/" in persisted
    finally:
        await store.close()


async def test_failed_bootstrap_is_retried_after_restart_despite_collection_file(tmp_path):
    settings = synced_settings(tmp_path)
    first_backend = FakeSyncBackend(
        [SyncCollectionResponse.FULL_SYNC],
        full_download_error=RuntimeError("temporary download failure"),
    )
    first = AnkiStore(settings, sync_backend=first_backend)

    with pytest.raises(RuntimeError, match="temporary download failure"):
        await first.open()

    assert first.collection is None
    assert first.collection_path.exists()
    assert first.bootstrap_path.exists()

    second_backend = FakeSyncBackend([SyncCollectionResponse.FULL_SYNC])
    second = AnkiStore(settings, sync_backend=second_backend)
    await second.open()
    try:
        assert second_backend.full_downloads == [("https://shard/", 42)]
        assert not second.bootstrap_path.exists()
    finally:
        await second.close()

    established_backend = FakeSyncBackend([])
    established = AnkiStore(settings, sync_backend=established_backend)
    await established.open()
    try:
        assert established_backend.auths == []
        assert established_backend.full_downloads == []
    finally:
        await established.close()


async def test_local_initialization_is_not_later_overwritten_as_a_fresh_bootstrap(tmp_path):
    local = AnkiStore(local_settings(tmp_path))
    await local.open()
    await local.close()

    backend = FakeSyncBackend([])
    synced = AnkiStore(synced_settings(tmp_path), sync_backend=backend)
    await synced.open()
    try:
        assert backend.auths == []
        assert backend.full_downloads == []
    finally:
        await synced.close()


async def test_sync_is_debounced_and_reuses_the_persisted_hkey(tmp_path):
    clock = FakeClock()
    first_backend = FakeSyncBackend([SyncCollectionResponse.NO_CHANGES] * 2)
    settings = synced_settings(tmp_path)
    first = AnkiStore(
        settings,
        sync_backend=first_backend,
        clock=clock,
        sleep=clock.sleep,
    )
    await first.open()
    try:
        await first.add_note(make_note("one"), "English::Vocabulary")
        await first.add_note(make_note("two"), "English::Vocabulary")
        await first.wait_for_sync()
        assert len(first_backend.auths) == 2  # bootstrap plus one coalesced trailing sync
        assert clock.delays == [SYNC_INTERVAL_SECONDS]
    finally:
        await first.close()

    second_backend = FakeSyncBackend([SyncCollectionResponse.NO_CHANGES])
    second = AnkiStore(settings, sync_backend=second_backend)
    await second.open()
    try:
        await second.add_note(make_note("three"), "English::Vocabulary")
        await second.wait_for_sync()
        assert second_backend.login_calls == []
        assert [auth.hkey for auth in second_backend.auths] == ["persisted-key"]
        assert [auth.endpoint for auth in second_backend.auths] == ["https://shard/"]
    finally:
        await second.close()


@pytest.mark.parametrize(
    ("first_values", "second_values", "expected_endpoint"),
    [
        ({}, {"ankiweb_user": "other@example.com"}, None),
        ({}, {"sync_endpoint": "https://self-hosted/"}, "https://self-hosted/"),
        (
            {"sync_endpoint": "https://self-hosted/"},
            {"sync_endpoint": ""},
            None,
        ),
    ],
)
async def test_changed_account_or_configured_endpoint_invalidates_persisted_auth(
    tmp_path,
    first_values,
    second_values,
    expected_endpoint,
):
    first_backend = FakeSyncBackend([SyncCollectionResponse.NO_CHANGES])
    first = AnkiStore(synced_settings(tmp_path, **first_values), sync_backend=first_backend)
    await first.open()
    await first.close()

    second_backend = FakeSyncBackend([SyncCollectionResponse.NO_CHANGES])
    second_settings = synced_settings(tmp_path, **second_values)
    second = AnkiStore(second_settings, sync_backend=second_backend)
    await second.open()
    try:
        await second.add_note(make_note(), "English::Vocabulary")
        await second.wait_for_sync()
        assert second_backend.login_calls == [
            (
                second_settings.ankiweb_user,
                "secret",
                expected_endpoint,
            ),
        ]
    finally:
        await second.close()


async def test_auth_error_discards_persisted_key_and_relogs_in(tmp_path):
    auth_error = SyncError("expired", None, None, None, SyncErrorKind.AUTH)
    backend = FakeSyncBackend(
        [auth_error, SyncCollectionResponse.NO_CHANGES],
    )
    store = AnkiStore(synced_settings(tmp_path), sync_backend=backend)

    await store.open()
    try:
        assert backend.login_calls == [
            ("owner@example.com", "secret", None),
            ("owner@example.com", "secret", None),
        ]
        assert len(backend.auths) == 2
    finally:
        await store.close()


async def test_transient_sync_failure_retries_on_the_next_debounce_tick(tmp_path, caplog):
    clock = FakeClock()
    backend = FakeSyncBackend(
        [
            SyncCollectionResponse.NO_CHANGES,
            RuntimeError("temporary outage"),
            SyncCollectionResponse.NO_CHANGES,
        ],
    )
    store = AnkiStore(
        synced_settings(tmp_path),
        sync_backend=backend,
        clock=clock,
        sleep=clock.sleep,
    )
    await store.open()
    try:
        with caplog.at_level(logging.WARNING, logger="echo_words.anki"):
            await store.add_note(make_note(), "English::Vocabulary")
            await store.wait_for_sync()
        assert len(backend.auths) == 3
        assert clock.delays == [SYNC_INTERVAL_SECONDS, SYNC_INTERVAL_SECONDS]
        assert "temporary outage" in caplog.text
        assert store.sync_error is None
    finally:
        await store.close()


async def test_sync_off_never_calls_the_sync_boundary(tmp_path):
    backend = FakeSyncBackend([])
    store = AnkiStore(local_settings(tmp_path), sync_backend=backend)
    await store.open()
    try:
        await store.add_note(make_note(), "English::Vocabulary")
        assert backend.login_calls == []
        assert backend.auths == []
    finally:
        await store.close()


class BlockingRetryClock(FakeClock):
    def __init__(self) -> None:
        super().__init__()
        self.second_sleep = asyncio.Event()

    async def sleep(self, delay: float) -> None:
        await super().sleep(delay)
        if len(self.delays) > 1:
            await self.second_sleep.wait()


async def test_a_required_full_sync_is_surfaced_and_never_auto_resolved(tmp_path, caplog):
    clock = BlockingRetryClock()
    backend = FakeSyncBackend(
        [SyncCollectionResponse.NO_CHANGES, SyncCollectionResponse.FULL_SYNC],
    )
    store = AnkiStore(
        synced_settings(tmp_path),
        sync_backend=backend,
        clock=clock,
        sleep=clock.sleep,
    )
    await store.open()
    try:
        with caplog.at_level(logging.ERROR, logger="echo_words.anki"):
            await store.add_note(make_note(), "English::Vocabulary")
            while store.sync_error is None:
                await asyncio.sleep(0)
        assert "one-way full sync" in store.sync_error
        assert "requires manual resolution" in caplog.text
        assert backend.full_downloads == []
    finally:
        await store.close()


async def test_collection_errors_propagate_to_the_caller(tmp_path, monkeypatch):
    store = AnkiStore(local_settings(tmp_path))
    await store.open()
    try:

        def fail(_query):
            raise RuntimeError("collection broke")

        monkeypatch.setattr(store.collection, "find_notes", fail)
        with pytest.raises(RuntimeError, match="collection broke"):
            await store.add_note(make_note(), "English::Vocabulary")
    finally:
        await store.close()


async def test_cancelled_add_finishes_its_writer_before_collection_close(tmp_path, monkeypatch):
    store = AnkiStore(local_settings(tmp_path))
    await store.open()
    original_add = store._add_note_blocking  # noqa: SLF001 - test replaces the thread boundary.
    writer_started = threading.Event()
    release_writer = threading.Event()
    writer_finished = threading.Event()

    def blocked_add(*args):
        writer_started.set()
        release_writer.wait()
        try:
            return original_add(*args)
        finally:
            writer_finished.set()

    monkeypatch.setattr(store, "_add_note_blocking", blocked_add)
    add_task = asyncio.create_task(store.add_note(make_note(), "English::Vocabulary"))
    while not writer_started.is_set():
        await asyncio.sleep(0)

    add_task.cancel()
    close_task = asyncio.create_task(store.close())
    await asyncio.sleep(0)
    assert not add_task.done()
    assert not close_task.done()
    assert store.collection is not None

    release_writer.set()
    with pytest.raises(asyncio.CancelledError):
        await add_task
    await close_task

    assert writer_finished.is_set()
    assert store.collection is None


@pytest.mark.parametrize("raises", [False, True])
async def test_full_download_closes_and_reopens_collection_even_on_failure(raises):
    calls = []

    class FullSyncCollection:
        def close_for_full_sync(self):
            calls.append("close")

        def full_upload_or_download(self, **kwargs):
            calls.append(("download", kwargs))
            if raises:
                raise RuntimeError("download failed")

        def reopen(self, *, after_full_sync):
            calls.append(("reopen", after_full_sync))

    collection = FullSyncCollection()
    auth = SyncAuth(hkey="key", endpoint="https://shard/")
    backend = PylibSyncBackend()

    if raises:
        with pytest.raises(RuntimeError, match="download failed"):
            backend.full_download(collection, auth, 42)
    else:
        backend.full_download(collection, auth, 42)

    assert calls == [
        "close",
        (
            "download",
            {"auth": auth, "server_usn": 42, "upload": False},
        ),
        ("reopen", True),
    ]
