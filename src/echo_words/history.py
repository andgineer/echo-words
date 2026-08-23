"""Restart-ephemeral word history, counters, and per-language undo state."""

from collections import Counter, deque
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from echo_words.shape import Shape


@dataclass
class Entry:
    """One submitted word, updated in place throughout its lifetime."""

    entry_id: str
    lang: str
    word: str
    action: str = "pending"
    analysis_html: str = ""
    audio_file: str | None = None
    context_audio_file: str | None = None
    suggestion: str | None = None
    shown_spelling: str = ""
    context: str = ""
    detail_html: str = ""
    created_at: datetime | None = None
    language: str = ""
    lookup_only: bool = False
    shape: Shape = "unit"
    segments: list[dict] = field(default_factory=list)
    card_status: str | None = None
    error: str | None = None
    model: str | None = None
    detail_available: bool = False
    correction_reversed: bool = False

    def __post_init__(self) -> None:
        if not self.shown_spelling:
            self.shown_spelling = self.word
        if self.created_at is None:
            self.created_at = datetime.now(tz=UTC)

    @property
    def text(self) -> str:
        return self.analysis_html

    @text.setter
    def text(self, value: str) -> None:
        self.analysis_html = value

    @property
    def audio_url(self) -> str | None:
        return f"/api/audio/{self.audio_file}" if self.audio_file else None

    @property
    def context_audio_url(self) -> str | None:
        return f"/api/audio/{self.context_audio_file}" if self.context_audio_file else None

    @property
    def status(self) -> str:
        if self.action == "pending":
            return "pending"
        if self.error:
            return "error"
        return "done"

    def public(self) -> dict[str, object]:
        value = asdict(self)
        value["created_at"] = self.created_at.isoformat() if self.created_at else None
        value["text"] = self.analysis_html
        value["audio_url"] = self.audio_url
        value["context_audio_url"] = self.context_audio_url
        value["status"] = self.status
        return value


@dataclass
class UndoState:
    word: str
    action: str
    note_id: int | None = None
    media_filename: str | None = None
    audio_file: str | None = None
    lookup_only: bool = False


class History:
    """A bounded insertion-ordered registry whose entries retain object identity."""

    def __init__(self, limit: int = 50) -> None:
        self.limit = limit
        self.entries: dict[str, Entry] = {}
        self.order: deque[str] = deque()
        self.counters: dict[str, Counter[str]] = {}
        self.undo: dict[str, UndoState] = {}

    def add(self, entry: Entry) -> None:
        if entry.entry_id not in self.entries:
            self.order.append(entry.entry_id)
        self.entries[entry.entry_id] = entry
        self.trim()

    def get(self, entry_id: str) -> Entry | None:
        return self.entries.get(entry_id)

    def recent(self, limit: int = 20) -> list[dict[str, object]]:
        ids = list(reversed(self.order))[:limit]
        return [self.entries[entry_id].public() for entry_id in ids]

    def bump(self, lang: str, action: str) -> None:
        if action not in {"duplicate", "lookup"}:
            return
        self.counters.setdefault(lang, Counter())[action] += 1

    def counts(self, lang: str) -> dict[str, int]:
        counter = self.counters.get(lang, Counter())
        return {"duplicates": counter["duplicate"], "lookup_only": counter["lookup"]}

    def trim(self) -> None:
        """Evict oldest terminal entries, never work the FIFO still needs."""
        while len(self.order) > self.limit:
            expired = next(
                (entry_id for entry_id in self.order if self.entries[entry_id].action != "pending"),
                None,
            )
            if expired is None:
                return
            self.order.remove(expired)
            self.entries.pop(expired, None)
