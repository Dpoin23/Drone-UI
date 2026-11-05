"""Fan-out of pipeline events (detections, alerts, status) from worker threads to WebSocket clients."""

import asyncio
import threading
from typing import Any


class Subscriber:
    def __init__(self, loop: asyncio.AbstractEventLoop, maxsize: int) -> None:
        self.loop = loop
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize)

    def offer(self, event: dict[str, Any]) -> None:
        """Enqueue on the subscriber's loop, dropping the oldest event if the client is slow."""
        if self.queue.full():
            self.queue.get_nowait()
        self.queue.put_nowait(event)


class EventHub:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subs: set[Subscriber] = set()

    def subscribe(self, loop: asyncio.AbstractEventLoop, maxsize: int = 200) -> Subscriber:
        sub = Subscriber(loop, maxsize)
        with self._lock:
            self._subs.add(sub)
        return sub

    def unsubscribe(self, sub: Subscriber) -> None:
        with self._lock:
            self._subs.discard(sub)

    def publish(self, event: dict[str, Any]) -> None:
        """Thread-safe: callable from inference workers as well as from the event loop."""
        with self._lock:
            subs = list(self._subs)
        for sub in subs:
            try:
                sub.loop.call_soon_threadsafe(sub.offer, event)
            except RuntimeError:  # The client's loop has closed.
                self.unsubscribe(sub)

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subs)
