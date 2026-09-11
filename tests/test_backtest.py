from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pyarrow.parquet as pq
import pytest

import botnet_council.backtest.engine as engine_module
from botnet_council.backtest import (
    AgentConfig,
    BacktestConfig,
    BacktestEngine,
    maximum_drawdown,
    persist_backtest,
)
from botnet_council.council import CouncilConfig
from botnet_council.market_data import (
    Asset,
    HistoricalBars,
    HistoricalRequest,
    Instrument,
    ProviderId,
    ProviderMetadata,
    Timeframe,
)
from botnet_council.market_data.quality import normalize_and_assess
from botnet_council.risk import DeterministicRiskGovernor, RiskPolicy
from botnet_council.schemas import (
    ExecutionStatus,
    MarketBar,
    MarketSnapshot,
    RiskReconciliation,
    RiskStatus,
)


class StaticHistoricalProvider:
    source_version = "fixture-v1"
    adapter_semantic_version = "fixture-causal-v1"

    def __init__(self, bars: tuple[MarketBar, ...], *, fetched_at: datetime) -> None:
        self.bars = bars
        self.fetched_at = fetched_at

    @property
    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider=ProviderId.IN_MEMORY,
            display_name="test fixture",
            supported_instruments=(Instrument(base=Asset.BTC, quote=Asset.USD),),
            supported_timeframes=(Timeframe.MINUTE_5, Timeframe.MINUTE_15, Timeframe.DAY_1),
            maximum_rows=10_000,
            requires_credentials=False,
            timestamp_convention="fixture interval start/end",
            availability_convention="explicit fixture available_at",
        )

    def fetch_historical(self, request: HistoricalRequest) -> HistoricalBars:
        selected = tuple(
            bar
            for bar in self.bars
            if request.start <= bar.opened_at < request.end and bar.available_at <= request.as_of
        )
        ordered, quality = normalize_and_assess(
            selected,
            request.timeframe,
            request_start=request.start,
            request_end=request.end,
        )
        return HistoricalBars(
            provider=ProviderId.IN_MEMORY,
            request=request,
            fetched_at=self.fetched_at,
            bars=ordered,
            quality=quality,
            source_version=self.source_version,
            adapter_semantic_version=self.adapter_semantic_version,
        )

    def snapshot(self, symbol: str, timeframe: str, *, as_of: datetime) -> MarketSnapshot:
        bars = tuple(bar for bar in self.bars if bar.available_at <= as_of)
        return MarketSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            as_of=as_of,
            observed_at=as_of,
            bars=bars,
        )


def _fixture(
    prices: tuple[float, ...] = (98.0, 99.0, 100.0, 100.0, 100.0, 100.0, 100.0),
    *,
    fee_bps: float = 10.0,
    slippage_bps: float = 10.0,
) -> tuple[StaticHistoricalProvider, BacktestConfig]:
    origin = datetime(2025, 1, 1, tzinfo=UTC)
    step = timedelta(minutes=5)
    bars = tuple(
        MarketBar(
            opened_at=origin + index * step,
            closed_at=origin + (index + 1) * step,
            available_at=origin + (index + 1) * step,
            open=price,
            high=price + 1.0,
            low=price - 1.0,
            close=price,
            volume=10.0,
        )
        for index, price in enumerate(prices)
    )
    provider = StaticHistoricalProvider(bars, fetched_at=bars[-1].closed_at)
    config = BacktestConfig(
        instrument="BTC/USD",
        timeframe="5m",
        start=origin + 3 * step,
        end=origin + 6 * step,
        starting_cash=1_000.0,
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
        agents=(AgentConfig(kind="trend", parameters={"fast_window": 1, "slow_window": 2}),),
        council=CouncilConfig(minimum_confidence=0.01, minimum_conviction=0.001),
        risk=RiskPolicy(
            minimum_confidence=0.01,
            max_position_fraction=0.5,
            max_gross_exposure_fraction=0.5,
            max_order_notional=1_000.0,
            minimum_cash_reserve_fraction=0.0,
            max_realized_volatility=1.0,
            max_signal_age_seconds=300,
            max_observation_age_seconds=300,
            order_validity_seconds=300,
            max_fee_bps=fee_bps,
            max_slippage_bps=slippage_bps,
            allowed_symbols=("BTC/USD",),
        ),
        warmup_bars=3,
    )
    return provider, config


