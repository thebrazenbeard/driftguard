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


class MeasurementMode(StrEnum):
    LEGACY_WEIGHTED = "LEGACY_WEIGHTED"
    CALIBRATED_QUORUM = "CALIBRATED_QUORUM"


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
    calibration: SourceBinding | None = None
    calibration_digest: str | None = None
    correlation_group: str | None = None
    score_scale: str | None = None

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
        if self.calibration is not None and type(self.calibration) is not SourceBinding:
            raise ValueError("probe calibration must be exact SourceBinding or None")
        if self.calibration_digest is not None:
            require_sha256_digest(
                self.calibration_digest,
                "probe calibration digest",
            )
        if self.correlation_group is not None:
            _require_nonempty_str(self.correlation_group, "probe correlation group")
        if self.score_scale is not None:
            _require_nonempty_str(self.score_scale, "probe score scale")

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "ProbeSource":
        if type(data) is not dict:
            raise ValueError("probe source must be an object")
        dimensions = data.get("dimensions")
        if type(dimensions) is not list:
            raise ValueError("probe dimensions must be a JSON array")
        calibration = data.get("calibration")
        if calibration is not None and type(calibration) is not dict:
            raise ValueError("probe calibration must be an object")
        return cls(
            binding=SourceBinding(
                ref=data.get("ref"),
                version=data.get("version"),
            ),
            max_independence=EvidenceIndependence.parse(
                data.get("max_independence")
            ),
            dimensions=tuple(dimensions),
            calibration=(
                SourceBinding.from_mapping(calibration)
                if calibration is not None
                else None
            ),
            calibration_digest=data.get("calibration_digest"),
            correlation_group=data.get("correlation_group"),
            score_scale=data.get("score_scale"),
        )


