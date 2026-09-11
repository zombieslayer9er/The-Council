"""Small deterministic paper-mode demonstration; not a live-trading CLI."""

from __future__ import annotations

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
from botnet_council.market_data import InMemoryMarketDataProvider
from botnet_council.pipeline import ResearchTradingPipeline
from botnet_council.risk import DeterministicRiskGovernor
from botnet_council.schemas import MarketBar, MarketSnapshot, OpeningPriceObservation


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    config = load_config(root / "config" / "default.toml")
    configure_logging(config.logging.level, config.logging.json_logs)
    now = datetime.now(UTC).replace(microsecond=0)
    bars = tuple(
        MarketBar(
            opened_at=now - timedelta(minutes=5 * (30 - index)),
            closed_at=now - timedelta(minutes=5 * (29 - index)),
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


if __name__ == "__main__":
    main()
