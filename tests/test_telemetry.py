from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from time import sleep

import pytest
from pydantic import ValidationError

from botnet_council.agents import TrendAgent, VolatilityAgent
from botnet_council.council import CouncilConfig, DeterministicCouncil
from botnet_council.execution import PaperExecutionAdapter
from botnet_council.market_data import InMemoryMarketDataProvider
from botnet_council.pipeline import ResearchTradingPipeline
from botnet_council.risk import DeterministicRiskGovernor, RiskPolicy
from botnet_council.schemas import (
    ApprovedOrder,
    FillPolicy,
    MarketBar,
    MarketSnapshot,
    OpeningPriceObservation,
    OrderSide,
    SnapshotProvenance,
)
from botnet_council.telemetry.contracts import (
    AgentSignalPayload,
    EventType,
    SnapshotPayload,
    StagePayload,
    TelemetryEvent,
)
from botnet_council.telemetry.events import event
from botnet_council.telemetry.publisher import EventFilter, EventPublisher, InMemoryEventBus
from botnet_council.telemetry.serializers import agent_signal, approved_order, snapshot


def build_pipeline(
    market_snapshot: MarketSnapshot,
    as_of: datetime,
    policy: RiskPolicy,
    bus: EventPublisher | None,
) -> ResearchTradingPipeline:
    return ResearchTradingPipeline(
        InMemoryMarketDataProvider({("TEST/USD", "5m"): market_snapshot}),
        (TrendAgent(), VolatilityAgent()),
        DeterministicCouncil(CouncilConfig(minimum_conviction=0.01)),
        DeterministicRiskGovernor(policy),
        PaperExecutionAdapter(100_000, opened_at=as_of - timedelta(days=1)),
        telemetry=bus,
    )


def opening(at: datetime, price: float) -> OpeningPriceObservation:
    return OpeningPriceObservation(
        symbol="TEST/USD",
        timeframe="5m",
        price=price,
        bar_opened_at=at,
        observed_at=at,
    )


def test_event_schema_is_versioned_immutable_and_requires_utc(as_of: datetime) -> None:
    value = event(
        EventType.PIPELINE_STARTED,
        run_id="run-1",
        emitted_at=as_of,
        payload=StagePayload(stage="pipeline"),
    )

    assert value.schema_version == "1.2"
    assert value.model_dump(mode="json")["emitted_at"].endswith("Z")
    with pytest.raises(ValidationError):
        TelemetryEvent(
            event_id="event-1",
            event_type=EventType.PIPELINE_STARTED,
            run_id="run-1",
            emitted_at=datetime(2026, 1, 1),
            payload=StagePayload(stage="pipeline"),
        )
    with pytest.raises(ValidationError):
        value.sequence = 3


def test_event_type_rejects_the_wrong_payload(as_of: datetime) -> None:
    with pytest.raises(ValidationError):
        event(
            EventType.SNAPSHOT_CREATED,
            run_id="run-1",
            emitted_at=as_of,
            payload=StagePayload(stage="snapshot"),
        )


def test_bus_preserves_order_filters_and_isolates_subscriber_failures(
    as_of: datetime,
) -> None:
    bus = InMemoryEventBus()
    received: list[str] = []
    bus.subscribe(
        lambda item: received.append(item.run_id), EventFilter(symbol="TEST/USD")
    )
    bus.subscribe(lambda _: (_ for _ in ()).throw(RuntimeError("broken observer")))
    for run_id, symbol in (("one", "TEST/USD"), ("two", "OTHER/USD")):
        bus.publish(
            event(
                EventType.PIPELINE_STARTED,
                run_id=run_id,
                emitted_at=as_of,
                symbol=symbol,
                payload=StagePayload(stage="pipeline"),
            )
        )

    assert [item.sequence for item in bus.list_events()] == [1, 2]
    assert received == ["one"]


