"""Standalone Freqtrade strategy consuming a frozen Council signal artifact.

This module intentionally imports no BotnetCouncil code. The process boundary is the
versioned JSON artifact emitted by CouncilDecisionStrategyAdapter.
"""

import json
import re
from datetime import UTC, datetime, timedelta
from functools import cached_property
from pathlib import Path
from typing import Any

import pandas as pd
from freqtrade.strategy import IStrategy
from pandas import DataFrame


class CouncilSignalStrategy(IStrategy):
    INTERFACE_VERSION = 3
    can_short = False
    minimal_roi = {"0": 100.0}
    stoploss = -0.99
    timeframe = "5m"
    process_only_new_candles = True
    startup_candle_count = 0
    use_exit_signal = True

    @cached_property
    def _signals(self) -> dict[str, dict[pd.Timestamp, dict[str, Any]]]:
        configured = self.config.get("botnet_council_signal_artifact")
        if not isinstance(configured, str) or not configured:
            raise ValueError("botnet_council_signal_artifact is required")
        payload = json.loads(Path(configured).read_text(encoding="utf-8"))
        if payload.get("adapter_id") != "council-decision-signals":
            raise ValueError("unsupported Council signal adapter")
        if payload.get("adapter_version") != "1.2":
            raise ValueError("unsupported Council signal artifact version")
        rows = payload.get("signals")
        if not isinstance(rows, list):
            raise ValueError("Council signal artifact signals must be an array")
        indexed: dict[str, dict[pd.Timestamp, dict[str, Any]]] = {}
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("Council signal rows must be objects")
            pair = row.get("pair")
            timestamp = row.get("candle_at")
            decided_at = row.get("decided_at")
            source_as_of = row.get("source_as_of")
            timeframe = row.get("timeframe")
            if (
                not isinstance(pair, str)
                or not isinstance(timestamp, str)
                or not isinstance(decided_at, str)
                or not isinstance(source_as_of, str)
                or not isinstance(timeframe, str)
            ):
                raise ValueError("Council signal pair and candle_at are required")
            for field in ("enter_long", "exit_long", "enter_short", "exit_short"):
                if type(row.get(field)) is not bool:
                    raise ValueError(f"Council signal {field} must be boolean")
            candle_at = pd.Timestamp(timestamp)
            if candle_at.tzinfo is None:
                raise ValueError("Council signal candle_at must be timezone-aware")
            candle_at = candle_at.tz_convert("UTC")
            decision_time = _parse_datetime(decided_at)
            source_time = _parse_datetime(source_as_of)
            if candle_at.to_pydatetime() >= source_time:
                raise ValueError("Council signal candle must open before the decision data cutoff")
            if candle_at.to_pydatetime() + _timeframe_duration(timeframe) < decision_time:
                raise ValueError("Council signal candle closes before the decision")
            pair_rows = indexed.setdefault(pair, {})
            if candle_at in pair_rows:
                raise ValueError(f"duplicate Council signal for {pair} at {candle_at}")
            pair_rows[candle_at] = row
        return indexed

    def populate_indicators(self, dataframe: DataFrame, metadata: dict[str, Any]) -> DataFrame:
        return dataframe

    def populate_entry_trend(
        self, dataframe: DataFrame, metadata: dict[str, Any]
    ) -> DataFrame:
        rows = self._signals.get(str(metadata["pair"]), {})
        normalized_dates = pd.to_datetime(dataframe["date"], utc=True)
        dataframe["enter_long"] = normalized_dates.map(
            lambda value: int(bool(rows.get(value, {}).get("enter_long", False)))
        )
        dataframe["enter_short"] = 0
        dataframe["enter_tag"] = normalized_dates.map(
            lambda value: rows.get(value, {}).get("signal_tag")
        )
        return dataframe

    def populate_exit_trend(
        self, dataframe: DataFrame, metadata: dict[str, Any]
    ) -> DataFrame:
        rows = self._signals.get(str(metadata["pair"]), {})
        normalized_dates = pd.to_datetime(dataframe["date"], utc=True)
        dataframe["exit_long"] = normalized_dates.map(
            lambda value: int(bool(rows.get(value, {}).get("exit_long", False)))
        )
        dataframe["exit_short"] = 0
        dataframe["exit_tag"] = normalized_dates.map(
            lambda value: rows.get(value, {}).get("signal_tag")
        )
        return dataframe


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Council signal timestamps must be timezone-aware")
    return parsed.astimezone(UTC)


def _timeframe_duration(timeframe: str) -> timedelta:
    match = re.fullmatch(r"([1-9][0-9]*)([mhdw])", timeframe)
    if match is None:
        raise ValueError(f"unknown timeframe: {timeframe}")
    count = int(match.group(1))
    return {
        "m": timedelta(minutes=count),
        "h": timedelta(hours=count),
        "d": timedelta(days=count),
        "w": timedelta(weeks=count),
    }[match.group(2)]
