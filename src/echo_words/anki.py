"""Headless Anki collection storage and safe, debounced AnkiWeb synchronization."""

import asyncio
import hashlib
import html
import json
import logging
import re
import shutil
import tempfile
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from anki.collection import Collection
from anki.errors import SyncError, SyncErrorKind
from anki.notes import Note as AnkiNote
from anki.notes import NoteId
from anki.sync import SyncAuth
from anki.sync_pb2 import SyncCollectionResponse, SyncStatusResponse

from echo_words.card import Note
from echo_words.config import Settings

NOTE_TYPE_NAME = "EchoWords"
FIELD_NAMES = (
    "Word",
    "Audio",
    "Label",
    "Translations",
    "Highlighted",
    "Gapped",
)
_TEMPLATES: tuple[tuple[str, str, str], ...] = (
    (
        "Recognition",
        "{{Word}}{{#Label}} ({{Label}}){{/Label}} {{Audio}}",
        "{{Translations}}",
    ),
    (
        "Recall",
        "{{Translations}}{{#Label}} ({{Label}}){{/Label}}",
        "{{Word}} {{Audio}}",
    ),
    (
        "ContextRecognition",
        "{{Highlighted}}",
        "{{Translations}}<br>{{Word}} {{Audio}}",
    ),
    (
        "ContextProduction",
        "{{Translations}}<br>{{Gapped}}",
        "{{Word}} {{Audio}}",
    ),
)
TEMPLATE_NAMES = tuple(name for name, _front, _back in _TEMPLATES)
SYNC_INTERVAL_SECONDS = 5 * 60
_NOTE_TYPE_ABSENT = f"note type {NOTE_TYPE_NAME} is absent; the next add creates it"

logger = logging.getLogger(__name__)


def collection_path(settings: Settings) -> Path:
    return settings.data_dir / "anki" / "collection.anki2"


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


class CollectionAbsentError(AnkiError):
    """There is no collection where the settings point."""

    def __init__(self, path: Path) -> None:
        super().__init__(f"no collection at {path} — nothing to rebuild")


class MergeFailedError(AnkiError):
    """AnkiWeb could not be merged in, so the rebuild deleted nothing."""

    def __init__(self, reason: object) -> None:
        super().__init__(
            f"could not sync with AnkiWeb before deleting: {reason} — nothing was changed",
        )


class UploadFailedError(AnkiError):
    """The rebuild changed the collection but could not carry that change to AnkiWeb."""

    def __init__(self, reason: object) -> None:
        super().__init__(
            f"the note type was deleted here but the AnkiWeb upload failed: {reason} — "
            "run the rebuild again to retry the upload",
        )


def _would_delete(path: Path, settings: Settings) -> str:
    """Counted on a copy: closing a collection saves it, and the pass that reports
    that nothing was changed must not be the one that changes it."""
    with tempfile.TemporaryDirectory() as workspace:
        copy = Path(workspace) / path.name
        shutil.copy2(path, copy)
        # An unclean stop leaves notes in a write-ahead log the main file does not hold.
        for sidecar in path.parent.glob(f"{path.name}-*"):
            shutil.copy2(sidecar, copy.parent / sidecar.name)
        collection = Collection(str(copy))
        try:
            absent = collection.models.by_name(NOTE_TYPE_NAME) is None
            summary = "" if absent else _note_type_summary(collection, path)
        finally:
            collection.close()
    # A confirmed run always syncs, so a pass that deletes nothing still changes what
    # AnkiWeb holds, and the operator has to be able to confirm knowing that.
    if absent:
        if not settings.anki_sync:
            return _NOTE_TYPE_ABSENT
        return f"{_NOTE_TYPE_ABSENT}; a confirmed run still settles the sync with AnkiWeb"
    plan = "would delete" if not settings.anki_sync else "would merge AnkiWeb in, delete"
    tail = "" if not settings.anki_sync else " and upload the result to AnkiWeb"
    return f"{plan} {summary}{tail}; nothing was changed — pass --yes to delete"


def _note_type_summary(collection: Collection, path: Path) -> str:
    notes = len(collection.find_notes(f"note:{NOTE_TYPE_NAME}"))
    cards = len(collection.find_cards(f"note:{NOTE_TYPE_NAME}"))
    return f"note type {NOTE_TYPE_NAME} in {path} with {notes} notes and {cards} cards"