def test_identical_inputs_produce_identical_run_and_ledger() -> None:
    provider, config = _fixture()
    first = BacktestEngine(provider).run(config)
    second = BacktestEngine(provider).run(config)

    assert first.result.run_id == second.result.run_id
    assert first.ledger == second.ledger
    assert first.result.metrics == second.result.metrics
    valued_at = tuple(event.portfolio.valued_at for event in first.ledger.events)
    assert valued_at == tuple(sorted(valued_at))


def test_trend_and_trend_mean_reversion_baselines_both_run() -> None:
    provider, config = _fixture()
    trend = BacktestEngine(provider).run(config)
    combined = BacktestEngine(provider).run(
        config.model_copy(
            update={
                "agents": (
                    *config.agents,
                    AgentConfig(
                        kind="mean_reversion",
                        parameters={"window": 3, "entry_z_score": 1.0},
                    ),
                )
            }
        )
    )

    assert any(len(event.signals) == 1 for event in trend.ledger.events)
    assert any(
        {signal.agent_id for signal in event.signals} == {"trend", "mean_reversion"}
        for event in combined.ledger.events
    )


def test_seasonality_agent_runs_through_council_backtest_path() -> None:
    origin = datetime(2021, 12, 25, tzinfo=UTC)
    step = timedelta(days=1)
    bar_count = (datetime(2024, 1, 15, tzinfo=UTC) - origin).days

    def seasonal_close(closed_at: datetime) -> float:
        recurring = (
            closed_at.year in (2022, 2023)
            and closed_at.month == 1
            and closed_at.day == 12
        )
        return 110.0 if recurring else 100.0

    bars = tuple(
        MarketBar(
            opened_at=origin + index * step,
            closed_at=origin + (index + 1) * step,
            available_at=origin + (index + 1) * step,
            open=100.0,
            high=max(100.0, seasonal_close(origin + (index + 1) * step)),
            low=min(100.0, seasonal_close(origin + (index + 1) * step)),
            close=seasonal_close(origin + (index + 1) * step),
            volume=10.0,
        )
        for index in range(bar_count)
    )
    provider = StaticHistoricalProvider(bars, fetched_at=bars[-1].closed_at)
    start = datetime(2024, 1, 10, tzinfo=UTC)
    config = BacktestConfig(
        instrument="BTC/USD",
        timeframe="1d",
        start=start,
        end=start + 3 * step,
        starting_cash=1_000.0,
        agents=(
            AgentConfig(
                kind="seasonality",
                parameters={
                    "tolerance_days": 0,
                    "horizon_days": 2,
                    "prior_years": 2,
                    "minimum_independent_years": 2,
                    "minimum_confidence": 0.0,
                },
            ),
        ),
        council=CouncilConfig(minimum_confidence=0.0, minimum_conviction=0.0),
        risk=RiskPolicy(
            minimum_confidence=0.0,
            max_position_fraction=1.0,
            max_gross_exposure_fraction=1.0,
            max_order_notional=1_000.0,
            minimum_cash_reserve_fraction=0.0,
            max_realized_volatility=1.0,
            max_signal_age_seconds=86_400,
            max_observation_age_seconds=86_400,
            order_validity_seconds=86_400,
            allowed_symbols=("BTC/USD",),
        ),
    )

    first = BacktestEngine(provider).run(config)
    second = BacktestEngine(provider).run(config)
    seasonal = tuple(
        signal
        for event in first.ledger.events
        for signal in event.signals
        if signal.agent_id == "seasonality"
    )

    assert seasonal
    assert all(signal.metadata["sample_count"] == 2 for signal in seasonal)
    assert first.result.trade_count >= 1
    assert first == second


def test_normalized_cached_and_uncached_inputs_have_same_deterministic_result() -> None:
    provider, config = _fixture()
    later_fetch = StaticHistoricalProvider(
        provider.bars, fetched_at=provider.fetched_at + timedelta(days=1)
    )

    uncached = BacktestEngine(provider).run(config)
    cached = BacktestEngine(later_fetch).run(config)

    assert uncached.result.run_id == cached.result.run_id
    assert uncached.result.metrics == cached.result.metrics
    assert uncached.ledger == cached.ledger


