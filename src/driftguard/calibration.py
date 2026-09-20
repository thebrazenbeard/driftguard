from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math
from typing import Any

from .model import canonical_digest, require_sha256_digest
from .sequential import SequentialDetectorSpec, advance_cusum


_WILSON_Z_95 = 1.959963984540054
_QUALIFICATION_RECEIPT_TOKEN = object()


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


def _wilson_from_counts(
    successes: int,
    trials: int,
) -> tuple[float, float, float]:
    if (
        type(successes) is not int
        or isinstance(successes, bool)
        or type(trials) is not int
        or isinstance(trials, bool)
        or trials < 1
        or not 0 <= successes <= trials
    ):
        raise ValueError("invalid binomial counts")
    p = successes / trials
    z2 = _WILSON_Z_95 * _WILSON_Z_95
    denominator = 1.0 + z2 / trials
    center = (p + z2 / (2.0 * trials)) / denominator
    margin = (
        _WILSON_Z_95
        * math.sqrt(
            (p * (1.0 - p) / trials)
            + (z2 / (4.0 * trials * trials))
        )
        / denominator
    )
    return (
        round(p, 12),
        round(max(0.0, center - margin), 12),
        round(min(1.0, center + margin), 12),
    )


class CalibrationCorpusRole(StrEnum):
    DESIGN = "DESIGN"
    HOLDOUT_QUALIFICATION = "HOLDOUT_QUALIFICATION"


class CalibrationTrajectoryRegime(StrEnum):
    STABLE = "STABLE"
    SHIFTED = "SHIFTED"


class CalibrationDisposition(StrEnum):
    DESIGN_CHARACTERIZATION = "DESIGN_CHARACTERIZATION"
    PASS = "PASS"
    FAIL = "FAIL"


@dataclass(frozen=True)
class CalibrationTrajectory:
    trajectory_id: str
    family_id: str
    regime: CalibrationTrajectoryRegime
    samples: tuple[tuple[tuple[str, float], ...], ...]
    shift_index: int | None = None
    shift_dimensions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _nonempty(self.trajectory_id, "trajectory id")
        _nonempty(self.family_id, "family id")
        if type(self.regime) is not CalibrationTrajectoryRegime:
            raise ValueError(
                "trajectory regime must be exact CalibrationTrajectoryRegime"
            )
        if type(self.samples) is not tuple or not self.samples:
            raise ValueError("trajectory samples must be a non-empty tuple")

        expected_dimensions: set[str] | None = None
        for index, sample in enumerate(self.samples):
            if type(sample) is not tuple or not sample:
                raise ValueError(
                    f"trajectory sample {index} must be a non-empty tuple"
                )
            dimensions: list[str] = []
            for dimension_id, score in sample:
                _nonempty(dimension_id, "sample dimension id")
                _unit(score, f"sample score {dimension_id}")
                dimensions.append(dimension_id)
            if len(dimensions) != len(set(dimensions)):
                raise ValueError(
                    f"trajectory sample {index} dimension ids must be unique"
                )
            current = set(dimensions)
            if expected_dimensions is None:
                expected_dimensions = current
            elif current != expected_dimensions:
                raise ValueError(
                    "trajectory sample dimension sets must remain constant"
                )

        if self.regime is CalibrationTrajectoryRegime.STABLE:
            if self.shift_index is not None or self.shift_dimensions:
                raise ValueError(
                    "stable trajectory cannot declare shift metadata"
                )
        else:
            if (
                type(self.shift_index) is not int
                or isinstance(self.shift_index, bool)
                or not 0 <= self.shift_index < len(self.samples)
            ):
                raise ValueError(
                    "shifted trajectory requires valid zero-based shift_index"
                )
            if (
                type(self.shift_dimensions) is not tuple
                or not self.shift_dimensions
            ):
                raise ValueError(
                    "shifted trajectory requires shift_dimensions"
                )
            if any(
                type(item) is not str or not item
                for item in self.shift_dimensions
            ):
                raise ValueError(
                    "shift_dimensions must contain non-empty exact strings"
                )
            if len(self.shift_dimensions) != len(set(self.shift_dimensions)):
                raise ValueError("shift_dimensions must be unique")
            if not set(self.shift_dimensions).issubset(
                expected_dimensions or set()
            ):
                raise ValueError(
                    "shift_dimensions must exist in trajectory samples"
                )

    def payload(self) -> dict[str, Any]:
        return {
            "trajectory_id": self.trajectory_id,
            "family_id": self.family_id,
            "regime": self.regime.value,
            "samples": [
                [
                    [dimension_id, float(score)]
                    for dimension_id, score in sorted(sample)
                ]
                for sample in self.samples
            ],
            "shift_index": self.shift_index,
            "shift_dimensions": sorted(self.shift_dimensions),
        }


