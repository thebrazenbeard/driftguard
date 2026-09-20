from dataclasses import replace
import unittest

from driftguard import (
    CalibrationCorpus,
    CalibrationCorpusRole,
    CalibrationDisposition,
    CalibrationFamilyPolicy,
    CalibrationPlan,
    CalibrationTrajectory,
    CalibrationTrajectoryRegime,
    CusumDimensionPolicy,
    SequentialDetectorSpec,
    SourceBinding,
    qualify_calibration,
)
from driftguard.comparison import (
    DetectorAlgorithm,
    DetectorCandidate,
    DetectorComparisonDisposition,
    DetectorComparisonPlan,
    EwmaDimensionPolicy,
    PageHinkleyDimensionPolicy,
    compare_detectors,
)
from driftguard.model import raw_bytes_digest


CAL = SourceBinding("calibration://r10", "v1")
CAL_DIGEST = raw_bytes_digest(b"r10-calibration")
PH_PARAMS = SourceBinding("comparison://page-hinkley", "v1")
PH_PARAMS_DIGEST = raw_bytes_digest(b"r10-page-hinkley-parameters")
EWMA_PARAMS = SourceBinding("comparison://ewma", "v1")
EWMA_PARAMS_DIGEST = raw_bytes_digest(b"r10-ewma-parameters")


def cusum_spec():
    return SequentialDetectorSpec(
        detector_id="r10-cusum",
        session_id="r10-session",
        state_digest=raw_bytes_digest(b"r10-state"),
        measurement_digest=raw_bytes_digest(b"r10-measurement"),
        subject_digest=raw_bytes_digest(b"r10-subject"),
        subject_epoch=0,
        calibration=CAL,
        calibration_digest=CAL_DIGEST,
        max_consecutive_unknown=1,
        max_turn_gap=2,
        dimensions=(
            CusumDimensionPolicy(
                "d",
                baseline_mean=0.10,
                allowance=0.05,
                alarm_threshold=0.50,
            ),
        ),
    )


def stable(index, *, family="base", value=0.10, length=8):
    return CalibrationTrajectory(
        trajectory_id=f"{family}-stable-{index}",
        family_id=family,
        regime=CalibrationTrajectoryRegime.STABLE,
        samples=tuple((("d", value),) for _ in range(length)),
    )


def shifted(
    index,
    *,
    family="base",
    baseline=0.10,
    shifted_value=0.80,
    prefix=4,
    suffix=4,
):
    return CalibrationTrajectory(
        trajectory_id=f"{family}-shifted-{index}",
        family_id=family,
        regime=CalibrationTrajectoryRegime.SHIFTED,
        samples=(
            tuple((("d", baseline),) for _ in range(prefix))
            + tuple((("d", shifted_value),) for _ in range(suffix))
        ),
        shift_index=prefix,
        shift_dimensions=("d",),
    )


def corpus(
    *,
    role=CalibrationCorpusRole.HOLDOUT_QUALIFICATION,
    family="base",
    n=25,
):
    rows = []
    for index in range(n):
        rows.append(stable(index, family=family))
        rows.append(shifted(index, family=family))
    return CalibrationCorpus(
        corpus_id="r10-corpus",
        version="1",
        role=role,
        trajectories=tuple(rows),
    )


def family_policy(family="base"):
    return CalibrationFamilyPolicy(
        family_id=family,
        minimum_stable_trajectories=20,
        minimum_shifted_trajectories=20,
        stable_horizon_observations=8,
        pre_shift_horizon_observations=4,
        post_shift_horizon_observations=4,
        maximum_stable_false_alarm_rate=0.15,
        maximum_pre_shift_false_alarm_rate=0.15,
        maximum_wrong_dimension_alarm_rate=0.15,
        minimum_detection_rate=0.85,
        maximum_mean_detection_delay=1.5,
    )


def calibration_plan(c, spec):
    return CalibrationPlan(
        plan_id="r10-calibration-plan",
        detector_spec_digest=spec.digest,
        corpus_digest=c.digest,
        corpus_role=c.role,
        family_policies=(family_policy(),),
    )


