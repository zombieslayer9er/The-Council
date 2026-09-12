"""Outcome-blind seeded selection and transparent batch aggregation."""

from __future__ import annotations

import json
from collections import defaultdict
from hashlib import sha256

from botnet_council.backtest.models import to_jsonable
from botnet_council.experiments.context import ExperimentContextBuilder, horizon_bars, instrument
from botnet_council.experiments.models import (
    BatchResult,
    CalibrationBucket,
    ConfigurationPerformance,
    ExperimentRecord,
    ExperimentRequest,
    ExperimentState,
    ForecastEvaluation,
    RandomExperimentRequest,
    duration,
)
from botnet_council.market_data import HistoricalMarketDataProvider, HistoricalRequest, Timeframe


class HistoricalExperimentSelector:
    """Select using only timestamps, availability, and completeness—not price values."""

    def __init__(self, market_data: HistoricalMarketDataProvider) -> None:
        self._market_data = market_data
        self._context_builder = ExperimentContextBuilder(market_data)

    def select(self, request: RandomExperimentRequest) -> tuple[ExperimentRequest, ...]:
        timeframe = Timeframe(request.template.timeframe)
        warmup = self._context_builder.required_context_bars(request.template)
        historical_request = HistoricalRequest(
            instrument=instrument(request.template.instrument),
            timeframe=timeframe,
            start=request.range_start - warmup * timeframe.duration,
            end=request.range_end + duration(request.template.forecast_horizon),
            as_of=request.range_end + duration(request.template.forecast_horizon),
        )
        history = self._market_data.fetch_historical(historical_request)
        if (
            history.request != historical_request
            or history.provider is not request.template.provider
        ):
            raise ValueError("historical provider returned data for a different selection request")
        available_closes = {bar.closed_at: bar.available_at for bar in history.bars}
        candidates = []
        for evaluation_time in sorted(available_closes):
            if not request.range_start <= evaluation_time <= request.range_end:
                continue
            context_times = tuple(
                evaluation_time - offset * timeframe.duration
                for offset in range(warmup - 1, -1, -1)
            )
            future_times = tuple(
                evaluation_time + offset * timeframe.duration
                for offset in range(1, horizon_bars(request.template) + 1)
            )
            if all(
                time in available_closes and available_closes[time] <= evaluation_time
                for time in context_times
            ) and all(
                time in available_closes and available_closes[time] <= future_times[-1]
                for time in future_times
            ):
                candidates.append(evaluation_time)
        if len(candidates) < request.samples:
            raise ValueError(
                f"only {len(candidates)} valid evaluation points are available for "
                f"{request.samples} requested samples"
            )
        selected = tuple(
            sorted(
                candidates,
                key=lambda item: sha256(
                    f"{request.seed}|{item.isoformat()}".encode()
                ).digest(),
            )[: request.samples]
        )
        return tuple(
            request.template.model_copy(
                update={"evaluation_time": selected_time, "random_seed": request.seed}
            )
            for selected_time in selected
        )


def aggregate_batch(records: tuple[ExperimentRecord, ...], seed: int) -> BatchResult:
    completed = tuple(record for record in records if record.state is ExperimentState.COMPLETE)
    if not completed:
        raise ValueError("batch contains no complete experiments")
    evaluations = tuple(record.evaluation for record in completed)
    if any(item is None for item in evaluations):
        raise RuntimeError("complete experiment is missing its evaluation")
    measured = tuple(item for item in evaluations if item is not None)
    errors = tuple(
        item.signed_return_error for item in measured if item.signed_return_error is not None
    )
    by_bucket: dict[str, list[ForecastEvaluation]] = defaultdict(list)
    for item in measured:
        by_bucket[item.calibration_bucket].append(item)
    calibration = tuple(
        CalibrationBucket(
            bucket=bucket,
            count=len(items),
            mean_confidence=sum(item.confidence for item in items) / len(items),
            directional_accuracy=sum(item.directional_correctness for item in items) / len(items),
        )
        for bucket, items in sorted(by_bucket.items())
    )
    by_configuration: dict[str, list[ExperimentRecord]] = defaultdict(list)
    for record in completed:
        by_configuration[_configuration_id(record.request)].append(record)
    configuration_performance = tuple(
        _configuration_performance(configuration_id, tuple(items))
        for configuration_id, items in sorted(by_configuration.items())
    )
    ids = tuple(record.experiment_id for record in records)
    batch_id = sha256(f"{seed}|{'|'.join(ids)}".encode()).hexdigest()[:24]
    return BatchResult(
        batch_id=batch_id,
        selection_seed=seed,
        experiment_ids=ids,
        experiment_count=len(completed),
        directional_accuracy=sum(item.directional_correctness for item in measured) / len(measured),
        mean_absolute_return_error=(
            None if not errors else sum(abs(item) for item in errors) / len(errors)
        ),
        forecast_bias=None if not errors else sum(errors) / len(errors),
        confidence_calibration=calibration,
        performance_by_configuration=configuration_performance,
    )


def _configuration_id(request: ExperimentRequest) -> str:
    material = {
        "instrument": request.instrument,
        "provider": request.provider,
        "forecast_horizon": request.forecast_horizon,
        "timeframe": request.timeframe,
        "agents": request.agents,
        "council": request.council,
        "context_bars": request.context_bars,
    }
    encoded = json.dumps(to_jsonable(material), sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode()).hexdigest()[:24]


def _configuration_performance(
    configuration_id: str, records: tuple[ExperimentRecord, ...]
) -> ConfigurationPerformance:
    evaluations = tuple(record.evaluation for record in records if record.evaluation is not None)
    errors = tuple(
        item.signed_return_error for item in evaluations if item.signed_return_error is not None
    )
    return ConfigurationPerformance(
        configuration_id=configuration_id,
        experiment_count=len(evaluations),
        directional_accuracy=sum(item.directional_correctness for item in evaluations)
        / len(evaluations),
        mean_absolute_return_error=(
            None if not errors else sum(abs(item) for item in errors) / len(errors)
        ),
        forecast_bias=None if not errors else sum(errors) / len(errors),
    )