@dataclass(frozen=True)
class CalibrationCorpus:
    corpus_id: str
    version: str
    role: CalibrationCorpusRole
    trajectories: tuple[CalibrationTrajectory, ...]

    def __post_init__(self) -> None:
        _nonempty(self.corpus_id, "corpus id")
        _nonempty(self.version, "corpus version")
        if type(self.role) is not CalibrationCorpusRole:
            raise ValueError("corpus role must be exact CalibrationCorpusRole")
        if type(self.trajectories) is not tuple or not self.trajectories:
            raise ValueError("corpus trajectories must be a non-empty tuple")
        if any(
            type(item) is not CalibrationTrajectory
            for item in self.trajectories
        ):
            raise ValueError(
                "corpus trajectories must contain exact CalibrationTrajectory"
            )
        ids = [item.trajectory_id for item in self.trajectories]
        if len(ids) != len(set(ids)):
            raise ValueError("trajectory ids must be unique")

    def payload(self) -> dict[str, Any]:
        return {
            "schema": "DRIFTGUARD_CALIBRATION_CORPUS_V1",
            "corpus_id": self.corpus_id,
            "version": self.version,
            "role": self.role.value,
            "trajectories": [
                item.payload()
                for item in sorted(
                    self.trajectories,
                    key=lambda row: row.trajectory_id,
                )
            ],
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.payload())


@dataclass(frozen=True, order=True)
class CalibrationFamilyPolicy:
    family_id: str
    minimum_stable_trajectories: int
    minimum_shifted_trajectories: int
    stable_horizon_observations: int
    pre_shift_horizon_observations: int
    post_shift_horizon_observations: int
    maximum_stable_false_alarm_rate: float
    maximum_pre_shift_false_alarm_rate: float
    maximum_wrong_dimension_alarm_rate: float
    minimum_detection_rate: float
    maximum_mean_detection_delay: float

    def __post_init__(self) -> None:
        _nonempty(self.family_id, "family policy id")
        for value, label in (
            (
                self.minimum_stable_trajectories,
                "minimum stable trajectories",
            ),
            (
                self.minimum_shifted_trajectories,
                "minimum shifted trajectories",
            ),
            (
                self.stable_horizon_observations,
                "stable horizon observations",
            ),
            (
                self.pre_shift_horizon_observations,
                "pre-shift horizon observations",
            ),
            (
                self.post_shift_horizon_observations,
                "post-shift horizon observations",
            ),
        ):
            if type(value) is not int or isinstance(value, bool) or value < 1:
                raise ValueError(f"{label} must be an integer >= 1")
        _unit(
            self.maximum_stable_false_alarm_rate,
            "maximum stable false alarm rate",
        )
        _unit(
            self.maximum_pre_shift_false_alarm_rate,
            "maximum pre-shift false alarm rate",
        )
        _unit(
            self.maximum_wrong_dimension_alarm_rate,
            "maximum wrong-dimension alarm rate",
        )
        _unit(self.minimum_detection_rate, "minimum detection rate")
        if (
            type(self.maximum_mean_detection_delay) not in (int, float)
            or isinstance(self.maximum_mean_detection_delay, bool)
            or not math.isfinite(float(self.maximum_mean_detection_delay))
            or float(self.maximum_mean_detection_delay) < 0
        ):
            raise ValueError(
                "maximum mean detection delay must be finite and >= 0"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "family_id": self.family_id,
            "minimum_stable_trajectories": (
                self.minimum_stable_trajectories
            ),
            "minimum_shifted_trajectories": (
                self.minimum_shifted_trajectories
            ),
            "stable_horizon_observations": (
                self.stable_horizon_observations
            ),
            "pre_shift_horizon_observations": (
                self.pre_shift_horizon_observations
            ),
            "post_shift_horizon_observations": (
                self.post_shift_horizon_observations
            ),
            "maximum_stable_false_alarm_rate": float(
                self.maximum_stable_false_alarm_rate
            ),
            "maximum_pre_shift_false_alarm_rate": float(
                self.maximum_pre_shift_false_alarm_rate
            ),
            "maximum_wrong_dimension_alarm_rate": float(
                self.maximum_wrong_dimension_alarm_rate
            ),
            "minimum_detection_rate": float(self.minimum_detection_rate),
            "maximum_mean_detection_delay": float(
                self.maximum_mean_detection_delay
            ),
        }


