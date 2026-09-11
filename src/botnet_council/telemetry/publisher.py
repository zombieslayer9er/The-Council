"""Transport-neutral ordered publication and development event storage."""

from __future__ import annotations

import logging
from collections import OrderedDict, deque
from collections.abc import Callable
from dataclasses import dataclass
from threading import RLock
from typing import Protocol, runtime_checkable
from uuid import uuid4

from botnet_council.telemetry.contracts import EventType, TelemetryEvent

logger = logging.getLogger(__name__)
EventHandler = Callable[[TelemetryEvent], None]
DEFAULT_HISTORY_LIMIT = 10_000
DEFAULT_DEDUP_LIMIT = 20_000


@dataclass(frozen=True, slots=True)
class EventBusSnapshot:
    stream_id: str
    sequence_watermark: int
    events: tuple[TelemetryEvent, ...]


@dataclass(frozen=True, slots=True)
class EventFilter:
    symbol: str | None = None
    run_id: str | None = None
    event_types: frozenset[EventType] | None = None
    timeframe: str | None = None

    def matches(self, event: TelemetryEvent) -> bool:
        return not (
            (self.symbol is not None and event.symbol != self.symbol)
            or (self.run_id is not None and event.run_id != self.run_id)
            or (self.event_types is not None and event.event_type not in self.event_types)
            or (self.timeframe is not None and event.timeframe != self.timeframe)
        )


@runtime_checkable
class EventStore(Protocol):
    def append(self, event: TelemetryEvent) -> None: ...
    def get(self, event_id: str) -> TelemetryEvent | None: ...
    def list_events(
        self, event_filter: EventFilter | None = None
    ) -> tuple[TelemetryEvent, ...]: ...


@runtime_checkable
class EventPublisher(Protocol):
    def publish(self, event: TelemetryEvent) -> None: ...
    def subscribe(
        self, handler: EventHandler, event_filter: EventFilter | None = None
    ) -> str: ...
    def unsubscribe(self, subscription_id: str) -> None: ...


class InMemoryEventBus(EventPublisher, EventStore):
    """Thread-safe, bounded process-local stream with generation-scoped ordering."""

    def __init__(
        self,
        *,
        history_limit: int = DEFAULT_HISTORY_LIMIT,
        dedup_limit: int = DEFAULT_DEDUP_LIMIT,
        stream_id: str | None = None,
    ) -> None:
        if history_limit < 1 or dedup_limit < 1:
            raise ValueError("telemetry limits must be positive")
        self._lock = RLock()
        self._dispatch_lock = RLock()
        self._stream_id = stream_id or str(uuid4())
        self._sequence = 0
        self._events: deque[TelemetryEvent] = deque(maxlen=history_limit)
        self._event_ids: OrderedDict[str, None] = OrderedDict()
        self._dedup_limit = dedup_limit
        self._subscribers: dict[str, tuple[EventHandler, EventFilter]] = {}

    @property
    def stream_id(self) -> str:
        return self._stream_id

    def publish(self, event: TelemetryEvent) -> None:
        # Serializing dispatch separately guarantees callback order without holding
        # the state lock while arbitrary subscriber code runs.
        with self._dispatch_lock:
            with self._lock:
                if event.event_id in self._event_ids:
                    return
                self._sequence += 1
                sequenced = event.model_copy(
                    update={"sequence": self._sequence, "stream_id": self._stream_id}
                )
                self._events.append(sequenced)
                self._event_ids[sequenced.event_id] = None
                while len(self._event_ids) > self._dedup_limit:
                    self._event_ids.popitem(last=False)
                subscribers = tuple(self._subscribers.values())
            for handler, event_filter in subscribers:
                if event_filter.matches(sequenced):
                    try:
                        handler(sequenced)
                    except Exception:
                        logger.exception("telemetry subscriber failed")

    def subscribe(
        self, handler: EventHandler, event_filter: EventFilter | None = None
    ) -> str:
        subscription_id = str(uuid4())
        with self._lock:
            self._subscribers[subscription_id] = (handler, event_filter or EventFilter())
        return subscription_id

    def unsubscribe(self, subscription_id: str) -> None:
        with self._lock:
            self._subscribers.pop(subscription_id, None)

    def append(self, event: TelemetryEvent) -> None:
        self.publish(event)

    def get(self, event_id: str) -> TelemetryEvent | None:
        with self._lock:
            return next((item for item in self._events if item.event_id == event_id), None)

    def snapshot(self) -> EventBusSnapshot:
        with self._lock:
            return EventBusSnapshot(
                stream_id=self._stream_id,
                sequence_watermark=self._sequence,
                events=tuple(self._events),
            )

    def list_events(
        self, event_filter: EventFilter | None = None
    ) -> tuple[TelemetryEvent, ...]:
        selected = event_filter or EventFilter()
        with self._lock:
            return tuple(item for item in self._events if selected.matches(item))


class NullEventPublisher(EventPublisher):
    def publish(self, event: TelemetryEvent) -> None:
        del event

    def subscribe(
        self, handler: EventHandler, event_filter: EventFilter | None = None
    ) -> str:
        del handler, event_filter
        return ""

    def unsubscribe(self, subscription_id: str) -> None:
        del subscription_id


def safe_publish(publisher: EventPublisher | None, value: TelemetryEvent) -> None:
    """Telemetry is explicitly best-effort and cannot fail the domain workflow."""
    if publisher is None:
        return
    try:
        publisher.publish(value)
    except Exception:
        logger.exception("telemetry publication failed")
