from datetime import datetime, timedelta

from botnet_council.agents import TrendAgent, VolatilityAgent
from botnet_council.council import CouncilConfig, DeterministicCouncil
from botnet_council.execution import PaperExecutionAdapter
from botnet_council.market_data import InMemoryMarketDataProvider
from botnet_council.pipeline import ResearchTradingPipeline
from botnet_council.risk import DeterministicRiskGovernor, RiskPolicy
from botnet_council.schemas import (
    ApprovedOrder,
    ExecutionReport,
    ExecutionStatus,
    MarketBar,
    MarketSnapshot,
    OpeningPriceObservation,
    RiskStatus,
)


class SpyPaperExecutionAdapter(PaperExecutionAdapter):
    execute_calls: int

    def __init__(self, starting_cash: float, *, opened_at: datetime) -> None:
        super().__init__(starting_cash, opened_at=opened_at)
        self.execute_calls = 0

    def execute(
        self,
        order: ApprovedOrder,
        opening_price: OpeningPriceObservation,
        *,
        submitted_at: datetime,
    ) -> ExecutionReport:
        self.execute_calls += 1
        return super().execute(order, opening_price, submitted_at=submitted_at)


def build_pipeline(
    snapshot: MarketSnapshot,
    as_of: datetime,
    policy: RiskPolicy,
    execution: PaperExecutionAdapter | None = None,
) -> tuple[ResearchTradingPipeline, PaperExecutionAdapter]:
    selected_execution = execution or PaperExecutionAdapter(
        100_000, opened_at=as_of - timedelta(days=1)
    )
    pipeline = ResearchTradingPipeline(
        InMemoryMarketDataProvider({("TEST/USD", "5m"): snapshot}),
        (TrendAgent(), VolatilityAgent()),
        DeterministicCouncil(CouncilConfig(minimum_conviction=0.01)),
        DeterministicRiskGovernor(policy),
        selected_execution,
    )
    return pipeline, selected_execution


def opening(as_of: datetime, price: float) -> OpeningPriceObservation:
    return OpeningPriceObservation(
        symbol="TEST/USD",
        timeframe="5m",
        price=price,
        bar_opened_at=as_of,
        observed_at=as_of,
    )


def test_pipeline_executes_only_after_approval(
    rising_snapshot: MarketSnapshot, as_of: datetime
) -> None:
    pipeline, _ = build_pipeline(rising_snapshot, as_of, RiskPolicy(max_realized_volatility=0.5))

    result = pipeline.run(
        "TEST/USD",
        "5m",
        "run-1",
        as_of,
        opening_price=opening(as_of, rising_snapshot.last_price),
    )

    assert result.risk_decision.status is RiskStatus.APPROVED
    assert result.execution_report is not None
    assert result.execution_report.status is ExecutionStatus.FILLED
    assert result.post_fill_reconciliation is not None
    assert result.post_fill_reconciliation.compliant is True


def test_veto_prevents_execution(rising_snapshot: MarketSnapshot, as_of: datetime) -> None:
    spy = SpyPaperExecutionAdapter(100_000, opened_at=as_of - timedelta(days=1))
    pipeline, execution = build_pipeline(
        rising_snapshot,
        as_of,
        RiskPolicy(max_realized_volatility=1e-12),
        execution=spy,
    )
    before = execution.portfolio_state()

    result = pipeline.run(
        "TEST/USD",
        "5m",
        "run-veto",
        as_of,
        opening_price=opening(as_of, rising_snapshot.last_price),
    )

    assert result.risk_decision.status is RiskStatus.VETOED
    assert result.execution_report is None
    assert spy.execute_calls == 0
    assert execution.portfolio_state().cash == before.cash
    assert execution.portfolio_state().positions == ()


def test_historical_snapshot_filters_bars_after_as_of(
    rising_snapshot: MarketSnapshot, as_of: datetime
) -> None:
    future_bar = MarketBar(
        opened_at=as_of,
        closed_at=as_of + timedelta(minutes=5),
        open=130.0,
        high=132.0,
        low=129.0,
        close=131.0,
        volume=1_000.0,
    )
    source = MarketSnapshot(
        symbol="TEST/USD",
        timeframe="5m",
        as_of=future_bar.closed_at,
        observed_at=future_bar.closed_at,
        bars=(*rising_snapshot.bars, future_bar),
    )
    provider = InMemoryMarketDataProvider({("TEST/USD", "5m"): source})

    historical = provider.snapshot("TEST/USD", "5m", as_of=as_of)

    assert historical.bars == rising_snapshot.bars
    assert all(bar.closed_at <= as_of for bar in historical.bars)