@dataclass(frozen=True)
class CalibrationPlan:
    plan_id: str
    detector_spec_digest: str
    corpus_digest: str
    corpus_role: CalibrationCorpusRole
    family_policies: tuple[CalibrationFamilyPolicy, ...]

    def __post_init__(self) -> None:
        _nonempty(self.plan_id, "calibration plan id")
        require_sha256_digest(
            self.detector_spec_digest,
            "calibration detector spec digest",
        )
        require_sha256_digest(
            self.corpus_digest,
            "calibration corpus digest",
        )
        if type(self.corpus_role) is not CalibrationCorpusRole:
            raise ValueError(
                "calibration corpus role must be exact CalibrationCorpusRole"
            )
        if type(self.family_policies) is not tuple or not self.family_policies:
            raise ValueError("family_policies must be a non-empty tuple")
        if any(
            type(item) is not CalibrationFamilyPolicy
            for item in self.family_policies
        ):
            raise ValueError(
                "family_policies must contain exact CalibrationFamilyPolicy"
            )
        ids = [item.family_id for item in self.family_policies]
        if len(ids) != len(set(ids)):
            raise ValueError("family policy ids must be unique")

    def payload(self) -> dict[str, Any]:
        return {
            "schema": "DRIFTGUARD_CALIBRATION_PLAN_V1",
            "plan_id": self.plan_id,
            "detector_spec_digest": self.detector_spec_digest,
            "corpus_digest": self.corpus_digest,
            "corpus_role": self.corpus_role.value,
            "family_policies": [
                item.payload()
                for item in sorted(
                    self.family_policies,
                    key=lambda row: row.family_id,
                )
            ],
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.payload())


@dataclass(frozen=True)
class BinomialEstimate:
    successes: int
    trials: int
    rate: float
    wilson_low_95: float
    wilson_high_95: float

    def __post_init__(self) -> None:
        expected = _wilson_from_counts(self.successes, self.trials)
        observed = (
            self.rate,
            self.wilson_low_95,
            self.wilson_high_95,
        )
        if any(
            type(value) not in (int, float) or isinstance(value, bool)
            for value in observed
        ):
            raise ValueError("binomial estimate values must be numeric")
        observed_normalized = tuple(round(float(value), 12) for value in observed)
        if observed_normalized != expected:
            raise ValueError(
                "binomial estimate fields do not match exact Wilson calculation"
            )

    @classmethod
    def from_counts(cls, successes: int, trials: int) -> "BinomialEstimate":
        rate, low, high = _wilson_from_counts(successes, trials)
        return cls(
            successes=successes,
            trials=trials,
            rate=rate,
            wilson_low_95=low,
            wilson_high_95=high,
        )

    def payload(self) -> dict[str, Any]:
        return {
            "successes": self.successes,
            "trials": self.trials,
            "rate": self.rate,
            "wilson_low_95": self.wilson_low_95,
            "wilson_high_95": self.wilson_high_95,
        }


