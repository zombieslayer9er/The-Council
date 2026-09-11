"""Deterministic demo plus an explicit, read-only historical download command."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from pathlib import Path

from botnet_council.agents import (
    MeanReversionAgent,
    RegimeClassificationAgent,
    TrendAgent,
    VolatilityAgent,
)
from botnet_council.config import load_config
from botnet_council.council import DeterministicCouncil
from botnet_council.execution import PaperExecutionAdapter
from botnet_council.logging import configure_logging
from botnet_council.market_data import (
    Asset,
    HistoricalRequest,
    InMemoryMarketDataProvider,
    Instrument,
    KrakenHistoricalProvider,
    ParquetMarketDataCache,
    Timeframe,
)
from botnet_council.pipeline import ResearchTradingPipeline
from botnet_council.risk import DeterministicRiskGovernor
from botnet_council.schemas import (
    MarketBar,
    MarketSnapshot,
    OpeningPriceObservation,
    SnapshotProvenance,
)


def run_demo() -> None:
    root = Path(__file__).resolve().parents[2]
    config = load_config(root / "config" / "default.toml")
    configure_logging(config.logging.level, config.logging.json_logs)
    now = datetime.now(UTC).replace(microsecond=0)
    bars = tuple(
        MarketBar(
            opened_at=now - timedelta(minutes=5 * (30 - index)),
            closed_at=now - timedelta(minutes=5 * (29 - index)),
            available_at=now - timedelta(minutes=5 * (29 - index)),
            open=100 + index,
            high=101.5 + index,
            low=99.5 + index,
            close=101 + index,
            volume=1_000 + index,
        )
        for index in range(30)
    )
    snapshot = MarketSnapshot(
        symbol="DEMO/USD", timeframe="5m", as_of=now, observed_at=now, bars=bars
    )
    execution = PaperExecutionAdapter(
        config.execution.starting_cash,
        opened_at=now,
        slippage_bps=config.execution.slippage_bps,
        fee_bps=config.execution.fee_bps,
    )
    pipeline = ResearchTradingPipeline(
        InMemoryMarketDataProvider({(snapshot.symbol, snapshot.timeframe): snapshot}),
        (TrendAgent(), MeanReversionAgent(), VolatilityAgent(), RegimeClassificationAgent()),
        DeterministicCouncil(config.council),
        DeterministicRiskGovernor(config.risk),
        execution,
    )
    opening = OpeningPriceObservation(
        symbol=snapshot.symbol,
        timeframe=snapshot.timeframe,
        price=snapshot.last_price,
        bar_opened_at=now,
        observed_at=now,
    )
    result = pipeline.run(snapshot.symbol, snapshot.timeframe, "demo", now, opening_price=opening)
    print(
        f"council={result.council_decision.forecast_direction.value} "
        f"risk={result.risk_decision.status.value} "
        f"execution={result.execution_report.status.value if result.execution_report else 'none'}"
    )


def download_market_data(args: argparse.Namespace) -> None:
    end = datetime.fromisoformat(args.end.replace("Z", "+00:00")).astimezone(UTC)
    start = datetime.fromisoformat(args.start.replace("Z", "+00:00")).astimezone(UTC)
    base, quote = args.symbol.split("/", maxsplit=1)
    instrument = Instrument(base=Asset(base), quote=Asset(quote))
    request = HistoricalRequest(
        instrument=instrument,
        timeframe=Timeframe(args.timeframe),
        start=start,
        end=end,
        as_of=end,
    )
    result = KrakenHistoricalProvider().fetch_historical(request)
    if not result.bars:
        raise LookupError("Kraken returned no committed candles for the requested range")
    cache_path = ParquetMarketDataCache(Path(args.cache_dir)).store(result)
    latest = result.bars[-1]
    snapshot = MarketSnapshot(
        symbol=instrument.symbol,
        timeframe=request.timeframe.value,
        as_of=request.as_of,
        observed_at=request.as_of,
        bars=result.bars,
        provenance=SnapshotProvenance(
            provider=result.provider.value,
            instrument=instrument.symbol,
            timeframe=request.timeframe.value,
            requested_start=request.start,
            requested_end=request.end,
            as_of=request.as_of,
            fetched_at=result.fetched_at,
            latest_observation_time=latest.closed_at,
            latest_available_at=latest.available_at,
            source_version=result.source_version,
            adapter_semantic_version=result.adapter_semantic_version,
            coverage_complete=result.quality.coverage_complete,
            cache_key=result.cache_key,
        ),
    )
    print(
        f"downloaded={len(result.bars)} gaps={len(result.quality.gaps)} "
        f"snapshot={snapshot.snapshot_id} "
        f"latest_available_at={snapshot.latest_available_at.isoformat()} "
        f"cache={cache_path}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    download = subparsers.add_parser(
        "download-market-data", help="download committed Kraken Spot OHLC candles"
    )
    download.add_argument("--symbol", default="BTC/USD", choices=("BTC/USD", "ETH/USD"))
    download.add_argument(
        "--timeframe", default="1h", choices=tuple(item.value for item in Timeframe)
    )
    download.add_argument("--start", required=True, help="inclusive ISO-8601 UTC timestamp")
    download.add_argument("--end", required=True, help="exclusive ISO-8601 UTC cutoff")
    download.add_argument("--cache-dir", default=".market-data-cache")
    args = parser.parse_args()
    if args.command == "download-market-data":
        download_market_data(args)
    else:
        run_demo()


if __name__ == "__main__":
    main()
