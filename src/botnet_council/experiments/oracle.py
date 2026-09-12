"""Post-lock oracle access; this module is never imported by forecasting code."""

from botnet_council.experiments.context import horizon_bars, instrument
from botnet_council.experiments.models import (
    ExperimentRequest,
    OracleOutcome,
    OracleProvenance,
)
from botnet_council.market_data import (
    HistoricalMarketDataProvider,
    HistoricalRequest,
    Timeframe,
    historical_content_identity,
)
from botnet_council.schemas import Direction


class HistoricalOracle:
    def __init__(self, market_data: HistoricalMarketDataProvider) -> None:
        if not isinstance(market_data, HistoricalMarketDataProvider):
            raise TypeError("oracle requires a historical market-data provider")
        self._market_data = market_data

    def outcome(self, request: ExperimentRequest) -> OracleOutcome:
        timeframe = Timeframe(request.timeframe)
        historical_request = HistoricalRequest(
            instrument=instrument(request.instrument),
            timeframe=timeframe,
            start=request.evaluation_time - timeframe.duration,
            end=request.horizon_end,
            as_of=request.horizon_end,
        )
        history = self._market_data.fetch_historical(historical_request)
        if history.request != historical_request or history.provider is not request.provider:
            raise ValueError("historical provider returned data for a different oracle request")
        provenance = OracleProvenance(
            request=historical_request,
            provider=history.provider,
            fetched_at=history.fetched_at,
            source_version=history.source_version,
            adapter_semantic_version=history.adapter_semantic_version,
            cache_key=history.cache_key,
            content_identity=historical_content_identity(history),
        )
        by_close = {bar.closed_at: bar for bar in history.bars}
        start = by_close.get(request.evaluation_time)
        endpoint = by_close.get(request.horizon_end)
        path = tuple(
            bar
            for bar in history.bars
            if request.evaluation_time < bar.closed_at <= request.horizon_end
        )
        complete = (
            history.quality.coverage_complete
            and start is not None
            and endpoint is not None
            and len(path) == horizon_bars(request)
            and all(bar.available_at <= request.horizon_end for bar in path)
        )
        if not complete or start is None or endpoint is None:
            return OracleOutcome(
                experiment_id=request.experiment_id,
                evaluation_time=request.evaluation_time,
                horizon_end=request.horizon_end,
                provenance=provenance,
                horizon_complete=False,
            )
        realized_return = endpoint.close / start.close - 1.0
        direction = (
            Direction.LONG
            if realized_return > 0
            else Direction.SHORT
            if realized_return < 0
            else Direction.FLAT
        )
        return OracleOutcome(
            experiment_id=request.experiment_id,
            evaluation_time=request.evaluation_time,
            horizon_end=request.horizon_end,
            start_price=start.close,
            endpoint_price=endpoint.close,
            realized_return=realized_return,
            realized_direction=direction,
            maximum_favorable_excursion=max(bar.high / start.close - 1.0 for bar in path),
            maximum_adverse_excursion=min(bar.low / start.close - 1.0 for bar in path),
            provenance=provenance,
            horizon_complete=True,
        )
