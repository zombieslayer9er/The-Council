"""Deterministic event-driven replay through agents, council, risk, and paper execution."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from hashlib import sha256
from math import isclose
from typing import Any, cast

from botnet_council.agents import SpecialistAgent, warmup_bars
from botnet_council.agents._math import timeframe_delta
from botnet_council.agents.factory import build_agents
from botnet_council.backtest.metrics import maximum_drawdown
from botnet_council.backtest.models import (
    BacktestConfig,
    BacktestDataProvenance,
    BacktestEvent,
    BacktestLedger,
    BacktestResult,
    BacktestRun,
    BenchmarkMetrics,
    OrderLifecycleRecord,
    OrderLifecycleStatus,
    PerformanceMetrics,
)
from botnet_council.council import DeterministicCouncil
from botnet_council.execution import PaperExecutionAdapter
from botnet_council.market_data import (
    Asset,
    HistoricalMarketDataProvider,
    HistoricalRequest,
    InMemoryMarketDataProvider,
    Instrument,
    Timeframe,
    historical_content_identity,
)
from botnet_council.risk import DeterministicRiskGovernor
from botnet_council.schemas import (
    ActionIntent,
    AgentContext,
    AgentSignal,
    ApprovedOrder,
    ExecutionStatus,
    MarketSnapshot,
    OpeningPriceObservation,
    OrderSide,
    PortfolioState,
    PriceObservation,
    RiskStatus,
)
from botnet_council.telemetry.contracts import (
    BacktestPayload,
    EventType,
    StagePayload,
    TelemetryPayload,
)
from botnet_council.telemetry.events import event as telemetry_event
from botnet_council.telemetry.publisher import EventPublisher, safe_publish
from botnet_council.telemetry.serializers import (
    agent_signal as serialize_agent_signal,
)
from botnet_council.telemetry.serializers import (
    approved_order as serialize_approved_order,
)
from botnet_council.telemetry.serializers import (
    council_decision as serialize_council_decision,
)
from botnet_council.telemetry.serializers import (
    execution_report as serialize_execution_report,
)
from botnet_council.telemetry.serializers import portfolio as serialize_portfolio
from botnet_council.telemetry.serializers import (
    reconciliation as serialize_reconciliation,
)
from botnet_council.telemetry.serializers import (
    risk_decision as serialize_risk_decision,
)
from botnet_council.telemetry.serializers import snapshot as serialize_snapshot


class BacktestEngine:
    def __init__(
        self,
        market_data: HistoricalMarketDataProvider,
        telemetry: EventPublisher | None = None,
    ) -> None:
        if not isinstance(market_data, HistoricalMarketDataProvider):
            raise TypeError("backtests require a historical market-data provider")
        self._market_data = market_data
        self._telemetry = telemetry

    def run(self, config: BacktestConfig) -> BacktestRun:
        agents = _build_agents(config)
        delta = timeframe_delta(config.timeframe)
        required_warmup = max(
            (warmup_bars(agent, config.timeframe) for agent in agents), default=0
        )
        effective_warmup = max(required_warmup, config.warmup_bars or 0)
        history_start = config.start - effective_warmup * delta
        # The extra bar exposes only its opening at evaluation_end. Its later fields
        # are never placed in a snapshot during this run.
        history_end = config.end + delta
        instrument = _instrument(config.instrument)
        timeframe = Timeframe(config.timeframe)
        request = HistoricalRequest(
            instrument=instrument,
            timeframe=timeframe,
            start=history_start,
            end=history_end,
            as_of=history_end,
        )
        history = self._market_data.fetch_historical(request)
        if history.request != request:
            raise ValueError("historical provider returned data for a different request")
        if not history.quality.coverage_complete:
            raise ValueError("historical coverage is incomplete for the required replay range")
        if not any(bar.opened_at == config.start for bar in history.bars):
            raise ValueError("evaluation start must align with a market bar opening")
        if not any(bar.opened_at == config.end for bar in history.bars):
            raise ValueError("evaluation end requires its causally valid opening observation")

        replay = _replay_provider(config, history.bars, history_end)
        content_identity = historical_content_identity(history)
        run_id = sha256(f"{config.identity}|{content_identity}".encode()).hexdigest()
        self._emit(
            EventType.BACKTEST_STARTED,
            run_id,
            config.start,
            BacktestPayload(status="started"),
            config,
        )
        execution = PaperExecutionAdapter(
            config.starting_cash,
            opened_at=history.bars[0].opened_at,
            slippage_bps=config.slippage_bps,
            fee_bps=config.fee_bps,
        )
        council = DeterministicCouncil(config.council)
        governor = DeterministicRiskGovernor(config.risk)

        opening_by_time = {bar.opened_at: bar.open for bar in history.bars}
        event_times = tuple(
            sorted(
                {time for time in opening_by_time if time <= config.end}
                | {bar.available_at for bar in history.bars if bar.available_at <= config.end}
                | {config.end}
            )
        )
        if any(
            current <= previous
            for previous, current in zip(event_times, event_times[1:], strict=False)
        ):
            raise RuntimeError("simulation time is not strictly monotonic")

        pending: ApprovedOrder | None = None
        events: list[BacktestEvent] = []
        outcomes = _RoundTripOutcomes()
        total_fees = 0.0
        slippage_cost = 0.0
        turnover_notional = 0.0
        equity_curve: list[float] = [config.starting_cash]
        exposure_samples: list[float] = []
        latest_market_mark: _MarketMark | None = None

        for simulation_time in event_times:
            lifecycle: list[OrderLifecycleRecord] = []
            report = None
            reconciliation = None
            current_open = opening_by_time.get(simulation_time)
            if pending is not None and current_open is not None:
                if simulation_time <= pending.authorized_at:
                    raise RuntimeError("queued order encountered a non-future opening")
                before_fill = execution.portfolio_state()
                opening = OpeningPriceObservation(
                    symbol=config.instrument,
                    timeframe=config.timeframe,
                    price=current_open,
                    bar_opened_at=simulation_time,
                    observed_at=simulation_time,
                )
                executing_order = pending
                self._emit(
                    EventType.EXECUTION_STARTED,
                    run_id,
                    simulation_time,
                    StagePayload(
                        stage="execution",
                        decision_id=executing_order.decision_id,
                        order_id=executing_order.authorization_id,
                    ),
                    config,
                    source_snapshot_id=executing_order.source_snapshot_id,
                    correlation_id=executing_order.decision_id,
                )
                report = execution.execute(pending, opening, submitted_at=pending.authorized_at)
                self._emit(
                    EventType.EXECUTION_REPORT_EMITTED,
                    run_id,
                    simulation_time,
                    partial(serialize_execution_report, report, executing_order),
                    config,
                    source_snapshot_id=executing_order.source_snapshot_id,
                    correlation_id=executing_order.decision_id,
                )
                status = (
                    OrderLifecycleStatus.FILLED
                    if report.status is ExecutionStatus.FILLED
                    else OrderLifecycleStatus.REJECTED
                )
                lifecycle.append(_lifecycle(status, simulation_time, pending, report.message))
                if report.status is ExecutionStatus.FILLED:
                    after_fill = execution.portfolio_state()
                    reconciliation = governor.reconcile(pending, report, before_fill, after_fill)
                    self._emit(
                        EventType.RECONCILIATION_COMPLETED,
                        run_id,
                        simulation_time,
                        partial(serialize_reconciliation, reconciliation, executing_order),
                        config,
                        source_snapshot_id=executing_order.source_snapshot_id,
                        correlation_id=executing_order.decision_id,
                    )
                    if not reconciliation.compliant:
                        raise RuntimeError(
                            "post-fill reconciliation failed: " + "; ".join(reconciliation.reasons)
                        )
                    fill_price = cast(float, report.fill_price)
                    fill_slippage = report.quantity * abs(fill_price - opening.price)
                    outcomes.apply(
                        pending,
                        market_price=opening.price,
                        fee=report.fee,
                        slippage_cost=fill_slippage,
                    )
                    total_fees += report.fee
                    slippage_cost += fill_slippage
                    turnover_notional += report.quantity * fill_price
                pending = None

            snapshot = _snapshot_or_none(replay, config, simulation_time)
            if snapshot is not None and any(
                bar.available_at > simulation_time for bar in snapshot.bars
            ):
                raise RuntimeError("future observation reached the replay snapshot")
            if snapshot is not None:
                self._emit(
                    EventType.SNAPSHOT_CREATED,
                    run_id,
                    simulation_time,
                    partial(serialize_snapshot, snapshot),
                    config,
                    source_snapshot_id=snapshot.snapshot_id,
                )
            latest_market_mark = _select_latest_market_mark(
                latest_market_mark,
                snapshot=snapshot,
                simulation_time=simulation_time,
                opening_price=current_open,
                symbol=config.instrument,
            )
            portfolio = _mark(execution, latest_market_mark, simulation_time)
            self._emit(
                EventType.PORTFOLIO_UPDATED,
                run_id,
                simulation_time,
                partial(serialize_portfolio, portfolio),
                config,
                source_snapshot_id=None if snapshot is None else snapshot.snapshot_id,
            )
            signals: tuple[AgentSignal, ...] = ()
            decision = None
            risk_decision = None
            queued_order = None
            measured = config.start <= simulation_time <= config.end
            if config.start <= simulation_time < config.end and snapshot is not None:
                context = AgentContext(
                    run_id=run_id,
                    parameters={"random_seed": config.random_seed},
                )
                collected: list[AgentSignal] = []
                for agent in agents:
                    self._emit(
                        EventType.AGENT_STARTED,
                        run_id,
                        simulation_time,
                        StagePayload(
                            stage="agent",
                            agent_id=agent.agent_id,
                            agent_version=getattr(agent, "agent_version", None),
                        ),
                        config,
                        source_snapshot_id=snapshot.snapshot_id,
                        correlation_id=agent.agent_id,
                    )
                    current_signal = agent.analyze(snapshot, context)
                    collected.append(current_signal)
                    self._emit(
                        EventType.AGENT_SIGNAL_EMITTED,
                        run_id,
                        simulation_time,
                        partial(serialize_agent_signal, current_signal),
                        config,
                        source_snapshot_id=snapshot.snapshot_id,
                        correlation_id=current_signal.agent_id,
                    )
                signals = tuple(collected)
                if any(signal.generated_at > simulation_time for signal in signals):
                    raise RuntimeError("agent emitted a future-dated signal")
                self._emit(
                    EventType.COUNCIL_ROUND_STARTED,
                    run_id,
                    simulation_time,
                    StagePayload(stage="council", total_agents=len(signals)),
                    config,
                    source_snapshot_id=snapshot.snapshot_id,
                )
                decision = council.aggregate(snapshot, signals)
                self._emit(
                    EventType.COUNCIL_DECISION_EMITTED,
                    run_id,
                    simulation_time,
                    partial(serialize_council_decision, decision),
                    config,
                    source_snapshot_id=snapshot.snapshot_id,
                    correlation_id=decision.decision_id,
                )
                if decision.action in (ActionIntent.TARGET_EXPOSURE, ActionIntent.REDUCE_ONLY):
                    lifecycle.append(
                        OrderLifecycleRecord(
                            status=OrderLifecycleStatus.PROPOSED,
                            occurred_at=simulation_time,
                            decision_id=decision.decision_id,
                            source_snapshot_id=snapshot.snapshot_id,
                        )
                    )
                self._emit(
                    EventType.RISK_EVALUATION_STARTED,
                    run_id,
                    simulation_time,
                    StagePayload(stage="risk", decision_id=decision.decision_id),
                    config,
                    source_snapshot_id=snapshot.snapshot_id,
                    correlation_id=decision.decision_id,
                )
                risk_decision = governor.evaluate(
                    decision, snapshot, portfolio, execution.cost_bounds, simulation_time
                )
                self._emit(
                    EventType.RISK_DECISION_EMITTED,
                    run_id,
                    simulation_time,
                    partial(serialize_risk_decision, risk_decision, decision, portfolio),
                    config,
                    source_snapshot_id=snapshot.snapshot_id,
                    correlation_id=decision.decision_id,
                )
                if risk_decision.status is RiskStatus.VETOED:
                    self._emit(
                        EventType.RISK_VETOED,
                        run_id,
                        simulation_time,
                        partial(serialize_risk_decision, risk_decision, decision, portfolio),
                        config,
                        source_snapshot_id=snapshot.snapshot_id,
                        correlation_id=decision.decision_id,
                    )
                if risk_decision.status is RiskStatus.APPROVED:
                    queued_order = risk_decision.approved_order
                    if queued_order is None:
                        raise RuntimeError("risk approval did not include an order")
                    self._emit(
                        EventType.ORDER_APPROVED,
                        run_id,
                        simulation_time,
                        partial(serialize_approved_order, queued_order),
                        config,
                        source_snapshot_id=snapshot.snapshot_id,
                        correlation_id=decision.decision_id,
                    )
                    lifecycle.extend(
                        (
                            _lifecycle(
                                OrderLifecycleStatus.AUTHORIZED,
                                simulation_time,
                                queued_order,
                                risk_decision.reasons[0],
                            ),
                            _lifecycle(
                                OrderLifecycleStatus.QUEUED,
                                simulation_time,
                                queued_order,
                                "eligible at the next strictly later opening",
                            ),
                        )
                    )
                    pending = queued_order
                elif decision.action in (
                    ActionIntent.TARGET_EXPOSURE,
                    ActionIntent.REDUCE_ONLY,
                ):
                    lifecycle.append(
                        OrderLifecycleRecord(
                            status=OrderLifecycleStatus.REJECTED,
                            occurred_at=simulation_time,
                            decision_id=decision.decision_id,
                            source_snapshot_id=snapshot.snapshot_id,
                            reason="; ".join(risk_decision.reasons),
                        )
                    )

            if measured:
                equity_curve.append(portfolio.equity)
                exposure_samples.append(
                    0.0 if portfolio.equity == 0 else portfolio.gross_exposure / portfolio.equity
                )
            events.append(
                BacktestEvent(
                    sequence=len(events),
                    simulation_time=simulation_time,
                    snapshot=snapshot,
                    signals=signals,
                    council_decision=decision,
                    risk_decision=risk_decision,
                    queued_order=queued_order,
                    execution_report=report,
                    reconciliation=reconciliation,
                    lifecycle=tuple(lifecycle),
                    portfolio=portfolio,
                    market_value=portfolio.equity - portfolio.cash,
                    gross_realized_pnl=outcomes.gross_realized_pnl,
                    net_realized_pnl=outcomes.net_realized_pnl,
                    unrealized_pnl=portfolio.unrealized_pnl,
                    cumulative_fees=total_fees,
                    cumulative_slippage_cost=slippage_cost,
                    measured=measured,
                )
            )
            self._emit(
                EventType.BACKTEST_PROGRESS,
                run_id,
                simulation_time,
                BacktestPayload(
                    status="in_progress",
                    current=len(events),
                    total=len(event_times),
                    progress=len(events) / len(event_times),
                    event_count=len(events),
                    trade_count=sum(
                        item.execution_report is not None
                        and item.execution_report.status is ExecutionStatus.FILLED
                        for item in events
                    ),
                ),
                config,
            )

        if pending is not None:
            raise RuntimeError("backtest ended with an unprocessed queued order")
        final_portfolio = execution.portfolio_state()
        start_bar = next(bar for bar in history.bars if bar.opened_at == config.start)
        end_snapshot = replay.snapshot(config.instrument, config.timeframe, as_of=config.end)
        benchmark_return = end_snapshot.last_price / start_bar.open - 1
        trade_count = sum(
            event.execution_report is not None
            and event.execution_report.status is ExecutionStatus.FILLED
            for event in events
        )
        metrics = PerformanceMetrics(
            starting_equity=config.starting_cash,
            ending_equity=final_portfolio.equity,
            total_return=final_portfolio.equity / config.starting_cash - 1,
            gross_realized_pnl=outcomes.gross_realized_pnl,
            net_realized_pnl=outcomes.net_realized_pnl,
            unrealized_pnl=final_portfolio.unrealized_pnl,
            maximum_drawdown=maximum_drawdown(tuple(equity_curve)),
            number_of_trades=trade_count,
            win_count=outcomes.win_count,
            loss_count=outcomes.loss_count,
            total_fees=total_fees,
            slippage_cost=slippage_cost,
            turnover=turnover_notional / config.starting_cash,
            average_gross_exposure=(
                sum(exposure_samples) / len(exposure_samples) if exposure_samples else 0.0
            ),
        )
        result = BacktestResult(
            run_id=run_id,
            config_identity=config.identity,
            market_data_provenance=BacktestDataProvenance(
                provider=history.provider,
                request=history.request,
                fetched_at=history.fetched_at,
                source_version=history.source_version,
                adapter_semantic_version=history.adapter_semantic_version,
                cache_key=history.cache_key,
                content_identity=content_identity,
                quality=history.quality,
            ),
            evaluation_start=config.start,
            evaluation_end=config.end,
            final_portfolio=final_portfolio,
            metrics=metrics,
            benchmark=BenchmarkMetrics(
                start_price=start_bar.open,
                end_price=end_snapshot.last_price,
                total_return=benchmark_return,
                ending_equity=config.starting_cash * (1 + benchmark_return),
            ),
            event_count=len(events),
            trade_count=trade_count,
            data_quality_status="complete",
        )
        run = BacktestRun(
            result=result, ledger=BacktestLedger(run_id=run_id, events=tuple(events))
        )
        self._emit(
            EventType.BACKTEST_COMPLETED,
            run_id,
            config.end,
            BacktestPayload(
                status="completed",
                current=len(events),
                total=len(events),
                progress=1.0,
                event_count=len(events),
                trade_count=trade_count,
            ),
            config,
        )
        return run

    def _emit(
        self,
        event_type: EventType,
        run_id: str,
        emitted_at: datetime,
        payload: TelemetryPayload | Callable[[], TelemetryPayload],
        config: BacktestConfig,
        *,
        source_snapshot_id: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        if self._telemetry is None:
            return
        try:
            resolved = payload() if callable(payload) else payload
            safe_publish(
                self._telemetry,
                telemetry_event(
                    event_type,
                    run_id=run_id,
                    emitted_at=emitted_at,
                    payload=resolved,
                    symbol=config.instrument,
                    timeframe=config.timeframe,
                    source_snapshot_id=source_snapshot_id,
                    correlation_id=correlation_id or run_id,
                ),
            )
        except Exception:
            # Observability must never change deterministic replay output.
            return


def _build_agents(config: BacktestConfig) -> tuple[SpecialistAgent, ...]:
    return build_agents(config.agents)


def _replay_provider(
    config: BacktestConfig, bars: tuple[Any, ...], history_end: datetime
) -> InMemoryMarketDataProvider:
    complete = MarketSnapshot(
        symbol=config.instrument,
        timeframe=config.timeframe,
        as_of=history_end,
        observed_at=history_end,
        bars=bars,
    )
    return InMemoryMarketDataProvider({(config.instrument, config.timeframe): complete})


def _snapshot_or_none(
    provider: InMemoryMarketDataProvider, config: BacktestConfig, simulation_time: datetime
) -> MarketSnapshot | None:
    try:
        return provider.snapshot(config.instrument, config.timeframe, as_of=simulation_time)
    except LookupError:
        return None


def _mark(
    execution: PaperExecutionAdapter,
    market_mark: _MarketMark | None,
    simulation_time: datetime,
) -> PortfolioState:
    positions = execution.portfolio_state().positions
    if positions and market_mark is None:
        raise RuntimeError("cannot mark an open position without a causal market observation")
    observations: tuple[PriceObservation, ...] = ()
    if positions and market_mark is not None:
        observations = (
            PriceObservation(
                symbol=market_mark.symbol,
                price=market_mark.price,
                observed_at=market_mark.available_at,
                source_snapshot_id=market_mark.source_id,
            ),
        )
    return execution.mark_to_market(observations, valued_at=simulation_time)


@dataclass(frozen=True, slots=True)
class _MarketMark:
    symbol: str
    price: float
    market_time: datetime
    available_at: datetime
    source_id: str


def _select_latest_market_mark(
    current: _MarketMark | None,
    *,
    snapshot: MarketSnapshot | None,
    simulation_time: datetime,
    opening_price: float | None,
    symbol: str,
) -> _MarketMark | None:
    selected = current
    if snapshot is not None:
        completed = _MarketMark(
            symbol=snapshot.symbol,
            price=snapshot.last_price,
            market_time=snapshot.latest_closed_at,
            available_at=snapshot.latest_available_at,
            source_id=snapshot.snapshot_id,
        )
        if selected is None or completed.market_time > selected.market_time:
            selected = completed
    if opening_price is not None:
        opening = _MarketMark(
            symbol=symbol,
            price=opening_price,
            market_time=simulation_time,
            available_at=simulation_time,
            source_id=f"opening:{symbol}:{simulation_time.isoformat()}",
        )
        # The opening is the newer micro-event when a completed close shares its
        # nominal timestamp, irrespective of when that close was published.
        if selected is None or opening.market_time >= selected.market_time:
            selected = opening
    return selected


def _instrument(symbol: str) -> Instrument:
    try:
        base, quote = symbol.split("/", maxsplit=1)
        return Instrument(base=Asset(base), quote=Asset(quote))
    except ValueError as error:
        raise ValueError(f"unsupported canonical backtest instrument {symbol!r}") from error


def _lifecycle(
    status: OrderLifecycleStatus,
    occurred_at: datetime,
    order: ApprovedOrder,
    reason: str,
) -> OrderLifecycleRecord:
    return OrderLifecycleRecord(
        status=status,
        occurred_at=occurred_at,
        decision_id=order.decision_id,
        source_snapshot_id=order.source_snapshot_id,
        authorization_id=order.authorization_id,
        reason=reason,
    )


@dataclass(slots=True)
class _RoundTripOutcomes:
    quantity: float = 0.0
    average_market_entry: float = 0.0
    open_costs: float = 0.0
    gross_realized_pnl: float = 0.0
    net_realized_pnl: float = 0.0
    win_count: int = 0
    loss_count: int = 0

    def apply(
        self,
        order: ApprovedOrder,
        *,
        market_price: float,
        fee: float,
        slippage_cost: float,
    ) -> None:
        signed_fill = order.quantity if order.side is OrderSide.BUY else -order.quantity
        fill_costs = fee + slippage_cost
        if self.quantity == 0 or self.quantity * signed_fill > 0:
            previous = abs(self.quantity)
            new_quantity = self.quantity + signed_fill
            self.average_market_entry = (
                previous * self.average_market_entry + order.quantity * market_price
            ) / abs(new_quantity)
            self.quantity = new_quantity
            self.open_costs += fill_costs
            return

        previous_quantity = abs(self.quantity)
        closed_quantity = min(previous_quantity, order.quantity)
        direction = 1.0 if self.quantity > 0 else -1.0
        gross = closed_quantity * (market_price - self.average_market_entry) * direction
        allocated_entry_costs = self.open_costs * closed_quantity / previous_quantity
        allocated_exit_costs = fill_costs * closed_quantity / order.quantity
        net = gross - allocated_entry_costs - allocated_exit_costs
        self.gross_realized_pnl += gross
        self.net_realized_pnl += net
        if net > 1e-12:
            self.win_count += 1
        elif net < -1e-12:
            self.loss_count += 1

        remaining = self.quantity + signed_fill
        if isclose(remaining, 0.0, abs_tol=1e-12):
            self.quantity = 0.0
            self.average_market_entry = 0.0
            self.open_costs = 0.0
        elif remaining * self.quantity > 0:
            self.quantity = remaining
            self.open_costs -= allocated_entry_costs
        else:
            opening_fraction = abs(remaining) / order.quantity
            self.quantity = remaining
            self.average_market_entry = market_price
            self.open_costs = fill_costs * opening_fraction
