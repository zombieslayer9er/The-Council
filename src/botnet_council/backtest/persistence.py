"""Local reproducible JSON and Parquet output for backtest runs."""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from botnet_council.backtest.models import BacktestConfig, BacktestRun, to_jsonable
from botnet_council.schemas import ExecutionStatus


def persist_backtest(run: BacktestRun, config: BacktestConfig, output_root: str | Path) -> Path:
    destination = Path(output_root) / run.result.run_id
    destination.mkdir(parents=True, exist_ok=True)
    _write_json(destination / "config.json", to_jsonable(config))
    _write_json(destination / "summary.json", to_jsonable(run.result))
    _write_json(
        destination / "provenance.json",
        to_jsonable(run.result.market_data_provenance),
    )
    event_rows = [to_jsonable(event) for event in run.ledger.events]
    pq.write_table(pa.Table.from_pylist(event_rows), destination / "events.parquet")
    trade_rows = [
        {
            "sequence": event.sequence,
            "simulation_time": event.simulation_time.isoformat(),
            **event.execution_report.model_dump(mode="json"),
        }
        for event in run.ledger.events
        if event.execution_report is not None
        and event.execution_report.status is ExecutionStatus.FILLED
    ]
    if trade_rows:
        pq.write_table(pa.Table.from_pylist(trade_rows), destination / "trades.parquet")
    equity_rows = [
        {
            "sequence": event.sequence,
            "simulation_time": event.simulation_time.isoformat(),
            "cash": event.portfolio.cash,
            "market_value": event.portfolio.equity - event.portfolio.cash,
            "equity": event.portfolio.equity,
            "gross_realized_pnl": event.gross_realized_pnl,
            "net_realized_pnl": event.net_realized_pnl,
            "unrealized_pnl": event.unrealized_pnl,
            "fees": event.cumulative_fees,
            "slippage_cost": event.cumulative_slippage_cost,
            "measured": event.measured,
        }
        for event in run.ledger.events
    ]
    pq.write_table(pa.Table.from_pylist(equity_rows), destination / "equity.parquet")
    return destination


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
