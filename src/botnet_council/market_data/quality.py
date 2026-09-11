"""Provider-neutral OHLCV quality checks; missing data is not fabricated."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from botnet_council.market_data.models import DataGap, DataQualityReport, Timeframe
from botnet_council.schemas import MarketBar


class MarketDataQualityError(ValueError):
    """Raised for invalid data, as distinct from valid data with missing intervals."""


def normalize_and_assess(
    bars: Iterable[MarketBar],
    timeframe: Timeframe,
    *,
    input_rows: int | None = None,
    request_start: datetime | None = None,
    request_end: datetime | None = None,
) -> tuple[tuple[MarketBar, ...], DataQualityReport]:
    supplied = tuple(bars)
    out_of_order = tuple(bar.opened_at for bar in supplied) != tuple(
        sorted(bar.opened_at for bar in supplied)
    )
    by_open: dict[object, MarketBar] = {}
    duplicates = 0
    for bar in supplied:
        previous = by_open.get(bar.opened_at)
        if previous is not None:
            if previous != bar:
                raise MarketDataQualityError(
                    f"conflicting duplicate candle at {bar.opened_at.isoformat()}"
                )
            duplicates += 1
            continue
        if bar.closed_at - bar.opened_at != timeframe.duration:
            raise MarketDataQualityError(
                f"candle duration does not match {timeframe.value} at {bar.opened_at.isoformat()}"
            )
        by_open[bar.opened_at] = bar
    ordered = tuple(sorted(by_open.values(), key=lambda bar: bar.opened_at))
    gaps: list[DataGap] = []
    for previous, current in zip(ordered, ordered[1:], strict=False):
        delta = current.opened_at - previous.opened_at
        if delta > timeframe.duration:
            gaps.append(
                DataGap(
                    after=previous.closed_at,
                    before=current.opened_at,
                    missing_intervals=int(delta / timeframe.duration) - 1,
                )
            )
        elif delta < timeframe.duration:
            raise MarketDataQualityError("candles overlap or are not aligned to the timeframe")
    expected = 0
    leading = 0
    trailing = 0
    range_aligned = True
    if (request_start is None) != (request_end is None):
        raise ValueError("request_start and request_end must be supplied together")
    if request_start is not None and request_end is not None:
        range_duration = request_end - request_start
        expected, remainder = divmod(range_duration, timeframe.duration)
        range_aligned = remainder.total_seconds() == 0
        if ordered:
            leading = max(0, int((ordered[0].opened_at - request_start) / timeframe.duration))
            trailing = max(0, int((request_end - ordered[-1].closed_at) / timeframe.duration))
        else:
            leading = expected
    internal_missing = sum(gap.missing_intervals for gap in gaps)
    complete = (
        request_start is not None
        and range_aligned
        and len(ordered) == expected
        and leading == 0
        and trailing == 0
        and internal_missing == 0
    )
    return ordered, DataQualityReport(
        input_rows=len(supplied) if input_rows is None else input_rows,
        output_rows=len(ordered),
        duplicate_rows_removed=duplicates,
        input_was_out_of_order=out_of_order,
        gaps=tuple(gaps),
        expected_intervals=expected,
        leading_missing_intervals=leading,
        trailing_missing_intervals=trailing,
        coverage_complete=complete,
    )
