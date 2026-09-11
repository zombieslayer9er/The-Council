"""Final, deterministic authority over every proposed order."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from math import isclose
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from botnet_council.agents._math import realized_volatility
from botnet_council.schemas import (
    NOTIONAL_ABS_TOLERANCE,
    QUANTITY_ABS_TOLERANCE,
    ActionIntent,
    ApprovedOrder,
    CouncilDecision,
    ExecutionCostBounds,
    ExecutionReport,
    ExecutionStatus,
    MarketSnapshot,
    ObservationStatus,
    OrderSide,
    PortfolioState,
    RiskDecision,
    RiskReconciliation,
    RiskStatus,
    SignalValidity,
)


class RiskPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    minimum_confidence: float = Field(default=0.30, ge=0, le=1, allow_inf_nan=False)
    max_position_fraction: float = Field(default=0.10, gt=0, le=1, allow_inf_nan=False)
    max_gross_exposure_fraction: float = Field(default=0.50, gt=0, le=1, allow_inf_nan=False)
    max_order_notional: float = Field(default=10_000.0, gt=0, allow_inf_nan=False)
    minimum_cash_reserve_fraction: float = Field(default=0.10, ge=0, le=1, allow_inf_nan=False)
    max_realized_volatility: float = Field(default=0.08, gt=0, allow_inf_nan=False)
    max_signal_age_seconds: int = Field(default=900, ge=0)
    max_observation_age_seconds: int = Field(default=900, ge=0)
    order_validity_seconds: int = Field(default=300, gt=0)
    max_fee_bps: float = Field(default=100.0, strict=True, ge=0, le=10_000, allow_inf_nan=False)
    max_slippage_bps: float = Field(
        default=100.0, strict=True, ge=0, le=10_000, allow_inf_nan=False
    )
    allow_shorting: bool = False
    allowed_symbols: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_limits(self) -> Self:
        if self.max_position_fraction > self.max_gross_exposure_fraction:
            raise ValueError("position limit cannot exceed gross exposure limit")
        return self


class DeterministicRiskGovernor:
    """Vetoes or produces the only order type accepted by execution adapters."""

    def __init__(self, policy: RiskPolicy) -> None:
        self._policy = policy

    def evaluate(
        self,
        decision: CouncilDecision,
        snapshot: MarketSnapshot,
        portfolio: PortfolioState,
        costs: ExecutionCostBounds,
        evaluated_at: datetime,
    ) -> RiskDecision:
        if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None:
            raise ValueError("evaluated_at must be timezone-aware")
        evaluated_at = evaluated_at.astimezone(UTC)
        reasons = self._causal_reasons(decision, snapshot, portfolio, evaluated_at)
        if reasons:
            return self._veto(evaluated_at, reasons)
        if costs.fee_bps > self._policy.max_fee_bps:
            return self._veto(evaluated_at, ["fee bound exceeds risk policy"])
        if costs.slippage_bps > self._policy.max_slippage_bps:
            return self._veto(evaluated_at, ["slippage bound exceeds risk policy"])
        if decision.action in (ActionIntent.ABSTAIN, ActionIntent.NO_ACTION):
            return self._veto(evaluated_at, [f"council intent is {decision.action.value}"])
        if decision.target_exposure is None:
            return self._veto(evaluated_at, ["actionable decision has no target exposure"])

        current = next(
            (position for position in portfolio.positions if position.symbol == decision.symbol),
            None,
        )
        current_quantity = 0.0 if current is None else current.quantity
        current_notional = current_quantity * snapshot.last_price
        target_notional = (
            decision.target_exposure * portfolio.equity * self._policy.max_position_fraction
        )
        delta_notional = target_notional - current_notional
        order_notional = min(abs(delta_notional), self._policy.max_order_notional)
        if order_notional <= NOTIONAL_ABS_TOLERANCE:
            return self._veto(evaluated_at, ["portfolio already matches the approved target"])

        side = OrderSide.BUY if delta_notional > 0 else OrderSide.SELL
        flattening = (
            abs(target_notional) <= NOTIONAL_ABS_TOLERANCE
            and current is not None
            and abs(current_notional) <= self._policy.max_order_notional + NOTIONAL_ABS_TOLERANCE
        )
        quantity = abs(current_quantity) if flattening else order_notional / snapshot.last_price
        signed_quantity = quantity if side is OrderSide.BUY else -quantity
        prospective_quantity = current_quantity + signed_quantity
        if abs(prospective_quantity) <= QUANTITY_ABS_TOLERANCE:
            prospective_quantity = 0.0
        strictly_reducing = self._strictly_reduces(current_quantity, prospective_quantity)
        if decision.action is ActionIntent.REDUCE_ONLY and not strictly_reducing:
            return self._veto(
                evaluated_at, ["reduce-only intent would not strictly reduce exposure"]
            )

        restriction_reasons = self._restriction_reasons(
            decision, snapshot, portfolio, prospective_quantity
        )
        if restriction_reasons and not strictly_reducing:
            return self._veto(evaluated_at, restriction_reasons)

        worst_fill_price = snapshot.last_price * (
            1 + costs.slippage_bps / 10_000
            if side is OrderSide.BUY
            else 1 - costs.slippage_bps / 10_000
        )
        if worst_fill_price <= 0:
            return self._veto(evaluated_at, ["slippage bound produces a non-positive fill price"])
        worst_fee = quantity * worst_fill_price * costs.fee_bps / 10_000
        cash_delta = quantity * worst_fill_price
        prospective_cash = (
            portfolio.cash - cash_delta - worst_fee
            if side is OrderSide.BUY
            else portfolio.cash + cash_delta - worst_fee
        )
        prospective_equity = (
            portfolio.equity
            + signed_quantity * snapshot.last_price
            + (prospective_cash - portfolio.cash)
        )
        prospective_symbol_notional = prospective_quantity * snapshot.last_price
        prospective_gross = (
            portfolio.gross_exposure - abs(current_notional) + abs(prospective_symbol_notional)
        )

        limit_reasons: list[str] = []
        required_cash = prospective_equity * self._policy.minimum_cash_reserve_fraction
        if prospective_cash < required_cash:
            limit_reasons.append("minimum cash reserve would be breached including costs")
        if prospective_equity <= 0:
            limit_reasons.append("worst-case execution costs would make equity non-positive")
        elif prospective_gross > prospective_equity * self._policy.max_gross_exposure_fraction:
            limit_reasons.append("maximum gross exposure would be breached including costs")
        if (
            prospective_equity > 0
            and abs(prospective_symbol_notional)
            > prospective_equity * self._policy.max_position_fraction + 1e-9
        ):
            limit_reasons.append("maximum position exposure would be breached including costs")
        if limit_reasons and not strictly_reducing:
            return self._veto(evaluated_at, limit_reasons)

        expires_at = min(
            decision.expires_at,
            evaluated_at + timedelta(seconds=self._policy.order_validity_seconds),
        )
        if expires_at < evaluated_at:
            return self._veto(evaluated_at, ["decision expired before authorization"])
        authorization_id = self._authorization_id(
            decision, side, quantity, snapshot.last_price, evaluated_at
        )
        order = ApprovedOrder(
            authorization_id=authorization_id,
            decision_id=decision.decision_id,
            source_snapshot_id=snapshot.snapshot_id,
            symbol=decision.symbol,
            timeframe=decision.timeframe,
            side=side,
            quantity=quantity,
            reference_price=snapshot.last_price,
            authorized_at=evaluated_at,
            earliest_fill_at=evaluated_at,
            expires_at=expires_at,
            max_fee_bps=costs.fee_bps,
            max_slippage_bps=costs.slippage_bps,
            reduce_only=strictly_reducing,
        )
        return RiskDecision(
            status=RiskStatus.APPROVED,
            evaluated_at=evaluated_at,
            reasons=("all deterministic risk checks passed",),
            approved_order=order,
        )

    def reconcile(
        self,
        order: ApprovedOrder,
        report: ExecutionReport,
        before: PortfolioState,
        after: PortfolioState,
    ) -> RiskReconciliation:
        reasons: list[str] = []
        if report.status is not ExecutionStatus.FILLED:
            reasons.append("execution did not fill")
        if report.authorization_id != order.authorization_id:
            reasons.append("execution report authorization does not match")
        if (report.symbol, report.side, report.quantity) != (
            order.symbol,
            order.side,
            order.quantity,
        ):
            reasons.append("execution report does not match authorized order terms")
        if report.fill_price is not None:
            direction = 1.0 if order.side is OrderSide.BUY else -1.0
            realized_slippage_bps = max(
                0.0,
                direction * (report.fill_price / order.reference_price - 1) * 10_000,
            )
            if realized_slippage_bps > order.max_slippage_bps + 1e-9:
                reasons.append("realized slippage exceeded its authorization bound")
            if not isclose(
                report.slippage_bps,
                realized_slippage_bps,
                rel_tol=1e-12,
                abs_tol=1e-9,
            ):
                reasons.append("reported slippage does not match authorization reference data")
            max_fee = report.quantity * report.fill_price * order.max_fee_bps / 10_000
            if report.fee > max_fee + 1e-9:
                reasons.append("realized fee exceeded its authorization bound")
        if report.submitted_at < order.authorized_at:
            reasons.append("submission preceded authorization")
        if report.filled_at is not None:
            if report.submitted_at > report.filled_at:
                reasons.append("fill preceded submission")
            if report.filled_at < order.earliest_fill_at:
                reasons.append("fill preceded its authorized window")
            if report.filled_at > order.expires_at:
                reasons.append("fill occurred after authorization expiry")
        if report.filled_at is not None and after.valued_at != report.filled_at:
            reasons.append("post-fill portfolio was not valued at fill time")
        before_position = next(
            (position for position in before.positions if position.symbol == order.symbol), None
        )
        after_position = next(
            (position for position in after.positions if position.symbol == order.symbol), None
        )
        before_quantity = 0.0 if before_position is None else before_position.quantity
        after_quantity = 0.0 if after_position is None else after_position.quantity
        if report.fill_price is not None:
            signed_fill = report.quantity if report.side is OrderSide.BUY else -report.quantity
            if not isclose(
                after_quantity,
                before_quantity + signed_fill,
                rel_tol=1e-12,
                abs_tol=1e-9,
            ):
                reasons.append("post-fill position quantity does not reconcile")
            cash_notional = report.quantity * report.fill_price
            expected_cash = (
                before.cash - cash_notional - report.fee
                if report.side is OrderSide.BUY
                else before.cash + cash_notional - report.fee
            )
            if not isclose(after.cash, expected_cash, rel_tol=1e-12, abs_tol=1e-9):
                reasons.append("post-fill cash does not reconcile")
        if order.reduce_only and not self._strictly_reduces(before_quantity, after_quantity):
            reasons.append("reduce-only fill did not strictly reduce exposure")
        if not order.reduce_only:
            if after.equity <= 0:
                reasons.append("post-fill equity is non-positive")
            elif after.gross_exposure > after.equity * self._policy.max_gross_exposure_fraction:
                reasons.append("post-fill gross exposure exceeds its limit")
            if after.cash < after.equity * self._policy.minimum_cash_reserve_fraction:
                reasons.append("post-fill cash reserve is below its limit")
            if order.quantity * order.reference_price > (
                self._policy.max_order_notional + NOTIONAL_ABS_TOLERANCE
            ):
                reasons.append("filled order exceeds its notional limit")
            for position in after.positions:
                if (
                    after.equity > 0
                    and abs(position.notional)
                    > after.equity * self._policy.max_position_fraction + NOTIONAL_ABS_TOLERANCE
                ):
                    reasons.append(
                        f"post-fill position exposure for {position.symbol} exceeds its limit"
                    )
                if position.quantity < -QUANTITY_ABS_TOLERANCE and not self._policy.allow_shorting:
                    reasons.append(
                        f"post-fill short position for {position.symbol} is not permitted"
                    )
            if self._policy.allowed_symbols and order.symbol not in self._policy.allowed_symbols:
                reasons.append("filled symbol is not permitted")
        return RiskReconciliation(
            compliant=not reasons,
            reconciled_at=report.filled_at or report.submitted_at,
            reasons=tuple(reasons) if reasons else ("post-fill state reconciled",),
        )

    def _causal_reasons(
        self,
        decision: CouncilDecision,
        snapshot: MarketSnapshot,
        portfolio: PortfolioState,
        evaluated_at: datetime,
    ) -> list[str]:
        reasons: list[str] = []
        if decision.symbol != snapshot.symbol or decision.timeframe != snapshot.timeframe:
            reasons.append("decision does not match market snapshot")
        if (
            decision.source_snapshot_id != snapshot.snapshot_id
            or decision.source_as_of != snapshot.as_of
        ):
            reasons.append("decision source does not match market snapshot")
        if snapshot.as_of > evaluated_at or snapshot.observed_at > evaluated_at:
            reasons.append("market snapshot is future-dated")
        observation_age = evaluated_at - snapshot.latest_closed_at
        if observation_age < timedelta(0):
            reasons.append("market observation is future-dated")
        elif observation_age > timedelta(seconds=self._policy.max_observation_age_seconds):
            reasons.append("market observation is stale")
        if portfolio.valued_at != evaluated_at:
            reasons.append("portfolio must be marked to market at the risk evaluation time")
        for position in portfolio.positions:
            mark_age = evaluated_at - position.mark_observed_at
            if mark_age < timedelta(0):
                reasons.append(f"mark for {position.symbol} is future-dated")
            elif mark_age > timedelta(seconds=self._policy.max_observation_age_seconds):
                reasons.append(f"mark for {position.symbol} is stale")
            if position.symbol == snapshot.symbol and (
                not isclose(position.mark_price, snapshot.last_price, rel_tol=1e-12)
                or position.mark_observed_at != snapshot.latest_closed_at
            ):
                reasons.append("decision-symbol position is not marked from the source snapshot")
        decision_age = evaluated_at - decision.decided_at
        if decision_age < timedelta(0):
            reasons.append("council decision is future-dated")
        elif decision_age > timedelta(seconds=self._policy.max_signal_age_seconds):
            reasons.append("council decision is stale")
        if decision.expires_at < evaluated_at:
            reasons.append("council decision has expired")
        for signal in decision.signals:
            age = evaluated_at - signal.generated_at
            if age < timedelta(0):
                reasons.append(f"signal from {signal.agent_id} is future-dated")
            elif age > timedelta(seconds=self._policy.max_signal_age_seconds):
                reasons.append(f"signal from {signal.agent_id} is stale")
            if signal.expires_at < evaluated_at:
                reasons.append(f"signal from {signal.agent_id} has expired")
            if signal.validity is SignalValidity.INVALID:
                reasons.append(f"signal from {signal.agent_id} is invalid")
            if (
                signal.source_snapshot_id != snapshot.snapshot_id
                or signal.source_as_of != snapshot.as_of
            ):
                reasons.append(f"signal from {signal.agent_id} has the wrong source snapshot")
            if signal.generated_at < snapshot.observed_at:
                reasons.append(f"signal from {signal.agent_id} predates source availability")
            if signal.volatility is not None:
                volatility_age = evaluated_at - signal.volatility.observed_at
                if volatility_age < timedelta(0):
                    reasons.append(f"volatility from {signal.agent_id} is future-dated")
                elif volatility_age > timedelta(seconds=self._policy.max_observation_age_seconds):
                    reasons.append(f"volatility from {signal.agent_id} is stale")
        return reasons

    def _restriction_reasons(
        self,
        decision: CouncilDecision,
        snapshot: MarketSnapshot,
        portfolio: PortfolioState,
        prospective_quantity: float,
    ) -> list[str]:
        reasons: list[str] = []
        if prospective_quantity < -QUANTITY_ABS_TOLERANCE and not self._policy.allow_shorting:
            reasons.append("shorting is disabled")
        if decision.confidence < self._policy.minimum_confidence:
            reasons.append("council confidence is below the risk threshold")
        if self._policy.allowed_symbols and decision.symbol not in self._policy.allowed_symbols:
            reasons.append("symbol is not permitted")
        if portfolio.equity <= 0 or portfolio.cash < 0:
            reasons.append("portfolio state is invalid")
        volatility = realized_volatility(snapshot, max(2, min(20, len(snapshot.bars))))
        observations = [volatility]
        observations.extend(
            signal.volatility for signal in decision.signals if signal.volatility is not None
        )
        valid_values = [
            observation.value
            for observation in observations
            if observation.status is ObservationStatus.VALID and observation.value is not None
        ]
        if not valid_values:
            reasons.append("realized volatility has insufficient data")
        elif max(valid_values) > self._policy.max_realized_volatility:
            reasons.append("realized volatility exceeds the configured limit")
        return reasons

    @staticmethod
    def _strictly_reduces(current_quantity: float, prospective_quantity: float) -> bool:
        if abs(current_quantity) <= QUANTITY_ABS_TOLERANCE:
            return False
        if abs(prospective_quantity) <= QUANTITY_ABS_TOLERANCE:
            return True
        return (
            current_quantity * prospective_quantity > 0
            and abs(prospective_quantity) < abs(current_quantity) - QUANTITY_ABS_TOLERANCE
        )

    @staticmethod
    def _veto(evaluated_at: datetime, reasons: list[str]) -> RiskDecision:
        return RiskDecision(
            status=RiskStatus.VETOED,
            evaluated_at=evaluated_at,
            reasons=tuple(reasons),
        )

    @staticmethod
    def _authorization_id(
        decision: CouncilDecision,
        side: OrderSide,
        quantity: float,
        price: float,
        evaluated_at: datetime,
    ) -> str:
        material = "|".join(
            (
                decision.decision_id,
                side.value,
                quantity.hex(),
                price.hex(),
                evaluated_at.isoformat(),
            )
        )
        return sha256(material.encode()).hexdigest()[:24]
