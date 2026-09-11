"""Small auditable metrics helpers."""

from __future__ import annotations


def maximum_drawdown(equity_curve: tuple[float, ...]) -> float:
    if not equity_curve:
        raise ValueError("maximum drawdown requires at least one equity value")
    peak = equity_curve[0]
    if peak <= 0:
        raise ValueError("maximum drawdown requires positive starting equity")
    result = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        if peak <= 0:
            raise ValueError("maximum drawdown encountered a non-positive peak")
        result = max(result, (peak - equity) / peak)
    return result
