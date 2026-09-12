"""Capability-aware specialist dispatch with deterministic abstention."""

from __future__ import annotations

from collections.abc import Iterable

from botnet_council.agents._math import timeframe_delta
from botnet_council.agents.base import SpecialistAgent, warmup_bars
from botnet_council.context.models import ContextCapability, MarketContext
from botnet_council.schemas import (
    ActionIntent,
    AgentContext,
    AgentSignal,
    Direction,
    SignalValidity,
)


def required_capabilities(agent: SpecialistAgent) -> frozenset[ContextCapability]:
    return _declaration(agent, "required_context_capabilities") | {
        ContextCapability.PRICE_HISTORY
    }


def optional_capabilities(agent: SpecialistAgent) -> frozenset[ContextCapability]:
    return _declaration(agent, "optional_context_capabilities") - required_capabilities(agent)


def requested_capabilities(
    agents: Iterable[SpecialistAgent],
) -> tuple[frozenset[ContextCapability], frozenset[ContextCapability]]:
    required: set[ContextCapability] = {ContextCapability.PRICE_HISTORY}
    optional: set[ContextCapability] = set()
    for agent in agents:
        required.update(required_capabilities(agent))
        optional.update(optional_capabilities(agent))
    optional.difference_update(required)
    return frozenset(required), frozenset(optional)


def analyze_with_context(
    agent: SpecialistAgent, market_context: MarketContext, agent_context: AgentContext
) -> AgentSignal:
    missing_required = required_capabilities(agent) - market_context.available_capabilities
    missing_optional = optional_capabilities(agent) - market_context.available_capabilities
    if missing_required:
        names = tuple(sorted(item.value for item in missing_required))
        return AgentSignal(
            schema_version="1.1",
            agent_id=agent.agent_id,
            agent_version=str(getattr(agent, "agent_version", "unknown")),
            signal_type=agent.signal_type,
            symbol=market_context.snapshot.symbol,
            timeframe=market_context.snapshot.timeframe,
            source_snapshot_id=market_context.snapshot.snapshot_id,
            source_as_of=market_context.as_of,
            forecast_direction=Direction.FLAT,
            expected_return=None,
            target_exposure=None,
            action=ActionIntent.ABSTAIN,
            validity=SignalValidity.INSUFFICIENT_DATA,
            confidence=0.0,
            horizon_bars=max(1, warmup_bars(agent, market_context.snapshot.timeframe)),
            generated_at=market_context.snapshot.observed_at,
            expires_at=(
                market_context.snapshot.observed_at
                + timeframe_delta(market_context.snapshot.timeframe)
            ),
            rationale=f"Missing required context: {', '.join(names)}.",
            metadata={
                "context_id": market_context.context_id,
                "missing_required_context": names,
                "missing_optional_context": tuple(
                    sorted(item.value for item in missing_optional)
                ),
            },
        )
    parameters = dict(agent_context.parameters)
    parameters.update(
        {
            "market_context_id": market_context.context_id,
            "available_context_capabilities": tuple(
                sorted(item.value for item in market_context.available_capabilities)
            ),
            "missing_optional_context": tuple(
                sorted(item.value for item in missing_optional)
            ),
        }
    )
    signal = agent.analyze(
        market_context.snapshot,
        AgentContext(run_id=agent_context.run_id, parameters=parameters),
    )
    metadata = dict(signal.metadata)
    metadata.update(
        {
            "context_id": market_context.context_id,
            "available_context_capabilities": tuple(
                sorted(item.value for item in market_context.available_capabilities)
            ),
            "missing_optional_context": tuple(
                sorted(item.value for item in missing_optional)
            ),
        }
    )
    values = signal.model_dump(mode="python", warnings=False)
    values["metadata"] = metadata
    return AgentSignal.model_validate(values)


def _declaration(agent: SpecialistAgent, name: str) -> frozenset[ContextCapability]:
    value: object = getattr(agent, name, frozenset())
    if not isinstance(value, frozenset) or any(
        not isinstance(item, ContextCapability) for item in value
    ):
        raise ValueError(f"agent {agent.agent_id!r} has an invalid {name} declaration")
    return value
