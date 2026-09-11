"""Event construction helpers with explicit causal metadata."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from botnet_council.telemetry.contracts import EventType, TelemetryEvent, TelemetryPayload


def event(
    event_type: EventType,
    *,
    run_id: str,
    emitted_at: datetime,
    payload: TelemetryPayload,
    symbol: str | None = None,
    timeframe: str | None = None,
    source_snapshot_id: str | None = None,
    correlation_id: str | None = None,
) -> TelemetryEvent:
    return TelemetryEvent(
        event_id=str(uuid4()),
        event_type=event_type,
        run_id=run_id,
        symbol=symbol,
        timeframe=timeframe,
        emitted_at=emitted_at,
        source_snapshot_id=source_snapshot_id,
        correlation_id=correlation_id,
        payload=payload,
    )
