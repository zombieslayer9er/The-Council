"""Process-isolated Freqtrade historical acquisition and canonical normalization."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import UTC, datetime
from math import isfinite
from pathlib import Path
from typing import Any, Protocol, cast

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.compute as pc  # type: ignore[import-untyped]
import pyarrow.feather as feather  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
from pydantic import ValidationError

from botnet_council.market_data.models import (
    Asset,
    AvailabilityRange,
    HistoricalBars,
    HistoricalRequest,
    Instrument,
    ProviderId,
    ProviderMetadata,
    Timeframe,
)
from botnet_council.market_data.quality import MarketDataQualityError, normalize_and_assess
from botnet_council.schemas import MarketBar, MarketSnapshot, SnapshotProvenance

FREQTRADE_ADAPTER_SEMANTIC_VERSION = "freqtrade-ohlcv-causal-v1"


class ProcessResult(Protocol):
    @property
    def returncode(self) -> int: ...

    @property
    def stdout(self) -> str: ...

    @property
    def stderr(self) -> str: ...


class CommandRunner(Protocol):
    def run(self, command: Sequence[str], *, cwd: Path, timeout: int) -> ProcessResult: ...


class SubprocessCommandRunner:
    def run(
        self, command: Sequence[str], *, cwd: Path, timeout: int
    ) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                tuple(command),
                cwd=cwd,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )
        except FileNotFoundError as error:
            raise RuntimeError("Freqtrade is not installed or not on PATH") from error


class FreqtradeHistoricalProvider:
    """Use Freqtrade only for download mechanics; expose canonical Council contracts."""

    def __init__(
        self,
        data_root: str | Path,
        *,
        runner: CommandRunner | None = None,
        executable: str = "freqtrade",
        markets: tuple[str, ...] = ("kraken",),
        instruments: tuple[Instrument, ...] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._data_root = Path(data_root).resolve()
        self._data_root.mkdir(parents=True, exist_ok=True)
        self._runner = runner or SubprocessCommandRunner()
        self._executable = executable
        self._markets = tuple(sorted(set(markets)))
        self._instruments = instruments or tuple(
            Instrument(base=base, quote=quote)
            for base in (Asset.BTC, Asset.ETH)
            for quote in (Asset.USD, Asset.USDT)
        )
        self._clock = clock or (lambda: datetime.now(UTC))
        self._source_version: str | None = None

    @property
    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider=ProviderId.FREQTRADE,
            display_name="Freqtrade historical downloader",
            supported_instruments=self._instruments,
            supported_timeframes=tuple(Timeframe),
            maximum_rows=10_000_000,
            requires_credentials=False,
            timestamp_convention="Freqtrade OHLCV date is normalized as candle open in UTC",
            availability_convention="downloaded closed candles use available_at=interval_end",
        )

    @property
    def source_version(self) -> str:
        if self._source_version is None:
            completed = self._runner.run(
                (self._executable, "--version"), cwd=self._data_root, timeout=60
            )
            if completed.returncode != 0 or not completed.stdout.strip():
                raise RuntimeError("Freqtrade version probe failed")
            self._source_version = completed.stdout.strip().splitlines()[0]
        return self._source_version

    @property
    def adapter_semantic_version(self) -> str:
        return FREQTRADE_ADAPTER_SEMANTIC_VERSION

    def list_markets(self) -> tuple[str, ...]:
        return self._markets

    def list_pairs(self, market: str) -> tuple[Instrument, ...]:
        self._require_market(market)
        return self._instruments

    def inspect_availability(
        self, market: str, instrument: Instrument, timeframe: Timeframe
    ) -> tuple[AvailabilityRange, ...]:
        self._require_supported(market, instrument, timeframe)
        path = self._locate_data_file(market, instrument, timeframe, required=False)
        if path is None:
            return ()
        rows = self._read_rows(path)
        opens = sorted(set(self._row_time(row) for row in rows))
        if not opens:
            return ()
        bounds: list[tuple[datetime, datetime]] = []
        start = opens[0]
        previous = opens[0]
        for opened_at in opens[1:]:
            if opened_at != previous + timeframe.duration:
                bounds.append((start, previous + timeframe.duration))
                start = opened_at
            previous = opened_at
        bounds.append((start, previous + timeframe.duration))
        return tuple(
            AvailabilityRange(
                provider=ProviderId.FREQTRADE,
                market=market,
                instrument=instrument,
                timeframe=timeframe,
                start=start,
                end=end,
                source_version=self.source_version,
                adapter_semantic_version=self.adapter_semantic_version,
            )
            for start, end in bounds
        )

    def fetch_range(self, request: HistoricalRequest) -> HistoricalBars:
        return self.fetch_historical(request)

    def fetch_historical(self, request: HistoricalRequest) -> HistoricalBars:
        self._require_supported(request.market, request.instrument, request.timeframe)
        destination = self._data_root / request.market
        destination.mkdir(parents=True, exist_ok=True)
        command = (
            self._executable,
            "download-data",
            "--exchange",
            request.market,
            "--pairs",
            request.instrument.symbol,
            "--timeframes",
            request.timeframe.value,
            "--timerange",
            f"{request.start:%Y%m%d}-{request.end:%Y%m%d}",
            "--data-format-ohlcv",
            "feather",
            "--datadir",
            self._runtime_path(destination),
        )
        completed = self._runner.run(command, cwd=self._data_root, timeout=3_600)
        if completed.returncode != 0:
            message = completed.stderr.strip() or "Freqtrade historical download failed"
            raise RuntimeError(message)
        path = self._locate_data_file(
            request.market, request.instrument, request.timeframe, required=True
        )
        assert path is not None
        return self.normalize(self._read_rows(path), request)

    def normalize(
        self, rows: Iterable[Mapping[str, Any]], request: HistoricalRequest
    ) -> HistoricalBars:
        bars: list[MarketBar] = []
        supplied = tuple(rows)
        for row in supplied:
            opened_at = self._row_time(row)
            values = tuple(
                self._number(row, name) for name in ("open", "high", "low", "close", "volume")
            )
            closed_at = opened_at + request.timeframe.duration
            if not (request.start <= opened_at < request.end and closed_at <= request.as_of):
                continue
            try:
                bars.append(
                    MarketBar(
                        opened_at=opened_at,
                        closed_at=closed_at,
                        available_at=closed_at,
                        open=values[0],
                        high=values[1],
                        low=values[2],
                        close=values[3],
                        volume=values[4],
                    )
                )
            except ValidationError as error:
                raise MarketDataQualityError("invalid Freqtrade OHLCV row") from error
        normalized, quality = normalize_and_assess(
            bars,
            request.timeframe,
            input_rows=len(supplied),
            request_start=request.start,
            request_end=request.end,
        )
        return HistoricalBars(
            provider=ProviderId.FREQTRADE,
            request=request,
            fetched_at=self._utc_clock(),
            bars=normalized,
            quality=quality,
            source_version=self.source_version,
            adapter_semantic_version=self.adapter_semantic_version,
        )

    def snapshot(self, symbol: str, timeframe: str, *, as_of: datetime) -> MarketSnapshot:
        base, quote = symbol.split("/", maxsplit=1)
        instrument = Instrument(base=Asset(base), quote=Asset(quote))
        selected = Timeframe(timeframe)
        request = HistoricalRequest(
            instrument=instrument,
            timeframe=selected,
            start=as_of - selected.duration * min(self.metadata.maximum_rows, 1_000),
            end=as_of,
            as_of=as_of,
            market=self._markets[0],
        )
        result = self.fetch_historical(request)
        if not result.bars:
            raise LookupError("no causally available Freqtrade candles")
        latest = result.bars[-1]
        return MarketSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            as_of=as_of,
            observed_at=as_of,
            bars=result.bars,
            provenance=SnapshotProvenance(
                provider=result.provider.value,
                instrument=symbol,
                timeframe=timeframe,
                requested_start=request.start,
                requested_end=request.end,
                as_of=request.as_of,
                fetched_at=result.fetched_at,
                latest_observation_time=latest.closed_at,
                latest_available_at=latest.available_at,
                source_version=result.source_version,
                adapter_semantic_version=result.adapter_semantic_version,
                coverage_complete=result.quality.coverage_complete,
                cache_key=result.cache_key,
            ),
        )

    def _locate_data_file(
        self,
        market: str,
        instrument: Instrument,
        timeframe: Timeframe,
        *,
        required: bool,
    ) -> Path | None:
        directory = (self._data_root / market).resolve()
        if self._data_root not in directory.parents and directory != self._data_root:
            raise ValueError("Freqtrade data directory escaped configured root")
        pair_tokens = {
            instrument.symbol.replace("/", "_").lower(),
            instrument.symbol.replace("/", "-").lower(),
        }
        candidates = tuple(
            path
            for path in sorted(directory.rglob("*"))
            if path.is_file()
            and path.suffix.lower() in {".feather", ".parquet", ".json"}
            and timeframe.value.lower() in path.stem.lower()
            and any(token in path.stem.lower() for token in pair_tokens)
        )
        if len(candidates) == 1:
            return candidates[0]
        if required:
            raise RuntimeError(
                f"expected exactly one Freqtrade OHLCV artifact, found {len(candidates)}"
            )
        return None

    def _runtime_path(self, path: Path) -> str:
        mapper = getattr(self._runner, "map_path", None)
        return str(mapper(path)) if callable(mapper) else str(path)

    @staticmethod
    def _read_rows(path: Path) -> tuple[Mapping[str, Any], ...]:
        if path.suffix.lower() == ".feather":
            table = feather.read_table(path)
        elif path.suffix.lower() == ".parquet":
            table = pq.read_table(path)
        else:
            raw = json.loads(path.read_text(encoding="utf-8"))
            values = raw.get("data", raw) if isinstance(raw, Mapping) else raw
            table = None
        if table is not None:
            for name in ("date", "timestamp"):
                index = table.schema.get_field_index(name)
                if index >= 0 and pa.types.is_timestamp(table.schema.field(index).type):
                    unit = table.schema.field(index).type.unit
                    divisor = {"s": 1, "ms": 1_000, "us": 1_000_000, "ns": 1_000_000_000}[unit]
                    seconds = pc.divide(pc.cast(table.column(index), pa.int64()), divisor)
                    table = table.set_column(index, name, seconds)
            values = table.to_pylist()
        if not isinstance(values, list) or not all(isinstance(row, Mapping) for row in values):
            raise MarketDataQualityError("Freqtrade OHLCV artifact must contain object rows")
        return tuple(cast(Mapping[str, Any], row) for row in values)

    @staticmethod
    def _row_time(row: Mapping[str, Any]) -> datetime:
        value = row.get("date", row.get("timestamp"))
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, int | float) and not isinstance(value, bool):
            seconds = float(value) / 1000 if float(value) > 10_000_000_000 else float(value)
            parsed = datetime.fromtimestamp(seconds, tz=UTC)
        elif isinstance(value, str):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            raise MarketDataQualityError("Freqtrade OHLCV row has no valid timestamp")
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    @staticmethod
    def _number(row: Mapping[str, Any], name: str) -> float:
        value = row.get(name)
        if isinstance(value, bool):
            raise MarketDataQualityError(f"Freqtrade {name} must be numeric")
        try:
            number = float(cast(Any, value))
        except (TypeError, ValueError) as error:
            raise MarketDataQualityError(f"Freqtrade {name} must be numeric") from error
        if not isfinite(number):
            raise MarketDataQualityError(f"Freqtrade {name} must be finite")
        return number

    def _require_market(self, market: str) -> None:
        if market not in self._markets:
            raise ValueError(f"unsupported Freqtrade exchange {market!r}")

    def _require_supported(self, market: str, instrument: Instrument, timeframe: Timeframe) -> None:
        self._require_market(market)
        if (
            instrument not in self._instruments
            or timeframe not in self.metadata.supported_timeframes
        ):
            raise ValueError("unsupported Freqtrade market identity")

    def _utc_clock(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock must be timezone-aware")
        return value.astimezone(UTC)