def test_agents_see_only_available_data_and_orders_fill_at_later_open() -> None:
    provider, config = _fixture()
    run = BacktestEngine(provider).run(config)

    for event in run.ledger.events:
        if event.snapshot is not None:
            assert all(bar.available_at <= event.simulation_time for bar in event.snapshot.bars)
        for signal in event.signals:
            assert signal.generated_at == event.simulation_time
            assert event.snapshot is not None
            assert signal.source_snapshot_id == event.snapshot.snapshot_id
        if event.execution_report is not None:
            authorization = next(
                earlier.queued_order
                for earlier in run.ledger.events
                if earlier.queued_order is not None
                and earlier.queued_order.authorization_id == event.execution_report.authorization_id
            )
            assert event.execution_report.filled_at is not None
            assert event.execution_report.filled_at > authorization.authorized_at


def test_warmup_is_unmeasured_and_costs_and_independent_marks_affect_equity() -> None:
    provider, config = _fixture()
    run = BacktestEngine(provider).run(config)

    warmup = [event for event in run.ledger.events if event.simulation_time < config.start]
    assert warmup and all(not event.measured for event in warmup)
    assert all(event.execution_report is None for event in warmup)
    fills = [
        event
        for event in run.ledger.events
        if event.execution_report is not None
        and event.execution_report.status is ExecutionStatus.FILLED
    ]
    assert fills
    first = fills[0]
    position = first.portfolio.positions[0]
    assert position.mark_price == provider.bars[4].open
    assert first.execution_report is not None
    assert position.mark_price != first.execution_report.fill_price
    assert run.result.metrics.total_fees > 0
    assert run.result.metrics.slippage_cost > 0
    assert run.result.metrics.ending_equity != config.starting_cash


def test_opening_gap_mark_is_not_overwritten_by_previous_close() -> None:
    provider, config = _fixture(fee_bps=0.0, slippage_bps=0.0)
    bars = list(provider.bars)
    bars[3] = bars[3].model_copy(update={"close": 101.0, "high": 101.0})
    bars[4] = bars[4].model_copy(update={"close": 102.0, "high": 102.0})
    bars[6] = bars[6].model_copy(update={"open": 50.0, "low": 49.0, "close": 50.0})
    gap_provider = StaticHistoricalProvider(tuple(bars), fetched_at=provider.fetched_at)

    run = BacktestEngine(gap_provider).run(config)

    final_position = run.result.final_portfolio.positions[0]
    assert final_position.mark_price == 50.0
    assert run.result.final_portfolio.equity == pytest.approx(
        run.result.final_portfolio.cash + final_position.quantity * 50.0
    )
    assert run.result.final_portfolio.equity < config.starting_cash


def test_delayed_older_close_cannot_replace_newer_opening_mark() -> None:
    provider, config = _fixture()
    bars = list(provider.bars)
    opening_time = bars[4].opened_at
    delayed_time = opening_time + timedelta(minutes=1)
    bars[3] = bars[3].model_copy(update={"available_at": delayed_time})
    bars[4] = bars[4].model_copy(update={"open": 50.0, "low": 49.0, "close": 50.0})
    delayed_provider = StaticHistoricalProvider(tuple(bars), fetched_at=provider.fetched_at)

    run = BacktestEngine(delayed_provider).run(config)
    opening_event = next(
        event for event in run.ledger.events if event.simulation_time == opening_time
    )
    publication_event = next(
        event for event in run.ledger.events if event.simulation_time == delayed_time
    )

    assert opening_event.portfolio.positions[0].mark_price == 50.0
    assert publication_event.snapshot is not None
    assert publication_event.snapshot.last_price == 100.0
    assert publication_event.portfolio.positions[0].mark_price == 50.0
    assert publication_event.portfolio.equity == pytest.approx(opening_event.portfolio.equity)


