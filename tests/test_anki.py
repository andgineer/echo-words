import asyncio
import hashlib
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from anki.collection import Collection
from anki.errors import SyncError, SyncErrorKind
from anki.models import ModelManager
from anki.sync import SyncAuth
from anki.sync_pb2 import SyncCollectionResponse

from echo_words.anki import (
    FIELD_NAMES,
    NOTE_TYPE_NAME,
    SYNC_INTERVAL_SECONDS,
    TEMPLATE_NAMES,
    Added,
    AnkiStore,
    CollectionAbsentError,
    MisconfiguredNoteTypeError,
    PylibSyncBackend,
    _wait_past_millisecond,
    card_fields,
    collection_path,
    rebuild_note_type,
    render_translations,
)
from echo_words.card import Example, Meaning, Note
from echo_words.config import Settings

pytestmark = pytest.mark.anyio


def make_note(
    word: str = "receive",
    *,
    meanings: list[Meaning] | None = None,
    sense: int = 0,
) -> Note:
    return Note(
        word,
        meanings
        or [
            Meaning(
                label="",
                translations=["получать", "принимать"],
                examples=[
                    Example(
                        "I receive a parcel.",
                        "Я получаю посылку.",
                        "I <b>receive</b> a parcel.",
                        "I ___ a parcel.",
                    ),
                ],
            ),
        ],
        sense=sense,
    )


def two_meanings() -> list[Meaning]:
    return [
        Meaning(
            label="учреждение",
            translations=["банк"],
            examples=[
                Example(
                    "The bank opens at nine.",
                    "Банк открывается в девять.",
                    "The <b>bank</b> opens at nine.",
                    "The ___ opens at nine.",
                ),
            ],
        ),
        Meaning(
            label="берег",
            translations=["берег"],
            examples=[
                Example(
                    "We sat on the bank.",
                    "Мы сидели на берегу.",
                    "We sat on the <b>bank</b>.",
                    "We sat on the ___.",
                ),
            ],
        ),
    ]


def three_meanings() -> list[Meaning]:
    return [
        *two_meanings(),
        Meaning(
            label="насыпь",
            translations=["насыпь"],
            examples=[
                Example(
                    "The bank of the road was steep.",
                    "Насыпь у дороги была крутой.",
                    "The <b>bank</b> of the road was steep.",
                    "The ___ of the road was steep.",
                ),
            ],
        ),
    ]


def local_settings(tmp_path: Path, **values: object) -> Settings:
    return Settings(_env_file=None, data_dir=tmp_path, anki_sync=False, **values)


async def test_note_type_bootstrap_creates_every_field_and_template(tmp_path):
    store = AnkiStore(local_settings(tmp_path))
    await store.open()
    try:
        result = await store.add_note(make_note(), "English::Vocabulary")
        assert isinstance(result, Added)
        model = store.collection.models.by_name(NOTE_TYPE_NAME)
        assert tuple(field["name"] for field in model["flds"]) == FIELD_NAMES
        assert tuple(template["name"] for template in model["tmpls"]) == TEMPLATE_NAMES
        fronts = {template["name"]: template["qfmt"] for template in model["tmpls"]}
        backs = {template["name"]: template["afmt"] for template in model["tmpls"]}
        assert fronts == {
            "Recognition": "{{Word}}{{#Label}} ({{Label}}){{/Label}} {{Audio}}",
            "Recall": "{{Translations}}{{#Label}} ({{Label}}){{/Label}}",
            "ContextRecognition": "{{Highlighted}}",
            "ContextProduction": "{{Translations}}<br>{{Gapped}}",
        }
        assert backs == {
            "Recognition": "{{Translations}}",
            "Recall": "{{Word}} {{Audio}}",
            "ContextRecognition": "{{Translations}}<br>{{Word}} {{Audio}}",
            "ContextProduction": "{{Word}} {{Audio}}",
        }
    finally:
        await store.close()


async def stored_kinds(store, note: Note) -> tuple[tuple[str, ...], int]:
    """The kinds the store reports, and the cards Anki actually made for that note."""
    result = await store.add_note(note, "English::Vocabulary")
    assert isinstance(result, Added)
    return result.kinds, len(store.collection.find_cards(f"nid:{result.note_id}"))


