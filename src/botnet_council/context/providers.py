"""Provider boundary for contextual evidence."""

from typing import Protocol, runtime_checkable

from botnet_council.context.models import ContextCapability, ContextDatum, ContextRequest


@runtime_checkable
class ContextProvider(Protocol):
    @property
    def provider_id(self) -> str: ...

    @property
    def source_version(self) -> str: ...

    @property
    def capabilities(self) -> frozenset[ContextCapability]: ...

    def fetch(self, request: ContextRequest) -> tuple[ContextDatum, ...]: ...


class BenchmarkContextProvider(ContextProvider, Protocol):
    """Provides benchmark performance evidence."""


class CrossAssetContextProvider(ContextProvider, Protocol):
    """Provides sector, relative-strength, correlation, volatility, or breadth evidence."""


class MacroContextProvider(ContextProvider, Protocol):
    """Provides rates, yields, macro, or event-calendar evidence."""
