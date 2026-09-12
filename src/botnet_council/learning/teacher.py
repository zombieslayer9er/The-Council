"""Deterministic held-out validation for Librarian proposals."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from math import prod
from statistics import mean, pstdev

from botnet_council.council import CouncilConfig, DeterministicCouncil
from botnet_council.experience import ExperienceEpisode
from botnet_council.learning.models import (
    EvaluationMetrics,
    MetricComparison,
    TeacherConfig,
    TeacherDecision,
    TeacherResult,
    WeightProfile,
    WeightProposal,
)
from botnet_council.learning.profiles import apply_changes, reduced_changes
from botnet_council.learning.trials import independent_trials


class Teacher:
    version = "teacher-v1"

    def __init__(self, config: TeacherConfig | None = None) -> None:
        self._config = config or TeacherConfig()

    def evaluate(
        self,
        base: WeightProfile,
        proposal: WeightProposal,
        held_out_episodes: Iterable[ExperienceEpisode],
        *,
        evaluated_at: datetime,
    ) -> TeacherResult:
        evaluated_at = _utc(evaluated_at)
        if proposal.base_generation_id != base.generation_id:
            raise ValueError("proposal does not target the supplied base profile")
        if proposal.created_at > evaluated_at:
            raise ValueError("proposal cannot be evaluated before it was created")
        episodes = independent_trials(held_out_episodes)
        if len(episodes) < self._config.minimum_held_out_episodes:
            raise ValueError("insufficient held-out episodes for Teacher evaluation")
        training_equivalence_ids = set(proposal.training_equivalence_ids)
        if not training_equivalence_ids:
            training_equivalence_ids = set(proposal.training_episode_ids)
        if any(
            item.equivalence_id in training_equivalence_ids
            or item.episode_id in proposal.training_episode_ids
            for item in episodes
        ):
            raise ValueError("held-out episodes overlap training episodes")
        if any(item.evidence.decision_timestamp < proposal.training_cutoff for item in episodes):
            raise ValueError("held-out decisions must not precede the training cutoff")
        if any(item.truth is None for item in episodes):
            raise ValueError("Teacher requires judged held-out outcomes")
        if any(
            item.truth is not None and item.truth.available_at > evaluated_at for item in episodes
        ):
            raise ValueError("Teacher cannot use truth unavailable at evaluation time")
        baseline = evaluate_profile(base, episodes, self._config)
        if baseline.episode_count < self._config.minimum_held_out_episodes:
            raise ValueError(
                "insufficient non-overlapping held-out episodes for Teacher evaluation"
            )
        proposed_profile = apply_changes(
            base,
            proposal.changes,
            created_at=evaluated_at,
            scoring_version=self._config.scoring_version,
        )
        proposed = evaluate_profile(proposed_profile, episodes, self._config)
        if _passes(baseline, proposed, self._config) and proposal.changes:
            decision = TeacherDecision.ACCEPT
            accepted = proposal.changes
            comparison = MetricComparison(baseline=baseline, proposed=proposed)
            reasons = ("Proposed profile improved held-out score within robustness bounds.",)
        else:
            reduced = reduced_changes(proposal.changes)
            reduced_profile = apply_changes(
                base,
                reduced,
                created_at=evaluated_at,
                scoring_version=self._config.scoring_version,
            )
            reduced_metrics = evaluate_profile(reduced_profile, episodes, self._config)
            if reduced and _passes(baseline, reduced_metrics, self._config):
                decision = TeacherDecision.ACCEPT_REDUCED_UPDATE
                accepted = reduced
                comparison = MetricComparison(baseline=baseline, proposed=reduced_metrics)
                reasons = (
                    "Full update failed held-out criteria; half-sized update passed.",
                )
            else:
                decision = TeacherDecision.REJECT
                accepted = ()
                comparison = MetricComparison(baseline=baseline, proposed=proposed)
                reasons = (_rejection_reason(baseline, proposed, self._config),)
        return TeacherResult(
            decision=decision,
            base_generation_id=base.generation_id,
            proposal_id=proposal.proposal_id,
            held_out_episode_ids=tuple(item.episode_id for item in episodes),
            comparison=comparison,
            accepted_changes=accepted,
            reasons=reasons,
            evaluated_at=evaluated_at,
            teacher_version=self.version,
            scoring_version=self._config.scoring_version,
        )


def evaluate_profile(
    profile: WeightProfile,
    episodes: tuple[ExperienceEpisode, ...],
    config: TeacherConfig,
) -> EvaluationMetrics:
    returns: list[float] = []
    benchmark_returns: list[float] = []
    correctness: list[float] = []
    calibration_errors: list[float] = []
    exposures: list[float] = []
    last_exit: datetime | None = None
    for episode in sorted(
        episodes, key=lambda item: (item.evidence.decision_timestamp, item.episode_id)
    ):
        truth = episode.truth
        if truth is None or truth.oracle_outcome.realized_return is None:
            raise ValueError("profile evaluation requires complete realized returns")
        evidence = episode.evidence
        if last_exit is not None and evidence.decision_timestamp < last_exit:
            continue
        last_exit = truth.oracle_outcome.horizon_end
        weights = {
            signal.agent_id: _resolved_agent_weight(
                profile,
                signal.agent_id,
                evidence.asset_class,
                evidence.symbol,
                evidence.regime,
                signal.horizon_bars,
            )
            for signal in evidence.specialist_outputs
        }
        council = CouncilConfig(
            agent_weights=weights,
            minimum_confidence=evidence.council_config.minimum_confidence,
            minimum_conviction=evidence.council_config.minimum_conviction,
        )
        decision = DeterministicCouncil(council).aggregate(
            evidence.snapshot, evidence.specialist_outputs
        )
        exposure = decision.target_exposure or 0.0
        realized = truth.oracle_outcome.realized_return
        returns.append(exposure * realized)
        benchmark_returns.append(realized)
        actual_direction = truth.oracle_outcome.realized_direction
        correct = float(decision.forecast_direction is actual_direction)
        correctness.append(correct)
        calibration_errors.append(abs(decision.confidence - correct))
        exposures.append(exposure)
    turnover = sum(
        abs(current - previous)
        for previous, current in zip((0.0, *exposures[:-1]), exposures, strict=True)
    )
    total_return = prod(1.0 + value for value in returns) - 1.0
    benchmark_return = prod(1.0 + value for value in benchmark_returns) - 1.0
    cost_adjusted = total_return - turnover * config.turnover_cost_bps / 10_000
    drawdown = _maximum_drawdown(returns)
    volatility = pstdev(returns) if len(returns) > 1 else 0.0
    risk_adjusted = max(-10.0, min(10.0, mean(returns) / max(volatility, 1e-12)))
    worst_slice = min(_slice_returns(returns))
    values: Mapping[str, float] = {
        "total_return": total_return,
        "benchmark_relative_return": total_return - benchmark_return,
        "maximum_drawdown": drawdown,
        "hit_rate": mean(correctness),
        "mean_calibration_error": mean(calibration_errors),
        "risk_adjusted_return": risk_adjusted,
        "cost_adjusted_return": cost_adjusted,
        "worst_slice_return": worst_slice,
    }
    score = sum(values[name] * weight for name, weight in config.metric_weights.items())
    return EvaluationMetrics(
        episode_count=len(returns),
        total_return=total_return,
        benchmark_relative_return=values["benchmark_relative_return"],
        maximum_drawdown=drawdown,
        hit_rate=values["hit_rate"],
        mean_calibration_error=values["mean_calibration_error"],
        risk_adjusted_return=risk_adjusted,
        turnover=turnover,
        cost_adjusted_return=cost_adjusted,
        worst_slice_return=worst_slice,
        score=score,
    )


def _resolved_agent_weight(
    profile: WeightProfile,
    agent_id: str,
    asset_class: str | None,
    symbol: str,
    regime: str | None,
    horizon_bars: int,
) -> float:
    return profile.resolve(
        asset_class=asset_class,
        symbol=symbol,
        regime=regime,
        horizon_bars=horizon_bars,
    ).get(agent_id, 1.0)


def _maximum_drawdown(returns: list[float]) -> float:
    equity = 1.0
    peak = 1.0
    maximum = 0.0
    for value in returns:
        equity *= 1.0 + value
        peak = max(peak, equity)
        maximum = max(maximum, 0.0 if peak == 0 else (peak - equity) / peak)
    return maximum


def _slice_returns(returns: list[float]) -> tuple[float, ...]:
    if not returns:
        return ()
    count = min(3, len(returns))
    size, remainder = divmod(len(returns), count)
    slices: list[float] = []
    offset = 0
    for index in range(count):
        end = offset + size + int(index < remainder)
        slices.append(prod(1.0 + value for value in returns[offset:end]) - 1.0)
        offset = end
    return tuple(slices)


def _passes(
    baseline: EvaluationMetrics, proposed: EvaluationMetrics, config: TeacherConfig
) -> bool:
    return (
        proposed.score >= baseline.score + config.minimum_score_improvement
        and proposed.worst_slice_return
        >= baseline.worst_slice_return - config.maximum_worst_slice_degradation
    )


def _rejection_reason(
    baseline: EvaluationMetrics, proposed: EvaluationMetrics, config: TeacherConfig
) -> str:
    if (
        proposed.worst_slice_return
        < baseline.worst_slice_return - config.maximum_worst_slice_degradation
    ):
        return "Proposed profile caused excessive degradation in an older validation slice."
    return "Proposed profile did not improve the deterministic held-out score enough."


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("evaluated_at must be timezone-aware")
    return value.astimezone(UTC)
