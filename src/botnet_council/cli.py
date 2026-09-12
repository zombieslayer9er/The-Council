"""Deterministic demo, historical download, and backtest commands."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from botnet_council.agents import (
    MeanReversionAgent,
    RegimeClassificationAgent,
    TrendAgent,
    VolatilityAgent,
)
from botnet_council.backtest import (
    AgentConfig,
    AuthoritativeBacktestRequest,
    BacktestConfig,
    BacktestEngine,
    FreqtradeBacktestEngine,
    ValidationKind,
    persist_backtest,
)
from botnet_council.config import load_config
from botnet_council.council import DeterministicCouncil
from botnet_council.execution import PaperExecutionAdapter
from botnet_council.logging import configure_logging
from botnet_council.market_data import (
    Asset,
    CachedHistoricalProvider,
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
    end = _parse_datetime(cast(str, args.end))
    start = _parse_datetime(cast(str, args.start))
    instrument = _instrument(cast(str, args.symbol))
    request = HistoricalRequest(
        instrument=instrument,
        timeframe=Timeframe(cast(str, args.timeframe)),
        start=start,
        end=end,
        as_of=end,
    )
    result = KrakenHistoricalProvider().fetch_historical(request)
    if not result.bars:
        raise LookupError("Kraken returned no committed candles for the requested range")
    cache_path = ParquetMarketDataCache(Path(cast(str, args.cache_dir))).store(result)
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


def run_backtest(args: argparse.Namespace) -> None:
    root = Path(__file__).resolve().parents[2]
    app_config = load_config(root / "config" / "default.toml")
    configure_logging(app_config.logging.level, app_config.logging.json_logs)
    timeframe = Timeframe(cast(str, args.timeframe))
    validity_seconds = int(timeframe.duration.total_seconds())
    instrument = cast(str, args.instrument)
    risk = app_config.risk.model_copy(
        update={
            "allowed_symbols": (instrument,),
            "max_signal_age_seconds": validity_seconds,
            "max_observation_age_seconds": validity_seconds,
            "order_validity_seconds": validity_seconds,
        }
    )
    agent_names = tuple(name.strip() for name in cast(str, args.agents).split(",") if name.strip())
    config = BacktestConfig(
        instrument=instrument,
        timeframe=timeframe.value,
        start=cast(datetime, args.start),
        end=cast(datetime, args.end),
        starting_cash=cast(float, args.starting_cash),
        fee_bps=cast(float, args.fee_bps),
        slippage_bps=cast(float, args.slippage_bps),
        agents=tuple(AgentConfig(kind=cast(Any, name), parameters={}) for name in agent_names),
        council=app_config.council,
        risk=risk,
    )
    provider = CachedHistoricalProvider(
        KrakenHistoricalProvider(),
        ParquetMarketDataCache(root / ".market-data-cache"),
    )
    run = BacktestEngine(provider).run(config)
    destination = persist_backtest(run, config, root / cast(str, args.output))
    metrics = run.result.metrics
    print(f"run_id={run.result.run_id}")
    print(f"interval={config.start.isoformat()}..{config.end.isoformat()}")
    print(f"agents={','.join(agent_names)}")
    print(f"starting_equity={metrics.starting_equity:.2f}")
    print(f"ending_equity={metrics.ending_equity:.2f}")
    print(f"total_return={metrics.total_return:.6%}")
    print(f"benchmark_return={run.result.benchmark.total_return:.6%}")
    print(f"maximum_drawdown={metrics.maximum_drawdown:.6%}")
    print(f"trades={metrics.number_of_trades}")
    print(f"fees={metrics.total_fees:.2f}")
    print(f"data_quality={run.result.data_quality_status}")
    print(f"output={destination}")
    print("profitability is not evidence of strategy quality")


def run_freqtrade(args: argparse.Namespace) -> None:
    request_path = Path(cast(str, args.request))
    request = AuthoritativeBacktestRequest.model_validate_json(
        request_path.read_text(encoding="utf-8")
    )
    engine = FreqtradeBacktestEngine(executable=cast(str, args.executable))
    if args.validation is None:
        print(engine.run(request).model_dump_json(indent=2))
    else:
        kind = ValidationKind(cast(str, args.validation))
        print(engine.validate(request, kind).model_dump_json(indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(prog="botnet-council")
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
    backtest = subparsers.add_parser("backtest", help="run a deterministic Kraken backtest")
    backtest.add_argument("--instrument", default="BTC/USD", choices=("BTC/USD", "ETH/USD"))
    backtest.add_argument(
        "--timeframe", default="1h", choices=tuple(item.value for item in Timeframe)
    )
    backtest.add_argument("--start", required=True, type=_parse_datetime)
    backtest.add_argument("--end", required=True, type=_parse_datetime)
    backtest.add_argument("--agents", default="trend,mean_reversion")
    backtest.add_argument("--starting-cash", default=100_000.0, type=float)
    backtest.add_argument("--fee-bps", default=1.0, type=float)
    backtest.add_argument("--slippage-bps", default=2.0, type=float)
    backtest.add_argument("--output", default="backtest-results")
    freqtrade = subparsers.add_parser(
        "freqtrade-backtest",
        help="run an authoritative Freqtrade backtest from a strict JSON request",
    )
    freqtrade.add_argument("--request", required=True, help="path to the request JSON")
    freqtrade.add_argument("--executable", default="freqtrade")
    freqtrade.add_argument(
        "--validation", choices=tuple(item.value for item in ValidationKind)
    )
    args = parser.parse_args()
    if args.command == "download-market-data":
        download_market_data(args)
    elif args.command == "backtest":
        run_backtest(args)
    elif args.command == "freqtrade-backtest":
        run_freqtrade(args)
    else:
        run_demo()


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamps must include a timezone")
    return parsed.astimezone(UTC)


def _instrument(symbol: str) -> Instrument:
    base, quote = symbol.split("/", maxsplit=1)
    return Instrument(base=Asset(base), quote=Asset(quote))


if __name__ == "__main__":
    main()
