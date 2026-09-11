"""Pure translation into Freqtrade-shaped paper/backtest requests.

No Freqtrade package is imported here. A future integration can consume this DTO
inside a strategy/plugin while council, agent, and risk code remain unchanged.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from botnet_council.schemas import ApprovedOrder

PaperMode = Literal["dry_run", "backtest"]


@dataclass(frozen=True, slots=True)
class FreqtradeOrderRequest:
    pair: str
    side: str
    amount: float
    reference_rate: float
    mode: PaperMode
    authorization_id: str
    authorized_at: datetime
    earliest_fill_at: datetime
    expires_at: datetime
    fill_policy: str


def to_freqtrade_order(order: ApprovedOrder, *, mode: PaperMode) -> FreqtradeOrderRequest:
    if mode not in ("dry_run", "backtest"):
        raise ValueError("Freqtrade adapter supports dry_run and backtest only")
    if not order.paper_only:
        raise ValueError("live orders are forbidden")
    return FreqtradeOrderRequest(
        pair=order.symbol,
        side=order.side.value,
        amount=order.quantity,
        reference_rate=order.reference_price,
        mode=mode,
        authorization_id=order.authorization_id,
        authorized_at=order.authorized_at,
        earliest_fill_at=order.earliest_fill_at,
        expires_at=order.expires_at,
        fill_policy=order.fill_policy.value,
    )
