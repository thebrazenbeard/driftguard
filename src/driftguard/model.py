from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import IntEnum, StrEnum
from hashlib import sha256
import json
import math
from typing import Any, Iterable


class EvidenceIndependence(IntEnum):
    SELF = 0
    SEPARATE_CONTEXT = 1
    EXTERNAL = 2

    @classmethod
    def parse(cls, value: str | int) -> "EvidenceIndependence":
        if isinstance(value, bool):
            raise ValueError("independence must not be bool")
        if isinstance(value, int):
            return cls(value)
        if not isinstance(value, str) or not value:
            raise ValueError("independence must be a non-empty string or integer")
        return cls[value.upper()]


class Decision(StrEnum):
    STABLE = "STABLE"
    WARN = "WARN"
    RELOAD = "RELOAD"
    UNKNOWN = "UNKNOWN"


def _require_nonempty_str(value: Any, label: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{label} must be a non-empty exact string")
    return value


def _require_unit_interval(value: Any, label: str) -> float:
    if type(value) not in (int, float) or isinstance(value, bool):
        raise ValueError(f"{label} must be numeric")
    value = float(value)
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{label} must be finite and within [0, 1]")
    return value


@dataclass(frozen=True, order=True)
class SourceBinding:
    ref: str
    version: str

    def __post_init__(self) -> None:
        _require_nonempty_str(self.ref, "source ref")
        _require_nonempty_str(self.version, "source version")

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "SourceBinding":
        return cls(ref=data.get("ref"), version=data.get("version"))


@dataclass(frozen=True)
class BehaviorDimension:
    dimension_id: str
    description: str
    weight: float = 1.0
    critical: bool = False
    min_independence: EvidenceIndependence = EvidenceIndependence.SEPARATE_CONTEXT

    def __post_init__(self) -> None:
        _require_nonempty_str(self.dimension_id, "dimension id")
        _require_nonempty_str(self.description, "dimension description")
        if type(self.weight) not in (int, float) or isinstance(self.weight, bool):
            raise ValueError("dimension weight must be numeric")
        if not math.isfinite(float(self.weight)) or float(self.weight) <= 0:
            raise ValueError("dimension weight must be finite and > 0")
        if type(self.critical) is not bool:
            raise ValueError("critical must be exact bool")
        if type(self.min_independence) is not EvidenceIndependence:
            raise ValueError("min_independence must be EvidenceIndependence")

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "BehaviorDimension":
        return cls(
            dimension_id=data.get("dimension_id"),
            description=data.get("description"),
            weight=data.get("weight", 1.0),
            critical=data.get("critical", False),
            min_independence=EvidenceIndependence.parse(
                data.get("min_independence", "SEPARATE_CONTEXT")
            ),
        )


@dataclass(frozen=True)
class DriftPolicy:
    warn_threshold: float = 0.25
    reload_threshold: float = 0.45
    critical_reload_threshold: float = 0.40
    max_turns_without_reload: int = 40
    reload_cooldown_turns: int = 6

    def __post_init__(self) -> None:
        warn = _require_unit_interval(self.warn_threshold, "warn threshold")
        reload = _require_unit_interval(self.reload_threshold, "reload threshold")
        _require_unit_interval(
            self.critical_reload_threshold, "critical reload threshold"
        )
        if warn >= reload:
            raise ValueError("warn threshold must be lower than reload threshold")
        for value, label in (
            (self.max_turns_without_reload, "max turns without reload"),
            (self.reload_cooldown_turns, "reload cooldown turns"),
        ):
            if type(value) is not int or value < 0:
                raise ValueError(f"{label} must be a non-negative integer")
        if (
            self.max_turns_without_reload > 0
            and self.reload_cooldown_turns >= self.max_turns_without_reload
        ):
            raise ValueError(
                "reload cooldown must be lower than max turns without reload"
            )

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> "DriftPolicy":
        data = data or {}
        return cls(
            warn_threshold=data.get("warn_threshold", 0.25),
            reload_threshold=data.get("reload_threshold", 0.45),
            critical_reload_threshold=data.get("critical_reload_threshold", 0.40),
            max_turns_without_reload=data.get("max_turns_without_reload", 40),
            reload_cooldown_turns=data.get("reload_cooldown_turns", 6),
        )


@dataclass(frozen=True)
class SaveState:
    state_id: str
    version: str
    restore_text: str
    dimensions: tuple[BehaviorDimension, ...]
    allowed_probe_sources: tuple[SourceBinding, ...]
    policy: DriftPolicy = DriftPolicy()

    def __post_init__(self) -> None:
        _require_nonempty_str(self.state_id, "state id")
        _require_nonempty_str(self.version, "state version")
        _require_nonempty_str(self.restore_text, "restore text")
        if type(self.dimensions) is not tuple or not self.dimensions:
            raise ValueError("dimensions must be a non-empty tuple")
        if any(type(item) is not BehaviorDimension for item in self.dimensions):
            raise ValueError("dimensions must contain exact BehaviorDimension values")
        ids = [item.dimension_id for item in self.dimensions]
        if len(ids) != len(set(ids)):
            raise ValueError("dimension ids must be unique")
        if type(self.allowed_probe_sources) is not tuple:
            raise ValueError("allowed_probe_sources must be a tuple")
        if any(type(item) is not SourceBinding for item in self.allowed_probe_sources):
            raise ValueError("allowed_probe_sources must contain exact SourceBinding values")
        if len(self.allowed_probe_sources) != len(set(self.allowed_probe_sources)):
            raise ValueError("allowed probe source bindings must be unique")
        if type(self.policy) is not DriftPolicy:
            raise ValueError("policy must be exact DriftPolicy")

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "SaveState":
        if type(data) is not dict:
            raise ValueError("save-state document must be an object")
        return cls(
            state_id=data.get("state_id"),
            version=data.get("version"),
            restore_text=data.get("restore_text"),
            dimensions=tuple(
                BehaviorDimension.from_mapping(item)
                for item in data.get("dimensions", ())
            ),
            allowed_probe_sources=tuple(
                SourceBinding.from_mapping(item)
                for item in data.get("allowed_probe_sources", ())
            ),
            policy=DriftPolicy.from_mapping(data.get("policy")),
        )

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "state_id": self.state_id,
            "version": self.version,
            "restore_text": self.restore_text,
            "dimensions": [
                {
                    "dimension_id": item.dimension_id,
                    "description": item.description,
                    "weight": float(item.weight),
                    "critical": item.critical,
                    "min_independence": item.min_independence.name,
                }
                for item in self.dimensions
            ],
            "allowed_probe_sources": [asdict(item) for item in self.allowed_probe_sources],
            "policy": asdict(self.policy),
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.canonical_payload())


