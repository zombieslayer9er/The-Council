"""Forecast generation that has no oracle dependency or oracle parameter."""

import json
from hashlib import sha256

from botnet_council.agents.factory import build_agents
from botnet_council.backtest.models import to_jsonable
from botnet_council.council import DeterministicCouncil
from botnet_council.experiments.models import (
    AgentVersion,
    CouncilWeight,
    ExperimentContext,
    ExperimentRequest,
    Forecast,
)


class BlindForecaster:
    def forecast(self, request: ExperimentRequest, context: ExperimentContext) -> Forecast:
        if context.experiment_id != request.experiment_id:
            raise ValueError("context belongs to a different experiment")
        if any(bar.available_at > request.evaluation_time for bar in context.snapshot.bars):
            raise RuntimeError("forecasting context contains future data")
        agents = build_agents(request.agents)
        signals = tuple(agent.analyze(context.snapshot, context.agent_context) for agent in agents)
        decision = DeterministicCouncil(request.council).aggregate(context.snapshot, signals)
        material = json.dumps(
            to_jsonable(
                {
                    "experiment_id": request.experiment_id,
                    "decision": decision,
                    "blind_provenance": context.provenance,
                }
            ),
            sort_keys=True,
            separators=(",", ":"),
        )
        return Forecast(
            forecast_id=sha256(material.encode()).hexdigest()[:24],
            experiment_id=request.experiment_id,
            evaluation_time=request.evaluation_time,
            instrument=request.instrument,
            forecast_horizon=request.forecast_horizon,
            expected_return=decision.expected_return,
            direction=decision.forecast_direction,
            confidence=decision.confidence,
            agent_forecasts=signals,
            council_decision=decision,
            council_weights=tuple(
                CouncilWeight(agent_id=key, weight=value)
                for key, value in sorted(request.council.agent_weights.items())
            ),
            source_provenance=context.provenance,
            agent_versions=tuple(
                AgentVersion(
                    agent_id=agent.agent_id,
                    version=str(getattr(agent, "agent_version", "unknown")),
                )
                for agent in agents
            ),
            finalized_at=request.evaluation_time,
        )
