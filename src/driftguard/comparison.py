from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math
from typing import Any, Callable

from .calibration import (
    BinomialEstimate,
    CalibrationCorpus,
    CalibrationCorpusRole,
    CalibrationDisposition,
    CalibrationFamilyMetrics,
    CalibrationFamilyPolicy,
    CalibrationPlan,
    CalibrationTrajectory,
    CalibrationTrajectoryRegime,
    qualify_calibration,
)
from .model import SourceBinding, canonical_digest, require_sha256_digest
from .sequential import SequentialDetectorSpec, advance_cusum


_COMPARISON_RECEIPT_TOKEN = object()


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


class DetectorAlgorithm(StrEnum):
    CUSUM = "CUSUM"
    PAGE_HINKLEY = "PAGE_HINKLEY"
    EWMA = "EWMA"


class DetectorComparisonDisposition(StrEnum):
    DESIGN_CHARACTERIZATION = "DESIGN_CHARACTERIZATION"
    NO_CANDIDATE_QUALIFIED = "NO_CANDIDATE_QUALIFIED"
    ONE_CANDIDATE_QUALIFIED = "ONE_CANDIDATE_QUALIFIED"
    MULTIPLE_CANDIDATES_QUALIFIED = "MULTIPLE_CANDIDATES_QUALIFIED"


@dataclass(frozen=True, order=True)
class PageHinkleyDimensionPolicy:
    dimension_id: str
    delta: float
    alarm_threshold: float
    burn_in: int

    def __post_init__(self) -> None:
        _nonempty(self.dimension_id, "Page-Hinkley dimension id")
        if (
            type(self.delta) not in (int, float)
            or isinstance(self.delta, bool)
            or not math.isfinite(float(self.delta))
            or float(self.delta) < 0.0
        ):
            raise ValueError("Page-Hinkley delta must be finite and >= 0")
        if (
            type(self.alarm_threshold) not in (int, float)
            or isinstance(self.alarm_threshold, bool)
            or not math.isfinite(float(self.alarm_threshold))
            or float(self.alarm_threshold) <= 0.0
        ):
            raise ValueError(
                "Page-Hinkley alarm_threshold must be finite and > 0"
            )
        if type(self.burn_in) is not int or isinstance(self.burn_in, bool):
            raise ValueError("Page-Hinkley burn_in must be exact int")
        if self.burn_in != 1:
            raise ValueError(
                "R10 V1 requires Page-Hinkley burn_in=1 so the detector "
                "cannot suppress any frozen qualification exposure"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "dimension_id": self.dimension_id,
            "delta": float(self.delta),
            "alarm_threshold": float(self.alarm_threshold),
            "burn_in": self.burn_in,
        }


@dataclass(frozen=True, order=True)
class EwmaDimensionPolicy:
    dimension_id: str
    baseline_mean: float
    smoothing: float
    alarm_threshold: float
    burn_in: int

    def __post_init__(self) -> None:
        _nonempty(self.dimension_id, "EWMA dimension id")
        _unit(self.baseline_mean, "EWMA baseline mean")
        smoothing = _unit(self.smoothing, "EWMA smoothing")
        if smoothing <= 0.0:
            raise ValueError("EWMA smoothing must be > 0")
        if (
            type(self.alarm_threshold) not in (int, float)
            or isinstance(self.alarm_threshold, bool)
            or not math.isfinite(float(self.alarm_threshold))
            or float(self.alarm_threshold) <= 0.0
        ):
            raise ValueError("EWMA alarm_threshold must be finite and > 0")
        if type(self.burn_in) is not int or isinstance(self.burn_in, bool):
            raise ValueError("EWMA burn_in must be exact int")
        if self.burn_in != 1:
            raise ValueError(
                "R10 V1 requires EWMA burn_in=1 so the detector cannot "
                "suppress any frozen qualification exposure"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "dimension_id": self.dimension_id,
            "baseline_mean": float(self.baseline_mean),
            "smoothing": float(self.smoothing),
            "alarm_threshold": float(self.alarm_threshold),
            "burn_in": self.burn_in,
        }


