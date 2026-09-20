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


class RecoveryStatus(StrEnum):
    VERIFIED_STABLE = "VERIFIED_STABLE"
    NOT_STABLE = "NOT_STABLE"
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


def is_sha256_digest(value: Any) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def require_sha256_digest(value: Any, label: str) -> str:
    if not is_sha256_digest(value):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
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
        if type(data) is not dict:
            raise ValueError("source binding must be an object")
        return cls(ref=data.get("ref"), version=data.get("version"))


@dataclass(frozen=True)
class ProbeSource:
    binding: SourceBinding
    max_independence: EvidenceIndependence
    dimensions: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.binding) is not SourceBinding:
            raise ValueError("probe binding must be exact SourceBinding")
        if type(self.max_independence) is not EvidenceIndependence:
            raise ValueError("probe max_independence must be EvidenceIndependence")
        if type(self.dimensions) is not tuple or not self.dimensions:
            raise ValueError("probe dimensions must be a non-empty tuple")
        if any(type(item) is not str or not item for item in self.dimensions):
            raise ValueError("probe dimensions must contain non-empty exact strings")
        if len(self.dimensions) != len(set(self.dimensions)):
            raise ValueError("probe dimensions must be unique")

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "ProbeSource":
        if type(data) is not dict:
            raise ValueError("probe source must be an object")
        dimensions = data.get("dimensions")
        if type(dimensions) is not list:
            raise ValueError("probe dimensions must be a JSON array")
        return cls(
            binding=SourceBinding(
                ref=data.get("ref"),
                version=data.get("version"),
            ),
            max_independence=EvidenceIndependence.parse(
                data.get("max_independence")
            ),
            dimensions=tuple(dimensions),
        )


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
        if type(data) is not dict:
            raise ValueError("dimension must be an object")
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

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> "DriftPolicy":
        data = data or {}
        if type(data) is not dict:
            raise ValueError("policy must be an object")
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
    probe_sources: tuple[ProbeSource, ...]
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
        dimension_ids = set(ids)
        if len(ids) != len(dimension_ids):
            raise ValueError("dimension ids must be unique")
        if type(self.probe_sources) is not tuple or not self.probe_sources:
            raise ValueError("probe_sources must be a non-empty tuple")
        if any(type(item) is not ProbeSource for item in self.probe_sources):
            raise ValueError("probe_sources must contain exact ProbeSource values")
        bindings = [item.binding for item in self.probe_sources]
        if len(bindings) != len(set(bindings)):
            raise ValueError("probe source bindings must be unique")
        for source in self.probe_sources:
            unknown = set(source.dimensions) - dimension_ids
            if unknown:
                raise ValueError(
                    f"probe source references unknown dimensions: {sorted(unknown)}"
                )
        for dimension in self.dimensions:
            eligible = [
                source
                for source in self.probe_sources
                if dimension.dimension_id in source.dimensions
                and source.max_independence >= dimension.min_independence
            ]
            if not eligible:
                raise ValueError(
                    f"dimension has no probe source meeting independence requirement: "
                    f"{dimension.dimension_id}"
                )
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
            probe_sources=tuple(
                ProbeSource.from_mapping(item)
                for item in data.get("probe_sources", ())
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
            "probe_sources": [
                {
                    "ref": item.binding.ref,
                    "version": item.binding.version,
                    "max_independence": item.max_independence.name,
                    "dimensions": list(item.dimensions),
                }
                for item in self.probe_sources
            ],
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
    state_digest: str
    observation_digest: str
    turn_index: int

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
        require_sha256_digest(self.state_digest, "evidence state digest")
        require_sha256_digest(self.observation_digest, "evidence observation digest")
        if type(self.turn_index) is not int or self.turn_index < 0:
            raise ValueError("evidence turn_index must be a non-negative integer")

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "DriftEvidence":
        if type(data) is not dict:
            raise ValueError("evidence must be an object")
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
            state_digest=data.get("state_digest"),
            observation_digest=data.get("observation_digest"),
            turn_index=data.get("turn_index"),
        )


