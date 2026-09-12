"""Conservative, post-outcome weight proposal generation."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from botnet_council.experience import ExperienceEpisode
from botnet_council.learning.models import (
    AdaptiveWeight,
    LibrarianConfig,
    WeightChange,
    WeightProfile,
    WeightProposal,
    WeightScope,
)
from botnet_council.schemas import SignalType, SignalValidity


class Librarian:
    version = "librarian-v1"

    def __init__(self, config: LibrarianConfig | None = None) -> None:
        self._config = config or LibrarianConfig()

    def propose(
        self,
        profile: WeightProfile,
        episodes: Iterable[ExperienceEpisode],
        *,
        scope: WeightScope,
        training_cutoff: datetime,
        created_at: datetime,
    ) -> WeightProposal:
        training_cutoff = _utc(training_cutoff, "training_cutoff")
        created_at = _utc(created_at, "created_at")
        eligible = tuple(
            sorted(
                (
                    item
                    for item in episodes
                    if item.truth is not None
                    and item.truth.available_at < training_cutoff
                    and item.evidence.decision_timestamp < training_cutoff
                    and _episode_matches(item, scope)
                ),
                key=lambda item: (item.evidence.decision_timestamp, item.episode_id),
            )
        )
        changes: list[WeightChange] = []
        for entry in profile.entries:
            if entry.scope != scope:
                continue
            correctness: list[bool] = []
            for item in eligible:
                assert item.truth is not None
                signal = next(
                    (
                        value
                        for value in item.evidence.specialist_outputs
                        if value.agent_id == entry.agent_id
                        and value.signal_type is SignalType.ALPHA
                        and value.validity is SignalValidity.VALID
                    ),
                    None,
                )
                if signal is not None:
                    correctness.append(
                        signal.forecast_direction is item.truth.oracle_outcome.realized_direction
                    )
            sample_count = len(correctness)
            if sample_count < self._config.minimum_samples:
                continue
            long_accuracy = sum(correctness) / sample_count
            recent_values = correctness[-self._config.recent_window :]
            recent_accuracy = sum(recent_values) / len(recent_values)
            confidence = min(1.0, sample_count / self._config.full_confidence_samples)
            maximum_delta = self._config.maximum_weight_delta * confidence
            long_target = _target_weight(long_accuracy, self._config)
            recent_target = _target_weight(recent_accuracy, self._config)
            proposed = AdaptiveWeight(
                long_term=_bounded_move(entry.weight.long_term, long_target, maximum_delta),
                recent=_bounded_move(entry.weight.recent, recent_target, maximum_delta),
                recent_mix=entry.weight.recent_mix,
            )
            if proposed == entry.weight:
                continue
            changes.append(
                WeightChange(
                    agent_id=entry.agent_id,
                    scope=scope,
                    current=entry.weight,
                    proposed=proposed,
                    sample_count=sample_count,
                    confidence=confidence,
                    long_term_accuracy=long_accuracy,
                    recent_accuracy=recent_accuracy,
                    reason=(
                        f"Observed {sum(correctness)}/{sample_count} correct historical "
                        f"directions; bounded delta to {maximum_delta:.6f}."
                    ),
                )
            )
        return WeightProposal(
            base_generation_id=profile.generation_id,
            created_at=created_at,
            training_cutoff=training_cutoff,
            training_episode_ids=tuple(item.episode_id for item in eligible),
            changes=tuple(changes),
            librarian_version=self.version,
        )


def _target_weight(accuracy: float, config: LibrarianConfig) -> float:
    target = config.target_weight_at_random + (accuracy - 0.5) * config.accuracy_weight_slope
    return max(0.0, min(4.0, target))


def _bounded_move(current: float, target: float, maximum_delta: float) -> float:
    return max(current - maximum_delta, min(current + maximum_delta, target))


def _episode_matches(episode: ExperienceEpisode, scope: WeightScope) -> bool:
    evidence = episode.evidence
    if scope.asset_class is not None and evidence.asset_class != scope.asset_class:
        return False
    if scope.symbol is not None and evidence.symbol != scope.symbol:
        return False
    if scope.regime is not None and evidence.regime != scope.regime:
        return False
    return scope.horizon_bars is None or any(
        item.horizon_bars == scope.horizon_bars for item in evidence.specialist_outputs
    )


def _utc(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)
