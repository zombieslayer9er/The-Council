"""Immutable experience episodes with a hard evidence/truth boundary."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from botnet_council.backtest.models import BacktestConfig, BacktestRun, to_jsonable
from botnet_council.council import CouncilConfig
from botnet_council.experiments import ExperimentRecord, ExperimentState
from botnet_council.experiments.models import (
    ForecastEvaluation,
    OracleOutcome,
    OracleProvenance,
)
from botnet_council.market_data import HistoricalRequest, Timeframe
from botnet_council.schemas import (
    AgentSignal,
    CouncilDecision,
    Direction,
    ExecutionReport,
    MarketBar,
    MarketSnapshot,
    PortfolioState,
    RiskDecision,
)

EXPERIENCE_SCHEMA_VERSION = "1.0"


class ExperienceModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class AgentVersion(ExperienceModel):
    agent_id: str
    version: str


class AppliedWeight(ExperienceModel):
    agent_id: str
    weight: float = Field(ge=0, allow_inf_nan=False)


class DecisionEvidence(ExperienceModel):
    """Only information available in the original decision/execution graph."""

    symbol: str
    asset_class: str | None = None
    timeframe: str
    decision_timestamp: datetime
    market_data_content_identity: str
    market_data_version: str
    snapshot: MarketSnapshot
    specialist_outputs: tuple[AgentSignal, ...]
    agent_versions: tuple[AgentVersion, ...]
    council_config: CouncilConfig
    applied_weights: tuple[AppliedWeight, ...]
    weight_generation_id: str
    council_decision: CouncilDecision
    risk_policy_version: str
    risk_decision: RiskDecision | None = None
    execution_report: ExecutionReport | None = None
    portfolio_state: PortfolioState | None = None
    backtest_run_id: str
    regime: str | None = None

    @field_validator("decision_timestamp")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("decision_timestamp must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_evidence(self) -> Self:
        if (self.symbol, self.timeframe) != (
            self.snapshot.symbol,
            self.snapshot.timeframe,
        ):
            raise ValueError("episode symbol and timeframe must match the snapshot")
        if self.decision_timestamp != self.council_decision.decided_at:
            raise ValueError("decision_timestamp must equal the Council decision time")
        if self.snapshot.as_of > self.decision_timestamp:
            raise ValueError("episode snapshot is from after the decision")
        if self.specialist_outputs != self.council_decision.signals:
            raise ValueError("specialist outputs must be the frozen Council inputs")
        versions = tuple(
            AgentVersion(agent_id=item.agent_id, version=item.agent_version)
            for item in self.specialist_outputs
        )
        if self.agent_versions != versions:
            raise ValueError("agent_versions must match specialist outputs in order")
        if len({item.agent_id for item in self.applied_weights}) != len(self.applied_weights):
            raise ValueError("applied weight agent IDs must be unique")
        if not all(
            (
                self.market_data_content_identity,
                self.market_data_version,
                self.weight_generation_id,
                self.risk_policy_version,
                self.backtest_run_id,
            )
        ):
            raise ValueError("episode provenance identity fields are required")
        if (
            self.risk_decision is not None
            and self.risk_decision.approved_order is not None
            and self.risk_decision.approved_order.decision_id
            != self.council_decision.decision_id
        ):
            raise ValueError("risk and Council decision identities differ")
        if self.execution_report is not None and self.risk_decision is None:
            raise ValueError("execution evidence requires a risk decision")
        return self


class OutcomeTruth(ExperienceModel):
    """Post-decision truth that must never enter Council replay inputs."""

    oracle_outcome: OracleOutcome
    judge_evaluation: ForecastEvaluation
    available_at: datetime

    @field_validator("available_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("available_at must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_truth(self) -> Self:
        if self.oracle_outcome.experiment_id != self.judge_evaluation.experiment_id:
            raise ValueError("oracle and Judge records belong to different experiments")
        if not self.oracle_outcome.horizon_complete:
            raise ValueError("experience truth requires a complete outcome horizon")
        if self.available_at < self.oracle_outcome.horizon_end:
            raise ValueError("truth cannot be available before the outcome horizon")
        if self.available_at < self.judge_evaluation.evaluated_at:
            raise ValueError("truth cannot be available before Judge evaluation")
        return self


class ExperienceEpisode(ExperienceModel):
    schema_version: str = EXPERIENCE_SCHEMA_VERSION
    evidence: DecisionEvidence
    truth: OutcomeTruth | None = None
    episode_id: str = ""
    equivalence_id: str = ""
    decision_cache_key: str = ""

    @model_validator(mode="after")
    def validate_episode(self) -> Self:
        if self.schema_version != EXPERIENCE_SCHEMA_VERSION:
            raise ValueError("unsupported experience schema version")
        if (
            self.truth is not None
            and self.truth.oracle_outcome.evaluation_time != self.evidence.snapshot.as_of
        ):
            raise ValueError("truth evaluation time differs from decision evidence")
        expected_episode = _identity(_episode_material(self.evidence, self.truth))
        expected_equivalence = _identity(_equivalence_material(self.evidence, self.truth))
        expected_cache = _identity(_decision_material(self.evidence))
        for name, supplied, expected in (
            ("episode_id", self.episode_id, expected_episode),
            ("equivalence_id", self.equivalence_id, expected_equivalence),
            ("decision_cache_key", self.decision_cache_key, expected_cache),
        ):
            if supplied and supplied != expected:
                raise ValueError(f"{name} does not match episode contents")
            object.__setattr__(self, name, expected)
        return self

    @property
    def training_eligible(self) -> bool:
        return self.truth is not None


class EpisodeQuery(ExperienceModel):
    symbol: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    weight_generation_id: str | None = None
    regime: str | None = None
    agent_id: str | None = None
    agent_version: str | None = None
    training_only: bool = False

    @field_validator("start", "end")
    @classmethod
    def normalize_time(cls, value: datetime | None, info: object) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            name = getattr(info, "field_name", "datetime")
            raise ValueError(f"{name} must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if self.start is not None and self.end is not None and self.end <= self.start:
            raise ValueError("query end must follow start")
        if self.agent_version is not None and self.agent_id is None:
            raise ValueError("agent_version requires agent_id")
        return self


class CouncilReplay(ExperienceModel):
    episode_id: str
    snapshot: MarketSnapshot
    specialist_outputs: tuple[AgentSignal, ...]
    original_council_config: CouncilConfig
    original_weight_generation_id: str
    original_decision_id: str


class TemporalReplaySplit(ExperienceModel):
    cutoff: datetime
    training: tuple[CouncilReplay, ...]
    held_out: tuple[CouncilReplay, ...]
    excluded_unavailable_truth: tuple[str, ...] = ()

    @field_validator("cutoff")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("cutoff must be timezone-aware")
        return value.astimezone(UTC)


def episode_from_experiment(
    record: ExperimentRecord,
    *,
    weight_generation_id: str = "weights-v0000",
    risk_policy_version: str = "not-applicable",
    regime: str | None = None,
    asset_class: str | None = None,
) -> ExperienceEpisode:
    if record.state is not ExperimentState.COMPLETE:
        raise ValueError("only complete judged experiments can become experiences")
    if (
        record.context is None
        or record.forecast is None
        or record.oracle_outcome is None
        or record.evaluation is None
    ):
        raise ValueError("complete experiment is missing required artifacts")
    forecast = record.forecast
    provenance = record.context.provenance
    evidence = DecisionEvidence(
        symbol=record.request.instrument,
        asset_class=asset_class,
        timeframe=record.request.timeframe,
        decision_timestamp=forecast.council_decision.decided_at,
        market_data_content_identity=provenance.content_identity,
        market_data_version=(
            f"{provenance.provider.value}:{provenance.source_version}:"
            f"{provenance.adapter_semantic_version}"
        ),
        snapshot=record.context.snapshot,
        specialist_outputs=forecast.agent_forecasts,
        agent_versions=tuple(
            AgentVersion(agent_id=item.agent_id, version=item.version)
            for item in forecast.agent_versions
        ),
        council_config=record.request.council,
        applied_weights=tuple(
            AppliedWeight(agent_id=item.agent_id, weight=item.weight)
            for item in forecast.council_weights
        ),
        weight_generation_id=weight_generation_id,
        council_decision=forecast.council_decision,
        risk_policy_version=risk_policy_version,
        portfolio_state=record.request.starting_portfolio,
        backtest_run_id=record.experiment_id,
        regime=regime,
    )
    truth = OutcomeTruth(
        oracle_outcome=record.oracle_outcome,
        judge_evaluation=record.evaluation,
        available_at=record.evaluation.evaluated_at,
    )
    return ExperienceEpisode(evidence=evidence, truth=truth)


def episodes_from_backtest(
    run: BacktestRun,
    config: BacktestConfig,
    candles: tuple[MarketBar, ...],
) -> tuple[ExperienceEpisode, ...]:
    """Convert complete, causally measurable backtest decisions into episodes."""
    timeframe = Timeframe(config.timeframe)
    by_close = {bar.closed_at: bar for bar in candles}
    executions = {
        event.execution_report.authorization_id: event.execution_report
        for event in run.ledger.events
        if event.execution_report is not None
    }
    provenance = run.result.market_data_provenance
    weight_generation_id = f"backtest-weights:{_identity(to_jsonable(config.council))}"
    risk_policy_version = f"backtest-risk:{_identity(to_jsonable(config.risk))}"
    episodes: list[ExperienceEpisode] = []
    for event in run.ledger.events:
        decision = event.council_decision
        snapshot = event.snapshot
        if not event.measured or decision is None or snapshot is None:
            continue
        horizons = {signal.horizon_bars for signal in decision.signals}
        if len(horizons) != 1 or decision.decided_at != snapshot.as_of:
            continue
        horizon_bars = horizons.pop()
        horizon_end = decision.decided_at + timeframe.duration * horizon_bars
        start = by_close.get(decision.decided_at)
        endpoint = by_close.get(horizon_end)
        path = tuple(
            bar
            for bar in candles
            if decision.decided_at < bar.closed_at <= horizon_end
        )
        if (
            start is None
            or endpoint is None
            or len(path) != horizon_bars
            or any(bar.available_at > horizon_end for bar in path)
        ):
            continue
        realized_return = endpoint.close / start.close - 1.0
        realized_direction = (
            Direction.LONG
            if realized_return > 0
            else Direction.SHORT
            if realized_return < 0
            else Direction.FLAT
        )
        experiment_id = _identity(
            {
                "run_id": run.result.run_id,
                "decision_id": decision.decision_id,
                "horizon_end": to_jsonable(horizon_end),
            }
        )[:24]
        oracle = OracleOutcome(
            experiment_id=experiment_id,
            evaluation_time=decision.decided_at,
            horizon_end=horizon_end,
            start_price=start.close,
            endpoint_price=endpoint.close,
            realized_return=realized_return,
            realized_direction=realized_direction,
            maximum_favorable_excursion=max(bar.high / start.close - 1.0 for bar in path),
            maximum_adverse_excursion=min(bar.low / start.close - 1.0 for bar in path),
            provenance=OracleProvenance(
                request=HistoricalRequest(
                    instrument=provenance.request.instrument,
                    timeframe=timeframe,
                    start=decision.decided_at - timeframe.duration,
                    end=horizon_end,
                    as_of=horizon_end,
                    market=provenance.request.market,
                ),
                provider=provenance.provider,
                fetched_at=provenance.fetched_at,
                source_version=provenance.source_version,
                adapter_semantic_version=provenance.adapter_semantic_version,
                cache_key=provenance.cache_key,
                content_identity=provenance.content_identity,
            ),
            horizon_complete=True,
        )
        signed_error = (
            None
            if decision.expected_return is None
            else decision.expected_return - realized_return
        )
        bucket_start = min(int(decision.confidence * 10), 9) * 10
        evaluation = ForecastEvaluation(
            experiment_id=experiment_id,
            forecast_id=decision.decision_id,
            directional_correctness=decision.forecast_direction is realized_direction,
            forecast_direction=decision.forecast_direction,
            realized_direction=realized_direction,
            expected_return=decision.expected_return,
            realized_return=realized_return,
            absolute_return_error=None if signed_error is None else abs(signed_error),
            signed_return_error=signed_error,
            confidence=decision.confidence,
            calibration_bucket=f"{bucket_start:02d}-{bucket_start + 10:02d}%",
            evaluated_at=horizon_end,
        )
        risk = event.risk_decision
        authorization_id = (
            None if risk is None or risk.approved_order is None
            else risk.approved_order.authorization_id
        )
        evidence = DecisionEvidence(
            symbol=decision.symbol,
            asset_class="crypto",
            timeframe=decision.timeframe,
            decision_timestamp=decision.decided_at,
            market_data_content_identity=provenance.content_identity,
            market_data_version=(
                f"{provenance.provider.value}:{provenance.source_version}:"
                f"{provenance.adapter_semantic_version}"
            ),
            snapshot=snapshot,
            specialist_outputs=decision.signals,
            agent_versions=tuple(
                AgentVersion(agent_id=item.agent_id, version=item.agent_version)
                for item in decision.signals
            ),
            council_config=config.council,
            applied_weights=tuple(
                AppliedWeight(
                    agent_id=item.agent_id,
                    weight=config.council.agent_weights.get(item.agent_id, 1.0),
                )
                for item in decision.signals
            ),
            weight_generation_id=weight_generation_id,
            council_decision=decision,
            risk_policy_version=risk_policy_version,
            risk_decision=risk,
            execution_report=(
                None if authorization_id is None else executions.get(authorization_id)
            ),
            portfolio_state=event.portfolio,
            backtest_run_id=run.result.run_id,
        )
        episodes.append(
            ExperienceEpisode(
                evidence=evidence,
                truth=OutcomeTruth(
                    oracle_outcome=oracle,
                    judge_evaluation=evaluation,
                    available_at=horizon_end,
                ),
            )
        )
    return tuple(episodes)


def _episode_material(evidence: DecisionEvidence, truth: OutcomeTruth | None) -> object:
    return {"evidence": to_jsonable(evidence), "truth": to_jsonable(truth)}


def _equivalence_material(evidence: DecisionEvidence, truth: OutcomeTruth | None) -> object:
    material = dict(to_jsonable(evidence))
    material.pop("backtest_run_id")
    return {"evidence": material, "truth": to_jsonable(truth)}


def _decision_material(evidence: DecisionEvidence) -> object:
    return {
        "snapshot_id": evidence.snapshot.snapshot_id,
        "market_data_content_identity": evidence.market_data_content_identity,
        "specialist_outputs": to_jsonable(evidence.specialist_outputs),
        "agent_versions": to_jsonable(evidence.agent_versions),
        "council_config": to_jsonable(evidence.council_config),
        "applied_weights": to_jsonable(evidence.applied_weights),
        "weight_generation_id": evidence.weight_generation_id,
    }


def _identity(material: object) -> str:
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256(encoded.encode()).hexdigest()