@dataclass(frozen=True)
class DetectorCandidate:
    candidate_id: str
    algorithm: DetectorAlgorithm
    cusum_spec_digest: str | None = None
    parameterization: SourceBinding | None = None
    parameterization_digest: str | None = None
    page_hinkley: tuple[PageHinkleyDimensionPolicy, ...] = ()
    ewma: tuple[EwmaDimensionPolicy, ...] = ()

    def __post_init__(self) -> None:
        _nonempty(self.candidate_id, "candidate id")
        if type(self.algorithm) is not DetectorAlgorithm:
            raise ValueError("algorithm must be exact DetectorAlgorithm")

        if self.algorithm is DetectorAlgorithm.CUSUM:
            if self.cusum_spec_digest is None:
                raise ValueError("CUSUM candidate requires cusum_spec_digest")
            require_sha256_digest(
                self.cusum_spec_digest,
                "CUSUM candidate spec digest",
            )
            if (
                self.page_hinkley
                or self.ewma
                or self.parameterization is not None
                or self.parameterization_digest is not None
            ):
                raise ValueError(
                    "CUSUM candidate cannot carry alternate parameterization"
                )
        elif self.algorithm is DetectorAlgorithm.PAGE_HINKLEY:
            if self.cusum_spec_digest is not None or self.ewma:
                raise ValueError(
                    "Page-Hinkley candidate contains incompatible policy"
                )
            self._validate_parameterization_provenance()
            self._validate_dimension_tuple(
                self.page_hinkley,
                PageHinkleyDimensionPolicy,
                "Page-Hinkley",
            )
        else:
            if self.cusum_spec_digest is not None or self.page_hinkley:
                raise ValueError("EWMA candidate contains incompatible policy")
            self._validate_parameterization_provenance()
            self._validate_dimension_tuple(
                self.ewma,
                EwmaDimensionPolicy,
                "EWMA",
            )

    def _validate_parameterization_provenance(self) -> None:
        if type(self.parameterization) is not SourceBinding:
            raise ValueError(
                "non-CUSUM candidate requires exact parameterization SourceBinding"
            )
        if self.parameterization_digest is None:
            raise ValueError(
                "non-CUSUM candidate requires parameterization digest"
            )
        require_sha256_digest(
            self.parameterization_digest,
            "candidate parameterization digest",
        )

    @staticmethod
    def _validate_dimension_tuple(
        values: tuple[Any, ...],
        expected_type: type,
        label: str,
    ) -> None:
        if type(values) is not tuple or not values:
            raise ValueError(f"{label} policies must be a non-empty tuple")
        if any(type(item) is not expected_type for item in values):
            raise ValueError(
                f"{label} policies must contain exact {expected_type.__name__}"
            )
        ids = [item.dimension_id for item in values]
        if len(ids) != len(set(ids)):
            raise ValueError(f"{label} dimension ids must be unique")

    @property
    def dimension_ids(self) -> tuple[str, ...]:
        if self.algorithm is DetectorAlgorithm.CUSUM:
            return ()
        rows = (
            self.page_hinkley
            if self.algorithm is DetectorAlgorithm.PAGE_HINKLEY
            else self.ewma
        )
        return tuple(sorted(item.dimension_id for item in rows))

    def payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": "DRIFTGUARD_DETECTOR_CANDIDATE_V1",
            "candidate_id": self.candidate_id,
            "algorithm": self.algorithm.value,
        }
        if self.algorithm is DetectorAlgorithm.CUSUM:
            payload["cusum_spec_digest"] = self.cusum_spec_digest
        elif self.algorithm is DetectorAlgorithm.PAGE_HINKLEY:
            payload["parameterization"] = {
                "ref": self.parameterization.ref,
                "version": self.parameterization.version,
            }
            payload["parameterization_digest"] = self.parameterization_digest
            payload["page_hinkley"] = [
                item.payload()
                for item in sorted(
                    self.page_hinkley,
                    key=lambda row: row.dimension_id,
                )
            ]
        else:
            payload["parameterization"] = {
                "ref": self.parameterization.ref,
                "version": self.parameterization.version,
            }
            payload["parameterization_digest"] = self.parameterization_digest
            payload["ewma"] = [
                item.payload()
                for item in sorted(
                    self.ewma,
                    key=lambda row: row.dimension_id,
                )
            ]
        return payload

    @property
    def digest(self) -> str:
        return canonical_digest(self.payload())