@dataclass(frozen=True)
class Added:
    note_id: int
    media_filename: str | None
    kinds: tuple[str, ...] = ()


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

    def full_upload(
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
        self._full_transfer(collection, auth, server_usn, upload=False)

    def full_upload(
        self,
        collection: Collection,
        auth: SyncAuth,
        server_usn: int,
    ) -> None:
        self._full_transfer(collection, auth, server_usn, upload=True)

    def _full_transfer(
        self,
        collection: Collection,
        auth: SyncAuth,
        server_usn: int,
        *,
        upload: bool,
    ) -> None:
        collection.close_for_full_sync()
        try:
            collection.full_upload_or_download(
                auth=auth,
                server_usn=server_usn,
                upload=upload,
            )
        finally:
            collection.reopen(after_full_sync=True)


def rebuild_note_type(
    settings: Settings,
    *,
    confirmed: bool,
    sync_backend: SyncBackend | None = None,
) -> str:
    """Merge AnkiWeb in, delete the EchoWords note type with its notes, upload the result.

    Deleting a note type deletes its notes, which makes this the only operation in
    the codebase that destroys anything. It is reachable from the console command
    alone: no startup path, and nothing the running app can call.
    """
    path = collection_path(settings)
    if not path.exists():
        raise CollectionAbsentError(path)
    if settings.anki_sync:
        _check_sync_credentials(settings)
    if not confirmed:
        return _would_delete(path, settings)
    collection = Collection(str(path))
    try:
        if not settings.anki_sync:
            deleted = _delete_note_type(collection, path)
            return f"{deleted}; sync is off, so AnkiWeb keeps the note type it has"
        backend = sync_backend or PylibSyncBackend()
        # Everything AnkiWeb knows has to be in this copy before the upload replaces
        # AnkiWeb with it, and nothing may be deleted until that has succeeded.
        _merge(collection, settings, backend)
        deleted = _delete_note_type(collection, path)
        return f"{deleted}; {_upload(collection, settings, backend)}"
    finally:
        collection.close()


def _delete_note_type(collection: Collection, path: Path) -> str:
    model = collection.models.by_name(NOTE_TYPE_NAME)
    if model is None:
        return _NOTE_TYPE_ABSENT
    summary = _note_type_summary(collection, path)
    collection.models.remove(model["id"])
    return f"deleted {summary}"


def _merge(collection: Collection, settings: Settings, backend: SyncBackend) -> None:
    """Take everything AnkiWeb holds, so the upload that follows only removes a note type.

    A one-way upload replaces every deck on AnkiWeb, which would silently undo work
    done on other devices since this copy last synced. A normal sync merges it in
    first, and where AnkiWeb refuses to merge, its copy is taken outright: all this
    collection can hold that AnkiWeb does not is EchoWords notes, their note type and
    their media — exactly what is about to be deleted. Nothing here is destructive,
    so a failure leaves the collection untouched.
    """
    try:
        auth, output = _sync(collection, settings, backend)
        if output.required in (
            SyncCollectionResponse.FULL_SYNC,
            SyncCollectionResponse.FULL_DOWNLOAD,
        ):
            backend.full_download(collection, auth, output.server_media_usn)
    except Exception as exc:
        raise MergeFailedError(exc) from exc


def _upload(collection: Collection, settings: Settings, backend: SyncBackend) -> str:
    """Send this collection to AnkiWeb one way, the only direction a rebuild can mean.

    The deletion exists in no other copy, so the running app's refusal to choose a
    sync direction would strand it here forever. The operator has just confirmed
    it, and every other device still answers the download prompt Anki raises there.
    """
    try:
        auth, output = _sync(collection, settings, backend)
        if output.required not in (
            SyncCollectionResponse.FULL_SYNC,
            SyncCollectionResponse.FULL_DOWNLOAD,
            SyncCollectionResponse.FULL_UPLOAD,
        ):
            return "AnkiWeb took the deletion without a one-way sync"
        backend.full_upload(collection, auth, output.server_media_usn)
    except Exception as exc:
        raise UploadFailedError(exc) from exc
    return "uploaded the collection to AnkiWeb — confirm the download in every Anki app"


def _sync(
    collection: Collection,
    settings: Settings,
    backend: SyncBackend,
) -> tuple[SyncAuth, SyncCollectionResponse]:
    try:
        auth = _resolve_auth(collection, settings, backend)
        output = backend.sync_collection(collection, auth)
    except SyncError as exc:
        if exc.kind != SyncErrorKind.AUTH:
            raise
        _auth_path(settings).unlink(missing_ok=True)
        auth = _resolve_auth(collection, settings, backend)
        output = backend.sync_collection(collection, auth)
    auth = _follow_endpoint(auth, output.new_endpoint)
    _save_auth(settings, auth)
    return auth, output


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
        self.collection_path = collection_path(settings)
        self.bootstrap_path = settings.data_dir / "anki" / "bootstrap.pending"
        self.auth_path = _auth_path(settings)
        self.sync_backend = sync_backend or PylibSyncBackend()
        self.clock = clock
        self.sleep = sleep
        self.collection: Collection | None = None
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
    ) -> Added:
        """Add a rendered note to the deck of its source language."""
        async with self._lock:
            result = await _to_thread_uncancellable(
                self._add_note_blocking,
                note,
                deck,
                audio_path,
            )
        self.schedule_sync()
        return result

    async def replace_note(
        self,
        note_id: int,
        note: Note,
        deck: str,
        audio_path: Path | None = None,
        old_media_filename: str | None = None,
    ) -> Added:
        """Replace one note with a freshly built one, resetting its scheduling."""
        async with self._lock:
            result = await _to_thread_uncancellable(
                self._replace_note_blocking,
                note_id,
                note,
                deck,
                audio_path,
                old_media_filename,
            )
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
        auth = _follow_endpoint(auth, output.new_endpoint)
        self._auth = auth
        _save_auth(self.settings, auth)
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
        if self._auth is None:
            self._auth = _resolve_auth(collection, self.settings, self.sync_backend)
        return self._auth

    def _add_note_blocking(
        self,
        note_data: Note,
        deck: str,
        audio_path: Path | None,
    ) -> Added:
        collection = self._require_collection()
        model = _ensure_note_type(collection)
        deck_id = collection.decks.id(deck)
        if deck_id is None:
            raise AnkiError(f"could not create Anki deck {deck!r}")
        media_filename = _add_media(collection, note_data.word, audio_path)
        note = collection.new_note(model)
        note.fields = _ordered_fields(card_fields(note_data, media_filename))
        collection.add_note(note, deck_id)
        return Added(note.id, media_filename, _created_kinds(model, note))

    def _replace_note_blocking(
        self,
        note_id: int,
        note_data: Note,
        deck: str,
        audio_path: Path | None,
        old_media_filename: str | None,
    ) -> Added:
        collection = self._require_collection()
        model = _ensure_note_type(collection)
        deck_id = collection.decks.id(deck)
        if deck_id is None:
            raise AnkiError(f"could not create Anki deck {deck!r}")
        media_filename = None
        undo_entry = collection.add_custom_undo_entry("Replace EchoWords note")
        try:
            # The product contract deliberately resets note/card identity and review
            # scheduling. Group delete + add in Anki's own undo transaction so an
            # add failure restores the old note, cards and scheduling exactly.
            collection.remove_notes([NoteId(note_id)])
            media_filename = _add_media(collection, note_data.word, audio_path)
            note = collection.new_note(model)
            note.fields = _ordered_fields(card_fields(note_data, media_filename))
            _wait_past_millisecond(note_id)
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
        return Added(note.id, media_filename, _created_kinds(model, note))

    def _require_collection(self) -> Collection:
        if self.collection is None:
            raise RuntimeError("Anki collection is not open")
        return self.collection

    def _check_sync_credentials(self) -> None:
        _check_sync_credentials(self.settings)


