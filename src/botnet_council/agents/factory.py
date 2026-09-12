"""Canonical construction of built-in specialist agents."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from botnet_council.agents.base import SpecialistAgent
from botnet_council.agents.mean_reversion import MeanReversionAgent
from botnet_council.agents.regime import RegimeClassificationAgent
from botnet_council.agents.seasonality import SeasonalityAgent
from botnet_council.agents.trend import TrendAgent
from botnet_council.agents.volatility import VolatilityAgent

_CONSTRUCTORS: dict[str, Any] = {
    "trend": TrendAgent,
    "mean_reversion": MeanReversionAgent,
    "volatility": VolatilityAgent,
    "regime": RegimeClassificationAgent,
    "seasonality": SeasonalityAgent,
}


def build_agents(specifications: Sequence[Any]) -> tuple[SpecialistAgent, ...]:
    """Build the configured agents through one deterministic registry."""
    try:
        return tuple(
            _CONSTRUCTORS[specification.kind](**dict(specification.parameters))
            for specification in specifications
        )
    except KeyError as error:
        raise ValueError(f"unsupported agent kind {error.args[0]!r}") from error
