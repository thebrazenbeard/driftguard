from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
import math
from typing import Any

from .model import (
    MonitoredSubject,
    SaveState,
    SourceBinding,
    canonical_digest,
    require_sha256_digest,
)


class SequentialStatus(StrEnum):
    MONITORING = "MONITORING"
    ALARM = "ALARM"
    SKIPPED_UNKNOWN = "SKIPPED_UNKNOWN"


def _nonempty(value: Any, label: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{label} must be a non-empty exact string")
    return value


def _unit(value: Any, label: str) -> float:
    if type(value) not in (int, float) or isinstance(value, bool):
        raise ValueError(f"{label} must be numeric")
    value = float(value)
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{label} must be finite and within [0, 1]")
    return value


@dataclass(frozen=True, order=True)
class CusumDimensionPolicy:
    dimension_id: str
    baseline_mean: float
    allowance: float
    alarm_threshold: float

    def __post_init__(self) -> None:
        _nonempty(self.dimension_id, "CUSUM dimension id")
        _unit(self.baseline_mean, "CUSUM baseline mean")
        _unit(self.allowance, "CUSUM allowance")
        if (
            type(self.alarm_threshold) not in (int, float)
            or isinstance(self.alarm_threshold, bool)
        ):
            raise ValueError("CUSUM alarm threshold must be numeric")
        threshold = float(self.alarm_threshold)
        if not math.isfinite(threshold) or threshold <= 0.0:
            raise ValueError(
                "CUSUM alarm threshold must be finite and > 0"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "dimension_id": self.dimension_id,
            "baseline_mean": float(self.baseline_mean),
            "allowance": float(self.allowance),
            "alarm_threshold": float(self.alarm_threshold),
        }


@dataclass(frozen=True)
class SequentialDetectorSpec:
    detector_id: str
    session_id: str
    state_digest: str
    measurement_digest: str
    subject_digest: str
    subject_epoch: int
    calibration: SourceBinding
    calibration_digest: str
    dimensions: tuple[CusumDimensionPolicy, ...]

    def __post_init__(self) -> None:
        _nonempty(self.detector_id, "detector id")
        _nonempty(self.session_id, "detector session id")
        require_sha256_digest(self.state_digest, "detector state digest")
        require_sha256_digest(
            self.measurement_digest,
            "detector measurement digest",
        )
        require_sha256_digest(
            self.subject_digest,
            "detector subject digest",
        )
        if (
            type(self.subject_epoch) is not int
            or isinstance(self.subject_epoch, bool)
            or self.subject_epoch < 0
        ):
            raise ValueError(
                "detector subject epoch must be a non-negative integer"
            )
        if type(self.calibration) is not SourceBinding:
            raise ValueError(
                "detector calibration must be exact SourceBinding"
            )
        require_sha256_digest(
            self.calibration_digest,
            "detector calibration digest",
        )
        if type(self.dimensions) is not tuple or not self.dimensions:
            raise ValueError(
                "detector dimensions must be a non-empty tuple"
            )
        if any(
            type(item) is not CusumDimensionPolicy
            for item in self.dimensions
        ):
            raise ValueError(
                "detector dimensions must contain exact "
                "CusumDimensionPolicy values"
            )
        ids = [item.dimension_id for item in self.dimensions]
        if len(ids) != len(set(ids)):
            raise ValueError("detector dimension ids must be unique")

    def payload(self) -> dict[str, Any]:
        return {
            "schema": "DRIFTGUARD_SEQUENTIAL_CUSUM_SPEC_V1",
            "detector_id": self.detector_id,
            "session_id": self.session_id,
            "state_digest": self.state_digest,
            "measurement_digest": self.measurement_digest,
            "subject_digest": self.subject_digest,
            "subject_epoch": self.subject_epoch,
            "calibration": asdict(self.calibration),
            "calibration_digest": self.calibration_digest,
            "dimensions": [
                item.payload()
                for item in sorted(
                    self.dimensions,
                    key=lambda row: row.dimension_id,
                )
            ],
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.payload())

    def validate_runtime(
        self,
        *,
        state: SaveState,
        subject: MonitoredSubject,
    ) -> None:
        if type(state) is not SaveState:
            raise ValueError("detector state must be exact SaveState")
        if type(subject) is not MonitoredSubject:
            raise ValueError(
                "detector subject must be exact MonitoredSubject"
            )
        if state.digest != self.state_digest:
            raise ValueError("detector state digest mismatch")
        if state.measurement_digest != self.measurement_digest:
            raise ValueError("detector measurement digest mismatch")
        if subject.configuration_digest != self.subject_digest:
            raise ValueError("detector subject digest mismatch")
        if subject.epoch != self.subject_epoch:
            raise ValueError("detector subject epoch mismatch")
        state_dimensions = {item.dimension_id for item in state.dimensions}
        policy_dimensions = {
            item.dimension_id for item in self.dimensions
        }
        if state_dimensions != policy_dimensions:
            raise ValueError(
                "detector dimensions must exactly match state dimensions"
            )


@dataclass(frozen=True)
class SequentialDetectionReceipt:
    detector_id: str
    spec_digest: str
    session_id: str
    generation_before: int
    generation_after: int
    evaluation_event_id: int
    evaluation_digest: str
    turn_index: int
    status: SequentialStatus
    observation_count: int
    dimension_scores: tuple[tuple[str, float], ...]
    cusum_values: tuple[tuple[str, float], ...]
    alarm_dimensions: tuple[str, ...]
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        _nonempty(self.detector_id, "receipt detector id")
        require_sha256_digest(self.spec_digest, "receipt spec digest")
        _nonempty(self.session_id, "receipt session id")
        for value, label in (
            (self.generation_before, "receipt generation before"),
            (self.generation_after, "receipt generation after"),
            (self.evaluation_event_id, "receipt evaluation event id"),
            (self.turn_index, "receipt turn index"),
            (self.observation_count, "receipt observation count"),
        ):
            if type(value) is not int or isinstance(value, bool) or value < 0:
                raise ValueError(f"{label} must be a non-negative integer")
        if self.generation_after != self.generation_before + 1:
            raise ValueError(
                "receipt generation must advance exactly one"
            )
        require_sha256_digest(
            self.evaluation_digest,
            "receipt evaluation digest",
        )
        if type(self.status) is not SequentialStatus:
            raise ValueError("receipt status must be SequentialStatus")
        if type(self.reasons) is not tuple or not self.reasons:
            raise ValueError("receipt reasons must be a non-empty tuple")

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "schema": "DRIFTGUARD_SEQUENTIAL_CUSUM_RECEIPT_V1",
                "detector_id": self.detector_id,
                "spec_digest": self.spec_digest,
                "session_id": self.session_id,
                "generation_before": self.generation_before,
                "generation_after": self.generation_after,
                "evaluation_event_id": self.evaluation_event_id,
                "evaluation_digest": self.evaluation_digest,
                "turn_index": self.turn_index,
                "status": self.status.value,
                "observation_count": self.observation_count,
                "dimension_scores": self.dimension_scores,
                "cusum_values": self.cusum_values,
                "alarm_dimensions": self.alarm_dimensions,
                "reasons": self.reasons,
            }
        )