@dataclass(frozen=True)
class CalibrationFamilyMetrics:
    family_id: str
    stable_false_alarm: BinomialEstimate
    pre_shift_false_alarm: BinomialEstimate
    wrong_dimension_alarm: BinomialEstimate
    detection: BinomialEstimate
    stable_alarm_run_lengths: tuple[int, ...]
    detection_delays: tuple[int, ...]
    mean_detection_delay: float | None
    wrong_dimension_alarms: int
    horizon_violations: int
    failures: tuple[str, ...]
    mixed_target_wrong_dimension_alarms: int = 0

    def __post_init__(self) -> None:
        _nonempty(self.family_id, "calibration metric family id")
        for value, label in (
            (self.stable_false_alarm, "stable false alarm estimate"),
            (self.pre_shift_false_alarm, "pre-shift false alarm estimate"),
            (self.wrong_dimension_alarm, "wrong-dimension alarm estimate"),
            (self.detection, "detection estimate"),
        ):
            if type(value) is not BinomialEstimate:
                raise ValueError(f"{label} must be exact BinomialEstimate")
        shifted_trials = self.detection.trials
        if (
            self.pre_shift_false_alarm.trials != shifted_trials
            or self.wrong_dimension_alarm.trials != shifted_trials
        ):
            raise ValueError(
                "shifted-family binomial estimates must share the same trial count"
            )
        if (
            type(self.mixed_target_wrong_dimension_alarms) is not int
            or isinstance(self.mixed_target_wrong_dimension_alarms, bool)
            or self.mixed_target_wrong_dimension_alarms < 0
            or self.mixed_target_wrong_dimension_alarms
            > self.wrong_dimension_alarm.successes
            or self.mixed_target_wrong_dimension_alarms
            > self.detection.successes
        ):
            raise ValueError(
                "mixed target/wrong-dimension count must be a valid overlap"
            )
        post_shift_alarm_union = (
            self.wrong_dimension_alarm.successes
            + self.detection.successes
            - self.mixed_target_wrong_dimension_alarms
        )
        if (
            self.pre_shift_false_alarm.successes
            + post_shift_alarm_union
            > shifted_trials
        ):
            raise ValueError(
                "shifted-family first-alarm outcome counts exceed trajectory count"
            )
        if (
            type(self.stable_alarm_run_lengths) is not tuple
            or any(
                type(item) is not int or isinstance(item, bool) or item < 1
                for item in self.stable_alarm_run_lengths
            )
            or len(self.stable_alarm_run_lengths)
            != self.stable_false_alarm.successes
        ):
            raise ValueError(
                "stable alarm run lengths must match stable false-alarm count"
            )
        if (
            type(self.detection_delays) is not tuple
            or any(
                type(item) is not int or isinstance(item, bool) or item < 1
                for item in self.detection_delays
            )
            or len(self.detection_delays) != self.detection.successes
        ):
            raise ValueError(
                "detection delays must match successful detection count"
            )
        expected_mean = (
            round(sum(self.detection_delays) / len(self.detection_delays), 12)
            if self.detection_delays
            else None
        )
        if self.mean_detection_delay != expected_mean:
            raise ValueError(
                "mean detection delay does not match detection delays"
            )
        if (
            type(self.wrong_dimension_alarms) is not int
            or isinstance(self.wrong_dimension_alarms, bool)
            or self.wrong_dimension_alarms
            != self.wrong_dimension_alarm.successes
        ):
            raise ValueError(
                "wrong_dimension_alarms must match wrong-dimension estimate"
            )
        if (
            type(self.horizon_violations) is not int
            or isinstance(self.horizon_violations, bool)
            or self.horizon_violations < 0
        ):
            raise ValueError("horizon_violations must be a non-negative integer")
        if (
            type(self.failures) is not tuple
            or any(type(item) is not str or not item for item in self.failures)
            or len(self.failures) != len(set(self.failures))
        ):
            raise ValueError(
                "calibration metric failures must be a tuple of unique strings"
            )

    @property
    def passed(self) -> bool:
        return not self.failures

    def payload(self) -> dict[str, Any]:
        return {
            "family_id": self.family_id,
            "stable_false_alarm": self.stable_false_alarm.payload(),
            "pre_shift_false_alarm": self.pre_shift_false_alarm.payload(),
            "wrong_dimension_alarm": self.wrong_dimension_alarm.payload(),
            "detection": self.detection.payload(),
            "stable_alarm_run_lengths": list(
                self.stable_alarm_run_lengths
            ),
            "detection_delays": list(self.detection_delays),
            "mean_detection_delay": self.mean_detection_delay,
            "wrong_dimension_alarms": self.wrong_dimension_alarms,
            "mixed_target_wrong_dimension_alarms": (
                self.mixed_target_wrong_dimension_alarms
            ),
            "horizon_violations": self.horizon_violations,
            "failures": list(self.failures),
            "passed": self.passed,
        }