@dataclass(frozen=True)
class DriftEvidence:
    evidence_id: str
    dimension_id: str
    drift_score: float
    independence: EvidenceIndependence
    source_bindings: tuple[SourceBinding, ...]
    execution_id: str

    def __post_init__(self) -> None:
        _require_nonempty_str(self.evidence_id, "evidence id")
        _require_nonempty_str(self.dimension_id, "evidence dimension id")
        _require_unit_interval(self.drift_score, "drift score")
        if type(self.independence) is not EvidenceIndependence:
            raise ValueError("evidence independence must be EvidenceIndependence")
        if type(self.source_bindings) is not tuple or not self.source_bindings:
            raise ValueError("evidence source bindings must be a non-empty tuple")
        if any(type(item) is not SourceBinding for item in self.source_bindings):
            raise ValueError("source bindings must contain exact SourceBinding values")
        if len(self.source_bindings) != len(set(self.source_bindings)):
            raise ValueError("evidence source bindings must be unique")
        _require_nonempty_str(self.execution_id, "execution id")

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "DriftEvidence":
        return cls(
            evidence_id=data.get("evidence_id"),
            dimension_id=data.get("dimension_id"),
            drift_score=data.get("drift_score"),
            independence=EvidenceIndependence.parse(data.get("independence")),
            source_bindings=tuple(
                SourceBinding.from_mapping(item)
                for item in data.get("source_bindings", ())
            ),
            execution_id=data.get("execution_id"),
        )


@dataclass(frozen=True)
class Evaluation:
    decision: Decision
    aggregate_drift: float | None
    dimension_scores: tuple[tuple[str, float], ...]
    reasons: tuple[str, ...]
    state_digest: str
    evidence_digest: str
    turn_index: int
    generation: int
    restore_packet: str | None = None

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "decision": self.decision.value,
                "aggregate_drift": self.aggregate_drift,
                "dimension_scores": self.dimension_scores,
                "reasons": self.reasons,
                "state_digest": self.state_digest,
                "evidence_digest": self.evidence_digest,
                "turn_index": self.turn_index,
                "generation": self.generation,
                "restore_packet": self.restore_packet,
            }
        )


def evidence_set_digest(evidence: Iterable[DriftEvidence]) -> str:
    payload = []
    for item in sorted(evidence, key=lambda row: row.evidence_id):
        payload.append(
            {
                "evidence_id": item.evidence_id,
                "dimension_id": item.dimension_id,
                "drift_score": float(item.drift_score),
                "independence": item.independence.name,
                "source_bindings": [asdict(binding) for binding in item.source_bindings],
                "execution_id": item.execution_id,
            }
        )
    return canonical_digest(payload)


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()
