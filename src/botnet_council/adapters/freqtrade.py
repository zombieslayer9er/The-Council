"""Pure translation into Freqtrade-shaped paper/backtest requests.

No Freqtrade package is imported here. A future integration can consume this DTO
inside a strategy/plugin while council, agent, and risk code remain unchanged.
"""

import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from botnet_council.schemas import ActionIntent, ApprovedOrder, CouncilDecision

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


@dataclass(frozen=True, slots=True)
class FreqtradeStrategySignal:
    """A Council decision reduced to Freqtrade's timestamped signal vocabulary."""

    pair: str
    candle_at: datetime
    enter_long: bool
    exit_long: bool
    enter_short: bool
    exit_short: bool
    signal_tag: str
    decision_id: str
    source_snapshot_id: str
    decided_at: datetime
    source_as_of: datetime
    timeframe: str


@dataclass(frozen=True, slots=True)
class CouncilDecisionStrategyAdapter:
    """Translate decisions without introducing Freqtrade types into Council contracts."""

    adapter_id: str = "council-decision-signals"
    adapter_version: str = "1.3"

    def translate(
        self,
        decisions: tuple[CouncilDecision, ...],
        *,
        candle_open_by_decision_id: Mapping[str, datetime],
    ) -> tuple[FreqtradeStrategySignal, ...]:
        ordered = tuple(sorted(decisions, key=lambda item: (item.decided_at, item.decision_id)))
        if len({item.decision_id for item in ordered}) != len(ordered):
            raise ValueError("Council decision identifiers must be unique")
        decision_ids = {item.decision_id for item in ordered}
        if set(candle_open_by_decision_id) != decision_ids:
            raise ValueError("exactly one candle-open timestamp is required per decision")
        signals: list[FreqtradeStrategySignal] = []
        for decision in ordered:
            if decision.source_as_of > decision.decided_at:
                raise ValueError("Council decision uses evidence after its decision time")
            candle_open = candle_open_by_decision_id[decision.decision_id]
            if candle_open.tzinfo is None or candle_open.utcoffset() is None:
                raise ValueError("Freqtrade candle-open timestamps must be timezone-aware")
            candle_open = candle_open.astimezone(UTC)
            if candle_open >= decision.source_as_of:
                raise ValueError("Freqtrade candle must open before the decision data cutoff")
            if candle_open + _timeframe_duration(decision.timeframe) < decision.decided_at:
                raise ValueError("Freqtrade candle closes before the decision")
            if decision.action is ActionIntent.REDUCE_ONLY and decision.target_exposure != 0:
                raise ValueError("nonzero reduce-only targets require current position context")
            if (
                decision.action is ActionIntent.TARGET_EXPOSURE
                and decision.target_exposure not in (None, 0)
            ):
                raise ValueError("nonzero target exposure requires position sizing support")
            actionable = decision.action in (
                ActionIntent.TARGET_EXPOSURE,
                ActionIntent.REDUCE_ONLY,
            )
            exposure = decision.target_exposure if actionable else None
            enter_long = exposure is not None and exposure > 0
            enter_short = exposure is not None and exposure < 0
            flatten = exposure == 0
            signals.append(
                FreqtradeStrategySignal(
                    pair=decision.symbol,
                    candle_at=candle_open,
                    enter_long=enter_long,
                    exit_long=flatten or enter_short,
                    enter_short=enter_short,
                    exit_short=flatten or enter_long,
                    signal_tag=decision.action.value,
                    decision_id=decision.decision_id,
                    source_snapshot_id=decision.source_snapshot_id,
                    decided_at=decision.decided_at,
                    source_as_of=decision.source_as_of,
                    timeframe=decision.timeframe,
                )
            )
        return tuple(signals)

    def write_signal_artifact(
        self,
        decisions: tuple[CouncilDecision, ...],
        destination: str | Path,
        *,
        candle_open_by_decision_id: Mapping[str, datetime],
    ) -> Path:
        """Write immutable input for a Freqtrade strategy's signal merge step."""
        path = Path(destination)
        rows = []
        for signal in self.translate(
            decisions, candle_open_by_decision_id=candle_open_by_decision_id
        ):
            row = asdict(signal)
            for field in ("candle_at", "decided_at", "source_as_of"):
                row[field] = getattr(signal, field).isoformat()
            rows.append(row)
        content = json.dumps(
            {
                "adapter_id": self.adapter_id,
                "adapter_version": self.adapter_version,
                "signals": rows,
            },
            sort_keys=True,
            separators=(",", ":"),
        ) + "\n"
        if path.exists():
            if path.read_text(encoding="utf-8") != content:
                raise FileExistsError(f"refusing to overwrite different signal artifact: {path}")
            return path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path


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


def _timeframe_duration(timeframe: str) -> timedelta:
    match = re.fullmatch(r"([1-9][0-9]*)([mhdw])", timeframe)
    if match is None:
        raise ValueError(f"unknown timeframe: {timeframe}")
    count = int(match.group(1))
    unit = match.group(2)
    return {
        "m": timedelta(minutes=count),
        "h": timedelta(hours=count),
        "d": timedelta(days=count),
        "w": timedelta(weeks=count),
    }[unit]