def test_delayed_available_at_creates_event_without_early_visibility() -> None:
    origin = datetime(2025, 1, 1, tzinfo=UTC)
    step = timedelta(minutes=15)
    bars = tuple(
        MarketBar(
            opened_at=origin + index * step,
            closed_at=origin + (index + 1) * step,
            available_at=(
                origin + timedelta(minutes=35) if index == 0 else origin + (index + 1) * step
            ),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            volume=1.0,
        )
        for index in range(5)
    )
    provider = StaticHistoricalProvider(bars, fetched_at=origin + timedelta(hours=2))
    _, base_config = _fixture()
    config = base_config.model_copy(
        update={
            "timeframe": "15m",
            "start": origin + timedelta(minutes=45),
            "end": origin + timedelta(minutes=60),
            "risk": base_config.risk.model_copy(
                update={
                    "max_signal_age_seconds": 900,
                    "max_observation_age_seconds": 900,
                    "order_validity_seconds": 900,
                }
            ),
            "warmup_bars": 3,
        }
    )

    run = BacktestEngine(provider).run(config)
    delayed = bars[0]

    assert all(
        event.snapshot is None or delayed not in event.snapshot.bars
        for event in run.ledger.events
        if event.simulation_time < delayed.available_at
    )
    available_event = next(
        event for event in run.ledger.events if event.simulation_time == delayed.available_at
    )
    assert available_event.snapshot is not None
    assert delayed in available_event.snapshot.bars


def test_net_round_trip_loss_is_not_counted_as_gross_win() -> None:
    prices = (98.0, 99.0, 100.0, 100.0, 100.0, 100.05, 100.0)
    provider, config = _fixture(prices)

    metrics = BacktestEngine(provider).run(config).result.metrics

    assert metrics.gross_realized_pnl > 0
    assert metrics.net_realized_pnl < 0
    assert metrics.win_count == 0
    assert metrics.loss_count == 1


def test_veto_is_normal_and_produces_no_execution() -> None:
    provider, config = _fixture()
    restrictive = config.model_copy(
        update={"risk": config.risk.model_copy(update={"max_realized_volatility": 1e-12})}
    )
    run = BacktestEngine(provider).run(restrictive)

    evaluated = [event for event in run.ledger.events if event.risk_decision is not None]
    assert evaluated
    assert all(event.risk_decision.status is RiskStatus.VETOED for event in evaluated)
    assert all(event.execution_report is None for event in run.ledger.events)


def test_incomplete_coverage_fails_loudly() -> None:
    provider, config = _fixture()
    truncated = StaticHistoricalProvider(provider.bars[:-1], fetched_at=provider.fetched_at)

    with pytest.raises(ValueError, match="coverage is incomplete"):
        BacktestEngine(truncated).run(config)


def test_reconciliation_failure_aborts(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, config = _fixture()

    class FailingGovernor(DeterministicRiskGovernor):
        def reconcile(self, *args: object, **kwargs: object) -> RiskReconciliation:
            del args, kwargs
            return RiskReconciliation(
                compliant=False,
                reconciled_at=config.start + timedelta(minutes=5),
                reasons=("injected accounting mismatch",),
            )

    monkeypatch.setattr(engine_module, "DeterministicRiskGovernor", FailingGovernor)
    with pytest.raises(RuntimeError, match="reconciliation failed"):
        BacktestEngine(provider).run(config)


def test_benchmark_and_maximum_drawdown_are_hand_verifiable() -> None:
    provider, config = _fixture()
    run = BacktestEngine(provider).run(config)

    assert run.result.benchmark.start_price == 100.0
    assert run.result.benchmark.end_price == 100.0
    assert run.result.benchmark.total_return == 0.0
    assert maximum_drawdown((100.0, 120.0, 90.0, 108.0)) == pytest.approx(0.25)


def test_parquet_persistence_is_reproducible(tmp_path: Path) -> None:
    provider, config = _fixture()
    run = BacktestEngine(provider).run(config)

    destination = persist_backtest(run, config, tmp_path)
    second = persist_backtest(run, config, tmp_path)

    assert second == destination
    assert (destination / "summary.json").is_file()
    assert pq.read_table(destination / "events.parquet").num_rows == len(run.ledger.events)
    assert pq.read_table(destination / "equity.parquet").num_rows == len(run.ledger.events)
