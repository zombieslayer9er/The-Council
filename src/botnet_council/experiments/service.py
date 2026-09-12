"""Experiment application service and the enforced blind-to-oracle handoff."""

from botnet_council.experiments.batch import HistoricalExperimentSelector, aggregate_batch
from botnet_council.experiments.context import ExperimentContextBuilder
from botnet_council.experiments.evaluation import evaluate
from botnet_council.experiments.forecasting import BlindForecaster
from botnet_council.experiments.lifecycle import transition
from botnet_council.experiments.models import (
    BatchResult,
    ExperimentRecord,
    ExperimentRequest,
    ExperimentState,
    Forecast,
    ForecastEvaluation,
    LifecycleEvent,
    OracleOutcome,
    RandomExperimentRequest,
)
from botnet_council.experiments.oracle import HistoricalOracle
from botnet_council.experiments.persistence import ExperimentRepository
from botnet_council.market_data import HistoricalMarketDataProvider


class ExperimentService:
    def __init__(
        self,
        market_data: HistoricalMarketDataProvider,
        repository: ExperimentRepository,
    ) -> None:
        self._contexts = ExperimentContextBuilder(market_data)
        self._forecaster = BlindForecaster()
        self._oracle = HistoricalOracle(market_data)
        self._selector = HistoricalExperimentSelector(market_data)
        self._repository = repository

    def create(self, request: ExperimentRequest) -> ExperimentRecord:
        try:
            existing = self._repository.get(request.experiment_id)
        except LookupError:
            existing = None
        if existing is not None:
            if existing.request != request:
                raise ValueError("experiment identity collision")
            return existing
        record = ExperimentRecord(
            experiment_id=request.experiment_id,
            request=request,
            state=ExperimentState.CREATED,
            lifecycle=(
                LifecycleEvent(
                    state=ExperimentState.CREATED,
                    occurred_at=request.evaluation_time,
                    message="experiment created",
                ),
            ),
        )
        self._repository.save(record)
        return record

    def run(self, experiment_id: str) -> ExperimentRecord:
        record = self._repository.get(experiment_id)
        if record.state in {ExperimentState.COMPLETE, ExperimentState.FAILED}:
            return record
        if record.state is not ExperimentState.CREATED:
            raise ValueError("experiment is already in progress")
        request = record.request
        try:
            context = self._contexts.build(request)
            record = transition(
                record,
                ExperimentState.CONTEXT_READY,
                request.evaluation_time,
                context=context,
            )
            self._repository.save(record)
            record = transition(record, ExperimentState.FORECASTING, request.evaluation_time)
            self._repository.save(record)
            forecast = self._forecaster.forecast(request, context)
            record = transition(
                record,
                ExperimentState.FORECAST_LOCKED,
                forecast.finalized_at,
                forecast=forecast,
            )
            self._repository.save(record)
            locked = self._repository.get(experiment_id)
            if locked.forecast != forecast or locked.state is not ExperimentState.FORECAST_LOCKED:
                raise RuntimeError("forecast lock was not durably persisted")
            record = transition(locked, ExperimentState.EVALUATING, request.horizon_end)
            self._repository.save(record)
            outcome = self._oracle.outcome(request)
            if not outcome.horizon_complete:
                record = transition(
                    record,
                    ExperimentState.FAILED,
                    request.horizon_end,
                    message="oracle horizon is incomplete",
                    oracle_outcome=outcome,
                    error="oracle horizon is incomplete",
                )
            else:
                evaluation = evaluate(forecast, outcome)
                record = transition(
                    record,
                    ExperimentState.COMPLETE,
                    evaluation.evaluated_at,
                    oracle_outcome=outcome,
                    evaluation=evaluation,
                )
        except Exception as error:
            if record.state in {ExperimentState.COMPLETE, ExperimentState.FAILED}:
                raise
            message = _safe_failure(error)
            record = transition(
                record,
                ExperimentState.FAILED,
                request.evaluation_time,
                message=message,
                error=message,
            )
        self._repository.save(record)
        return record

    def get(self, experiment_id: str) -> ExperimentRecord:
        return self._repository.get(experiment_id)

    def list(self) -> tuple[ExperimentRecord, ...]:
        return self._repository.list()

    def forecast(self, experiment_id: str) -> Forecast:
        record = self.get(experiment_id)
        if record.forecast is None:
            raise LookupError("forecast is not locked")
        return record.forecast

    def oracle_outcome(self, experiment_id: str) -> OracleOutcome:
        record = self.get(experiment_id)
        if record.state in {
            ExperimentState.CREATED,
            ExperimentState.CONTEXT_READY,
            ExperimentState.FORECASTING,
        }:
            raise PermissionError("oracle outcome is hidden until FORECAST_LOCKED")
        if record.oracle_outcome is None:
            raise LookupError("oracle outcome is not available")
        return record.oracle_outcome

    def evaluation(self, experiment_id: str) -> ForecastEvaluation:
        record = self.get(experiment_id)
        if record.evaluation is None:
            raise LookupError("evaluation is not available")
        return record.evaluation

    def run_random_batch(self, request: RandomExperimentRequest) -> BatchResult:
        selected = self._selector.select(request)
        records = tuple(self.run(self.create(item).experiment_id) for item in selected)
        return aggregate_batch(records, request.seed)


def _safe_failure(error: Exception) -> str:
    known = {
        "insufficient complete historical context",
        "oracle horizon is incomplete",
    }
    message = str(error)
    return message if message in known else "experiment run failed"
