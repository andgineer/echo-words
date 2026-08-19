"""Headless Anki collection storage and safe, debounced AnkiWeb synchronization."""

import asyncio
import hashlib
import html
import json
import logging
import re
import shutil
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from anki.collection import Collection
from anki.errors import SyncError, SyncErrorKind
from anki.notes import NoteId
from anki.sync import SyncAuth
from anki.sync_pb2 import SyncCollectionResponse, SyncStatusResponse

from echo_words.card import Meaning, Note
from echo_words.config import Settings

NOTE_TYPE_NAME = "EchoWords"
FIELD_NAMES = ("Word", "Translations", "Meanings", "Audio")
TEMPLATE_NAMES = ("Recognition", "Recall")
SYNC_INTERVAL_SECONDS = 5 * 60

logger = logging.getLogger(__name__)


class AnkiError(RuntimeError):
    """A card could not be safely stored in the configured collection."""


class MisconfiguredNoteTypeError(AnkiError):
    """The existing EchoWords note type is incompatible with this version."""

    def __init__(self) -> None:
        super().__init__(
            "note type EchoWords is misconfigured — fix or delete it in Anki",
        )


class FullSyncRequiredError(AnkiError):
    """Anki requires a destructive one-way transfer that must be resolved manually."""

    def __init__(self) -> None:
        super().__init__("Anki requires a one-way full sync — resolve it manually")


@dataclass(frozen=True)
class Added:
    note_id: int
    media_filename: str | None


@dataclass(frozen=True)
class Duplicate:
    pass


AddResult = Added | Duplicate


@dataclass(frozen=True)
class SyncState:
    enabled: bool
    last_result: str | None
    last_sync_at: datetime | None
    unsynced_changes: bool
    full_sync_required: bool


class Clock(Protocol):
    def __call__(self) -> float: ...


class Sleeper(Protocol):
    async def __call__(self, delay: float) -> None: ...


class SyncBackend(Protocol):
    """The only network-capable part of the store; tests replace this boundary."""

    def login(
        self,
        collection: Collection,
        username: str,
        password: str,
        endpoint: str | None,
    ) -> SyncAuth: ...

    def sync_collection(
        self,
        collection: Collection,
        auth: SyncAuth,
    ) -> SyncCollectionResponse: ...

    def sync_status(
        self,
        collection: Collection,
        auth: SyncAuth,
    ) -> SyncStatusResponse: ...

    def full_download(
        self,
        collection: Collection,
        auth: SyncAuth,
        server_usn: int,
    ) -> None: ...


class PylibSyncBackend:
    """Calls Anki's own synchronization implementation without a GUI."""

    def login(
        self,
        collection: Collection,
        username: str,
        password: str,
        endpoint: str | None,
    ) -> SyncAuth:
        return collection.sync_login(username, password, endpoint)

    def sync_collection(
        self,
        collection: Collection,
        auth: SyncAuth,
    ) -> SyncCollectionResponse:
        return collection.sync_collection(auth, sync_media=True)

    def sync_status(
        self,
        collection: Collection,
        auth: SyncAuth,
    ) -> SyncStatusResponse:
        return collection.sync_status(auth)

    def full_download(
        self,
        collection: Collection,
        auth: SyncAuth,
        server_usn: int,
    ) -> None:
        collection.close_for_full_sync()
        try:
            collection.full_upload_or_download(
                auth=auth,
                server_usn=server_usn,
                upload=False,
            )
        finally:
            collection.reopen(after_full_sync=True)