@pytest.mark.parametrize(
    "note",
    [
        make_note("bank"),
        make_note("bank", meanings=two_meanings()),
        make_note("bank", meanings=two_meanings(), sense=1),
    ],
)
async def test_every_accepted_note_makes_exactly_all_four_cards(tmp_path, note):
    store = AnkiStore(local_settings(tmp_path))
    await store.open()
    try:
        kinds, cards = await stored_kinds(store, note)
        assert kinds == TEMPLATE_NAMES
        assert cards == 4
    finally:
        await store.close()


async def test_separable_verb_uses_the_model_finished_sentence_forms(tmp_path):
    note = Note(
        "aufstehen",
        [
            Meaning(
                "",
                ["вставать"],
                [
                    Example(
                        "Er steht jeden Morgen um sechs auf.",
                        "Он встаёт каждое утро в шесть.",
                        "Er <b>steht</b> jeden Morgen um sechs <b>auf</b>.",
                        "Er ___ jeden Morgen um sechs ___.",
                    ),
                ],
            ),
        ],
    )
    fields = card_fields(note)

    assert fields["Highlighted"] == "Er <b>steht</b> jeden Morgen um sechs <b>auf</b>."
    assert fields["Gapped"] == "Er ___ jeden Morgen um sechs ___."

    store = AnkiStore(local_settings(tmp_path))
    await store.open()
    try:
        kinds, cards = await stored_kinds(store, note)
        assert kinds == TEMPLATE_NAMES
        assert cards == 4
    finally:
        await store.close()


def test_label_is_filled_only_when_the_answer_has_several_senses():
    assert card_fields(make_note("bank"))["Label"] == ""
    assert card_fields(make_note("bank", meanings=two_meanings()))["Label"] == "учреждение"


def test_the_selected_sense_alone_populates_every_card_field():
    fields = card_fields(make_note("bank", meanings=two_meanings(), sense=1))

    assert fields == {
        "Word": "bank",
        "Audio": "",
        "Label": "берег",
        "Translations": "берег",
        "Highlighted": "We sat on the <b>bank</b>.",
        "Gapped": "We sat on the ___.",
    }
    assert "банк" not in "".join(fields.values())


def test_rendered_translations_use_only_the_selected_sense_and_escape_them():
    note = Note(
        "a&b",
        [
            Meaning(
                "<finance>",
                ["x < y", 'say "yes" & go'],
                [
                    Example(
                        "Use a&b <now>.",
                        "A & B <сейчас>.",
                        "Use <b>a&amp;b</b> &lt;now&gt;.",
                        "Use ___ &lt;now&gt;.",
                    ),
                ],
            ),
            *two_meanings(),
        ],
        sense=0,
    )

    assert render_translations(note) == "x &lt; y, say &quot;yes&quot; &amp; go"


@pytest.mark.parametrize("wrong_part", ["fields", "templates"])
async def test_a_preexisting_incompatible_note_type_fails_without_adding(
    tmp_path,
    wrong_part,
    caplog,
):
    store = AnkiStore(local_settings(tmp_path))
    await store.open()
    try:
        models = store.collection.models
        model = models.new(NOTE_TYPE_NAME)
        fields = FIELD_NAMES if wrong_part == "templates" else ("Word", "Wrong")
        for name in fields:
            models.add_field(model, models.new_field(name))
        templates = TEMPLATE_NAMES if wrong_part == "fields" else ("Recognition", "Wrong")
        second_field = "Wrong" if wrong_part == "fields" else "Translations"
        for index, name in enumerate(templates):
            template = models.new_template(name)
            # Anki refuses two templates with the same front, so each names itself.
            template["qfmt"] = "{{Word}}" if index == 0 else f"{name} {{{{{second_field}}}}}"
            models.add_template(model, template)
        models.add(model)

        with (
            caplog.at_level(logging.WARNING, logger="echo_words.anki"),
            pytest.raises(MisconfiguredNoteTypeError, match="fix or delete it in Anki"),
        ):
            await store.add_note(make_note(), "English::Vocabulary")
        assert store.collection.note_count() == 0
        assert "Wrong" in caplog.text and "expected" in caplog.text
    finally:
        await store.close()


# The collection syncs from AnkiWeb, so anything destructive runs beside decks and
# note types this project never wrote. "Basic" is one Anki ships with.
FOREIGN_NOTE_TYPE = "Basic"