@dataclass(frozen=True)
class DetectorComparisonPlan:
    comparison_id: str
    calibration_plan_digest: str
    corpus_digest: str
    candidates: tuple[DetectorCandidate, ...]
    comparison_claim: str = "COMPARISON_ONLY_NO_HOLDOUT_SELECTION"

    def __post_init__(self) -> None:
        _nonempty(self.comparison_id, "comparison id")
        require_sha256_digest(
            self.calibration_plan_digest,
            "comparison calibration plan digest",
        )
        require_sha256_digest(
            self.corpus_digest,
            "comparison corpus digest",
        )
        if type(self.candidates) is not tuple or len(self.candidates) < 2:
            raise ValueError("comparison requires at least two candidates")
        if any(type(item) is not DetectorCandidate for item in self.candidates):
            raise ValueError(
                "comparison candidates must contain exact DetectorCandidate"
            )
        ids = [item.candidate_id for item in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("comparison candidate ids must be unique")
        algorithms = [item.algorithm for item in self.candidates]
        if len(algorithms) != len(set(algorithms)):
            raise ValueError(
                "comparison permits only one candidate per algorithm"
            )
        required_algorithms = set(DetectorAlgorithm)
        if set(algorithms) != required_algorithms:
            raise ValueError(
                "R10 V1 comparison requires exactly CUSUM, PAGE_HINKLEY, "
                "and EWMA candidates"
            )
        if self.comparison_claim != "COMPARISON_ONLY_NO_HOLDOUT_SELECTION":
            raise ValueError("unsupported comparison claim")

    def payload(self) -> dict[str, Any]:
        return {
            "schema": "DRIFTGUARD_DETECTOR_COMPARISON_PLAN_V1",
            "comparison_id": self.comparison_id,
            "calibration_plan_digest": self.calibration_plan_digest,
            "corpus_digest": self.corpus_digest,
            "candidates": [
                item.payload()
                for item in sorted(
                    self.candidates,
                    key=lambda row: row.candidate_id,
                )
            ],
            "comparison_claim": self.comparison_claim,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.payload())


@dataclass(frozen=True)
class DetectorCandidateResult:
    candidate_id: str
    algorithm: DetectorAlgorithm
    candidate_digest: str
    disposition: CalibrationDisposition
    family_metrics: tuple[CalibrationFamilyMetrics, ...]
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        _nonempty(self.candidate_id, "candidate result id")
        if type(self.algorithm) is not DetectorAlgorithm:
            raise ValueError("candidate result algorithm must be DetectorAlgorithm")
        require_sha256_digest(
            self.candidate_digest,
            "candidate result digest",
        )
        if type(self.disposition) is not CalibrationDisposition:
            raise ValueError(
                "candidate result disposition must be CalibrationDisposition"
            )
        if type(self.family_metrics) is not tuple or not self.family_metrics:
            raise ValueError("candidate result family metrics must be non-empty")
        if type(self.reasons) is not tuple or not self.reasons:
            raise ValueError("candidate result reasons must be non-empty")
        if any(
            type(item) is not CalibrationFamilyMetrics
            for item in self.family_metrics
        ):
            raise ValueError(
                "candidate result family metrics must contain exact metrics"
            )
        family_ids = [item.family_id for item in self.family_metrics]
        if family_ids != sorted(family_ids) or len(family_ids) != len(set(family_ids)):
            raise ValueError(
                "candidate result family metrics must have unique canonical ids"
            )
        failures = tuple(
            f"{metric.family_id}:{failure}"
            for metric in self.family_metrics
            for failure in metric.failures
        )
        if self.disposition is CalibrationDisposition.DESIGN_CHARACTERIZATION:
            expected_reasons = ("design_corpus_cannot_qualify", *failures)
        elif self.disposition is CalibrationDisposition.FAIL:
            if not failures:
                raise ValueError(
                    "candidate FAIL disposition requires family failures"
                )
            expected_reasons = failures
        else:
            if failures:
                raise ValueError(
                    "candidate PASS disposition cannot contain family failures"
                )
            expected_reasons = ("all_family_criteria_passed",)
        if self.reasons != expected_reasons:
            raise ValueError(
                "candidate result reasons contradict disposition/family failures"
            )

    @property
    def qualified(self) -> bool:
        return self.disposition is CalibrationDisposition.PASS

    def payload(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "algorithm": self.algorithm.value,
            "candidate_digest": self.candidate_digest,
            "disposition": self.disposition.value,
            "family_metrics": [
                item.payload() for item in self.family_metrics
            ],
            "reasons": list(self.reasons),
            "qualified": self.qualified,
        }


@dataclass(frozen=True, init=False)
class DetectorComparisonReceipt:
    comparison_plan_digest: str
    calibration_plan_digest: str
    corpus_digest: str
    corpus_role: CalibrationCorpusRole
    disposition: DetectorComparisonDisposition
    candidate_results: tuple[DetectorCandidateResult, ...]
    qualified_candidate_ids: tuple[str, ...]
    descriptive_pareto_candidate_ids: tuple[str, ...]
    promotion_authorized: bool
    reasons: tuple[str, ...]

    def __init__(
        self,
        *,
        comparison_plan_digest: str,
        calibration_plan_digest: str,
        corpus_digest: str,
        corpus_role: CalibrationCorpusRole,
        disposition: DetectorComparisonDisposition,
        candidate_results: tuple[DetectorCandidateResult, ...],
        qualified_candidate_ids: tuple[str, ...],
        descriptive_pareto_candidate_ids: tuple[str, ...],
        promotion_authorized: bool,
        reasons: tuple[str, ...],
        _comparison_token: object | None = None,
    ) -> None:
        if _comparison_token is not _COMPARISON_RECEIPT_TOKEN:
            raise ValueError(
                "DetectorComparisonReceipt must come from compare_detectors"
            )
        object.__setattr__(self, "comparison_plan_digest", comparison_plan_digest)
        object.__setattr__(self, "calibration_plan_digest", calibration_plan_digest)
        object.__setattr__(self, "corpus_digest", corpus_digest)
        object.__setattr__(self, "corpus_role", corpus_role)
        object.__setattr__(self, "disposition", disposition)
        object.__setattr__(self, "candidate_results", candidate_results)
        object.__setattr__(self, "qualified_candidate_ids", qualified_candidate_ids)
        object.__setattr__(
            self,
            "descriptive_pareto_candidate_ids",
            descriptive_pareto_candidate_ids,
        )
        object.__setattr__(self, "promotion_authorized", promotion_authorized)
        object.__setattr__(self, "reasons", reasons)
        self.__post_init__()

    def __post_init__(self) -> None:
        for value, label in (
            (
                self.comparison_plan_digest,
                "comparison receipt plan digest",
            ),
            (
                self.calibration_plan_digest,
                "comparison receipt calibration plan digest",
            ),
            (self.corpus_digest, "comparison receipt corpus digest"),
        ):
            require_sha256_digest(value, label)
        if type(self.corpus_role) is not CalibrationCorpusRole:
            raise ValueError(
                "comparison receipt corpus role must be CalibrationCorpusRole"
            )
        if type(self.disposition) is not DetectorComparisonDisposition:
            raise ValueError(
                "comparison receipt disposition must be DetectorComparisonDisposition"
            )
        if (
            type(self.candidate_results) is not tuple
            or len(self.candidate_results) < 2
        ):
            raise ValueError(
                "comparison receipt requires at least two candidate results"
            )
        if type(self.promotion_authorized) is not bool:
            raise ValueError("promotion_authorized must be exact bool")
        if self.promotion_authorized:
            raise ValueError(
                "R10 comparison cannot authorize holdout-based promotion"
            )
        if type(self.reasons) is not tuple or not self.reasons:
            raise ValueError("comparison receipt reasons must be non-empty")
        if any(
            type(item) is not DetectorCandidateResult
            for item in self.candidate_results
        ):
            raise ValueError(
                "comparison receipt candidates must be exact DetectorCandidateResult"
            )
        result_ids = [item.candidate_id for item in self.candidate_results]
        if result_ids != sorted(result_ids) or len(result_ids) != len(set(result_ids)):
            raise ValueError(
                "comparison candidate result ids must be unique and canonical"
            )
        algorithms = [item.algorithm for item in self.candidate_results]
        if len(algorithms) != len(set(algorithms)):
            raise ValueError("comparison candidate result algorithms must be unique")
        if set(algorithms) != set(DetectorAlgorithm):
            raise ValueError(
                "comparison receipt must contain exact declared algorithm set"
            )
        expected_qualified = tuple(
            sorted(
                item.candidate_id
                for item in self.candidate_results
                if item.qualified
            )
        )
        if self.qualified_candidate_ids != expected_qualified:
            raise ValueError(
                "qualified_candidate_ids contradict candidate results"
            )
        if (
            type(self.descriptive_pareto_candidate_ids) is not tuple
            or self.descriptive_pareto_candidate_ids
            != tuple(sorted(set(self.descriptive_pareto_candidate_ids)))
        ):
            raise ValueError(
                "descriptive Pareto candidate ids must be unique and canonical"
            )
        if not set(self.descriptive_pareto_candidate_ids).issubset(
            set(expected_qualified)
        ):
            raise ValueError(
                "descriptive Pareto candidates must be known qualified candidates"
            )
        expected_pareto = []
        for candidate in self.candidate_results:
            if not candidate.qualified:
                continue
            dominated = any(
                _descriptively_dominates(other, candidate)
                for other in self.candidate_results
                if other.candidate_id != candidate.candidate_id
            )
            if not dominated:
                expected_pareto.append(candidate.candidate_id)
        if self.descriptive_pareto_candidate_ids != tuple(sorted(expected_pareto)):
            raise ValueError(
                "descriptive Pareto ids contradict candidate metrics"
            )

        qualified_count = len(expected_qualified)
        if self.corpus_role is CalibrationCorpusRole.DESIGN:
            expected_disposition = (
                DetectorComparisonDisposition.DESIGN_CHARACTERIZATION
            )
            expected_reasons = (
                "design_comparison_only",
                "no_candidate_promotion_authorized",
            )
        elif qualified_count == 0:
            expected_disposition = (
                DetectorComparisonDisposition.NO_CANDIDATE_QUALIFIED
            )
            expected_reasons = (
                "no_candidate_met_holdout_criteria",
                "no_candidate_promotion_authorized",
            )
        elif qualified_count == 1:
            expected_disposition = (
                DetectorComparisonDisposition.ONE_CANDIDATE_QUALIFIED
            )
            expected_reasons = (
                "one_candidate_met_holdout_criteria",
                "holdout_selection_bias_not_controlled",
                "no_candidate_promotion_authorized",
            )
        else:
            expected_disposition = (
                DetectorComparisonDisposition.MULTIPLE_CANDIDATES_QUALIFIED
            )
            expected_reasons = (
                "multiple_candidates_met_holdout_criteria",
                "descriptive_pareto_is_not_significance_test",
                "holdout_selection_bias_not_controlled",
                "no_candidate_promotion_authorized",
            )
        if self.disposition is not expected_disposition:
            raise ValueError(
                "comparison disposition contradicts corpus role/qualified results"
            )
        if self.reasons != expected_reasons:
            raise ValueError(
                "comparison reasons contradict corpus role/qualified results"
            )

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "schema": "DRIFTGUARD_DETECTOR_COMPARISON_RECEIPT_V1",
                "comparison_plan_digest": self.comparison_plan_digest,
                "calibration_plan_digest": self.calibration_plan_digest,
                "corpus_digest": self.corpus_digest,
                "corpus_role": self.corpus_role.value,
                "disposition": self.disposition.value,
                "candidate_results": [
                    item.payload() for item in self.candidate_results
                ],
                "qualified_candidate_ids": list(
                    self.qualified_candidate_ids
                ),
                "descriptive_pareto_candidate_ids": list(
                    self.descriptive_pareto_candidate_ids
                ),
                "promotion_authorized": self.promotion_authorized,
                "reasons": list(self.reasons),
            }
        )


