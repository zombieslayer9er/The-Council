import asyncio
from datetime import UTC, datetime
from threading import Thread

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from botnet_council.api.app import _enqueue_or_lag, create_app
from botnet_council.telemetry.contracts import (
    BacktestPayload,
    EventType,
    PipelineFailedPayload,
    StagePayload,
    TelemetryEvent,
)
from botnet_council.telemetry.events import event
from botnet_council.telemetry.publisher import InMemoryEventBus
from botnet_council.telemetry.sanitize import sanitize_exception


def _started(run_id: str = "run-api") -> TelemetryEvent:
    return event(
        EventType.PIPELINE_STARTED,
        run_id=run_id,
        emitted_at=datetime(2026, 1, 1, tzinfo=UTC),
        symbol="TEST/USD",
        timeframe="5m",
        payload=StagePayload(stage="pipeline"),
    )


def test_health_and_collection_contracts_are_versioned() -> None:
    bus = InMemoryEventBus()
    bus.publish(_started())
    client = TestClient(create_app(bus))

    health = client.get("/api/health")
    runs = client.get("/api/runs?limit=10&offset=0")
    missing = client.get("/api/decisions/missing")

    assert health.status_code == 200
    assert health.json()["api_version"] == "v1"
    assert health.json()["read_only"] is True
    assert health.json()["capabilities"] == ["telemetry_read", "experiment_read"]
    assert health.json()["command_authentication"] == "disabled"
    assert runs.json()["total"] == 1
    assert runs.json()["items"][0]["status"] == "running"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "http_error"
    assert missing.json()["error"]["request_id"]
    assert "traceback" not in missing.text.lower()
    assert "TelemetryEvent" in client.get("/openapi.json").json()["components"]["schemas"]


def test_empty_state_matches_the_public_response_contract() -> None:
    client = TestClient(create_app(InMemoryEventBus()))

    response = client.get("/api/state")

    assert response.status_code == 200
    assert response.json()["active_runs"] == []
    assert response.json()["last_sequence"] == 0
    assert response.json()["stream_id"]
    assert response.json()["sequence_watermark"] == 0


def test_websocket_serializes_envelope_and_applies_filters() -> None:
    bus = InMemoryEventBus()
    client = TestClient(create_app(bus))
    with client.websocket_connect("/ws/events?symbol=TEST%2FUSD") as socket:
        thread = Thread(target=lambda: bus.publish(_started()), daemon=True)
        thread.start()
        message = socket.receive_json()
        thread.join()

    assert message["event_type"] == "pipeline_started"
    assert message["schema_version"] == "1.1"
    assert message["stream_id"] == bus.stream_id
    assert message["symbol"] == "TEST/USD"
    assert message["sequence"] == 1


def test_bootstrap_is_atomic_and_runs_use_time_and_explicit_kind() -> None:
    bus = InMemoryEventBus(stream_id="generation-test")
    later = datetime(2026, 1, 2, tzinfo=UTC)
    bus.publish(_started("zzzz-hash"))
    bus.publish(
        event(
            EventType.BACKTEST_STARTED,
            run_id="0000-hash",
            emitted_at=later,
            payload=BacktestPayload(status="started"),
        )
    )
    client = TestClient(create_app(bus))

    response = client.get("/api/bootstrap")
    backtests = client.get("/api/backtests")

    assert response.status_code == 200
    body = response.json()
    assert body["stream_id"] == "generation-test"
    assert body["sequence_watermark"] == 2
    assert body["state"]["sequence_watermark"] == 2
    assert [item["run_id"] for item in body["runs"]] == ["0000-hash", "zzzz-hash"]
    assert body["runs"][0]["run_kind"] == "backtest"
    assert [item["run_id"] for item in backtests.json()["items"]] == ["0000-hash"]


def test_websocket_rejects_untrusted_browser_origin() -> None:
    client = TestClient(create_app(InMemoryEventBus()))
    with (
        pytest.raises(WebSocketDisconnect) as caught,
        client.websocket_connect(
            "/ws/events", headers={"origin": "https://evil.example"}
        ),
    ):
        pass
    assert caught.value.code == 1008


def test_bounded_websocket_queue_marks_slow_consumer_for_resync() -> None:
    queue: asyncio.Queue[TelemetryEvent | None] = asyncio.Queue(maxsize=1)
    first = _started("one")
    second = _started("two")

    _enqueue_or_lag(queue, first)
    _enqueue_or_lag(queue, second)

    assert queue.qsize() == 1
    assert queue.get_nowait() is None


def test_synthetic_secrets_and_private_paths_do_not_reach_rest_or_websocket() -> None:
    bus = InMemoryEventBus()
    client = TestClient(create_app(bus))
    raw = "api_key=SYNTHETIC_SECRET token=OTHER C:\\Users\\alice\\private.txt /home/alice/secret"
    safe = sanitize_exception(RuntimeError(raw), stage="agent_analysis")

    def failed(event_id: str) -> TelemetryEvent:
        return event(
            EventType.PIPELINE_FAILED,
            run_id="opaque-failure",
            emitted_at=datetime(2026, 1, 1, tzinfo=UTC),
            payload=PipelineFailedPayload(
                stage="agent_analysis", error_code=safe.code, message=safe.message
            ),
        ).model_copy(update={"event_id": event_id})

    bus.publish(failed("rest-failure"))
    rest_text = client.get("/api/runs/opaque-failure").text
    with client.websocket_connect("/ws/events") as socket:
        thread = Thread(target=lambda: bus.publish(failed("ws-failure")), daemon=True)
        thread.start()
        websocket_text = socket.receive_text()
        thread.join()

    combined = rest_text + websocket_text
    assert "SYNTHETIC_SECRET" not in combined
    assert "OTHER" not in combined
    assert "alice" not in combined
    assert "agent analysis failed" in combined