@dataclass(frozen=True)
class Survivors:
    note_type: object | None
    notes: int
    foreign_note_type: object | None
    foreign_notes: int


async def with_one_note(tmp_path) -> Settings:
    settings = local_settings(tmp_path)
    store = AnkiStore(settings)
    await store.open()
    try:
        await store.add_note(make_note("bank"), "English::Vocabulary")
        collection = store.collection
        foreign = collection.new_note(collection.models.by_name(FOREIGN_NOTE_TYPE))
        foreign["Front"] = "Vorlesung"
        foreign["Back"] = "лекция"
        collection.add_note(foreign, collection.decks.id("German::Own"))
    finally:
        await store.close()
    return settings


async def surviving_note_types(settings: Settings) -> Survivors:
    store = AnkiStore(settings)
    await store.open()
    try:
        collection = store.collection
        return Survivors(
            collection.models.by_name(NOTE_TYPE_NAME),
            len(collection.find_notes(f"note:{NOTE_TYPE_NAME}")),
            collection.models.by_name(FOREIGN_NOTE_TYPE),
            len(collection.find_notes(f"note:{FOREIGN_NOTE_TYPE}")),
        )
    finally:
        await store.close()


async def test_a_rebuild_names_what_it_would_delete_and_changes_nothing_unconfirmed(tmp_path):
    settings = await with_one_note(tmp_path)

    summary = rebuild_note_type(settings, confirmed=False)

    assert "would delete" in summary
    assert NOTE_TYPE_NAME in summary
    assert "1 notes and 4 cards" in summary
    assert "--yes" in summary
    survivors = await surviving_note_types(settings)
    assert survivors.note_type is not None
    assert survivors.notes == 1


async def test_a_confirmed_rebuild_deletes_the_note_type_with_its_notes(tmp_path):
    settings = await with_one_note(tmp_path)

    summary = rebuild_note_type(settings, confirmed=True)

    assert summary.startswith("deleted")
    assert "1 notes and 4 cards" in summary
    survivors = await surviving_note_types(settings)
    assert survivors.note_type is None
    assert survivors.notes == 0
    # The blast radius is one note type: what the user built stays where it is.
    assert survivors.foreign_note_type is not None
    assert survivors.foreign_notes == 1


def test_a_rebuild_finding_no_collection_fails_rather_than_reporting_success(tmp_path):
    """A rebuild that quietly did nothing is indistinguishable from one that worked."""
    with pytest.raises(CollectionAbsentError):
        rebuild_note_type(local_settings(tmp_path), confirmed=True)


async def test_the_pass_that_changes_nothing_does_not_touch_the_collection(tmp_path):
    settings = await with_one_note(tmp_path)
    path = collection_path(settings)
    before = (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)

    summary = rebuild_note_type(settings, confirmed=False)

    # Counted off a copy, so the count has to be the real collection's all the same.
    assert "1 notes and 4 cards" in summary
    assert str(path) in summary
    assert (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns) == before


async def test_no_startup_path_removes_a_note_type_or_a_note(tmp_path, monkeypatch):
    """A startup that silently drops notes would one day meet a collection that mattered."""
    settings = await with_one_note(tmp_path)
    removed_types = []
    removed_notes = []
    monkeypatch.setattr(ModelManager, "remove", lambda _self, ntid: removed_types.append(ntid))
    monkeypatch.setattr(
        Collection,
        "remove_notes",
        lambda _self, ids: removed_notes.append(list(ids)),
    )

    store = AnkiStore(settings)
    await store.open()
    try:
        await store.add_note(make_note("Kuchen"), "German::Vocabulary")
        assert store.collection.note_count() == 3
    finally:
        await store.close()

    assert (removed_types, removed_notes) == ([], [])


async def test_a_rebuild_of_a_collection_without_the_note_type_deletes_nothing(tmp_path):
    settings = local_settings(tmp_path)
    store = AnkiStore(settings)
    await store.open()
    await store.close()

    assert "is absent" in rebuild_note_type(settings, confirmed=True)


def test_a_replacement_never_reuses_the_millisecond_of_the_note_it_buried():
    buried = int(time.time() * 1000)
    _wait_past_millisecond(buried)
    assert int(time.time() * 1000) > buried