def test_pipeline_emits_approved_execution_chain_without_changing_result(
    rising_snapshot: MarketSnapshot, as_of: datetime
) -> None:
    policy = RiskPolicy(max_realized_volatility=0.5)
    bus = InMemoryEventBus()
    instrumented = build_pipeline(rising_snapshot, as_of, policy, bus)
    baseline = build_pipeline(rising_snapshot, as_of, policy, None)
    next_open = opening(as_of, rising_snapshot.last_price)

    observed = instrumented.run("TEST/USD", "5m", "run-live", as_of, opening_price=next_open)
    expected = baseline.run("TEST/USD", "5m", "run-live", as_of, opening_price=next_open)

    assert observed == expected
    types = [item.event_type for item in bus.list_events()]
    assert types[0] is EventType.PIPELINE_STARTED
    assert types[-1] is EventType.PIPELINE_COMPLETED
    assert types.index(EventType.SNAPSHOT_CREATED) < types.index(
        EventType.MARKET_CONTEXT_READY
    ) < types.index(EventType.AGENT_SIGNAL_EMITTED)
    assert EventType.ORDER_APPROVED in types
    assert EventType.EXECUTION_REPORT_EMITTED in types
    assert EventType.RECONCILIATION_COMPLETED in types
    assert all(
        earlier.sequence < later.sequence
        for earlier, later in zip(bus.list_events(), bus.list_events()[1:], strict=False)
    )


def test_concurrent_publication_callbacks_follow_assigned_sequence(as_of: datetime) -> None:
    bus = InMemoryEventBus()
    received: list[int] = []

    def observe(item: TelemetryEvent) -> None:
        sleep(0.001)
        received.append(item.sequence)

    bus.subscribe(observe)
    values = [
        event(
            EventType.PIPELINE_STARTED,
            run_id=f"opaque-{index}",
            emitted_at=as_of,
            payload=StagePayload(stage="pipeline"),
        )
        for index in range(30)
    ]
    with ThreadPoolExecutor(max_workers=8) as executor:
        tuple(executor.map(bus.publish, values))

    assert received == list(range(1, 31))


def test_bus_bounds_history_and_dedup_without_resetting_sequence(as_of: datetime) -> None:
    bus = InMemoryEventBus(history_limit=2, dedup_limit=3, stream_id="generation-a")
    values = [
        event(
            EventType.PIPELINE_STARTED,
            run_id=f"opaque-{index}",
            emitted_at=as_of,
            payload=StagePayload(stage="pipeline"),
        ).model_copy(update={"event_id": f"event-{index}"})
        for index in range(5)
    ]
    for value in values:
        bus.publish(value)

    assert bus.stream_id == "generation-a"
    assert [item.sequence for item in bus.list_events()] == [4, 5]
    bus.publish(values[-1])
    assert bus.snapshot().sequence_watermark == 5
    bus.publish(values[0])
    assert [item.sequence for item in bus.list_events()] == [5, 6]


def test_publisher_failure_cannot_change_pipeline_output(
    rising_snapshot: MarketSnapshot, as_of: datetime
) -> None:
    class FailingPublisher:
        def publish(self, value: TelemetryEvent) -> None:
            raise RuntimeError("telemetry is unavailable")

        def subscribe(self, handler: object, event_filter: object = None) -> str:
            return "unused"

        def unsubscribe(self, subscription_id: str) -> None:
            return None

    policy = RiskPolicy(max_realized_volatility=0.5)
    expected = build_pipeline(rising_snapshot, as_of, policy, None).run(
        "TEST/USD", "5m", "run-failure", as_of
    )
    observed = build_pipeline(
        rising_snapshot, as_of, policy, FailingPublisher()
    ).run("TEST/USD", "5m", "run-failure", as_of)

    assert observed == expected