def candidates(spec, *, ph_threshold=0.50, ewma_threshold=0.50):
    return (
        DetectorCandidate(
            candidate_id="cusum",
            algorithm=DetectorAlgorithm.CUSUM,
            cusum_spec_digest=spec.digest,
        ),
        DetectorCandidate(
            candidate_id="page-hinkley",
            algorithm=DetectorAlgorithm.PAGE_HINKLEY,
            parameterization=PH_PARAMS,
            parameterization_digest=PH_PARAMS_DIGEST,
            page_hinkley=(
                PageHinkleyDimensionPolicy(
                    "d",
                    delta=0.01,
                    alarm_threshold=ph_threshold,
                    burn_in=1,
                ),
            ),
        ),
        DetectorCandidate(
            candidate_id="ewma",
            algorithm=DetectorAlgorithm.EWMA,
            parameterization=EWMA_PARAMS,
            parameterization_digest=EWMA_PARAMS_DIGEST,
            ewma=(
                EwmaDimensionPolicy(
                    "d",
                    baseline_mean=0.10,
                    smoothing=0.80,
                    alarm_threshold=ewma_threshold,
                    burn_in=1,
                ),
            ),
        ),
    )


def comparison_plan(c, cal_plan, rows):
    return DetectorComparisonPlan(
        comparison_id="r10-comparison",
        calibration_plan_digest=cal_plan.digest,
        corpus_digest=c.digest,
        candidates=rows,
    )


