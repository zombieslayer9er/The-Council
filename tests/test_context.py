from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from botnet_council.agents import TrendAgent
from botnet_council.context import (
    ContextCapability,
    ContextDatum,
    ContextRequest,
    ContextService,
    MarketContext,
    TemporalProvenance,
    analyze_with_context,
)
from botnet_council.schemas import AgentContext, AgentSignal, MarketSnapshot, SignalType


@dataclass
class FakeContextProvider:
    datum: ContextDatum
    calls: int = 0
    provider_id: str = "macro-fixture"
    source_version: str = "2026-01-01"
    capabilities: frozenset[ContextCapability] = frozenset(
        {ContextCapability.MACRO_INDICATORS}
    )

    def fetch(self, request: ContextRequest) -> tuple[ContextDatum, ...]:
        self.calls += 1
        return (self.datum,)


@dataclass(frozen=True)
class MacroRequiredAgent:
    agent_id: str = "macro-required"
    agent_version: str = "1"
    signal_type: SignalType = SignalType.ALPHA
    required_context_capabilities = frozenset(
        {ContextCapability.PRICE_HISTORY, ContextCapability.MACRO_INDICATORS}
    )
    optional_context_capabilities = frozenset({ContextCapability.EVENT_CALENDAR})

    def analyze(self, snapshot: MarketSnapshot, context: AgentContext) -> AgentSignal:
        raise AssertionError("missing required context must abstain before agent execution")


def datum(as_of: datetime, *, available_at: datetime | None = None) -> ContextDatum:
    return ContextDatum(
        capability=ContextCapability.MACRO_INDICATORS,
        instrument="US",
        name="cpi_year_over_year",
        value=2.4,
        unit="percent",
        provenance=TemporalProvenance(
            provider="macro-fixture",
            source_id="cpi-2025-12",
            observed_at=as_of - timedelta(days=31),
            period_start=as_of - timedelta(days=62),
            period_end=as_of - timedelta(days=31),
            published_at=as_of - timedelta(days=1),
            provider_available_at=available_at or as_of - timedelta(hours=1),
            ingested_at=available_at or as_of - timedelta(minutes=30),
            vintage="2025-12-first",
            source_version="2026-01-01",
        ),
    )


def request(as_of: datetime) -> ContextRequest:
    return ContextRequest(
        instrument="TEST/USD",
        timeframe="5m",
        as_of=as_of,
        required=frozenset(
            {ContextCapability.PRICE_HISTORY, ContextCapability.MACRO_INDICATORS}
        ),
        optional=frozenset({ContextCapability.EVENT_CALENDAR}),
    )


def test_context_service_is_causal_deterministic_and_cached(
    rising_snapshot: MarketSnapshot, as_of: datetime
) -> None:
    provider = FakeContextProvider(datum(as_of))
    service = ContextService((provider,))

    first = service.enrich(rising_snapshot, request(as_of))
    second = service.enrich(rising_snapshot, request(as_of))

    assert first == second
    assert first.context_id == second.context_id
    assert provider.calls == 1
    assert first.missing_required == frozenset()
    assert first.missing_optional == frozenset({ContextCapability.EVENT_CALENDAR})


def test_context_rejects_evidence_that_was_not_available_at_cutoff(
    rising_snapshot: MarketSnapshot, as_of: datetime
) -> None:
    provider = FakeContextProvider(datum(as_of, available_at=as_of + timedelta(seconds=1)))

    with pytest.raises(ValidationError, match="unavailable at as_of"):
        ContextService((provider,)).enrich(rising_snapshot, request(as_of))


def test_missing_required_capability_abstains_without_calling_agent(
    rising_snapshot: MarketSnapshot, as_of: datetime
) -> None:
    context = MarketContext(
        snapshot=rising_snapshot,
        as_of=as_of,
        requested_required=frozenset(
            {ContextCapability.PRICE_HISTORY, ContextCapability.MACRO_INDICATORS}
        ),
        requested_optional=frozenset({ContextCapability.EVENT_CALENDAR}),
        missing_required=frozenset({ContextCapability.MACRO_INDICATORS}),
        missing_optional=frozenset({ContextCapability.EVENT_CALENDAR}),
    )

    signal = analyze_with_context(MacroRequiredAgent(), context, AgentContext(run_id="run"))

    assert signal.validity.value == "insufficient_data"
    assert signal.action.value == "abstain"
    assert signal.metadata["missing_required_context"] == ("macro_indicators",)


def test_missing_optional_capability_is_attached_to_signal_telemetry(
    rising_snapshot: MarketSnapshot, as_of: datetime
) -> None:
    context = MarketContext(
        snapshot=rising_snapshot,
        as_of=as_of,
        requested_optional=frozenset(
            {ContextCapability.BENCHMARK_PERFORMANCE, ContextCapability.RELATIVE_STRENGTH}
        ),
        missing_optional=frozenset(
            {ContextCapability.BENCHMARK_PERFORMANCE, ContextCapability.RELATIVE_STRENGTH}
        ),
    )

    signal = analyze_with_context(TrendAgent(), context, AgentContext(run_id="run"))

    assert signal.metadata["context_id"] == context.context_id
    assert signal.metadata["missing_optional_context"] == (
        "benchmark_performance",
        "relative_strength",
    )
