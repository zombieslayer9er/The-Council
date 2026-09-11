from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite

from botnet_council.schemas import (
    QUANTITY_ABS_TOLERANCE,
    ApprovedOrder,
    ExecutionCostBounds,
    ExecutionReport,
    ExecutionStatus,
    FillPolicy,
    OpeningPriceObservation,
    OrderSide,
    PortfolioState,
    Position,
    PriceObservation,
)


@dataclass(frozen=True, slots=True)
class _PaperPosition:
    quantity: float
    average_entry_price: float
    mark_price: float
    mark_observed_at: datetime


class PaperExecutionAdapter:
    """Atomic in-memory simulator with an explicit next-bar-open fill policy."""

    def __init__(
        self,
        starting_cash: float,
        *,
        opened_at: datetime,
        slippage_bps: float = 0,
        fee_bps: float = 0,
    ) -> None:
        values = (starting_cash, slippage_bps, fee_bps)
        if any(isinstance(value, bool) or not isfinite(value) for value in values):
            raise ValueError("paper execution settings must be finite numbers")
        if starting_cash <= 0 or not 0 <= slippage_bps <= 10_000 or not 0 <= fee_bps <= 10_000:
            raise ValueError("paper execution settings are invalid")
        if opened_at.tzinfo is None or opened_at.utcoffset() is None:
            raise ValueError("opened_at must be timezone-aware")
        self._cash = float(starting_cash)
        self._slippage_bps = float(slippage_bps)
        self._fee_bps = float(fee_bps)
        self._valued_at = opened_at.astimezone(UTC)
        self._positions: dict[str, _PaperPosition] = {}
        self._processed: set[str] = set()

    @property
    def cost_bounds(self) -> ExecutionCostBounds:
        return ExecutionCostBounds(fee_bps=self._fee_bps, slippage_bps=self._slippage_bps)

    def portfolio_state(self) -> PortfolioState:
        return self._build_state(self._cash, self._positions, self._valued_at)

    def mark_to_market(
        self, observations: tuple[PriceObservation, ...], *, valued_at: datetime
    ) -> PortfolioState:
        if valued_at.tzinfo is None or valued_at.utcoffset() is None:
            raise ValueError("valued_at must be timezone-aware")
        valued_at = valued_at.astimezone(UTC)
        if valued_at < self._valued_at:
            raise ValueError("mark-to-market time cannot precede account state time")
        by_symbol = {observation.symbol: observation for observation in observations}
        if len(by_symbol) != len(observations):
            raise ValueError("mark observations must have unique symbols")
        missing = set(self._positions) - set(by_symbol)
        if missing:
            raise ValueError(f"missing current marks for: {', '.join(sorted(missing))}")
        candidate = dict(self._positions)
        for symbol, position in candidate.items():
            observation = by_symbol[symbol]
            if observation.observed_at > valued_at:
                raise ValueError("cannot value a portfolio using a future mark")
            candidate[symbol] = _PaperPosition(
                quantity=position.quantity,
                average_entry_price=position.average_entry_price,
                mark_price=observation.price,
                mark_observed_at=observation.observed_at,
            )
        state = self._build_state(self._cash, candidate, valued_at)
        self._positions = candidate
        self._valued_at = state.valued_at
        return state

    def execute(
        self,
        order: ApprovedOrder,
        opening_price: OpeningPriceObservation,
        *,
        submitted_at: datetime,
    ) -> ExecutionReport:
        if submitted_at.tzinfo is None or submitted_at.utcoffset() is None:
            raise ValueError("submitted_at must be timezone-aware")
        submitted_at = submitted_at.astimezone(UTC)
        rejection = self._rejection_reason(order, opening_price, submitted_at)
        if rejection is not None:
            return self._rejected(order, submitted_at, rejection)

        direction = 1.0 if order.side is OrderSide.BUY else -1.0
        fill_price = opening_price.price * (1 + direction * self._slippage_bps / 10_000)
        adverse_slippage_bps = max(
            0.0,
            direction * (fill_price / order.reference_price - 1) * 10_000,
        )
        if adverse_slippage_bps > order.max_slippage_bps + 1e-9:
            return self._rejected(order, submitted_at, "opening gap exceeds slippage authorization")
        notional = order.quantity * fill_price
        fee = notional * self._fee_bps / 10_000
        if self._fee_bps > order.max_fee_bps + 1e-9:
            return self._rejected(order, submitted_at, "fee exceeds authorization")

        cash_change = -notional - fee if order.side is OrderSide.BUY else notional - fee
        candidate_cash = self._cash + cash_change
        if candidate_cash < 0 and not order.reduce_only:
            return self._rejected(order, submitted_at, "insufficient paper cash")

        candidate_positions = dict(self._positions)
        current = candidate_positions.get(order.symbol)
        current_quantity = 0.0 if current is None else current.quantity
        new_quantity = current_quantity + direction * order.quantity
        if abs(new_quantity) <= QUANTITY_ABS_TOLERANCE:
            new_quantity = 0.0
        if order.reduce_only and not self._strictly_reduces(current_quantity, new_quantity):
            return self._rejected(order, submitted_at, "order violates reduce-only authorization")

        if new_quantity == 0.0:
            candidate_positions.pop(order.symbol, None)
        else:
            average_entry = self._average_entry(
                current, direction * order.quantity, fill_price, new_quantity
            )
            candidate_positions[order.symbol] = _PaperPosition(
                quantity=new_quantity,
                average_entry_price=average_entry,
                mark_price=opening_price.price,
                mark_observed_at=opening_price.observed_at,
            )

        # Constructing the full immutable state is the commit gate. Any validation
        # failure above or here leaves every mutable account field unchanged.
        candidate_state = self._build_state(
            candidate_cash, candidate_positions, opening_price.bar_opened_at
        )
        report = ExecutionReport(
            authorization_id=order.authorization_id,
            status=ExecutionStatus.FILLED,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            submitted_at=submitted_at,
            filled_at=opening_price.bar_opened_at,
            fill_price=fill_price,
            fee=fee,
            slippage_bps=adverse_slippage_bps,
            message="paper fill at causally valid next-bar open",
        )
        self._cash = candidate_cash
        self._positions = candidate_positions
        self._valued_at = candidate_state.valued_at
        self._processed.add(order.authorization_id)
        return report

    def _rejection_reason(
        self,
        order: ApprovedOrder,
        opening_price: OpeningPriceObservation,
        submitted_at: datetime,
    ) -> str | None:
        if not order.paper_only:
            return "live orders are forbidden"
        if order.authorization_id in self._processed:
            return "duplicate authorization"
        if order.fill_policy is not FillPolicy.NEXT_BAR_OPEN:
            return "unsupported fill policy"
        if (order.symbol, order.timeframe) != (opening_price.symbol, opening_price.timeframe):
            return "opening price does not match the order"
        if submitted_at < order.authorized_at:
            return "order was submitted before authorization"
        if submitted_at > opening_price.bar_opened_at:
            return "order cannot fill retroactively at an earlier bar open"
        if opening_price.observed_at != opening_price.bar_opened_at:
            return "next-bar opening price must be observed at the bar open"
        if opening_price.bar_opened_at < order.earliest_fill_at:
            return "opening price precedes the causal fill window"
        if opening_price.bar_opened_at > order.expires_at:
            return "authorization expired before the opening price"
        if opening_price.bar_opened_at < self._valued_at:
            return "fill time cannot precede account state time"
        return None

    @staticmethod
    def _average_entry(
        current: _PaperPosition | None,
        signed_fill_quantity: float,
        fill_price: float,
        new_quantity: float,
    ) -> float:
        if current is None or current.quantity * signed_fill_quantity > 0:
            existing_quantity = 0.0 if current is None else abs(current.quantity)
            existing_cost = (
                0.0 if current is None else existing_quantity * current.average_entry_price
            )
            return (existing_cost + abs(signed_fill_quantity) * fill_price) / abs(new_quantity)
        if current.quantity * new_quantity > 0:
            return current.average_entry_price
        return fill_price

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
    def _build_state(
        cash: float, positions: dict[str, _PaperPosition], valued_at: datetime
    ) -> PortfolioState:
        public_positions = tuple(
            Position(
                symbol=symbol,
                quantity=position.quantity,
                average_entry_price=position.average_entry_price,
                mark_price=position.mark_price,
                mark_observed_at=position.mark_observed_at,
            )
            for symbol, position in sorted(positions.items())
        )
        equity = cash + sum(position.notional for position in public_positions)
        return PortfolioState(
            cash=cash,
            equity=equity,
            valued_at=valued_at,
            positions=public_positions,
        )

    @staticmethod
    def _rejected(order: ApprovedOrder, submitted_at: datetime, message: str) -> ExecutionReport:
        return ExecutionReport(
            authorization_id=order.authorization_id,
            status=ExecutionStatus.REJECTED,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            submitted_at=submitted_at,
            filled_at=None,
            fill_price=None,
            fee=0.0,
            slippage_bps=0.0,
            message=message,
        )