def test_an_unreachable_millisecond_gives_up_instead_of_hanging():
    started = time.monotonic()
    _wait_past_millisecond(int(time.time() * 1000) + 60_000)
    assert time.monotonic() - started < 1


async def test_decks_are_created_per_language(tmp_path):
    store = AnkiStore(local_settings(tmp_path))
    await store.open()
    try:
        english = await store.add_note(make_note("Hand"), "English::Vocabulary")
        german = await store.add_note(make_note("Hand"), "German::Vocabulary")

        assert isinstance(english, Added)
        assert isinstance(german, Added)
        assert store.collection.note_count() == 2
        deck_names = {deck.name for deck in store.collection.decks.all_names_and_ids()}
        assert {"English::Vocabulary", "German::Vocabulary"} <= deck_names
    finally:
        await store.close()


async def test_the_same_word_twice_makes_two_notes_and_leaves_the_first_alone(tmp_path):
    """A second submission is how a second sense reaches the deck, so it is never refused."""
    store = AnkiStore(local_settings(tmp_path))
    await store.open()
    try:
        first = await store.add_note(make_note("bank"), "English::Vocabulary")
        second = await store.add_note(
            make_note(
                "bank",
                meanings=two_meanings(),
                sense=1,
            ),
            "English::Vocabulary",
        )

        assert isinstance(first, Added)
        assert isinstance(second, Added)
        assert second.note_id != first.note_id
        assert store.collection.note_count() == 2
        assert store.collection.get_note(first.note_id)["Translations"] != ""
        assert len(store.collection.find_cards(f"nid:{first.note_id}")) == 4
    finally:
        await store.close()


async def test_a_colon_in_a_deck_name_keeps_counts_deck_scoped(tmp_path):
    # ":" is Anki search syntax, and the shipped deck names ("EchoWords: Serbian") carry one.
    store = AnkiStore(local_settings(tmp_path))
    await store.open()
    try:
        serbian = await store.add_note(make_note("kuća"), "EchoWords: Serbian")
        german = await store.add_note(make_note("kuća"), "EchoWords: German")
        counts = await store.note_counts({"sr": "EchoWords: Serbian"})

        assert isinstance(serbian, Added)
        assert isinstance(german, Added)
        assert counts["sr"]["all_time"] == 1
    finally:
        await store.close()


async def test_replacement_deletes_then_adds_a_fresh_note(tmp_path):
    store = AnkiStore(local_settings(tmp_path))
    await store.open()
    try:
        original = await store.add_note(make_note("recieve"), "English::Vocabulary")
        assert isinstance(original, Added)

        replaced = await store.replace_note(
            original.note_id,
            make_note("receive"),
            "English::Vocabulary",
            old_media_filename=original.media_filename,
        )

        assert isinstance(replaced, Added)
        assert replaced.note_id != original.note_id
        assert store.collection.note_count() == 1
        assert store.collection.get_note(replaced.note_id)["Word"] == "receive"
        assert store.collection.find_notes(f"nid:{original.note_id}") == []
    finally:
        await store.close()


async def test_a_replacement_carries_the_card_set_and_reports_the_kinds(tmp_path):
    store = AnkiStore(local_settings(tmp_path))
    await store.open()
    try:
        original = await store.add_note(make_note("bank"), "English::Vocabulary")
        assert isinstance(original, Added)
        assert original.kinds == TEMPLATE_NAMES

        replaced = await store.replace_note(
            original.note_id,
            make_note(
                "bank",
                meanings=two_meanings(),
                sense=0,
            ),
            "English::Vocabulary",
            old_media_filename=original.media_filename,
        )

        assert isinstance(replaced, Added)
        assert replaced.kinds == TEMPLATE_NAMES
        assert len(store.collection.find_cards(f"nid:{replaced.note_id}")) == 4
        stored = store.collection.get_note(replaced.note_id)
        assert stored["Highlighted"] == "The <b>bank</b> opens at nine."
    finally:
        await store.close()


