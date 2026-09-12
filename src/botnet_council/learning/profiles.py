"""Immutable profile transformations and versioned local profile storage."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from threading import RLock
from uuid import uuid4

from botnet_council.backtest.models import to_jsonable
from botnet_council.learning.models import (
    AdaptiveWeight,
    ScopedAgentWeight,
    TeacherDecision,
    TeacherResult,
    WeightChange,
    WeightProfile,
    WeightProposal,
)


class WeightProfileStore:
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._profiles = self._root / "profiles"
        self._active = self._root / "active-generation.txt"
        self._lock = RLock()
        self._profiles.mkdir(parents=True, exist_ok=True)

    def initialize(self, profile: WeightProfile) -> WeightProfile:
        if profile.generation != 0 or profile.parent_generation_id is not None:
            raise ValueError("initial profile must be generation zero without a parent")
        with self._lock:
            self._write_profile(profile)
            if self._active.exists():
                active = self.active()
                if active != profile:
                    raise ValueError("weight profile store is already initialized")
            else:
                self._write_active(profile.generation_id)
        return profile

    def active(self) -> WeightProfile:
        try:
            generation_id = self._active.read_text(encoding="utf-8").strip()
        except FileNotFoundError as error:
            raise LookupError("weight profile store is not initialized") from error
        return self.get(generation_id)

    def get(self, generation_id: str) -> WeightProfile:
        path = self._profile_path(generation_id)
        try:
            value = WeightProfile.model_validate_json(path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise LookupError(f"unknown weight generation {generation_id}") from error
        if value.generation_id != generation_id:
            raise ValueError("stored profile generation identity mismatch")
        return value

    def list(self) -> tuple[WeightProfile, ...]:
        return tuple(
            sorted(
                (
                    self.get(path.stem)
                    for path in self._profiles.glob("weights-v[0-9][0-9][0-9][0-9].json")
                ),
                key=lambda item: item.generation,
            )
        )

    def promote(
        self,
        base: WeightProfile,
        proposal: WeightProposal,
        result: TeacherResult,
    ) -> WeightProfile:
        with self._lock:
            active = self.active()
            if active != base:
                raise ValueError("base profile is not the active generation")
            if proposal.base_generation_id != base.generation_id:
                raise ValueError("proposal does not target the active generation")
            if result.base_generation_id != base.generation_id:
                raise ValueError("Teacher result targets another base generation")
            if result.proposal_id != proposal.proposal_id:
                raise ValueError("Teacher result belongs to another proposal")
            if result.decision is TeacherDecision.REJECT:
                raise PermissionError("a rejected proposal cannot create a generation")
            profile = apply_changes(
                base,
                result.accepted_changes,
                created_at=result.evaluated_at,
                scoring_version=result.scoring_version,
            )
            self._write_profile(profile)
            self._write_active(profile.generation_id)
            return profile

    def rollback(self, generation_id: str) -> WeightProfile:
        with self._lock:
            target = self.get(generation_id)
            current = self.active()
            ancestors: set[str] = set()
            cursor = current
            while cursor.parent_generation_id is not None:
                ancestors.add(cursor.parent_generation_id)
                cursor = self.get(cursor.parent_generation_id)
            if target.generation_id not in ancestors:
                raise ValueError("rollback target is not an ancestor of the active generation")
            self._write_active(target.generation_id)
            return target

    def _write_profile(self, profile: WeightProfile) -> None:
        path = self._profile_path(profile.generation_id)
        content = json.dumps(
            to_jsonable(profile), sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ) + "\n"
        if path.exists():
            if path.read_text(encoding="utf-8") != content:
                raise FileExistsError("refusing to overwrite an immutable weight generation")
            return
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)

    def _write_active(self, generation_id: str) -> None:
        temporary = self._active.with_name(f".{self._active.name}.{uuid4().hex}.tmp")
        temporary.write_text(generation_id + "\n", encoding="utf-8")
        temporary.replace(self._active)

    def _profile_path(self, generation_id: str) -> Path:
        if re.fullmatch(r"weights-v[0-9]{4}", generation_id) is None:
            raise ValueError("invalid weight generation ID")
        return self._profiles / f"{generation_id}.json"


def apply_changes(
    base: WeightProfile,
    changes: tuple[WeightChange, ...],
    *,
    created_at: datetime,
    scoring_version: str,
) -> WeightProfile:
    replacements = {(item.agent_id, item.scope): item for item in changes}
    entries: list[ScopedAgentWeight] = []
    applied: set[tuple[str, object]] = set()
    for entry in base.entries:
        identity = (entry.agent_id, entry.scope)
        change = replacements.get(identity)
        if change is None:
            entries.append(entry)
            continue
        if change.current != entry.weight:
            raise ValueError("proposal current weight differs from base profile")
        entries.append(
            ScopedAgentWeight(
                agent_id=entry.agent_id,
                scope=entry.scope,
                weight=change.proposed,
            )
        )
        applied.add(identity)
    if applied != set(replacements):
        raise ValueError("proposal cannot create undeclared profile scopes")
    return WeightProfile(
        generation=base.generation + 1,
        generation_id=f"weights-v{base.generation + 1:04d}",
        parent_generation_id=base.generation_id,
        created_at=created_at,
        entries=tuple(entries),
        scoring_version=scoring_version,
    )


def reduced_changes(changes: tuple[WeightChange, ...]) -> tuple[WeightChange, ...]:
    return tuple(
        change.model_copy(
            update={
                "proposed": AdaptiveWeight(
                    long_term=(change.current.long_term + change.proposed.long_term) / 2.0,
                    recent=(change.current.recent + change.proposed.recent) / 2.0,
                    recent_mix=change.proposed.recent_mix,
                ),
                "reason": change.reason + " Reduced by Teacher validation.",
            }
        )
        for change in changes
    )
