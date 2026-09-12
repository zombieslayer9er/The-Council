"""Process-isolated Freqtrade backtest engine and validation adapter."""

from __future__ import annotations

import csv
import json
import os
import re
import shutil
import subprocess
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any, Protocol, cast
from uuid import uuid4

from botnet_council.backtest.authoritative import (
    AuthoritativeBacktestRequest,
    AuthoritativeBacktestResult,
    EngineProvenance,
    EquityPoint,
    NormalizedTrade,
    ValidationArtifact,
    ValidationKind,
    ValidationStatus,
)


class FreqtradeEngineError(RuntimeError):
    """Base class for structured external-engine failures."""


class FreqtradeUnavailableError(FreqtradeEngineError):
    pass


class FreqtradeProcessError(FreqtradeEngineError):
    def __init__(self, command: Sequence[str], returncode: int, stderr: str) -> None:
        super().__init__(f"Freqtrade exited with status {returncode}: {stderr.strip()}")
        self.command = tuple(command)
        self.returncode = returncode


class FreqtradeArtifactError(FreqtradeEngineError):
    pass


@dataclass(frozen=True, slots=True)
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    def run(self, command: Sequence[str], *, cwd: Path, timeout: int) -> ProcessResult: ...


class SubprocessCommandRunner:
    def run(self, command: Sequence[str], *, cwd: Path, timeout: int) -> ProcessResult:
        completed = subprocess.run(
            tuple(command),
            cwd=cwd,
            capture_output=True,
            check=False,
            shell=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return ProcessResult(completed.returncode, completed.stdout, completed.stderr)


class DockerComposeCommandRunner:
    """Run the external engine in the repository's isolated Compose service."""

    def __init__(
        self,
        compose_file: str | Path,
        workspace_root: str | Path,
        *,
        docker_executable: str = "docker",
    ) -> None:
        self._compose_file = Path(compose_file).resolve()
        self._workspace_root = Path(workspace_root).resolve()
        self._docker_executable = docker_executable
        if not self._compose_file.is_file():
            raise ValueError(f"Compose file does not exist: {self._compose_file}")
        if not self._workspace_root.is_dir():
            raise ValueError(f"workspace root does not exist: {self._workspace_root}")

    def map_path(self, path: str | Path) -> str:
        resolved = Path(path).resolve()
        try:
            relative = resolved.relative_to(self._workspace_root)
        except ValueError as error:
            raise ValueError(
                f"Docker Freqtrade paths must remain inside {self._workspace_root}: {resolved}"
            ) from error
        return str(PurePosixPath("/workspace", *relative.parts))

    def run(self, command: Sequence[str], *, cwd: Path, timeout: int) -> ProcessResult:
        if not command or command[0] != "freqtrade":
            raise ValueError("Docker runner accepts only the Freqtrade executable")
        self.map_path(cwd)
        resolved_docker = shutil.which(self._docker_executable)
        if resolved_docker is None and self._docker_executable == "docker" and os.name == "nt":
            local_app_data = os.environ.get("LOCALAPPDATA")
            if local_app_data:
                desktop_cli = (
                    Path(local_app_data)
                    / "Programs"
                    / "DockerDesktop"
                    / "resources"
                    / "bin"
                    / "docker.exe"
                )
                try:
                    if desktop_cli.is_file():
                        resolved_docker = str(desktop_cli)
                except OSError:
                    pass
        if resolved_docker is None:
            raise FreqtradeUnavailableError(
                f"Docker executable {self._docker_executable!r} is not installed or not on PATH"
            )
        docker_command = (
            resolved_docker,
            "compose",
            "--project-directory",
            str(self._compose_file.parent),
            "--file",
            str(self._compose_file),
            "run",
            "--rm",
            "--no-deps",
            "-T",
            "freqtrade",
            *command[1:],
        )
        environment = os.environ.copy()
        environment["BOTNET_COUNCIL_WORKSPACE"] = str(self._workspace_root)
        completed = subprocess.run(
            docker_command,
            cwd=self._compose_file.parent,
            env=environment,
            capture_output=True,
            check=False,
            shell=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return ProcessResult(completed.returncode, completed.stdout, completed.stderr)


class FreqtradeBacktestEngine:
    engine_id = "freqtrade"

    def __init__(
        self,
        executable: str = "freqtrade",
        *,
        runner: CommandRunner | None = None,
        timeout_seconds: int = 3_600,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._executable = executable
        self._runner = runner or SubprocessCommandRunner()
        self._timeout = timeout_seconds

    def run(self, request: AuthoritativeBacktestRequest) -> AuthoritativeBacktestResult:
        version = self._version(request.artifact_directory)
        run_directory = request.artifact_directory / request.request_id
        run_directory.mkdir(parents=True, exist_ok=True)
        invocation = run_directory / "invocations" / uuid4().hex
        invocation.mkdir(parents=True, exist_ok=False)
        config = self._effective_config(request)
        config_path = run_directory / "effective-config.json"
        config_path.write_text(_canonical_json(config), encoding="utf-8")
        command = self._base_command(request, config_path, "backtesting")
        command.extend(("--export", "trades", "--cache", "none"))
        command.extend(("--backtest-directory", self._runtime_path(invocation)))
        completed = self._runner.run(command, cwd=invocation, timeout=self._timeout)
        transcript = run_directory / "process.txt"
        transcript_content = f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        transcript.write_text(transcript_content, encoding="utf-8")
        if completed.returncode != 0:
            raise FreqtradeProcessError(command, completed.returncode, completed.stderr)
        artifact = _single_result_artifact(invocation)
        (invocation / "process.txt").write_text(transcript_content, encoding="utf-8")
        artifact = _publish_artifact(run_directory / "results", artifact)
        payload = _load_result(artifact)
        return _normalize_result(request, version, config, artifact, payload)

    def validate(
        self, request: AuthoritativeBacktestRequest, kind: ValidationKind
    ) -> ValidationArtifact:
        version = self._version(request.artifact_directory)
        run_directory = request.artifact_directory / request.request_id
        run_directory.mkdir(parents=True, exist_ok=True)
        invocation = run_directory / "invocations" / uuid4().hex
        invocation.mkdir(parents=True, exist_ok=False)
        config = self._effective_config(request)
        config_path = run_directory / "effective-config.json"
        config_path.write_text(_canonical_json(config), encoding="utf-8")
        command = self._base_command(
            request,
            config_path,
            f"{kind.value}-analysis",
            include_execution=kind is ValidationKind.LOOKAHEAD,
        )
        csv_path = invocation / f"{kind.value}.csv"
        if kind is ValidationKind.LOOKAHEAD:
            command.extend(
                ("--lookahead-analysis-exportfilename", self._runtime_path(csv_path))
            )
        completed = self._runner.run(command, cwd=invocation, timeout=self._timeout)
        transcript = run_directory / f"{kind.value}.txt"
        transcript_content = f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        transcript.write_text(transcript_content, encoding="utf-8")
        if completed.returncode != 0:
            raise FreqtradeProcessError(command, completed.returncode, completed.stderr)
        (invocation / f"{kind.value}.txt").write_text(
            transcript_content, encoding="utf-8"
        )
        if kind is ValidationKind.LOOKAHEAD:
            artifact = _single_result_artifact(invocation)
        else:
            artifact = invocation / f"{kind.value}.txt"
        results_directory = run_directory / "results"
        results_directory.mkdir(parents=True, exist_ok=True)
        published = _publish_artifact(results_directory, artifact)
        findings = _validation_findings(kind, artifact, completed.stdout)
        if not findings:
            status = ValidationStatus.INCONCLUSIVE
        elif any(item.startswith("BIAS:") for item in findings):
            status = ValidationStatus.FAILED
        else:
            status = ValidationStatus.PASSED
        return ValidationArtifact(
            kind=kind,
            status=status,
            engine_version=version,
            request_id=request.request_id,
            artifact_path=published,
            artifact_sha256=_file_sha256(published),
            findings=findings,
        )

    def _version(self, artifact_directory: Path) -> str:
        if (
            isinstance(self._runner, SubprocessCommandRunner)
            and shutil.which(self._executable) is None
        ):
            raise FreqtradeUnavailableError(
                f"Freqtrade executable {self._executable!r} is not installed or not on PATH"
            )
        artifact_directory.mkdir(parents=True, exist_ok=True)
        command = [self._executable, "--version"]
        completed = self._runner.run(command, cwd=artifact_directory, timeout=30)
        if completed.returncode != 0:
            raise FreqtradeProcessError(command, completed.returncode, completed.stderr)
        version = completed.stdout.strip()
        if not version:
            raise FreqtradeArtifactError("Freqtrade returned an empty version string")
        return version

    def _base_command(
        self,
        request: AuthoritativeBacktestRequest,
        config_path: Path,
        subcommand: str,
        *,
        include_execution: bool = True,
    ) -> list[str]:
        command = [
            self._executable,
            subcommand,
            "--no-color",
            "--config",
            self._runtime_path(config_path),
            "--datadir",
            self._runtime_path(request.data_directory),
            "--strategy",
            request.strategy.strategy_name,
            "--strategy-path",
            self._runtime_path(request.strategy.strategy_path),
            "--timeframe",
            request.timeframe,
            "--timerange",
            _timerange(request.start, request.end),
            "-p",
            *request.instruments,
        ]
        if include_execution:
            command.extend(
                (
                    "--fee",
                    str(request.fee_ratio),
                    "--dry-run-wallet",
                    str(request.starting_capital),
                )
            )
        return command

    def _runtime_path(self, path: str | Path) -> str:
        mapper = getattr(self._runner, "map_path", None)
        return str(path) if mapper is None else str(mapper(path))

    def _effective_config(self, request: AuthoritativeBacktestRequest) -> dict[str, Any]:
        supplied = dict(request.engine_configuration)
        protected = {
            "dry_run",
            "db_url",
            "api_server",
            "telegram",
            "trading_mode",
            "timeframe",
            "dry_run_wallet",
            "exchange",
            "pairlists",
            "order_types",
            "entry_pricing",
            "exit_pricing",
            "bot_name",
            "botnet_council_seed",
            "botnet_council_dataset_id",
            "botnet_council_context",
            "botnet_council_signal_artifact",
        }
        forbidden = protected & supplied.keys()
        if forbidden:
            raise ValueError(
                f"engine_configuration cannot override safety fields: {sorted(forbidden)}"
            )
        exchange_name = str(supplied.pop("exchange_name", "kraken"))
        order_types: dict[str, str | bool] = {
            "entry": "market",
            "exit": "market",
            "emergency_exit": "market",
            "force_entry": "market",
            "force_exit": "market",
            "stoploss": "market",
            "stoploss_on_exchange": False,
        }
        order_types.update(request.order_types)
        config: dict[str, Any] = {
            "dry_run": True,
            "trading_mode": "spot",
            "stake_currency": str(supplied.pop("stake_currency", "USD")),
            "stake_amount": supplied.pop("stake_amount", "unlimited"),
            "max_open_trades": int(supplied.pop("max_open_trades", 1)),
            "timeframe": request.timeframe,
            "dry_run_wallet": request.starting_capital,
            "exchange": {
                "name": exchange_name,
                "pair_whitelist": list(request.instruments),
                "pair_blacklist": [],
            },
            "pairlists": [{"method": "StaticPairList"}],
            "order_types": order_types,
            "entry_pricing": {"price_side": "other", "use_order_book": False},
            "exit_pricing": {"price_side": "other", "use_order_book": False},
            "bot_name": f"botnet-council-{request.request_id[:12]}",
            "botnet_council_seed": request.seed,
            "botnet_council_dataset_id": request.dataset_id,
            "botnet_council_context": dict(request.context_configuration),
        }
        if request.strategy.signal_artifact is not None:
            config["botnet_council_signal_artifact"] = self._runtime_path(
                request.strategy.signal_artifact
            )
        config.update(supplied)
        return config


def _timerange(start: datetime, end: datetime) -> str:
    return f"{start.astimezone(UTC):%Y%m%dT%H%M}-{end.astimezone(UTC):%Y%m%dT%H%M}"


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n"


def _single_result_artifact(directory: Path) -> Path:
    marker = directory / ".last_result.json"
    selected: Path | None = None
    if marker.exists():
        try:
            value = json.loads(marker.read_text(encoding="utf-8"))
            filename = value.get("latest_backtest") if isinstance(value, dict) else None
            selected = directory / filename if isinstance(filename, str) else None
        except (OSError, ValueError):
            selected = None
        if selected is not None and (
            not selected.is_file() or selected.parent != directory
        ):
            selected = None
    candidates = sorted(
        path
        for path in (
            *directory.glob("*.zip"),
            *directory.glob("*.json"),
            *directory.glob("*.csv"),
        )
        if not path.name.startswith(".")
    )
    if len(candidates) != 1:
        if not candidates:
            raise FreqtradeArtifactError("Freqtrade process produced no result artifact")
        raise FreqtradeArtifactError(
            f"expected exactly one Freqtrade result artifact, found {len(candidates)}"
        )
    if selected is not None and selected != candidates[0]:
        raise FreqtradeArtifactError("Freqtrade marker does not identify the result artifact")
    return candidates[0]


def _publish_artifact(directory: Path, artifact: Path) -> Path:
    content = artifact.read_bytes()
    destination = directory / f"{sha256(content).hexdigest()[:24]}{artifact.suffix}"
    directory.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.read_bytes() != content:
            raise FreqtradeArtifactError(
                f"content-addressed artifact conflicts with existing file: {destination}"
            )
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    return destination


def _load_result(path: Path) -> Mapping[str, Any]:
    try:
        if path.suffix == ".zip":
            with zipfile.ZipFile(path) as archive:
                names = sorted(name for name in archive.namelist() if name.endswith(".json"))
                value = None
                for name in names:
                    candidate = json.loads(archive.read(name))
                    if isinstance(candidate, dict) and isinstance(candidate.get("strategy"), dict):
                        value = candidate
                        break
                if value is None:
                    raise FreqtradeArtifactError("Freqtrade zip contains no JSON report")
        else:
            value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        raise FreqtradeArtifactError(f"cannot read Freqtrade result: {error}") from error
    if not isinstance(value, dict):
        raise FreqtradeArtifactError("Freqtrade result root must be an object")
    return cast(Mapping[str, Any], value)


def _normalize_result(
    request: AuthoritativeBacktestRequest,
    version: str,
    config: Mapping[str, Any],
    artifact: Path,
    payload: Mapping[str, Any],
) -> AuthoritativeBacktestResult:
    strategies = payload.get("strategy")
    if not isinstance(strategies, dict):
        raise FreqtradeArtifactError("Freqtrade result has no strategy object")
    raw = strategies.get(request.strategy.strategy_name)
    if not isinstance(raw, dict):
        raise FreqtradeArtifactError("Freqtrade result does not contain the requested strategy")
    raw_trades = raw.get("trades", [])
    if not isinstance(raw_trades, list):
        raise FreqtradeArtifactError("Freqtrade trades must be an array")
    trades = tuple(_normalize_trade(item, index) for index, item in enumerate(raw_trades))
    for trade in trades:
        if trade.instrument not in request.instruments:
            raise FreqtradeArtifactError(
                f"trade instrument {trade.instrument!r} not in request"
            )
        if not request.start <= trade.opened_at <= trade.closed_at <= request.end:
            raise FreqtradeArtifactError("trade outside requested period")
    _validate_result_period(request, raw)
    starting = _number(raw, "starting_balance")
    ending = _number(raw, "final_balance")
    pnl = _number(raw, "profit_total_abs")
    total_return = _number(raw, "profit_total")
    maximum_drawdown = abs(_number(raw, "max_drawdown_account"))
    equity = _normalize_equity(raw.get("daily_profit"), starting)
    rejected_count = int(_number(raw, "rejected_signals", 0.0))
    warnings: list[str] = []
    if not equity:
        warnings.append("Freqtrade export did not contain an authoritative equity series")
    if rejected_count:
        warnings.append(
            "Freqtrade reported aggregate rejected signals without per-order records"
        )
    config_hash = _effective_config_hash(artifact, config)
    run_id = sha256(
        f"freqtrade|{version}|{request.request_id}|{_file_sha256(artifact)}".encode()
    ).hexdigest()
    return AuthoritativeBacktestResult(
        provenance=EngineProvenance(
            engine="freqtrade",
            engine_version=version,
            effective_config_hash=config_hash,
            dataset_id=request.dataset_id,
            request_id=request.request_id,
            run_id=run_id,
            artifact_path=artifact,
            artifact_sha256=_file_sha256(artifact),
        ),
        trades=trades,
        equity_curve=equity,
        rejected_order_count=rejected_count,
        starting_capital=starting,
        ending_capital=ending,
        total_pnl=pnl,
        total_return=total_return,
        maximum_drawdown=maximum_drawdown,
        warnings=tuple(warnings),
    )


def _normalize_trade(value: Any, index: int) -> NormalizedTrade:
    if not isinstance(value, dict):
        raise FreqtradeArtifactError("Freqtrade trade must be an object")
    opened = _date(value, "open_date")
    closed = _date(value, "close_date")
    entry = _number(value, "open_rate")
    exit_price = _number(value, "close_rate")
    quantity = _number(value, "amount")
    maximum = _optional_number(value.get("max_rate"))
    minimum = _optional_number(value.get("min_rate"))
    side = "short" if bool(value.get("is_short", False)) else "long"
    if side == "long":
        mfe = None if maximum is None else (maximum - entry) / entry
        mae = None if minimum is None else (minimum - entry) / entry
    else:
        mfe = None if minimum is None else (entry - minimum) / entry
        mae = None if maximum is None else (entry - maximum) / entry
    holding = value.get("trade_duration")
    holding_seconds = (
        int(float(holding) * 60) if holding is not None else int((closed - opened).total_seconds())
    )
    trade_id = str(value.get("trade_id", index))
    return NormalizedTrade(
        trade_id=trade_id,
        instrument=str(value.get("pair", "")),
        side=side,
        opened_at=opened,
        closed_at=closed,
        entry_price=entry,
        exit_price=exit_price,
        quantity=quantity,
        entry_fee=_fee_cost(value, "fee_open_cost", "fee_open", entry * quantity),
        exit_fee=_fee_cost(value, "fee_close_cost", "fee_close", exit_price * quantity),
        pnl=_number(value, "profit_abs"),
        return_ratio=_number(value, "profit_ratio"),
        maximum_favorable_excursion=mfe,
        maximum_adverse_excursion=mae,
        holding_seconds=holding_seconds,
        entry_tag=_optional_text(value.get("enter_tag")),
        exit_reason=_optional_text(value.get("exit_reason")),
    )


def _validate_result_period(
    request: AuthoritativeBacktestRequest, strategy: Mapping[str, Any]
) -> None:
    supplied = {
        "start": strategy.get("backtest_start_ts"),
        "end": strategy.get("backtest_end_ts"),
        "timeframe": strategy.get("timeframe"),
    }
    if not any(value is not None for value in supplied.values()):
        return
    if supplied["timeframe"] != request.timeframe:
        raise FreqtradeArtifactError("result period does not match request")
    if supplied["start"] is None or supplied["end"] is None:
        raise FreqtradeArtifactError("result period does not match request")
    try:
        start = _parse_export_datetime(supplied["start"])
        end = _parse_export_datetime(supplied["end"])
    except (TypeError, ValueError) as error:
        raise FreqtradeArtifactError("result period does not match request") from error
    tolerance = _timeframe_duration(request.timeframe)
    if abs(start - request.start) > tolerance or abs(end - request.end) > tolerance:
        raise FreqtradeArtifactError("result period does not match request")


def _parse_export_datetime(value: Any) -> datetime:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        seconds = float(value) / (1000.0 if abs(value) >= 10**11 else 1.0)
        return datetime.fromtimestamp(seconds, tz=UTC)
    if isinstance(value, str):
        return _parse_datetime(value)
    raise TypeError("invalid export timestamp")


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


def _normalize_equity(value: Any, starting: float) -> tuple[EquityPoint, ...]:
    if not isinstance(value, list):
        return ()
    running = starting
    peak = starting
    points: list[EquityPoint] = []
    for item in value:
        if not isinstance(item, list | tuple) or len(item) < 2:
            raise FreqtradeArtifactError("daily_profit entries must contain date and profit")
        timestamp = _parse_datetime(item[0])
        running += float(item[1])
        peak = max(peak, running)
        drawdown = 0.0 if peak == 0 else max(0.0, (peak - running) / peak)
        points.append(EquityPoint(timestamp=timestamp, equity=running, drawdown_ratio=drawdown))
    return tuple(points)


def _validation_findings(kind: ValidationKind, artifact: Path, stdout: str) -> tuple[str, ...]:
    if kind is ValidationKind.LOOKAHEAD and artifact.suffix == ".csv":
        with artifact.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        findings: list[str] = []
        for row in rows:
            biased = any(
                str(value).strip().lower() in {"true", "yes", "1"}
                for key, value in row.items()
                if "bias" in key.lower()
            )
            prefix = "BIAS" if biased else "CLEAR"
            findings.append(f"{prefix}: {json.dumps(row, sort_keys=True)}")
        return tuple(findings)
    normalized = stdout.lower()
    if "lookahead bias detected" in normalized or "recursive variance detected" in normalized:
        return (f"BIAS: {kind.value} analysis reported a finding",)
    if "analysis completed" in normalized or "no bias" in normalized:
        return (f"CLEAR: {kind.value} analysis completed",)
    return ()


def _number(source: Mapping[str, Any], key: str, default: float | None = None) -> float:
    value = source.get(key, default)
    if value is None or isinstance(value, bool) or not isinstance(value, int | float):
        raise FreqtradeArtifactError(f"Freqtrade field {key!r} must be numeric")
    result = float(value)
    if result != result or result in (float("inf"), float("-inf")):
        raise FreqtradeArtifactError(f"Freqtrade field {key!r} must be finite")
    return result


def _optional_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise FreqtradeArtifactError("Freqtrade excursion rate must be numeric")
    return float(value)


def _date(source: Mapping[str, Any], key: str) -> datetime:
    value = source.get(key)
    return _parse_datetime(value)


def _parse_datetime(value: Any) -> datetime:
    if not isinstance(value, str):
        raise FreqtradeArtifactError("Freqtrade timestamp must be a string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        except ValueError:
            raise FreqtradeArtifactError(f"invalid Freqtrade timestamp {value!r}") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _optional_text(value: Any) -> str | None:
    return None if value is None else str(value)


def _fee_cost(
    source: Mapping[str, Any], cost_key: str, ratio_key: str, notional: float
) -> float:
    if source.get(cost_key) is not None:
        return _number(source, cost_key)
    return _number(source, ratio_key, 0.0) * notional


def _effective_config_hash(artifact: Path, submitted: Mapping[str, Any]) -> str:
    if artifact.suffix == ".zip":
        try:
            with zipfile.ZipFile(artifact) as archive:
                for name in sorted(archive.namelist()):
                    if name.endswith(".json") and "config" in name.lower():
                        return sha256(archive.read(name)).hexdigest()
        except (OSError, zipfile.BadZipFile):
            pass
    return sha256(_canonical_json(submitted).encode()).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