@dataclass(frozen=True, init=False)
class CalibrationQualificationReceipt:
    plan_digest: str
    corpus_digest: str
    detector_spec_digest: str
    corpus_role: CalibrationCorpusRole
    disposition: CalibrationDisposition
    family_metrics: tuple[CalibrationFamilyMetrics, ...]
    reasons: tuple[str, ...]

    def __init__(
        self,
        *,
        plan_digest: str,
        corpus_digest: str,
        detector_spec_digest: str,
        corpus_role: CalibrationCorpusRole,
        disposition: CalibrationDisposition,
        family_metrics: tuple[CalibrationFamilyMetrics, ...],
        reasons: tuple[str, ...],
        _qualification_token: object | None = None,
    ) -> None:
        if _qualification_token is not _QUALIFICATION_RECEIPT_TOKEN:
            raise ValueError(
                "CalibrationQualificationReceipt must come from qualify_calibration"
            )
        object.__setattr__(self, "plan_digest", plan_digest)
        object.__setattr__(self, "corpus_digest", corpus_digest)
        object.__setattr__(self, "detector_spec_digest", detector_spec_digest)
        object.__setattr__(self, "corpus_role", corpus_role)
        object.__setattr__(self, "disposition", disposition)
        object.__setattr__(self, "family_metrics", family_metrics)
        object.__setattr__(self, "reasons", reasons)
        self.__post_init__()

    def __post_init__(self) -> None:
        require_sha256_digest(self.plan_digest, "qualification plan digest")
        require_sha256_digest(
            self.corpus_digest,
            "qualification corpus digest",
        )
        require_sha256_digest(
            self.detector_spec_digest,
            "qualification detector spec digest",
        )
        if type(self.corpus_role) is not CalibrationCorpusRole:
            raise ValueError(
                "qualification corpus role must be CalibrationCorpusRole"
            )
        if type(self.disposition) is not CalibrationDisposition:
            raise ValueError(
                "qualification disposition must be CalibrationDisposition"
            )
        if type(self.family_metrics) is not tuple or not self.family_metrics:
            raise ValueError(
                "qualification family_metrics must be non-empty"
            )
        if any(
            type(item) is not CalibrationFamilyMetrics
            for item in self.family_metrics
        ):
            raise ValueError(
                "qualification family_metrics must contain exact metrics"
            )
        if type(self.reasons) is not tuple or not self.reasons:
            raise ValueError("qualification reasons must be non-empty")
        family_ids = [item.family_id for item in self.family_metrics]
        if family_ids != sorted(family_ids) or len(family_ids) != len(set(family_ids)):
            raise ValueError(
                "qualification family metrics must have unique canonical family ids"
            )
        failures = tuple(
            f"{metric.family_id}:{failure}"
            for metric in self.family_metrics
            for failure in metric.failures
        )
        if self.corpus_role is CalibrationCorpusRole.DESIGN:
            expected_disposition = CalibrationDisposition.DESIGN_CHARACTERIZATION
            expected_reasons = ("design_corpus_cannot_qualify", *failures)
        elif failures:
            expected_disposition = CalibrationDisposition.FAIL
            expected_reasons = failures
        else:
            expected_disposition = CalibrationDisposition.PASS
            expected_reasons = ("all_family_criteria_passed",)
        if self.disposition is not expected_disposition:
            raise ValueError(
                "qualification disposition contradicts corpus role/family failures"
            )
        if self.reasons != expected_reasons:
            raise ValueError(
                "qualification reasons contradict corpus role/family failures"
            )

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "schema": "DRIFTGUARD_CALIBRATION_QUALIFICATION_V1",
                "plan_digest": self.plan_digest,
                "corpus_digest": self.corpus_digest,
                "detector_spec_digest": self.detector_spec_digest,
                "corpus_role": self.corpus_role.value,
                "disposition": self.disposition.value,
                "family_metrics": [
                    item.payload() for item in self.family_metrics
                ],
                "reasons": list(self.reasons),
            }
        )


@dataclass(frozen=True)
class _TrajectoryOutcome:
    first_alarm_index: int | None
    first_alarm_dimensions: tuple[str, ...]