@dataclass(frozen=True)
class BehaviorDimension:
    dimension_id: str
    description: str
    weight: float = 1.0
    critical: bool = False
    min_independence: EvidenceIndependence = EvidenceIndependence.SEPARATE_CONTEXT
    min_sources: int = 1
    min_correlation_groups: int = 1
    score_scale: str | None = None
    warn_threshold: float | None = None
    reload_threshold: float | None = None
    critical_reload_threshold: float | None = None

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
        if type(self.min_sources) is not int or self.min_sources < 1:
            raise ValueError("min_sources must be an integer >= 1")
        if (
            type(self.min_correlation_groups) is not int
            or self.min_correlation_groups < 1
        ):
            raise ValueError("min_correlation_groups must be an integer >= 1")
        if self.min_correlation_groups > self.min_sources:
            raise ValueError("min_correlation_groups cannot exceed min_sources")
        if self.score_scale is not None:
            _require_nonempty_str(self.score_scale, "dimension score scale")
        for value, label in (
            (self.warn_threshold, "dimension warn threshold"),
            (self.reload_threshold, "dimension reload threshold"),
            (self.critical_reload_threshold, "dimension critical reload threshold"),
        ):
            if value is not None:
                _require_unit_interval(value, label)
        if (
            self.warn_threshold is not None
            and self.reload_threshold is not None
            and float(self.warn_threshold) >= float(self.reload_threshold)
        ):
            raise ValueError(
                "dimension warn threshold must be lower than reload threshold"
            )

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
            min_sources=data.get("min_sources", 1),
            min_correlation_groups=data.get("min_correlation_groups", 1),
            score_scale=data.get("score_scale"),
            warn_threshold=data.get("warn_threshold"),
            reload_threshold=data.get("reload_threshold"),
            critical_reload_threshold=data.get("critical_reload_threshold"),
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
    measurement_mode: MeasurementMode = MeasurementMode.LEGACY_WEIGHTED

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
        if type(self.measurement_mode) is not MeasurementMode:
            raise ValueError("measurement_mode must be exact MeasurementMode")

        if self.measurement_mode is MeasurementMode.CALIBRATED_QUORUM:
            dimension_by_id = {
                item.dimension_id: item for item in self.dimensions
            }
            for dimension in self.dimensions:
                if float(dimension.weight) != 1.0:
                    raise ValueError(
                        "calibrated quorum dimensions do not permit legacy weights: "
                        f"{dimension.dimension_id}"
                    )
                if dimension.score_scale is None:
                    raise ValueError(
                        "calibrated quorum dimensions require explicit score_scale: "
                        f"{dimension.dimension_id}"
                    )
                if (
                    dimension.warn_threshold is None
                    or dimension.reload_threshold is None
                ):
                    raise ValueError(
                        "calibrated quorum dimensions require explicit "
                        "warn_threshold and reload_threshold: "
                        f"{dimension.dimension_id}"
                    )
                if (
                    dimension.critical
                    and dimension.critical_reload_threshold is None
                ):
                    raise ValueError(
                        "critical calibrated dimensions require explicit "
                        "critical_reload_threshold: "
                        f"{dimension.dimension_id}"
                    )
            for source in self.probe_sources:
                if source.calibration is None:
                    raise ValueError(
                        "calibrated quorum probe sources require calibration: "
                        f"{source.binding.ref}@{source.binding.version}"
                    )
                if source.calibration_digest is None:
                    raise ValueError(
                        "calibrated quorum probe sources require calibration_digest: "
                        f"{source.binding.ref}@{source.binding.version}"
                    )
                if source.correlation_group is None:
                    raise ValueError(
                        "calibrated quorum probe sources require correlation_group: "
                        f"{source.binding.ref}@{source.binding.version}"
                    )
                if source.score_scale is None:
                    raise ValueError(
                        "calibrated quorum probe sources require score_scale: "
                        f"{source.binding.ref}@{source.binding.version}"
                    )
                for dimension_id in source.dimensions:
                    dimension = dimension_by_id[dimension_id]
                    if source.score_scale != dimension.score_scale:
                        raise ValueError(
                            "probe score_scale must match governed dimension scale: "
                            f"{dimension_id}"
                        )
            for dimension in self.dimensions:
                eligible = [
                    source
                    for source in self.probe_sources
                    if dimension.dimension_id in source.dimensions
                    and source.max_independence >= dimension.min_independence
                ]
                if len(eligible) < dimension.min_sources:
                    raise ValueError(
                        "dimension has insufficient eligible calibrated sources: "
                        f"{dimension.dimension_id}"
                    )
                groups = {
                    source.correlation_group
                    for source in eligible
                    if source.correlation_group is not None
                }
                if len(groups) < dimension.min_correlation_groups:
                    raise ValueError(
                        "dimension has insufficient eligible correlation groups: "
                        f"{dimension.dimension_id}"
                    )

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
            measurement_mode=MeasurementMode(
                data.get("measurement_mode", MeasurementMode.LEGACY_WEIGHTED.value)
            ),
        )

    def behavior_payload(self) -> dict[str, Any]:
        return {
            "dimensions": [
                {
                    "dimension_id": item.dimension_id,
                    "description": item.description,
                }
                for item in self.dimensions
            ],
        }

    def control_policy_payload(self) -> dict[str, Any]:
        return {
            "restore_text": self.restore_text,
        }

    def measurement_payload(self) -> dict[str, Any]:
        dimensions = []
        for item in self.dimensions:
            row = {
                "dimension_id": item.dimension_id,
                "min_independence": item.min_independence.name,
                "min_sources": item.min_sources,
                "min_correlation_groups": item.min_correlation_groups,
                "score_scale": item.score_scale,
            }
            if self.measurement_mode is MeasurementMode.LEGACY_WEIGHTED:
                row["weight"] = float(item.weight)
                row["critical"] = item.critical
            dimensions.append(row)
        return {
            "measurement_mode": self.measurement_mode.value,
            "dimensions": dimensions,
            "probe_sources": [
                {
                    "ref": item.binding.ref,
                    "version": item.binding.version,
                    "max_independence": item.max_independence.name,
                    "dimensions": list(item.dimensions),
                    "calibration": (
                        asdict(item.calibration)
                        if item.calibration is not None
                        else None
                    ),
                    "calibration_digest": item.calibration_digest,
                    "correlation_group": item.correlation_group,
                    "score_scale": item.score_scale,
                }
                for item in self.probe_sources
            ],
        }

    @property
    def behavior_digest(self) -> str:
        return canonical_digest(self.behavior_payload())

    @property
    def measurement_digest(self) -> str:
        return canonical_digest(self.measurement_payload())

    @property
    def control_policy_digest(self) -> str:
        return canonical_digest(self.control_policy_payload())

    def detection_policy_payload(self) -> dict[str, Any]:
        if self.measurement_mode is MeasurementMode.LEGACY_WEIGHTED:
            return asdict(self.policy)
        return {
            "measurement_mode": self.measurement_mode.value,
            "dimensions": [
                {
                    "dimension_id": item.dimension_id,
                    "critical": item.critical,
                    "warn_threshold": float(item.warn_threshold),
                    "reload_threshold": float(item.reload_threshold),
                    "critical_reload_threshold": (
                        float(item.critical_reload_threshold)
                        if item.critical_reload_threshold is not None
                        else None
                    ),
                }
                for item in self.dimensions
            ],
            "max_turns_without_reload": self.policy.max_turns_without_reload,
            "reload_cooldown_turns": self.policy.reload_cooldown_turns,
        }

    @property
    def detection_policy_digest(self) -> str:
        return canonical_digest(self.detection_policy_payload())

    def canonical_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "state_id": self.state_id,
            "version": self.version,
            "restore_text": self.restore_text,
            "dimensions": [],
            "probe_sources": [],
            "policy": asdict(self.policy),
        }
        for item in self.dimensions:
            dimension = {
                "dimension_id": item.dimension_id,
                "description": item.description,
                "critical": item.critical,
                "min_independence": item.min_independence.name,
            }
            if self.measurement_mode is MeasurementMode.LEGACY_WEIGHTED:
                dimension["weight"] = float(item.weight)
            if item.min_sources != 1:
                dimension["min_sources"] = item.min_sources
            if item.min_correlation_groups != 1:
                dimension["min_correlation_groups"] = item.min_correlation_groups
            if item.score_scale is not None:
                dimension["score_scale"] = item.score_scale
            if item.warn_threshold is not None:
                dimension["warn_threshold"] = float(item.warn_threshold)
            if item.reload_threshold is not None:
                dimension["reload_threshold"] = float(item.reload_threshold)
            if item.critical_reload_threshold is not None:
                dimension["critical_reload_threshold"] = float(
                    item.critical_reload_threshold
                )
            payload["dimensions"].append(dimension)
        for item in self.probe_sources:
            source = {
                "ref": item.binding.ref,
                "version": item.binding.version,
                "max_independence": item.max_independence.name,
                "dimensions": list(item.dimensions),
            }
            if item.calibration is not None:
                source["calibration"] = asdict(item.calibration)
            if item.calibration_digest is not None:
                source["calibration_digest"] = item.calibration_digest
            if item.correlation_group is not None:
                source["correlation_group"] = item.correlation_group
            if item.score_scale is not None:
                source["score_scale"] = item.score_scale
            payload["probe_sources"].append(source)
        if self.measurement_mode is not MeasurementMode.LEGACY_WEIGHTED:
            payload["measurement_mode"] = self.measurement_mode.value
        return payload

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
    behavioral_decision: Decision | None = None
    evidence_trace: tuple[
        tuple[str, str, str, str, float, str, str], ...
    ] = ()

    @property
    def digest(self) -> str:
        payload = {
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
        if self.behavioral_decision is not None:
            payload["behavioral_decision"] = self.behavioral_decision.value
        if self.evidence_trace:
            payload["evidence_trace"] = self.evidence_trace
        return canonical_digest(payload)


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