class AnkiStore:
    """Own one local collection and serialize every blocking pylib operation."""

    def __init__(
        self,
        settings: Settings,
        *,
        sync_backend: SyncBackend | None = None,
        clock: Clock = time.monotonic,
        sleep: Sleeper = asyncio.sleep,
    ) -> None:
        self.settings = settings
        self.collection_path = settings.data_dir / "anki" / "collection.anki2"
        self.bootstrap_path = settings.data_dir / "anki" / "bootstrap.pending"
        self.auth_path = settings.data_dir / "anki-sync.json"
        self.sync_backend = sync_backend or PylibSyncBackend()
        self.clock = clock
        self.sleep = sleep
        self.collection: Collection | None = None
        self.last_added_by_deck: dict[str, Added] = {}
        self.sync_error: str | None = None
        self._lock = asyncio.Lock()
        self._sync_task: asyncio.Task[None] | None = None
        self._sync_generation = 0
        self._synced_generation = 0
        self._last_sync_at: float | None = None
        self._last_sync_wall: datetime | None = None
        self._last_sync_result: str | None = None
        self._auth: SyncAuth | None = None

    async def open(self) -> None:
        """Open the collection and bootstrap a fresh synced copy by download."""
        if self.collection is not None:
            return
        self.collection_path.parent.mkdir(parents=True, exist_ok=True)
        fresh = not self.collection_path.exists()
        if self.settings.anki_sync:
            self._check_sync_credentials()
            if fresh:
                # Collection() creates its database before a bootstrap can run.
                # Persist the intent first so a crash or failed download retries.
                self.bootstrap_path.write_text("pending\n", encoding="utf-8")
            needs_bootstrap = fresh or self.bootstrap_path.exists()
        else:
            # Explicitly opting into a local-only collection abandons any earlier
            # incomplete download and prevents a later sync setting from treating
            # locally added notes as safe to overwrite.
            self.bootstrap_path.unlink(missing_ok=True)
            needs_bootstrap = False
        self.collection = await asyncio.to_thread(Collection, str(self.collection_path))
        try:
            if needs_bootstrap:
                async with self._lock:
                    await self._sync_with_auth_retry(bootstrap=True)
                self._last_sync_at = self.clock()
                self._last_sync_wall = datetime.now(tz=UTC)
                self._last_sync_result = "ok"
                self.bootstrap_path.unlink(missing_ok=True)
        except (Exception, asyncio.CancelledError):
            collection = self._require_collection()
            self.collection = None
            await _to_thread_uncancellable(collection.close)
            raise

    async def close(self) -> None:
        """Stop the debounce task and close the local collection."""
        if self._sync_task is not None:
            self._sync_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._sync_task
            self._sync_task = None
        async with self._lock:
            collection = self.collection
            self.collection = None
            if collection is not None:
                await _to_thread_uncancellable(collection.close)

    async def add_note(
        self,
        note: Note,
        deck: str,
        audio_path: Path | None = None,
    ) -> AddResult:
        """Add a rendered note unless its canonical word already exists in the deck."""
        async with self._lock:
            result = await _to_thread_uncancellable(
                self._add_note_blocking,
                note,
                deck,
                audio_path,
            )
        if isinstance(result, Added):
            self.last_added_by_deck[deck] = result
            self.schedule_sync()
        return result

    async def replace_note(
        self,
        note_id: int,
        note: Note,
        deck: str,
        audio_path: Path | None = None,
        old_media_filename: str | None = None,
    ) -> AddResult:
        """Replace a note, removing the old result when the target is a duplicate."""
        async with self._lock:
            result = await _to_thread_uncancellable(
                self._replace_note_blocking,
                note_id,
                note,
                deck,
                audio_path,
                old_media_filename,
            )
        if isinstance(result, Added):
            self.last_added_by_deck[deck] = result
        elif (
            last_added := self.last_added_by_deck.get(deck)
        ) is not None and last_added.note_id == note_id:
            self.last_added_by_deck.pop(deck, None)
        self.schedule_sync()
        return result

    def schedule_sync(self) -> None:
        """Request a sync; repeated requests are coalesced into five-minute ticks."""
        if not self.settings.anki_sync:
            return
        self._sync_generation += 1
        if self._sync_task is None or self._sync_task.done():
            self._sync_task = asyncio.create_task(
                self._sync_loop(),
                name="echo-words-anki-sync",
            )

    async def wait_for_sync(self) -> None:
        """Wait for the currently scheduled sync, primarily for orderly tests."""
        if self._sync_task is not None:
            await self._sync_task

    async def _sync_loop(self) -> None:
        try:
            while self._synced_generation < self._sync_generation:
                if self._last_sync_at is not None:
                    delay = self._last_sync_at + SYNC_INTERVAL_SECONDS - self.clock()
                    if delay > 0:
                        await self.sleep(delay)
                try:
                    async with self._lock:
                        target_generation = self._sync_generation
                        await self._sync_with_auth_retry(bootstrap=False)
                        self._synced_generation = target_generation
                except FullSyncRequiredError as exc:
                    self.sync_error = str(exc)
                    self._last_sync_result = "full-sync-required"
                    logger.error("Anki sync requires manual resolution: %s", exc)
                except Exception as exc:  # noqa: BLE001 - sync never affects card delivery.
                    self.sync_error = str(exc)
                    self._last_sync_result = "error"
                    logger.warning("Anki sync failed: %s", exc)
                else:
                    self.sync_error = None
                    self._last_sync_result = "ok"
                self._last_sync_at = self.clock()
                self._last_sync_wall = datetime.now(tz=UTC)
        finally:
            self._sync_task = None

    async def remove_note(self, note_id: int, media_filename: str | None = None) -> None:
        """Remove one note and its collection media, then schedule delivery of the change."""
        async with self._lock:
            await _to_thread_uncancellable(
                self._remove_note_blocking,
                note_id,
                media_filename,
            )
        self.schedule_sync()

    def _remove_note_blocking(self, note_id: int, media_filename: str | None) -> None:
        collection = self._require_collection()
        collection.remove_notes([NoteId(note_id)])
        if media_filename:
            collection.media.trash_files([media_filename])

    async def note_counts(
        self,
        decks: dict[str, str],
        *,
        now: datetime | None = None,
    ) -> dict[str, dict[str, int]]:
        """Count EchoWords note ids in creation-time windows, grouped by language."""
        current = now or datetime.now().astimezone()
        if current.tzinfo is None:
            current = current.replace(tzinfo=UTC)
        start_today = current.replace(hour=0, minute=0, second=0, microsecond=0)
        start_week = start_today - timedelta(days=6)
        async with self._lock:
            return await _to_thread_uncancellable(
                self._note_counts_blocking,
                decks,
                int(start_today.timestamp() * 1000),
                int(start_week.timestamp() * 1000),
            )

    def _note_counts_blocking(
        self,
        decks: dict[str, str],
        today_cutoff: int,
        week_cutoff: int,
    ) -> dict[str, dict[str, int]]:
        collection = self._require_collection()
        result: dict[str, dict[str, int]] = {}
        for code, deck in decks.items():
            query = f'deck:"{_query_value(deck)}" note:{NOTE_TYPE_NAME}'
            note_ids = collection.find_notes(query)
            result[code] = {
                "today": sum(note_id >= today_cutoff for note_id in note_ids),
                "last_7_days": sum(note_id >= week_cutoff for note_id in note_ids),
                "all_time": len(note_ids),
            }
        return result

    async def status(self) -> SyncState:
        """Return sync state, including durable collection changes after a restart."""
        required = SyncCollectionResponse.NO_CHANGES
        if self.settings.anki_sync:
            try:
                async with self._lock:
                    required = await _to_thread_uncancellable(self._sync_status_blocking)
            except Exception as exc:  # noqa: BLE001 - status still reports its cached state.
                logger.warning("could not read Anki sync status: %s", exc)
                required = (
                    SyncCollectionResponse.NORMAL_SYNC
                    if self._synced_generation < self._sync_generation
                    else SyncCollectionResponse.NO_CHANGES
                )
        full_sync_required = required in (
            SyncCollectionResponse.FULL_SYNC,
            SyncCollectionResponse.FULL_DOWNLOAD,
            SyncCollectionResponse.FULL_UPLOAD,
        )
        return SyncState(
            enabled=self.settings.anki_sync,
            last_result=self._last_sync_result,
            last_sync_at=self._last_sync_wall,
            unsynced_changes=required != SyncCollectionResponse.NO_CHANGES,
            full_sync_required=full_sync_required
            or bool(self.sync_error and "one-way full sync" in self.sync_error),
        )

    def _sync_status_blocking(self) -> int:
        collection = self._require_collection()
        auth = self._get_auth(collection)
        response = self.sync_backend.sync_status(collection, auth)
        return response.required

    async def _sync_with_auth_retry(self, *, bootstrap: bool) -> None:
        try:
            await _to_thread_uncancellable(self._sync_blocking, bootstrap)
        except SyncError as exc:
            if exc.kind != SyncErrorKind.AUTH:
                raise
            self._auth = None
            self.auth_path.unlink(missing_ok=True)
            await _to_thread_uncancellable(self._sync_blocking, bootstrap)

    def _sync_blocking(self, bootstrap: bool) -> None:
        collection = self._require_collection()
        auth = self._get_auth(collection)
        output = self.sync_backend.sync_collection(collection, auth)
        auth = self._follow_endpoint(auth, output.new_endpoint)
        self._auth = auth
        self._save_auth(auth)
        required = output.required
        if bootstrap:
            if required in (
                SyncCollectionResponse.FULL_DOWNLOAD,
                SyncCollectionResponse.FULL_SYNC,
            ):
                self.sync_backend.full_download(collection, auth, output.server_media_usn)
            elif required == SyncCollectionResponse.FULL_UPLOAD:
                raise FullSyncRequiredError
        elif required in (
            SyncCollectionResponse.FULL_SYNC,
            SyncCollectionResponse.FULL_DOWNLOAD,
            SyncCollectionResponse.FULL_UPLOAD,
        ):
            raise FullSyncRequiredError

    def _get_auth(self, collection: Collection) -> SyncAuth:
        if self._auth is not None:
            return self._auth
        stored = self._load_auth()
        if stored is not None:
            self._auth = stored
            return stored
        endpoint = self.settings.sync_endpoint or None
        auth = self.sync_backend.login(
            collection,
            self.settings.ankiweb_user,
            self.settings.ankiweb_password,
            endpoint,
        )
        self._auth = auth
        self._save_auth(auth)
        return auth

    def _load_auth(self) -> SyncAuth | None:
        try:
            value = json.loads(self.auth_path.read_text(encoding="utf-8"))
            hkey = value["hkey"]
            endpoint = value.get("endpoint", "")
            username = value["username"]
            configured_endpoint = value["configured_endpoint"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            return None
        if not isinstance(hkey, str) or not hkey:
            return None
        if username != self.settings.ankiweb_user:
            return None
        if configured_endpoint != self.settings.sync_endpoint:
            return None
        return SyncAuth(hkey=hkey, endpoint=endpoint if isinstance(endpoint, str) else "")

    def _save_auth(self, auth: SyncAuth) -> None:
        self.auth_path.parent.mkdir(parents=True, exist_ok=True)
        self.auth_path.write_text(
            json.dumps(
                {
                    "hkey": auth.hkey,
                    "endpoint": auth.endpoint,
                    "username": self.settings.ankiweb_user,
                    "configured_endpoint": self.settings.sync_endpoint,
                },
            ),
            encoding="utf-8",
        )

    def _follow_endpoint(self, auth: SyncAuth, endpoint: str) -> SyncAuth:
        if not endpoint or endpoint == auth.endpoint:
            return auth
        return SyncAuth(hkey=auth.hkey, endpoint=endpoint)

    def _add_note_blocking(
        self,
        note_data: Note,
        deck: str,
        audio_path: Path | None,
    ) -> AddResult:
        collection = self._require_collection()
        model = _ensure_note_type(collection)
        deck_id = collection.decks.id(deck)
        if deck_id is None:
            raise AnkiError(f"could not create Anki deck {deck!r}")
        query = (
            f'deck:"{_query_value(deck)}" note:{NOTE_TYPE_NAME} '
            f'"Word:{_query_value(note_data.word)}"'
        )
        if collection.find_notes(query):
            return Duplicate()

        media_filename = _add_media(collection, note_data.word, audio_path)
        note = collection.new_note(model)
        note["Word"] = note_data.word
        note["Translations"] = render_translations(note_data)
        note["Meanings"] = render_meanings(note_data)
        note["Audio"] = f"[sound:{media_filename}]" if media_filename else ""
        collection.add_note(note, deck_id)
        return Added(note.id, media_filename)

    def _replace_note_blocking(
        self,
        note_id: int,
        note_data: Note,
        deck: str,
        audio_path: Path | None,
        old_media_filename: str | None,
    ) -> AddResult:
        collection = self._require_collection()
        model = _ensure_note_type(collection)
        deck_id = collection.decks.id(deck)
        if deck_id is None:
            raise AnkiError(f"could not create Anki deck {deck!r}")
        query = (
            f'deck:"{_query_value(deck)}" note:{NOTE_TYPE_NAME} '
            f'"Word:{_query_value(note_data.word)}"'
        )
        if any(int(found) != note_id for found in collection.find_notes(query)):
            collection.remove_notes([NoteId(note_id)])
            if old_media_filename:
                _trash_replaced_media(collection, old_media_filename)
            return Duplicate()

        media_filename = None
        undo_entry = collection.add_custom_undo_entry("Replace EchoWords note")
        try:
            # The product contract deliberately resets note/card identity and review
            # scheduling. Group delete + add in Anki's own undo transaction so an
            # add failure restores the old note, cards and scheduling exactly.
            collection.remove_notes([NoteId(note_id)])
            media_filename = _add_media(collection, note_data.word, audio_path)
            note = collection.new_note(model)
            note["Word"] = note_data.word
            note["Translations"] = render_translations(note_data)
            note["Meanings"] = render_meanings(note_data)
            note["Audio"] = f"[sound:{media_filename}]" if media_filename else ""
            collection.add_note(note, deck_id)
            collection.merge_undo_entries(undo_entry)
        except Exception:
            _rollback_note_replacement(
                collection,
                undo_entry,
                media_filename,
                old_media_filename,
            )
            raise
        if old_media_filename and old_media_filename != media_filename:
            _trash_replaced_media(collection, old_media_filename)
        return Added(note.id, media_filename)

    def _require_collection(self) -> Collection:
        if self.collection is None:
            raise RuntimeError("Anki collection is not open")
        return self.collection

    def _check_sync_credentials(self) -> None:
        if not self.settings.ankiweb_user or not self.settings.ankiweb_password:
            raise AnkiError(
                "ECHOWORDS_ANKIWEB_USER and ECHOWORDS_ANKIWEB_PASSWORD are required "
                "when Anki sync is enabled",
            )


def _ensure_note_type(collection: Collection) -> dict:
    models = collection.models
    existing = models.by_name(NOTE_TYPE_NAME)
    if existing is not None:
        fields = tuple(field["name"] for field in existing["flds"])
        templates = tuple(template["name"] for template in existing["tmpls"])
        if fields != FIELD_NAMES or templates != TEMPLATE_NAMES:
            raise MisconfiguredNoteTypeError
        return existing

    model = models.new(NOTE_TYPE_NAME)
    for name in FIELD_NAMES:
        models.add_field(model, models.new_field(name))
    recognition = models.new_template("Recognition")
    recognition["qfmt"] = "{{Word}} {{Audio}}"
    recognition["afmt"] = "{{Meanings}}"
    models.add_template(model, recognition)
    recall = models.new_template("Recall")
    recall["qfmt"] = "{{Translations}}"
    recall["afmt"] = "{{Word}} {{Audio}}"
    models.add_template(model, recall)
    model["css"] = ".card { font-family: sans-serif; font-size: 20px; text-align: left; }"
    models.add(model)
    created = models.by_name(NOTE_TYPE_NAME)
    if created is None:
        raise RuntimeError("Anki did not create the EchoWords note type")
    return created


def render_translations(note: Note) -> str:
    """Render the recall front without ever leaking an unmasked source example."""
    multiple = len(note.meanings) > 1
    return "<br><br>".join(
        _render_translation_block(meaning, note.word, multiple) for meaning in note.meanings
    )


def _render_translation_block(meaning: Meaning, word: str, show_label: bool) -> str:
    parts = []
    if show_label:
        parts.append(f"<b>{html.escape(meaning.label)}</b>")
    parts.append(", ".join(html.escape(value) for value in meaning.translations))
    for example in meaning.examples:
        masked = _mask_word(example.text, word)
        if masked is not None:
            parts.append(
                f"<i>{html.escape(masked)}</i> — {html.escape(example.translation)}",
            )
            break
    else:
        if meaning.pos:
            parts.append(f"<i>{html.escape(meaning.pos)}</i>")
    return "<br>".join(parts)


def render_meanings(note: Note) -> str:
    """Render compact recognition-card meaning blocks."""
    multiple = len(note.meanings) > 1
    blocks = [_render_meaning_block(meaning, multiple) for meaning in note.meanings]
    if multiple:
        return "<ol>" + "".join(f"<li>{block}</li>" for block in blocks) + "</ol>"
    return blocks[0]


def _render_meaning_block(meaning: Meaning, show_label: bool) -> str:
    parts = []
    if show_label:
        parts.append(f"<b>{html.escape(meaning.label)}</b>")
    parts.append(", ".join(html.escape(value) for value in meaning.translations))
    parts.extend(
        f"<i>{html.escape(example.text)}</i> — {html.escape(example.translation)}"
        for example in meaning.examples
    )
    return "<br>".join(parts)


def _mask_word(sentence: str, word: str) -> str | None:
    pattern = re.compile(rf"(?<!\w){re.escape(word)}(?!\w)", re.IGNORECASE)
    if pattern.search(sentence) is None:
        return None
    return pattern.sub("___", sentence)


def _add_media(collection: Collection, word: str, audio_path: Path | None) -> str | None:
    if audio_path is None:
        return None
    slug = re.sub(r"[\W_]+", "-", word.casefold()).strip("-")
    digest = hashlib.sha1(word.encode("utf-8"), usedforsecurity=False).hexdigest()[:8]
    filename = f"echo-words-{slug}-{digest}.mp3"
    staging_dir = Path(collection.path).parent / "echo-words-staging"
    staging_dir.mkdir(exist_ok=True)
    staged = staging_dir / filename
    shutil.copyfile(audio_path, staged)
    try:
        return collection.media.add_file(str(staged))
    finally:
        staged.unlink(missing_ok=True)


def _rollback_note_replacement(
    collection: Collection,
    undo_entry: int,
    media_filename: str | None,
    old_media_filename: str | None,
) -> None:
    try:
        collection.merge_undo_entries(undo_entry)
        collection.undo()
    except Exception as exc:
        raise AnkiError(
            "replacement failed and the old Anki note could not be restored",
        ) from exc
    if media_filename and media_filename != old_media_filename:
        try:
            collection.media.trash_files([media_filename])
        except Exception as exc:  # noqa: BLE001 - the note rollback already succeeded.
            logger.warning("could not trash rolled-back Anki media %r: %s", media_filename, exc)


def _trash_replaced_media(collection: Collection, media_filename: str) -> None:
    try:
        collection.media.trash_files([media_filename])
    except Exception as exc:  # noqa: BLE001 - the replacement itself is already durable.
        logger.warning("could not trash replaced Anki media %r: %s", media_filename, exc)


def _query_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


async def _to_thread_uncancellable[T](function: Callable[..., T], *args: object) -> T:
    """Let a blocking pylib call finish before cancellation closes its collection."""
    task = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await task
        raise
