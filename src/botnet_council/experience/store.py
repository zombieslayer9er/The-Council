"""SQLite index and immutable Parquet payload store for experience episodes."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from threading import RLock
from uuid import uuid4

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from botnet_council.backtest.models import to_jsonable
from botnet_council.council import CouncilConfig, DeterministicCouncil
from botnet_council.experience.models import (
    EXPERIENCE_SCHEMA_VERSION,
    CouncilReplay,
    EpisodeQuery,
    ExperienceEpisode,
    TemporalReplaySplit,
    episode_from_experiment,
)
from botnet_council.experiments import ExperimentRecord
from botnet_council.schemas import CouncilDecision


class ExperienceStoreError(RuntimeError):
    pass


class ExperienceCorruptionError(ExperienceStoreError):
    pass


class IncompatibleExperienceStoreError(ExperienceStoreError):
    pass


class CacheWriteStatus(StrEnum):
    STORED = "stored"
    HIT = "hit"


class ExperienceStore:
    """Content-addressed payloads plus queryable, replace-never metadata."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._database = self._root / "experience.sqlite3"
        self._payloads = self._root / "episodes"
        self._lock = RLock()
        self._root.mkdir(parents=True, exist_ok=True)
        self._payloads.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def save(self, episode: ExperienceEpisode) -> CacheWriteStatus:
        payload = _canonical_payload(episode)
        payload_hash = sha256(payload.encode()).hexdigest()
        path = self._payload_path(episode.episode_id)
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT payload_hash FROM episodes WHERE episode_id = ?",
                (episode.episode_id,),
            ).fetchone()
            if row is not None:
                if str(row[0]) != payload_hash:
                    raise ExperienceCorruptionError(
                        "stored episode index conflicts with immutable content"
                    )
                loaded = self._read_payload(path, payload_hash)
                if loaded != episode:
                    raise ExperienceCorruptionError(
                        "stored episode payload conflicts with immutable content"
                    )
                return CacheWriteStatus.HIT
            if path.exists():
                loaded = self._read_payload(path, payload_hash)
                if loaded != episode:
                    raise ExperienceCorruptionError(
                        "unindexed episode payload conflicts with immutable content"
                    )
            else:
                self._write_payload(path, episode, payload, payload_hash)
            agent_versions = json.dumps(
                [f"{item.agent_id}@{item.version}" for item in episode.evidence.agent_versions],
                sort_keys=True,
                separators=(",", ":"),
            )
            connection.execute(
                """
                INSERT INTO episodes (
                    episode_id, equivalence_id, decision_cache_key, schema_version,
                    symbol, timeframe, decision_timestamp, weight_generation_id,
                    regime, agent_versions, training_eligible, truth_available_at,
                    payload_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    episode.episode_id,
                    episode.equivalence_id,
                    episode.decision_cache_key,
                    episode.schema_version,
                    episode.evidence.symbol,
                    episode.evidence.timeframe,
                    _time_text(episode.evidence.decision_timestamp),
                    episode.evidence.weight_generation_id,
                    episode.evidence.regime,
                    agent_versions,
                    int(episode.training_eligible),
                    None if episode.truth is None else _time_text(episode.truth.available_at),
                    payload_hash,
                ),
            )
            connection.commit()
        return CacheWriteStatus.STORED

    def save_experiment(
        self,
        record: ExperimentRecord,
        *,
        weight_generation_id: str = "weights-v0000",
        risk_policy_version: str = "not-applicable",
        regime: str | None = None,
        asset_class: str | None = None,
    ) -> tuple[ExperienceEpisode, CacheWriteStatus]:
        episode = episode_from_experiment(
            record,
            weight_generation_id=weight_generation_id,
            risk_policy_version=risk_policy_version,
            regime=regime,
            asset_class=asset_class,
        )
        return episode, self.save(episode)

    def get(self, episode_id: str) -> ExperienceEpisode:
        _validate_identity(episode_id, "episode_id")
        with self._connection() as connection:
            row = connection.execute(
                "SELECT schema_version, payload_hash FROM episodes WHERE episode_id = ?",
                (episode_id,),
            ).fetchone()
        if row is None:
            raise LookupError(f"unknown experience episode {episode_id}")
        if str(row[0]) != EXPERIENCE_SCHEMA_VERSION:
            raise IncompatibleExperienceStoreError(
                f"episode uses unsupported schema version {row[0]!r}"
            )
        return self._read_payload(self._payload_path(episode_id), str(row[1]))

    def query(self, query: EpisodeQuery | None = None) -> tuple[ExperienceEpisode, ...]:
        query = query or EpisodeQuery()
        clauses: list[str] = []
        parameters: list[object] = []
        for column, value in (
            ("symbol", query.symbol),
            ("weight_generation_id", query.weight_generation_id),
            ("regime", query.regime),
        ):
            if value is not None:
                clauses.append(f"{column} = ?")
                parameters.append(value)
        if query.start is not None:
            clauses.append("decision_timestamp >= ?")
            parameters.append(_time_text(query.start))
        if query.end is not None:
            clauses.append("decision_timestamp < ?")
            parameters.append(_time_text(query.end))
        if query.training_only:
            clauses.append("training_eligible = 1")
        where = "" if not clauses else " WHERE " + " AND ".join(clauses)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT episode_id, agent_versions FROM episodes"
                + where
                + " ORDER BY decision_timestamp, episode_id",
                tuple(parameters),
            ).fetchall()
        selected: list[ExperienceEpisode] = []
        for episode_id, versions_json in rows:
            versions = set(json.loads(str(versions_json)))
            if query.agent_id is not None:
                prefix = f"{query.agent_id}@"
                if query.agent_version is None:
                    if not any(value.startswith(prefix) for value in versions):
                        continue
                elif f"{query.agent_id}@{query.agent_version}" not in versions:
                    continue
            selected.append(self.get(str(episode_id)))
        return tuple(selected)

    def equivalent(self, equivalence_id: str) -> tuple[ExperienceEpisode, ...]:
        return self._by_identity("equivalence_id", equivalence_id)

    def cached_decisions(self, decision_cache_key: str) -> tuple[CouncilReplay, ...]:
        return tuple(
            self.replay(item.episode_id)
            for item in self._by_identity("decision_cache_key", decision_cache_key)
        )

    def replay(self, episode_id: str) -> CouncilReplay:
        episode = self.get(episode_id)
        evidence = episode.evidence
        return CouncilReplay(
            episode_id=episode.episode_id,
            snapshot=evidence.snapshot,
            specialist_outputs=evidence.specialist_outputs,
            original_council_config=evidence.council_config,
            original_weight_generation_id=evidence.weight_generation_id,
            original_decision_id=evidence.council_decision.decision_id,
        )

    def reaggregate(self, episode_id: str, config: CouncilConfig) -> CouncilDecision:
        replay = self.replay(episode_id)
        return DeterministicCouncil(config).aggregate(
            replay.snapshot, replay.specialist_outputs
        )

    def temporal_split(
        self, cutoff: datetime, query: EpisodeQuery | None = None
    ) -> TemporalReplaySplit:
        if cutoff.tzinfo is None or cutoff.utcoffset() is None:
            raise ValueError("cutoff must be timezone-aware")
        cutoff = cutoff.astimezone(UTC)
        training: list[CouncilReplay] = []
        held_out: list[CouncilReplay] = []
        excluded: list[str] = []
        selected_query = query or EpisodeQuery(training_only=True)
        for episode in self.query(selected_query):
            if episode.evidence.decision_timestamp >= cutoff:
                held_out.append(self.replay(episode.episode_id))
            elif episode.truth is None or episode.truth.available_at >= cutoff:
                excluded.append(episode.episode_id)
            else:
                training.append(self.replay(episode.episode_id))
        return TemporalReplaySplit(
            cutoff=cutoff,
            training=tuple(training),
            held_out=tuple(held_out),
            excluded_unavailable_truth=tuple(excluded),
        )

    def _by_identity(self, column: str, identity: str) -> tuple[ExperienceEpisode, ...]:
        if column not in {"equivalence_id", "decision_cache_key"}:
            raise ValueError("unsupported experience identity column")
        _validate_identity(identity, column)
        with self._connection() as connection:
            rows = connection.execute(
                f"SELECT episode_id FROM episodes WHERE {column} = ? "
                "ORDER BY decision_timestamp, episode_id",
                (identity,),
            ).fetchall()
        return tuple(self.get(str(row[0])) for row in rows)

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            version = connection.execute(
                "SELECT value FROM metadata WHERE key = 'schema_version'"
            ).fetchone()
            if version is not None and str(version[0]) != EXPERIENCE_SCHEMA_VERSION:
                raise IncompatibleExperienceStoreError(
                    f"store uses unsupported schema version {version[0]!r}"
                )
            connection.execute(
                "INSERT OR IGNORE INTO metadata (key, value) VALUES ('schema_version', ?)",
                (EXPERIENCE_SCHEMA_VERSION,),
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS episodes (
                    episode_id TEXT PRIMARY KEY,
                    equivalence_id TEXT NOT NULL,
                    decision_cache_key TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    decision_timestamp TEXT NOT NULL,
                    weight_generation_id TEXT NOT NULL,
                    regime TEXT,
                    agent_versions TEXT NOT NULL,
                    training_eligible INTEGER NOT NULL,
                    truth_available_at TEXT,
                    payload_hash TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_episode_symbol_time "
                "ON episodes (symbol, decision_timestamp)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_episode_weight_generation "
                "ON episodes (weight_generation_id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_episode_equivalence "
                "ON episodes (equivalence_id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_episode_decision_cache "
                "ON episodes (decision_cache_key)"
            )
            connection.commit()

    def _write_payload(
        self,
        path: Path,
        episode: ExperienceEpisode,
        payload: str,
        payload_hash: str,
    ) -> None:
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        table = pa.Table.from_pylist(
            [
                {
                    "schema_version": episode.schema_version,
                    "episode_id": episode.episode_id,
                    "equivalence_id": episode.equivalence_id,
                    "decision_cache_key": episode.decision_cache_key,
                    "payload_hash": payload_hash,
                    "payload_json": payload,
                }
            ]
        )
        pq.write_table(table, temporary)
        temporary.replace(path)

    @staticmethod
    def _read_payload(path: Path, expected_hash: str) -> ExperienceEpisode:
        try:
            rows = pq.read_table(path).to_pylist()
            if len(rows) != 1 or not isinstance(rows[0].get("payload_json"), str):
                raise ExperienceCorruptionError("episode payload must contain exactly one row")
            payload = str(rows[0]["payload_json"])
            if sha256(payload.encode()).hexdigest() != expected_hash:
                raise ExperienceCorruptionError("episode payload hash mismatch")
            episode = ExperienceEpisode.model_validate_json(payload)
            if episode.episode_id != path.stem:
                raise ExperienceCorruptionError("episode payload path identity mismatch")
            return episode
        except ExperienceStoreError:
            raise
        except Exception as error:
            raise ExperienceCorruptionError(f"cannot read episode payload: {error}") from error

    def _payload_path(self, episode_id: str) -> Path:
        _validate_identity(episode_id, "episode_id")
        return self._payloads / f"{episode_id}.parquet"

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._database, timeout=30)
        try:
            yield connection
        finally:
            connection.close()


def _canonical_payload(episode: ExperienceEpisode) -> str:
    return json.dumps(
        to_jsonable(episode), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )


def _time_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _validate_identity(value: str, field_name: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{field_name} must be a 64-character lowercase hexadecimal identity")