def _run_trajectory(
    *,
    spec: SequentialDetectorSpec,
    trajectory: CalibrationTrajectory,
) -> _TrajectoryOutcome:
    policy_dimensions = {
        item.dimension_id for item in spec.dimensions
    }
    sample_dimensions = {
        dimension_id
        for dimension_id, _ in trajectory.samples[0]
    }
    if sample_dimensions != policy_dimensions:
        raise ValueError(
            "trajectory dimensions must exactly match detector dimensions"
        )
    previous = tuple(
        (item.dimension_id, 0.0)
        for item in sorted(
            spec.dimensions,
            key=lambda row: row.dimension_id,
        )
    )
    prior_alarms: tuple[str, ...] = ()
    for index, sample in enumerate(trajectory.samples):
        current, alarms = advance_cusum(
            policies=spec.dimensions,
            previous=previous,
            scores=sample,
            prior_alarms=prior_alarms,
        )
        if not prior_alarms and alarms:
            return _TrajectoryOutcome(
                first_alarm_index=index,
                first_alarm_dimensions=alarms,
            )
        previous = current
        prior_alarms = alarms
    return _TrajectoryOutcome(None, ())


def _family_metrics(
    *,
    policy: CalibrationFamilyPolicy,
    spec: SequentialDetectorSpec,
    trajectories: tuple[CalibrationTrajectory, ...],
) -> CalibrationFamilyMetrics:
    stable = tuple(
        item
        for item in trajectories
        if item.regime is CalibrationTrajectoryRegime.STABLE
    )
    shifted = tuple(
        item
        for item in trajectories
        if item.regime is CalibrationTrajectoryRegime.SHIFTED
    )

    horizon_violations = 0
    for trajectory in stable:
        if len(trajectory.samples) != policy.stable_horizon_observations:
            horizon_violations += 1
    for trajectory in shifted:
        assert trajectory.shift_index is not None
        if (
            trajectory.shift_index
            != policy.pre_shift_horizon_observations
            or len(trajectory.samples) - trajectory.shift_index
            != policy.post_shift_horizon_observations
        ):
            horizon_violations += 1

    stable_false_alarms = 0
    stable_alarm_run_lengths: list[int] = []
    for trajectory in stable:
        outcome = _run_trajectory(spec=spec, trajectory=trajectory)
        if outcome.first_alarm_index is not None:
            stable_false_alarms += 1
            stable_alarm_run_lengths.append(outcome.first_alarm_index + 1)

    pre_shift_false_alarms = 0
    detections = 0
    detection_delays: list[int] = []
    wrong_dimension_alarms = 0
    mixed_target_wrong_dimension_alarms = 0
    for trajectory in shifted:
        outcome = _run_trajectory(spec=spec, trajectory=trajectory)
        alarm_index = outcome.first_alarm_index
        if alarm_index is None:
            continue
        assert trajectory.shift_index is not None
        if alarm_index < trajectory.shift_index:
            pre_shift_false_alarms += 1
            continue
        alarm_dimensions = set(outcome.first_alarm_dimensions)
        shift_dimensions = set(trajectory.shift_dimensions)
        target_alarm = bool(alarm_dimensions.intersection(shift_dimensions))
        collateral_wrong_dimension_alarm = bool(
            alarm_dimensions.difference(shift_dimensions)
        )
        if target_alarm:
            detections += 1
            detection_delays.append(
                alarm_index - trajectory.shift_index + 1
            )
        if collateral_wrong_dimension_alarm:
            wrong_dimension_alarms += 1
        if target_alarm and collateral_wrong_dimension_alarm:
            mixed_target_wrong_dimension_alarms += 1

    if not stable or not shifted:
        raise ValueError(
            f"family {policy.family_id} requires stable and shifted trajectories"
        )

    stable_estimate = BinomialEstimate.from_counts(
        stable_false_alarms,
        len(stable),
    )
    pre_shift_estimate = BinomialEstimate.from_counts(
        pre_shift_false_alarms,
        len(shifted),
    )
    wrong_dimension_estimate = BinomialEstimate.from_counts(
        wrong_dimension_alarms,
        len(shifted),
    )
    detection_estimate = BinomialEstimate.from_counts(
        detections,
        len(shifted),
    )
    mean_delay = (
        round(sum(detection_delays) / len(detection_delays), 12)
        if detection_delays
        else None
    )

    failures: list[str] = []
    if horizon_violations:
        failures.append("trajectory_horizon_mismatch")
    if len(stable) < policy.minimum_stable_trajectories:
        failures.append("insufficient_stable_trajectories")
    if len(shifted) < policy.minimum_shifted_trajectories:
        failures.append("insufficient_shifted_trajectories")
    if (
        stable_estimate.wilson_high_95
        > policy.maximum_stable_false_alarm_rate
    ):
        failures.append("stable_false_alarm_upper_bound_exceeded")
    if (
        pre_shift_estimate.wilson_high_95
        > policy.maximum_pre_shift_false_alarm_rate
    ):
        failures.append("pre_shift_false_alarm_upper_bound_exceeded")
    if (
        wrong_dimension_estimate.wilson_high_95
        > policy.maximum_wrong_dimension_alarm_rate
    ):
        failures.append("wrong_dimension_alarm_upper_bound_exceeded")
    if detection_estimate.wilson_low_95 < policy.minimum_detection_rate:
        failures.append("detection_lower_bound_below_minimum")
    if (
        mean_delay is None
        or mean_delay > policy.maximum_mean_detection_delay
    ):
        failures.append("mean_detection_delay_exceeded_or_unobserved")

    return CalibrationFamilyMetrics(
        family_id=policy.family_id,
        stable_false_alarm=stable_estimate,
        pre_shift_false_alarm=pre_shift_estimate,
        wrong_dimension_alarm=wrong_dimension_estimate,
        detection=detection_estimate,
        stable_alarm_run_lengths=tuple(stable_alarm_run_lengths),
        detection_delays=tuple(detection_delays),
        mean_detection_delay=mean_delay,
        wrong_dimension_alarms=wrong_dimension_alarms,
        horizon_violations=horizon_violations,
        failures=tuple(failures),
        mixed_target_wrong_dimension_alarms=(
            mixed_target_wrong_dimension_alarms
        ),
    )