@dataclass(frozen=True)
class _TrajectoryOutcome:
    first_alarm_index: int | None
    first_alarm_dimensions: tuple[str, ...]


def _run_cusum(
    spec: SequentialDetectorSpec,
    trajectory: CalibrationTrajectory,
) -> _TrajectoryOutcome:
    policy_dimensions = {item.dimension_id for item in spec.dimensions}
    if {
        dimension_id for dimension_id, _ in trajectory.samples[0]
    } != policy_dimensions:
        raise ValueError(
            "trajectory dimensions must exactly match CUSUM candidate"
        )
    previous = tuple(
        (item.dimension_id, 0.0)
        for item in sorted(spec.dimensions, key=lambda row: row.dimension_id)
    )
    alarms: tuple[str, ...] = ()
    for index, sample in enumerate(trajectory.samples):
        current, next_alarms = advance_cusum(
            policies=spec.dimensions,
            previous=previous,
            scores=sample,
            prior_alarms=alarms,
        )
        if not alarms and next_alarms:
            return _TrajectoryOutcome(index, next_alarms)
        previous = current
        alarms = next_alarms
    return _TrajectoryOutcome(None, ())


def _run_page_hinkley(
    candidate: DetectorCandidate,
    trajectory: CalibrationTrajectory,
) -> _TrajectoryOutcome:
    policy = {item.dimension_id: item for item in candidate.page_hinkley}
    if {
        dimension_id for dimension_id, _ in trajectory.samples[0]
    } != set(policy):
        raise ValueError(
            "trajectory dimensions must exactly match Page-Hinkley candidate"
        )
    count = {dimension_id: 0 for dimension_id in policy}
    mean = {dimension_id: 0.0 for dimension_id in policy}
    cumulative = {dimension_id: 0.0 for dimension_id in policy}
    minimum = {dimension_id: 0.0 for dimension_id in policy}

    for index, sample in enumerate(trajectory.samples):
        alarmed: list[str] = []
        for dimension_id, score in sorted(sample):
            row = policy[dimension_id]
            count[dimension_id] += 1
            n = count[dimension_id]
            x = float(score)
            mean[dimension_id] += (
                x - mean[dimension_id]
            ) / n
            cumulative[dimension_id] += (
                x - mean[dimension_id] - float(row.delta)
            )
            minimum[dimension_id] = min(
                minimum[dimension_id],
                cumulative[dimension_id],
            )
            statistic = round(
                cumulative[dimension_id] - minimum[dimension_id],
                12,
            )
            if (
                n >= row.burn_in
                and statistic > float(row.alarm_threshold)
            ):
                alarmed.append(dimension_id)
        if alarmed:
            return _TrajectoryOutcome(index, tuple(sorted(alarmed)))
    return _TrajectoryOutcome(None, ())