def advance_cusum(
    *,
    policies: tuple[CusumDimensionPolicy, ...],
    previous: tuple[tuple[str, float], ...],
    scores: tuple[tuple[str, float], ...],
    prior_alarms: tuple[str, ...],
) -> tuple[
    tuple[tuple[str, float], ...],
    tuple[str, ...],
]:
    policy_by_id = {item.dimension_id: item for item in policies}
    previous_by_id = dict(previous)
    scores_by_id = dict(scores)
    if set(policy_by_id) != set(scores_by_id):
        raise ValueError(
            "CUSUM score dimensions must exactly match detector policy"
        )
    if set(previous_by_id) != set(policy_by_id):
        raise ValueError(
            "CUSUM prior state dimensions must exactly match detector policy"
        )

    updated = []
    alarmed = set(prior_alarms)
    for dimension_id in sorted(policy_by_id):
        policy = policy_by_id[dimension_id]
        score = _unit(
            scores_by_id[dimension_id],
            f"CUSUM score {dimension_id}",
        )
        prior = float(previous_by_id[dimension_id])
        value = max(
            0.0,
            prior
            + score
            - float(policy.baseline_mean)
            - float(policy.allowance),
        )
        # Canonicalize tiny floating representation noise without changing
        # the governed score scale materially.
        value = round(value, 12)
        updated.append((dimension_id, value))
        if value >= float(policy.alarm_threshold):
            alarmed.add(dimension_id)

    return tuple(updated), tuple(sorted(alarmed))