def qualify_calibration(
    *,
    plan: CalibrationPlan,
    corpus: CalibrationCorpus,
    detector_spec: SequentialDetectorSpec,
) -> CalibrationQualificationReceipt:
    if type(plan) is not CalibrationPlan:
        raise ValueError("plan must be exact CalibrationPlan")
    if type(corpus) is not CalibrationCorpus:
        raise ValueError("corpus must be exact CalibrationCorpus")
    if type(detector_spec) is not SequentialDetectorSpec:
        raise ValueError(
            "detector_spec must be exact SequentialDetectorSpec"
        )
    if plan.detector_spec_digest != detector_spec.digest:
        raise ValueError("calibration detector spec digest mismatch")
    if plan.corpus_digest != corpus.digest:
        raise ValueError("calibration corpus digest mismatch")
    if plan.corpus_role is not corpus.role:
        raise ValueError("calibration corpus role mismatch")

    corpus_families = {item.family_id for item in corpus.trajectories}
    policy_families = {item.family_id for item in plan.family_policies}
    if corpus_families != policy_families:
        raise ValueError(
            "calibration plan families must exactly match corpus families"
        )

    metrics = []
    for policy in sorted(
        plan.family_policies,
        key=lambda row: row.family_id,
    ):
        family_trajectories = tuple(
            item
            for item in corpus.trajectories
            if item.family_id == policy.family_id
        )
        metrics.append(
            _family_metrics(
                policy=policy,
                spec=detector_spec,
                trajectories=family_trajectories,
            )
        )

    failures = tuple(
        f"{metric.family_id}:{failure}"
        for metric in metrics
        for failure in metric.failures
    )
    if corpus.role is CalibrationCorpusRole.DESIGN:
        disposition = CalibrationDisposition.DESIGN_CHARACTERIZATION
        reasons = (
            "design_corpus_cannot_qualify",
            *failures,
        )
    elif failures:
        disposition = CalibrationDisposition.FAIL
        reasons = failures
    else:
        disposition = CalibrationDisposition.PASS
        reasons = ("all_family_criteria_passed",)

    return CalibrationQualificationReceipt(
        plan_digest=plan.digest,
        corpus_digest=corpus.digest,
        detector_spec_digest=detector_spec.digest,
        corpus_role=corpus.role,
        disposition=disposition,
        family_metrics=tuple(metrics),
        reasons=tuple(reasons),
        _qualification_token=_QUALIFICATION_RECEIPT_TOKEN,
    )


__all__ = [
    "BinomialEstimate",
    "CalibrationCorpus",
    "CalibrationCorpusRole",
    "CalibrationDisposition",
    "CalibrationFamilyMetrics",
    "CalibrationFamilyPolicy",
    "CalibrationPlan",
    "CalibrationQualificationReceipt",
    "CalibrationTrajectory",
    "CalibrationTrajectoryRegime",
    "qualify_calibration",
]