def _run_ewma(
    candidate: DetectorCandidate,
    trajectory: CalibrationTrajectory,
) -> _TrajectoryOutcome:
    policy = {item.dimension_id: item for item in candidate.ewma}
    if {
        dimension_id for dimension_id, _ in trajectory.samples[0]
    } != set(policy):
        raise ValueError(
            "trajectory dimensions must exactly match EWMA candidate"
        )
    count = {dimension_id: 0 for dimension_id in policy}
    value = {
        dimension_id: float(row.baseline_mean)
        for dimension_id, row in policy.items()
    }
    for index, sample in enumerate(trajectory.samples):
        alarmed: list[str] = []
        for dimension_id, score in sorted(sample):
            row = policy[dimension_id]
            count[dimension_id] += 1
            smoothing = float(row.smoothing)
            value[dimension_id] = round(
                smoothing * float(score)
                + (1.0 - smoothing) * value[dimension_id],
                12,
            )
            if (
                count[dimension_id] >= row.burn_in
                and value[dimension_id] - float(row.baseline_mean)
                >= float(row.alarm_threshold)
            ):
                alarmed.append(dimension_id)
        if alarmed:
            return _TrajectoryOutcome(index, tuple(sorted(alarmed)))
    return _TrajectoryOutcome(None, ())