def test_pipeline_emits_veto_and_never_execution(
    rising_snapshot: MarketSnapshot, as_of: datetime
) -> None:
    bus = InMemoryEventBus()
    pipeline = build_pipeline(
        rising_snapshot, as_of, RiskPolicy(max_realized_volatility=1e-12), bus
    )
    pipeline.run(
        "TEST/USD",
        "5m",
        "run-veto",
        as_of,
        opening_price=opening(as_of, rising_snapshot.last_price),
    )
    types = [item.event_type for item in bus.list_events()]

    assert EventType.RISK_VETOED in types
    assert EventType.EXECUTION_STARTED not in types
    assert EventType.EXECUTION_REPORT_EMITTED not in types


def test_agent_metadata_is_json_safe_and_secret_like_values_are_redacted(
    rising_snapshot: MarketSnapshot, as_of: datetime
) -> None:
    result = build_pipeline(rising_snapshot, as_of, RiskPolicy(), None).run(
        "TEST/USD", "5m", "metadata", as_of
    )
    signal = result.signals[0].model_copy(
        update={"metadata": {"nested": {"api_token": "do-not-expose", "window": 5}}}
    )

    payload = agent_signal(signal)

    assert payload.metadata == {
        "nested": {"api_token": "[REDACTED]", "window": 5}
    }
    payload.model_dump_json()


def test_insufficient_data_and_abstain_are_observable(as_of: datetime) -> None:
    short_snapshot = MarketSnapshot(
        symbol="TEST/USD",
        timeframe="5m",
        as_of=as_of,
        observed_at=as_of,
        bars=(
            MarketBar(
                opened_at=as_of - timedelta(minutes=5),
                closed_at=as_of,
                available_at=as_of,
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.0,
                volume=1.0,
            ),
        ),
    )
    bus = InMemoryEventBus()
    pipeline = build_pipeline(short_snapshot, as_of, RiskPolicy(), bus)
    result = pipeline.run("TEST/USD", "5m", "short", as_of)
    signals: list[AgentSignalPayload] = []
    for item in bus.list_events():
        if (
            item.event_type is EventType.AGENT_SIGNAL_EMITTED
            and isinstance(item.payload, AgentSignalPayload)
        ):
            signals.append(item.payload)

    assert result.execution_report is None
    assert all(item.validity == "insufficient_data" for item in signals)
    assert all(item.action == "abstain" for item in signals)


def test_reduce_only_and_snapshot_provenance_are_preserved(as_of: datetime) -> None:
    order = ApprovedOrder(
        authorization_id="order-1",
        decision_id="decision-1",
        source_snapshot_id="snapshot-1",
        symbol="TEST/USD",
        timeframe="5m",
        side=OrderSide.SELL,
        quantity=1.0,
        reference_price=100.0,
        authorized_at=as_of,
        earliest_fill_at=as_of,
        expires_at=as_of + timedelta(minutes=5),
        fill_policy=FillPolicy.NEXT_BAR_OPEN,
        reduce_only=True,
    )
    assert approved_order(order).reduce_only is True
    assert approved_order(order).paper_only is True

    bar = MarketBar(
        opened_at=as_of - timedelta(minutes=5),
        closed_at=as_of,
        available_at=as_of,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.0,
        volume=1.0,
    )
    market_snapshot = MarketSnapshot(
        symbol="TEST/USD",
        timeframe="5m",
        as_of=as_of,
        observed_at=as_of,
        bars=(bar,),
        provenance=SnapshotProvenance(
            provider="test",
            instrument="TEST/USD",
            timeframe="5m",
            requested_start=bar.opened_at,
            requested_end=as_of,
            as_of=as_of,
            fetched_at=as_of,
            latest_observation_time=bar.closed_at,
            latest_available_at=bar.available_at,
            source_version="fixture-1",
            adapter_semantic_version="1.2.3",
            coverage_complete=True,
            cache_key="safe-cache-key",
        ),
    )
    payload: SnapshotPayload = snapshot(market_snapshot)
    assert payload.provenance is not None
    assert payload.provenance.adapter_version == "1.2.3"
    assert payload.provenance.cache_key == "safe-cache-key"