@dataclass(frozen=True)
class ReloadAcknowledgement:
    ack_id: str
    evaluation_digest: str
    state_digest: str
    turn_index: int

    def __post_init__(self) -> None:
        _require_nonempty_str(self.ack_id, "ack id")
        require_sha256_digest(self.evaluation_digest, "ack evaluation digest")
        require_sha256_digest(self.state_digest, "ack state digest")
        if type(self.turn_index) is not int or self.turn_index < 0:
            raise ValueError("ack turn_index must be a non-negative integer")

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "ReloadAcknowledgement":
        if type(data) is not dict:
            raise ValueError("reload acknowledgement must be an object")
        return cls(
            ack_id=data.get("ack_id"),
            evaluation_digest=data.get("evaluation_digest"),
            state_digest=data.get("state_digest"),
            turn_index=data.get("turn_index"),
        )


@dataclass(frozen=True)
class Evaluation:
    decision: Decision
    reload_required: bool
    aggregate_drift: float | None
    dimension_scores: tuple[tuple[str, float], ...]
    reasons: tuple[str, ...]
    state_digest: str
    observation_digest: str
    evidence_digest: str
    turn_index: int
    generation: int
    restore_packet: str | None = None

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "decision": self.decision.value,
                "reload_required": self.reload_required,
                "aggregate_drift": self.aggregate_drift,
                "dimension_scores": self.dimension_scores,
                "reasons": self.reasons,
                "state_digest": self.state_digest,
                "observation_digest": self.observation_digest,
                "evidence_digest": self.evidence_digest,
                "turn_index": self.turn_index,
                "generation": self.generation,
                "restore_packet": self.restore_packet,
            }
        )


@dataclass(frozen=True)
class RecoveryVerification:
    ack_id: str
    acknowledged_evaluation_digest: str
    replay_evaluation_digest: str
    state_digest: str
    observation_digest: str
    evidence_digest: str
    turn_index: int
    status: RecoveryStatus
    reasons: tuple[str, ...]
    generation: int

    def __post_init__(self) -> None:
        _require_nonempty_str(self.ack_id, "recovery acknowledgement id")
        require_sha256_digest(
            self.acknowledged_evaluation_digest,
            "recovery acknowledged evaluation digest",
        )
        require_sha256_digest(
            self.replay_evaluation_digest,
            "recovery replay evaluation digest",
        )
        require_sha256_digest(self.state_digest, "recovery state digest")
        require_sha256_digest(
            self.observation_digest,
            "recovery observation digest",
        )
        require_sha256_digest(self.evidence_digest, "recovery evidence digest")
        if type(self.turn_index) is not int or self.turn_index < 0:
            raise ValueError(
                "recovery turn_index must be a non-negative integer"
            )
        if type(self.status) is not RecoveryStatus:
            raise ValueError("recovery status must be exact RecoveryStatus")
        if type(self.reasons) is not tuple or not self.reasons:
            raise ValueError("recovery reasons must be a non-empty tuple")
        if any(type(item) is not str or not item for item in self.reasons):
            raise ValueError(
                "recovery reasons must contain non-empty exact strings"
            )
        if type(self.generation) is not int or self.generation < 0:
            raise ValueError(
                "recovery generation must be a non-negative integer"
            )

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "ack_id": self.ack_id,
                "acknowledged_evaluation_digest": (
                    self.acknowledged_evaluation_digest
                ),
                "replay_evaluation_digest": self.replay_evaluation_digest,
                "state_digest": self.state_digest,
                "observation_digest": self.observation_digest,
                "evidence_digest": self.evidence_digest,
                "turn_index": self.turn_index,
                "status": self.status.value,
                "reasons": self.reasons,
                "generation": self.generation,
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
                "state_digest": item.state_digest,
                "observation_digest": item.observation_digest,
                "turn_index": item.turn_index,
            }
        )
    return canonical_digest(payload)


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def raw_bytes_digest(data: bytes) -> str:
    return sha256(data).hexdigest()