class DetectorComparisonTests(unittest.TestCase):
    def test_all_three_candidates_can_be_compared_on_identical_holdout(self):
        spec = cusum_spec()
        c = corpus()
        cal = calibration_plan(c, spec)
        receipt = compare_detectors(
            plan=comparison_plan(c, cal, candidates(spec)),
            calibration_plan=cal,
            corpus=c,
            cusum_spec=spec,
        )
        self.assertEqual(
            DetectorComparisonDisposition.MULTIPLE_CANDIDATES_QUALIFIED,
            receipt.disposition,
        )
        self.assertEqual(
            ("cusum", "ewma", "page-hinkley"),
            receipt.qualified_candidate_ids,
        )
        self.assertEqual(
            ("cusum", "ewma", "page-hinkley"),
            receipt.descriptive_pareto_candidate_ids,
        )
        self.assertFalse(receipt.promotion_authorized)

    def test_cusum_comparison_result_exactly_matches_r9_qualification(self):
        spec = cusum_spec()
        c = corpus()
        cal = calibration_plan(c, spec)
        r9 = qualify_calibration(
            plan=cal,
            corpus=c,
            detector_spec=spec,
        )
        comparison = compare_detectors(
            plan=comparison_plan(c, cal, candidates(spec)),
            calibration_plan=cal,
            corpus=c,
            cusum_spec=spec,
        )
        cusum = next(
            row
            for row in comparison.candidate_results
            if row.algorithm is DetectorAlgorithm.CUSUM
        )
        self.assertEqual(r9.disposition, cusum.disposition)
        self.assertEqual(r9.family_metrics, cusum.family_metrics)
        self.assertEqual(r9.reasons, cusum.reasons)

    def test_design_comparison_never_qualifies_or_promotes(self):
        spec = cusum_spec()
        c = corpus(role=CalibrationCorpusRole.DESIGN)
        cal = calibration_plan(c, spec)
        receipt = compare_detectors(
            plan=comparison_plan(c, cal, candidates(spec)),
            calibration_plan=cal,
            corpus=c,
            cusum_spec=spec,
        )
        self.assertEqual(
            DetectorComparisonDisposition.DESIGN_CHARACTERIZATION,
            receipt.disposition,
        )
        self.assertEqual((), receipt.qualified_candidate_ids)
        self.assertFalse(receipt.promotion_authorized)
        self.assertTrue(
            all(
                row.disposition
                is CalibrationDisposition.DESIGN_CHARACTERIZATION
                for row in receipt.candidate_results
            )
        )

    def test_only_one_candidate_passing_still_does_not_authorize_promotion(self):
        spec = cusum_spec()
        c = corpus()
        cal = calibration_plan(c, spec)
        rows = candidates(
            spec,
            ph_threshold=99.0,
            ewma_threshold=99.0,
        )
        receipt = compare_detectors(
            plan=comparison_plan(c, cal, rows),
            calibration_plan=cal,
            corpus=c,
            cusum_spec=spec,
        )
        self.assertEqual(
            DetectorComparisonDisposition.ONE_CANDIDATE_QUALIFIED,
            receipt.disposition,
        )
        self.assertEqual(("cusum",), receipt.qualified_candidate_ids)
        self.assertFalse(receipt.promotion_authorized)
        self.assertIn(
            "holdout_selection_bias_not_controlled",
            receipt.reasons,
        )

    def test_duplicate_algorithm_candidates_are_rejected(self):
        spec = cusum_spec()
        c = corpus()
        cal = calibration_plan(c, spec)
        rows = (
            *candidates(spec),
            DetectorCandidate(
                candidate_id="ewma-sweep",
                algorithm=DetectorAlgorithm.EWMA,
                parameterization=SourceBinding("comparison://ewma-sweep", "v1"),
                parameterization_digest=raw_bytes_digest(b"ewma-sweep"),
                ewma=(
                    EwmaDimensionPolicy(
                        "d",
                        baseline_mean=0.10,
                        smoothing=0.20,
                        alarm_threshold=0.20,
                        burn_in=1,
                    ),
                ),
            ),
        )
        with self.assertRaisesRegex(
            ValueError,
            "only one candidate per algorithm",
        ):
            comparison_plan(c, cal, rows)

    def test_comparison_requires_exact_r8_cusum_baseline(self):
        spec = cusum_spec()
        c = corpus()
        cal = calibration_plan(c, spec)
        rows = tuple(
            replace(
                row,
                cusum_spec_digest=raw_bytes_digest(b"wrong-cusum"),
            )
            if row.algorithm is DetectorAlgorithm.CUSUM
            else row
            for row in candidates(spec)
        )
        with self.assertRaisesRegex(
            ValueError,
            "CUSUM candidate spec digest mismatch",
        ):
            compare_detectors(
                plan=comparison_plan(c, cal, rows),
                calibration_plan=cal,
                corpus=c,
                cusum_spec=spec,
            )

    def test_non_cusum_dimension_set_must_match_baseline(self):
        spec = cusum_spec()
        c = corpus()
        cal = calibration_plan(c, spec)
        bad_ph = DetectorCandidate(
            candidate_id="page-hinkley",
            algorithm=DetectorAlgorithm.PAGE_HINKLEY,
            parameterization=PH_PARAMS,
            parameterization_digest=PH_PARAMS_DIGEST,
            page_hinkley=(
                PageHinkleyDimensionPolicy(
                    "other",
                    delta=0.01,
                    alarm_threshold=0.50,
                    burn_in=1,
                ),
            ),
        )
        rows = (
            candidates(spec)[0],
            bad_ph,
            candidates(spec)[2],
        )
        with self.assertRaisesRegex(
            ValueError,
            "dimensions must exactly match",
        ):
            compare_detectors(
                plan=comparison_plan(c, cal, rows),
                calibration_plan=cal,
                corpus=c,
                cusum_spec=spec,
            )

    def test_non_cusum_parameterization_provenance_is_required(self):
        with self.assertRaisesRegex(
            ValueError,
            "parameterization SourceBinding",
        ):
            DetectorCandidate(
                candidate_id="page-hinkley",
                algorithm=DetectorAlgorithm.PAGE_HINKLEY,
                page_hinkley=(
                    PageHinkleyDimensionPolicy(
                        "d",
                        delta=0.01,
                        alarm_threshold=0.50,
                        burn_in=1,
                    ),
                ),
            )

    def test_burn_in_cannot_hide_pre_shift_exposure(self):
        with self.assertRaisesRegex(
            ValueError,
            "cannot suppress any frozen qualification exposure",
        ):
            PageHinkleyDimensionPolicy(
                "d",
                delta=0.01,
                alarm_threshold=0.50,
                burn_in=5,
            )
        with self.assertRaisesRegex(
            ValueError,
            "cannot suppress any frozen qualification exposure",
        ):
            EwmaDimensionPolicy(
                "d",
                baseline_mean=0.10,
                smoothing=0.80,
                alarm_threshold=0.50,
                burn_in=5,
            )

    def test_r10_requires_exact_declared_algorithm_set(self):
        spec = cusum_spec()
        c = corpus()
        cal = calibration_plan(c, spec)
        with self.assertRaisesRegex(
            ValueError,
            "requires exactly CUSUM, PAGE_HINKLEY, and EWMA",
        ):
            comparison_plan(c, cal, candidates(spec)[:2])

    def test_candidate_parameter_mutation_moves_comparison_plan_digest(self):
        spec = cusum_spec()
        c = corpus()
        cal = calibration_plan(c, spec)
        first = comparison_plan(c, cal, candidates(spec))
        changed_rows = candidates(spec, ewma_threshold=0.60)
        changed = comparison_plan(c, cal, changed_rows)
        self.assertNotEqual(first.digest, changed.digest)

    def test_candidate_order_is_canonical(self):
        spec = cusum_spec()
        c = corpus()
        cal = calibration_plan(c, spec)
        rows = candidates(spec)
        first = comparison_plan(c, cal, rows)
        second = comparison_plan(c, cal, tuple(reversed(rows)))
        self.assertEqual(first.digest, second.digest)

    def test_corpus_mutation_invalidates_comparison_plan(self):
        spec = cusum_spec()
        c = corpus()
        cal = calibration_plan(c, spec)
        plan = comparison_plan(c, cal, candidates(spec))
        first = c.trajectories[0]
        samples = list(first.samples)
        samples[0] = (("d", 0.11),)
        changed = replace(
            c,
            trajectories=(
                replace(first, samples=tuple(samples)),
                *c.trajectories[1:],
            ),
        )
        with self.assertRaisesRegex(
            ValueError,
            "comparison corpus digest mismatch",
        ):
            compare_detectors(
                plan=plan,
                calibration_plan=cal,
                corpus=changed,
                cusum_spec=spec,
            )

    def test_calibration_plan_mutation_invalidates_comparison(self):
        spec = cusum_spec()
        c = corpus()
        cal = calibration_plan(c, spec)
        plan = comparison_plan(c, cal, candidates(spec))
        changed_policy = replace(
            cal.family_policies[0],
            minimum_detection_rate=0.90,
        )
        changed = replace(cal, family_policies=(changed_policy,))
        with self.assertRaisesRegex(
            ValueError,
            "comparison calibration plan digest mismatch",
        ):
            compare_detectors(
                plan=plan,
                calibration_plan=changed,
                corpus=c,
                cusum_spec=spec,
            )

    def test_page_hinkley_and_ewma_fail_under_overly_high_thresholds(self):
        spec = cusum_spec()
        c = corpus()
        cal = calibration_plan(c, spec)
        receipt = compare_detectors(
            plan=comparison_plan(
                c,
                cal,
                candidates(
                    spec,
                    ph_threshold=99.0,
                    ewma_threshold=99.0,
                ),
            ),
            calibration_plan=cal,
            corpus=c,
            cusum_spec=spec,
        )
        by_algorithm = {
            row.algorithm: row for row in receipt.candidate_results
        }
        self.assertEqual(
            CalibrationDisposition.FAIL,
            by_algorithm[DetectorAlgorithm.PAGE_HINKLEY].disposition,
        )
        self.assertEqual(
            CalibrationDisposition.FAIL,
            by_algorithm[DetectorAlgorithm.EWMA].disposition,
        )
        self.assertIn(
            "base:detection_lower_bound_below_minimum",
            by_algorithm[DetectorAlgorithm.PAGE_HINKLEY].reasons,
        )

    def test_pareto_is_descriptive_not_promotion_authority(self):
        spec = cusum_spec()
        c = corpus()
        cal = calibration_plan(c, spec)
        receipt = compare_detectors(
            plan=comparison_plan(c, cal, candidates(spec)),
            calibration_plan=cal,
            corpus=c,
            cusum_spec=spec,
        )
        self.assertTrue(receipt.descriptive_pareto_candidate_ids)
        self.assertFalse(receipt.promotion_authorized)
        self.assertIn(
            "descriptive_pareto_is_not_significance_test",
            receipt.reasons,
        )

    def test_page_hinkley_policy_rejects_invalid_burn_in(self):
        with self.assertRaisesRegex(ValueError, "burn_in"):
            PageHinkleyDimensionPolicy(
                "d",
                delta=0.01,
                alarm_threshold=0.50,
                burn_in=0,
            )

    def test_ewma_policy_rejects_zero_smoothing(self):
        with self.assertRaisesRegex(ValueError, "smoothing"):
            EwmaDimensionPolicy(
                "d",
                baseline_mean=0.10,
                smoothing=0.0,
                alarm_threshold=0.50,
                burn_in=1,
            )

    def test_comparison_receipt_digest_is_stable(self):
        spec = cusum_spec()
        c = corpus()
        cal = calibration_plan(c, spec)
        plan = comparison_plan(c, cal, candidates(spec))
        first = compare_detectors(
            plan=plan,
            calibration_plan=cal,
            corpus=c,
            cusum_spec=spec,
        )
        second = compare_detectors(
            plan=plan,
            calibration_plan=cal,
            corpus=c,
            cusum_spec=spec,
        )
        self.assertEqual(first.digest, second.digest)
        self.assertEqual(64, len(first.digest))


if __name__ == "__main__":
    unittest.main()
