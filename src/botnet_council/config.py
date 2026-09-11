"""Typed, strictly validated TOML configuration."""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from botnet_council.council import CouncilConfig
from botnet_council.risk import RiskPolicy


class LoggingConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True, populate_by_name=True)

    level: str = "INFO"
    json_logs: bool = Field(default=True, alias="json")


class ExecutionConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    adapter: Literal["paper"] = "paper"
    starting_cash: float = Field(default=100_000.0, strict=True, gt=0, allow_inf_nan=False)
    slippage_bps: float = Field(default=0.0, strict=True, ge=0, le=10_000, allow_inf_nan=False)
    fee_bps: float = Field(default=0.0, strict=True, ge=0, le=10_000, allow_inf_nan=False)


class AppConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    logging: LoggingConfig
    council: CouncilConfig
    risk: RiskPolicy
    execution: ExecutionConfig


def load_config(path: str | Path) -> AppConfig:
    with Path(path).open("rb") as config_file:
        raw = tomllib.load(config_file)
    logging_raw = _section(raw, "logging")
    council_raw = _section(raw, "council")
    risk_raw = _section(raw, "risk")
    execution_raw = _section(raw, "execution")
    return AppConfig(
        logging=LoggingConfig(**logging_raw),
        council=CouncilConfig(**council_raw),
        risk=RiskPolicy(
            **{
                **risk_raw,
                "allowed_symbols": tuple(risk_raw.get("allowed_symbols", ())),
            }
        ),
        execution=ExecutionConfig(**execution_raw),
    )


def _section(raw: Mapping[str, Any], name: str) -> dict[str, Any]:
    value = raw.get(name, {})
    if not isinstance(value, dict):
        raise ValueError(f"configuration section {name!r} must be a table")
    return value
