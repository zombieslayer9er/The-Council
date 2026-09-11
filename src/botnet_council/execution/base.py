from datetime import datetime
from typing import Protocol, runtime_checkable

from botnet_council.schemas import (
    ApprovedOrder,
    ExecutionCostBounds,
    ExecutionReport,
    OpeningPriceObservation,
    PortfolioState,
    PriceObservation,
)


@runtime_checkable
class ExecutionAdapter(Protocol):
    """A deliberately narrow, paper-only execution boundary."""

    @property
    def cost_bounds(self) -> ExecutionCostBounds: ...

    def portfolio_state(self) -> PortfolioState: ...

    def mark_to_market(
        self, observations: tuple[PriceObservation, ...], *, valued_at: datetime
    ) -> PortfolioState: ...

    def execute(
        self,
        order: ApprovedOrder,
        opening_price: OpeningPriceObservation,
        *,
        submitted_at: datetime,
    ) -> ExecutionReport: ...
