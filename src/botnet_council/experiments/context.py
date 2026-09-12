"""Construction of the blind, pre-cutoff forecasting context."""

from botnet_council.agents import warmup_bars
from botnet_council.agents.factory import build_agents
from botnet_council.experiments.models import (
    BlindInputProvenance,
    ExperimentContext,
    ExperimentRequest,
    duration,
)
from botnet_council.market_data import (
    Asset,
    HistoricalMarketDataProvider,
    HistoricalRequest,
    Instrument,
    Timeframe,
    historical_content_identity,
)
from botnet_council.schemas import AgentContext, MarketSnapshot, SnapshotProvenance


class InsufficientContextError(ValueError):
    pass


def instrument(symbol: str) -> Instrument:
    try:
        base, quote = symbol.split("/", maxsplit=1)
        return Instrument(base=Asset(base), quote=Asset(quote))
    except ValueError as error:
        raise ValueError(f"unsupported canonical experiment instrument {symbol!r}") from error


class ExperimentContextBuilder:
    """Owns the historical provider but returns a provider-free blind object."""

    def __init__(self, market_data: HistoricalMarketDataProvider) -> None:
        if not isinstance(market_data, HistoricalMarketDataProvider):
            raise TypeError("experiments require a historical market-data provider")
        self._market_data = market_data

    def required_context_bars(self, request: ExperimentRequest) -> int:
        agents = build_agents(request.agents)
        required = max((warmup_bars(agent, request.timeframe) for agent in agents), default=1)
        return max(required, request.context_bars or 1)

    def build(self, request: ExperimentRequest) -> ExperimentContext:
        timeframe = Timeframe(request.timeframe)
        required_bars = self.required_context_bars(request)
        historical_request = HistoricalRequest(
            instrument=instrument(request.instrument),
            timeframe=timeframe,
            start=request.evaluation_time - required_bars * timeframe.duration,
            end=request.evaluation_time,
            as_of=request.evaluation_time,
        )
        history = self._market_data.fetch_historical(historical_request)
        if history.request != historical_request or history.provider is not request.provider:
            raise ValueError("historical provider returned data for a different blind request")
        if not history.quality.coverage_complete or len(history.bars) < required_bars:
            raise InsufficientContextError("insufficient complete historical context")
        if any(bar.available_at > request.evaluation_time for bar in history.bars):
            raise RuntimeError("future market data reached the blind context builder")

        latest = history.bars[-1]
        snapshot_provenance = SnapshotProvenance(
            provider=history.provider.value,
            instrument=request.instrument,
            timeframe=request.timeframe,
            requested_start=historical_request.start,
            requested_end=historical_request.end,
            as_of=request.evaluation_time,
            fetched_at=history.fetched_at,
            latest_observation_time=latest.closed_at,
            latest_available_at=latest.available_at,
            source_version=history.source_version,
            adapter_semantic_version=history.adapter_semantic_version,
            coverage_complete=history.quality.coverage_complete,
            cache_key=history.cache_key,
        )
        snapshot = MarketSnapshot(
            symbol=request.instrument,
            timeframe=request.timeframe,
            as_of=request.evaluation_time,
            observed_at=request.evaluation_time,
            bars=history.bars,
            provenance=snapshot_provenance,
        )
        provenance = BlindInputProvenance(
            request=historical_request,
            provider=history.provider,
            fetched_at=history.fetched_at,
            source_version=history.source_version,
            adapter_semantic_version=history.adapter_semantic_version,
            cache_key=history.cache_key,
            content_identity=historical_content_identity(history),
            snapshot_id=snapshot.snapshot_id,
        )
        parameters = {} if request.random_seed is None else {"random_seed": request.random_seed}
        return ExperimentContext(
            experiment_id=request.experiment_id,
            evaluation_time=request.evaluation_time,
            snapshot=snapshot,
            agent_context=AgentContext(run_id=request.experiment_id, parameters=parameters),
            provenance=provenance,
        )


def horizon_bars(request: ExperimentRequest) -> int:
    return int(duration(request.forecast_horizon) / duration(request.timeframe))
