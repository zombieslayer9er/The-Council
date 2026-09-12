"""Composition, causal validation, and immutable caching for market context."""

from __future__ import annotations

from collections.abc import Iterable
from threading import RLock

from botnet_council.context.models import (
    ContextCapability,
    ContextDatum,
    ContextRequest,
    MarketContext,
)
from botnet_council.context.providers import ContextProvider
from botnet_council.schemas import MarketSnapshot


class ContextProviderError(RuntimeError):
    def __init__(self, provider_id: str, message: str) -> None:
        super().__init__(f"context provider {provider_id!r} failed: {message}")
        self.provider_id = provider_id


class ContextService:
    """Build one causal context without exposing providers to specialists."""

    def __init__(self, providers: Iterable[ContextProvider] = ()) -> None:
        self._providers = tuple(providers)
        self._cache: dict[tuple[str, str, str], tuple[ContextDatum, ...]] = {}
        self._lock = RLock()
        claimed: dict[ContextCapability, str] = {}
        for provider in self._providers:
            if not provider.provider_id or not provider.source_version:
                raise ValueError("context providers require stable identity and source version")
            if ContextCapability.PRICE_HISTORY in provider.capabilities:
                raise ValueError("context providers cannot replace the canonical price snapshot")
            for capability in provider.capabilities:
                previous = claimed.setdefault(capability, provider.provider_id)
                if previous != provider.provider_id:
                    raise ValueError(f"multiple providers claim {capability.value}")

    def enrich(self, snapshot: MarketSnapshot, request: ContextRequest) -> MarketContext:
        if (
            snapshot.symbol != request.instrument
            or snapshot.timeframe != request.timeframe
            or snapshot.as_of != request.as_of
        ):
            raise ValueError("context request must match the canonical price snapshot")
        requested = (request.required | request.optional) - {
            ContextCapability.PRICE_HISTORY
        }
        found: list[ContextDatum] = []
        for provider in self._providers:
            selected = requested & provider.capabilities
            if not selected:
                continue
            cache_key = (
                provider.provider_id,
                provider.source_version,
                request.identity,
            )
            with self._lock:
                cached = self._cache.get(cache_key)
            if cached is None:
                try:
                    fetched = provider.fetch(request)
                except Exception as error:
                    raise ContextProviderError(provider.provider_id, str(error)) from error
                if any(item.capability not in provider.capabilities for item in fetched):
                    raise ContextProviderError(
                        provider.provider_id, "returned an undeclared capability"
                    )
                if any(item.provenance.provider != provider.provider_id for item in fetched):
                    raise ContextProviderError(
                        provider.provider_id, "returned mismatched provenance"
                    )
                cached = tuple(fetched)
                with self._lock:
                    self._cache[cache_key] = cached
            found.extend(item for item in cached if item.capability in selected)
        found.sort(
            key=lambda item: (
                item.capability.value,
                item.instrument,
                item.name,
                item.provenance.source_id,
            )
        )
        available = {ContextCapability.PRICE_HISTORY, *(item.capability for item in found)}
        return MarketContext(
            snapshot=snapshot,
            as_of=request.as_of,
            data=tuple(found),
            requested_required=request.required,
            requested_optional=request.optional,
            missing_required=frozenset(request.required - available),
            missing_optional=frozenset(request.optional - available),
        )