def _check_sync_credentials(settings: Settings) -> None:
    if not settings.ankiweb_user or not settings.ankiweb_password:
        raise AnkiError(
            "ECHOWORDS_ANKIWEB_USER and ECHOWORDS_ANKIWEB_PASSWORD are required "
            "when Anki sync is enabled",
        )


def _auth_path(settings: Settings) -> Path:
    return settings.data_dir / "anki-sync.json"


def _resolve_auth(collection: Collection, settings: Settings, backend: SyncBackend) -> SyncAuth:
    stored = _load_auth(settings)
    if stored is not None:
        return stored
    auth = backend.login(
        collection,
        settings.ankiweb_user,
        settings.ankiweb_password,
        settings.sync_endpoint or None,
    )
    _save_auth(settings, auth)
    return auth


def _load_auth(settings: Settings) -> SyncAuth | None:
    try:
        value = json.loads(_auth_path(settings).read_text(encoding="utf-8"))
        hkey = value["hkey"]
        endpoint = value.get("endpoint", "")
        username = value["username"]
        configured_endpoint = value["configured_endpoint"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return None
    if not isinstance(hkey, str) or not hkey:
        return None
    if username != settings.ankiweb_user:
        return None
    if configured_endpoint != settings.sync_endpoint:
        return None
    return SyncAuth(hkey=hkey, endpoint=endpoint if isinstance(endpoint, str) else "")


def _save_auth(settings: Settings, auth: SyncAuth) -> None:
    path = _auth_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "hkey": auth.hkey,
                "endpoint": auth.endpoint,
                "username": settings.ankiweb_user,
                "configured_endpoint": settings.sync_endpoint,
            },
        ),
        encoding="utf-8",
    )


