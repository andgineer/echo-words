"""In-process publication of pipeline progress to every connected SSE client."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Event:
    name: str
    data: dict[str, Any]


class EventHub:
    """Fan events out without ever letting a slow browser stall the worker."""

    def __init__(self, *, subscriber_capacity: int = 100) -> None:
        self._subscriber_capacity = subscriber_capacity
        self._subscribers: set[asyncio.Queue[Event]] = set()

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[Event]]:
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=self._subscriber_capacity)
        self._subscribers.add(queue)
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)

    async def publish(self, name: str, data: dict[str, Any]) -> None:
        event = Event(name, data)
        slow: list[asyncio.Queue[Event]] = []
        for queue in tuple(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                slow.append(queue)
        for queue in slow:
            self._subscribers.discard(queue)
            while not queue.empty():
                queue.get_nowait()
            queue.put_nowait(Event("_disconnect", {}))