def _family_metrics_from_runner(
    *,
    policy: CalibrationFamilyPolicy,
    trajectories: tuple[CalibrationTrajectory, ...],
    runner: Callable[[CalibrationTrajectory], _TrajectoryOutcome],
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
    if not stable or not shifted:
        raise ValueError(
            f"family {policy.family_id} requires stable and shifted trajectories"
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
        outcome = runner(trajectory)
        if outcome.first_alarm_index is not None:
            stable_false_alarms += 1
            stable_alarm_run_lengths.append(outcome.first_alarm_index + 1)

    pre_shift_false_alarms = 0
    detections = 0
    detection_delays: list[int] = []
    wrong_dimension_alarms = 0
    for trajectory in shifted:
        outcome = runner(trajectory)
        alarm_index = outcome.first_alarm_index
        if alarm_index is None:
            continue
        assert trajectory.shift_index is not None
        if alarm_index < trajectory.shift_index:
            pre_shift_false_alarms += 1
            continue
        if set(outcome.first_alarm_dimensions).intersection(
            trajectory.shift_dimensions
        ):
            detections += 1
            detection_delays.append(
                alarm_index - trajectory.shift_index + 1
            )
        else:
            wrong_dimension_alarms += 1

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
    )


def _candidate_result(
    *,
    candidate: DetectorCandidate,
    calibration_plan: CalibrationPlan,
    corpus: CalibrationCorpus,
    cusum_spec: SequentialDetectorSpec,
) -> DetectorCandidateResult:
    if candidate.algorithm is DetectorAlgorithm.CUSUM:
        if candidate.cusum_spec_digest != cusum_spec.digest:
            raise ValueError("CUSUM candidate spec digest mismatch")
        receipt = qualify_calibration(
            plan=calibration_plan,
            corpus=corpus,
            detector_spec=cusum_spec,
        )
        return DetectorCandidateResult(
            candidate_id=candidate.candidate_id,
            algorithm=candidate.algorithm,
            candidate_digest=candidate.digest,
            disposition=receipt.disposition,
            family_metrics=receipt.family_metrics,
            reasons=receipt.reasons,
        )

    expected_dimensions = tuple(
        sorted(item.dimension_id for item in cusum_spec.dimensions)
    )
    if candidate.dimension_ids != expected_dimensions:
        raise ValueError(
            "candidate dimensions must exactly match R8 CUSUM dimensions"
        )

    if candidate.algorithm is DetectorAlgorithm.PAGE_HINKLEY:
        runner = lambda trajectory: _run_page_hinkley(
            candidate,
            trajectory,
        )
    else:
        runner = lambda trajectory: _run_ewma(candidate, trajectory)

    metrics = []
    for policy in sorted(
        calibration_plan.family_policies,
        key=lambda row: row.family_id,
    ):
        rows = tuple(
            item
            for item in corpus.trajectories
            if item.family_id == policy.family_id
        )
        metrics.append(
            _family_metrics_from_runner(
                policy=policy,
                trajectories=rows,
                runner=runner,
            )
        )

    failures = tuple(
        f"{metric.family_id}:{failure}"
        for metric in metrics
        for failure in metric.failures
    )
    if corpus.role is CalibrationCorpusRole.DESIGN:
        disposition = CalibrationDisposition.DESIGN_CHARACTERIZATION
        reasons = ("design_corpus_cannot_qualify", *failures)
    elif failures:
        disposition = CalibrationDisposition.FAIL
        reasons = failures
    else:
        disposition = CalibrationDisposition.PASS
        reasons = ("all_family_criteria_passed",)

    return DetectorCandidateResult(
        candidate_id=candidate.candidate_id,
        algorithm=candidate.algorithm,
        candidate_digest=candidate.digest,
        disposition=disposition,
        family_metrics=tuple(metrics),
        reasons=tuple(reasons),
    )


def _metric_no_worse(
    a: CalibrationFamilyMetrics,
    b: CalibrationFamilyMetrics,
) -> tuple[bool, bool]:
    a_delay = (
        a.mean_detection_delay
        if a.mean_detection_delay is not None
        else math.inf
    )
    b_delay = (
        b.mean_detection_delay
        if b.mean_detection_delay is not None
        else math.inf
    )
    comparisons = (
        a.stable_false_alarm.rate <= b.stable_false_alarm.rate,
        a.pre_shift_false_alarm.rate <= b.pre_shift_false_alarm.rate,
        a.wrong_dimension_alarm.rate <= b.wrong_dimension_alarm.rate,
        a.detection.rate >= b.detection.rate,
        a_delay <= b_delay,
    )
    strict = (
        a.stable_false_alarm.rate < b.stable_false_alarm.rate
        or a.pre_shift_false_alarm.rate < b.pre_shift_false_alarm.rate
        or a.wrong_dimension_alarm.rate < b.wrong_dimension_alarm.rate
        or a.detection.rate > b.detection.rate
        or a_delay < b_delay
    )
    return all(comparisons), strict


def _descriptively_dominates(
    a: DetectorCandidateResult,
    b: DetectorCandidateResult,
) -> bool:
    if not a.qualified or not b.qualified:
        return False
    by_family_b = {item.family_id: item for item in b.family_metrics}
    strict_any = False
    for metric_a in a.family_metrics:
        metric_b = by_family_b[metric_a.family_id]
        no_worse, strict = _metric_no_worse(metric_a, metric_b)
        if not no_worse:
            return False
        strict_any = strict_any or strict
    return strict_any


def compare_detectors(
    *,
    plan: DetectorComparisonPlan,
    calibration_plan: CalibrationPlan,
    corpus: CalibrationCorpus,
    cusum_spec: SequentialDetectorSpec,
) -> DetectorComparisonReceipt:
    if type(plan) is not DetectorComparisonPlan:
        raise ValueError("plan must be exact DetectorComparisonPlan")
    if type(calibration_plan) is not CalibrationPlan:
        raise ValueError("calibration_plan must be exact CalibrationPlan")
    if type(corpus) is not CalibrationCorpus:
        raise ValueError("corpus must be exact CalibrationCorpus")
    if type(cusum_spec) is not SequentialDetectorSpec:
        raise ValueError("cusum_spec must be exact SequentialDetectorSpec")
    if plan.calibration_plan_digest != calibration_plan.digest:
        raise ValueError("comparison calibration plan digest mismatch")
    if plan.corpus_digest != corpus.digest:
        raise ValueError("comparison corpus digest mismatch")
    if calibration_plan.corpus_digest != corpus.digest:
        raise ValueError("calibration plan corpus digest mismatch")
    if calibration_plan.detector_spec_digest != cusum_spec.digest:
        raise ValueError("calibration plan CUSUM spec digest mismatch")

    results = tuple(
        _candidate_result(
            candidate=candidate,
            calibration_plan=calibration_plan,
            corpus=corpus,
            cusum_spec=cusum_spec,
        )
        for candidate in sorted(
            plan.candidates,
            key=lambda row: row.candidate_id,
        )
    )
    qualified = tuple(
        sorted(item.candidate_id for item in results if item.qualified)
    )
    pareto = []
    for candidate in results:
        if not candidate.qualified:
            continue
        dominated = any(
            _descriptively_dominates(other, candidate)
            for other in results
            if other.candidate_id != candidate.candidate_id
        )
        if not dominated:
            pareto.append(candidate.candidate_id)

    if corpus.role is CalibrationCorpusRole.DESIGN:
        disposition = DetectorComparisonDisposition.DESIGN_CHARACTERIZATION
        reasons = (
            "design_comparison_only",
            "no_candidate_promotion_authorized",
        )
    elif not qualified:
        disposition = DetectorComparisonDisposition.NO_CANDIDATE_QUALIFIED
        reasons = (
            "no_candidate_met_holdout_criteria",
            "no_candidate_promotion_authorized",
        )
    elif len(qualified) == 1:
        disposition = DetectorComparisonDisposition.ONE_CANDIDATE_QUALIFIED
        reasons = (
            "one_candidate_met_holdout_criteria",
            "holdout_selection_bias_not_controlled",
            "no_candidate_promotion_authorized",
        )
    else:
        disposition = (
            DetectorComparisonDisposition.MULTIPLE_CANDIDATES_QUALIFIED
        )
        reasons = (
            "multiple_candidates_met_holdout_criteria",
            "descriptive_pareto_is_not_significance_test",
            "holdout_selection_bias_not_controlled",
            "no_candidate_promotion_authorized",
        )

    return DetectorComparisonReceipt(
        comparison_plan_digest=plan.digest,
        calibration_plan_digest=calibration_plan.digest,
        corpus_digest=corpus.digest,
        corpus_role=corpus.role,
        disposition=disposition,
        candidate_results=results,
        qualified_candidate_ids=qualified,
        descriptive_pareto_candidate_ids=tuple(sorted(pareto)),
        promotion_authorized=False,
        reasons=reasons,
        _comparison_token=_COMPARISON_RECEIPT_TOKEN,
    )


__all__ = [
    "DetectorAlgorithm",
    "DetectorCandidate",
    "DetectorCandidateResult",
    "DetectorComparisonDisposition",
    "DetectorComparisonPlan",
    "DetectorComparisonReceipt",
    "EwmaDimensionPolicy",
    "PageHinkleyDimensionPolicy",
    "compare_detectors",
]
