from datetime import UTC, datetime, timedelta

import pytest

from botnet_council.schemas import MarketBar, MarketSnapshot


@pytest.fixture
def as_of() -> datetime:
    return datetime(2026, 1, 1, 12, tzinfo=UTC)


@pytest.fixture
def rising_snapshot(as_of: datetime) -> MarketSnapshot:
    bars = tuple(
        MarketBar(
            opened_at=as_of - timedelta(minutes=5 * (30 - index)),
            closed_at=as_of - timedelta(minutes=5 * (29 - index)),
            open=100.0 + index,
            high=102.0 + index,
            low=99.0 + index,
            close=101.0 + index,
            volume=1_000.0,
        )
        for index in range(30)
    )
    return MarketSnapshot(
        symbol="TEST/USD", timeframe="5m", as_of=as_of, observed_at=as_of, bars=bars
    )