async def test_failed_replacement_leaves_the_existing_note_intact(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    store = AnkiStore(local_settings(tmp_path))
    await store.open()
    try:
        old_audio = tmp_path / "old.mp3"
        old_audio.write_bytes(b"old audio")
        original = await store.add_note(
            make_note("recieve"),
            "English::Vocabulary",
            old_audio,
        )
        assert isinstance(original, Added)
        assert original.media_filename is not None
        old_media = Path(store.collection.media.dir()) / original.media_filename
        old_cards = list(store.collection.find_cards(f"nid:{original.note_id}"))
        new_audio = tmp_path / "new.mp3"
        new_audio.write_bytes(b"new audio")

        def fail_add(_note, _deck_id):
            raise RuntimeError("write failed")

        monkeypatch.setattr(store.collection, "add_note", fail_add)
        with pytest.raises(RuntimeError, match="write failed"):
            await store.replace_note(
                original.note_id,
                make_note("receive"),
                "English::Vocabulary",
                new_audio,
                old_media_filename=original.media_filename,
            )

        assert store.collection.note_count() == 1
        assert store.collection.get_note(original.note_id)["Word"] == "recieve"
        assert list(store.collection.find_cards(f"nid:{original.note_id}")) == old_cards
        assert old_media.read_bytes() == b"old audio"
        media_files = {path.name for path in Path(store.collection.media.dir()).iterdir()}
        assert media_files == {original.media_filename}
    finally:
        await store.close()


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
        assert (media_dir / requested).read_bytes() == b"old file"
    finally:
        await store.close()


async def test_remove_note_trashes_its_collection_media(tmp_path):
    store = AnkiStore(local_settings(tmp_path))
    await store.open()
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"audio")
    try:
        added = await store.add_note(make_note(), "English::Vocabulary", audio)
        assert isinstance(added, Added)
        assert added.media_filename is not None
        media = Path(store.collection.media.dir()) / added.media_filename
        assert media.exists()

        await store.remove_note(added.note_id, added.media_filename)

        assert store.collection.note_count() == 0
        assert not media.exists()
    finally:
        await store.close()


async def test_note_counts_are_broken_down_by_deck_and_creation_window(tmp_path, monkeypatch):
    store = AnkiStore(local_settings(tmp_path))
    await store.open()
    now = datetime(2026, 8, 19, 12, tzinfo=UTC)
    today = int((now - timedelta(hours=1)).timestamp() * 1000)
    this_week = int((now - timedelta(days=3)).timestamp() * 1000)
    old = int((now - timedelta(days=20)).timestamp() * 1000)
    try:

        def note_ids(query):
            return [today, this_week, old] if "English" in query else [today]

        monkeypatch.setattr(store.collection, "find_notes", note_ids)
        counts = await store.note_counts(
            {"en": "English::Vocabulary", "de": "German::Vocabulary"},
            now=now,
        )

        assert counts == {
            "en": {"today": 1, "last_7_days": 2, "all_time": 3},
            "de": {"today": 1, "last_7_days": 1, "all_time": 1},
        }
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
        status_required: int = SyncCollectionResponse.NO_CHANGES,
    ) -> None:
        self.required = deque(required)
        self.full_download_error = full_download_error
        self.status_required = status_required
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

    def sync_status(self, _collection, _auth):
        return SyncCollectionResponse(required=self.status_required)

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


async def test_local_sync_status_distinguishes_ok_unsynced_and_full_sync(tmp_path):
    store = AnkiStore(local_settings(tmp_path))
    assert (await store.status()).unsynced_changes is False
    assert (await store.status()).full_sync_required is False

    store._sync_generation = 2  # noqa: SLF001
    store._synced_generation = 1  # noqa: SLF001
    assert (await store.status()).unsynced_changes is False

    store.sync_error = "Anki requires a one-way full sync — resolve it manually"
    assert (await store.status()).full_sync_required is True


async def test_sync_status_reads_collection_state_after_a_restart(tmp_path):
    backend = FakeSyncBackend(
        [],
        status_required=SyncCollectionResponse.NORMAL_SYNC,
    )
    store = AnkiStore(synced_settings(tmp_path), sync_backend=backend)
    await store.open()
    try:
        store._sync_generation = 0  # noqa: SLF001 - simulates fresh process memory.
        store._synced_generation = 0  # noqa: SLF001
        assert (await store.status()).unsynced_changes is True
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

        def fail(_note, _deck_id):
            raise RuntimeError("collection broke")

        monkeypatch.setattr(store.collection, "add_note", fail)
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