def _follow_endpoint(auth: SyncAuth, endpoint: str) -> SyncAuth:
    if not endpoint or endpoint == auth.endpoint:
        return auth
    return SyncAuth(hkey=auth.hkey, endpoint=endpoint)


def _wait_past_millisecond(note_id: int) -> None:
    """Anki mints a note id from the millisecond clock, so a replacement that lands inside
    the same millisecond would resurrect the id it has just written to the graves table."""
    deadline = time.monotonic() + 0.1
    while int(time.time() * 1000) <= note_id and time.monotonic() < deadline:
        time.sleep(0.001)


def _ensure_note_type(collection: Collection) -> dict:
    models = collection.models
    existing = models.by_name(NOTE_TYPE_NAME)
    if existing is not None:
        fields = tuple(field["name"] for field in existing["flds"])
        templates = tuple(template["name"] for template in existing["tmpls"])
        if fields != FIELD_NAMES or templates != TEMPLATE_NAMES:
            logger.warning(
                "note type %s has fields %s and templates %s; expected %s and %s",
                NOTE_TYPE_NAME,
                fields,
                templates,
                FIELD_NAMES,
                TEMPLATE_NAMES,
            )
            raise MisconfiguredNoteTypeError
        return existing

    model = models.new(NOTE_TYPE_NAME)
    for name in FIELD_NAMES:
        models.add_field(model, models.new_field(name))
    for name, front, back in _TEMPLATES:
        template = models.new_template(name)
        template["qfmt"] = front
        template["afmt"] = back
        models.add_template(model, template)
    model["css"] = ".card { font-family: sans-serif; font-size: 20px; text-align: left; }"
    models.add(model)
    created = models.by_name(NOTE_TYPE_NAME)
    if created is None:
        raise RuntimeError("Anki did not create the EchoWords note type")
    return created


def card_fields(note: Note, media_filename: str | None = None) -> dict[str, str]:
    """Render all six fields required by the note's four unconditional cards."""
    meaning = note.meaning
    example = meaning.examples[0]
    return {
        "Word": note.word,
        "Audio": f"[sound:{media_filename}]" if media_filename else "",
        "Label": html.escape(meaning.label) if len(note.meanings) > 1 else "",
        "Translations": render_translations(note),
        "Highlighted": example.highlighted,
        "Gapped": example.gapped,
    }


def _ordered_fields(fields: dict[str, str]) -> list[str]:
    return [fields[name] for name in FIELD_NAMES]


def _created_kinds(model: dict, note: AnkiNote) -> tuple[str, ...]:
    names = [template["name"] for template in model["tmpls"]]
    return tuple(names[card.ord] for card in sorted(note.cards(), key=lambda card: card.ord))


def render_translations(note: Note) -> str:
    """Render the selected sense's target-language translations."""
    return ", ".join(html.escape(value) for value in note.meaning.translations)


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
