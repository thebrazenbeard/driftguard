from dataclasses import replace
import unittest

from driftguard import (
    BinomialEstimate,
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
from driftguard.model import raw_bytes_digest


CAL = SourceBinding("calibration://r9-cusum", "v1")
CAL_DIGEST = raw_bytes_digest(b"r9-cusum-calibration")


def detector(*, alarm_threshold=0.50):
    return SequentialDetectorSpec(
        detector_id="r9-detector",
        session_id="r9-session",
        state_digest=raw_bytes_digest(b"r9-state"),
        measurement_digest=raw_bytes_digest(b"r9-measurement"),
        subject_digest=raw_bytes_digest(b"r9-subject"),
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
                alarm_threshold=alarm_threshold,
            ),
        ),
    )


def stable_trajectory(index, *, family="iid-like", value=0.10, length=8):
    return CalibrationTrajectory(
        trajectory_id=f"{family}-stable-{index}",
        family_id=family,
        regime=CalibrationTrajectoryRegime.STABLE,
        samples=tuple(((("d", value),)) for _ in range(length)),
    )


def shifted_trajectory(
    index,
    *,
    family="iid-like",
    baseline=0.10,
    shifted=0.80,
    prefix=4,
    suffix=4,
):
    return CalibrationTrajectory(
        trajectory_id=f"{family}-shifted-{index}",
        family_id=family,
        regime=CalibrationTrajectoryRegime.SHIFTED,
        samples=tuple(
            ((("d", baseline),)) for _ in range(prefix)
        )
        + tuple(
            ((("d", shifted),)) for _ in range(suffix)
        ),
        shift_index=prefix,
        shift_dimensions=("d",),
    )


def corpus(
    *,
    role=CalibrationCorpusRole.HOLDOUT_QUALIFICATION,
    families=("iid-like",),
    n=25,
    bad_family=None,
):
    rows = []
    for family in families:
        for index in range(n):
            rows.append(
                stable_trajectory(
                    index,
                    family=family,
                    value=0.80 if family == bad_family else 0.10,
                )
            )
            rows.append(
                shifted_trajectory(
                    index,
                    family=family,
                    baseline=0.80 if family == bad_family else 0.10,
                )
            )
    return CalibrationCorpus(
        corpus_id="r9-corpus",
        version="1",
        role=role,
        trajectories=tuple(rows),
    )


def family_policy(family="iid-like", *, min_count=20):
    return CalibrationFamilyPolicy(
        family_id=family,
        minimum_stable_trajectories=min_count,
        minimum_shifted_trajectories=min_count,
        maximum_stable_false_alarm_rate=0.15,
        maximum_pre_shift_false_alarm_rate=0.15,
        minimum_detection_rate=0.85,
        maximum_mean_detection_delay=1.5,
    )


def plan(c, spec, *, families=("iid-like",), min_count=20):
    return CalibrationPlan(
        plan_id="r9-plan",
        detector_spec_digest=spec.digest,
        corpus_digest=c.digest,
        corpus_role=c.role,
        family_policies=tuple(
            family_policy(family, min_count=min_count)
            for family in families
        ),
    )


class CalibrationQualificationTests(unittest.TestCase):
    def test_holdout_pass_requires_conservative_family_bounds(self):
        spec = detector()
        c = corpus()
        receipt = qualify_calibration(
            plan=plan(c, spec),
            corpus=c,
            detector_spec=spec,
        )
        self.assertEqual(CalibrationDisposition.PASS, receipt.disposition)
        self.assertEqual(("all_family_criteria_passed",), receipt.reasons)
        metrics = receipt.family_metrics[0]
        self.assertEqual(0, metrics.stable_false_alarm.successes)
        self.assertLess(
            metrics.stable_false_alarm.wilson_high_95,
            0.15,
        )
        self.assertEqual(25, metrics.detection.successes)
        self.assertGreater(
            metrics.detection.wilson_low_95,
            0.85,
        )
        self.assertEqual(1.0, metrics.mean_detection_delay)

    def test_design_corpus_can_characterize_but_never_qualify(self):
        spec = detector()
        c = corpus(role=CalibrationCorpusRole.DESIGN)
        receipt = qualify_calibration(
            plan=plan(c, spec),
            corpus=c,
            detector_spec=spec,
        )
        self.assertEqual(
            CalibrationDisposition.DESIGN_CHARACTERIZATION,
            receipt.disposition,
        )
        self.assertIn("design_corpus_cannot_qualify", receipt.reasons)

    def test_tiny_sample_does_not_fake_confidence(self):
        spec = detector()
        c = corpus(n=3)
        permissive = CalibrationFamilyPolicy(
            family_id="iid-like",
            minimum_stable_trajectories=1,
            minimum_shifted_trajectories=1,
            maximum_stable_false_alarm_rate=0.20,
            maximum_pre_shift_false_alarm_rate=0.20,
            minimum_detection_rate=0.80,
            maximum_mean_detection_delay=2.0,
        )
        p = CalibrationPlan(
            "tiny-plan",
            spec.digest,
            c.digest,
            c.role,
            (permissive,),
        )
        receipt = qualify_calibration(
            plan=p,
            corpus=c,
            detector_spec=spec,
        )
        self.assertEqual(CalibrationDisposition.FAIL, receipt.disposition)
        metrics = receipt.family_metrics[0]
        self.assertGreater(
            metrics.stable_false_alarm.wilson_high_95,
            0.20,
        )
        self.assertLess(metrics.detection.wilson_low_95, 0.80)

    def test_bad_family_cannot_hide_behind_good_family(self):
        spec = detector()
        c = corpus(
            families=("good", "bad"),
            bad_family="bad",
        )
        p = plan(
            c,
            spec,
            families=("good", "bad"),
        )
        receipt = qualify_calibration(
            plan=p,
            corpus=c,
            detector_spec=spec,
        )
        self.assertEqual(CalibrationDisposition.FAIL, receipt.disposition)
        by_family = {
            item.family_id: item for item in receipt.family_metrics
        }
        self.assertTrue(by_family["good"].passed)
        self.assertFalse(by_family["bad"].passed)
        self.assertTrue(
            any(reason.startswith("bad:") for reason in receipt.reasons)
        )

    def test_pre_shift_alarm_is_failure_not_detection(self):
        spec = detector()
        rows = []
        for index in range(25):
            rows.append(stable_trajectory(index))
            trajectory = shifted_trajectory(index)
            samples = list(trajectory.samples)
            samples[0] = (("d", 0.90),)
            rows.append(replace(trajectory, samples=tuple(samples)))
        c = CalibrationCorpus(
            "pre-shift",
            "1",
            CalibrationCorpusRole.HOLDOUT_QUALIFICATION,
            tuple(rows),
        )
        receipt = qualify_calibration(
            plan=plan(c, spec),
            corpus=c,
            detector_spec=spec,
        )
        self.assertEqual(CalibrationDisposition.FAIL, receipt.disposition)
        metrics = receipt.family_metrics[0]
        self.assertEqual(25, metrics.pre_shift_false_alarm.successes)
        self.assertEqual(0, metrics.detection.successes)

    def test_corpus_mutation_invalidates_frozen_plan(self):
        spec = detector()
        c = corpus()
        p = plan(c, spec)
        first = c.trajectories[0]
        changed_samples = list(first.samples)
        changed_samples[0] = (("d", 0.11),)
        changed = replace(
            c,
            trajectories=(
                replace(first, samples=tuple(changed_samples)),
                *c.trajectories[1:],
            ),
        )
        self.assertNotEqual(c.digest, changed.digest)
        with self.assertRaisesRegex(ValueError, "corpus digest mismatch"):
            qualify_calibration(
                plan=p,
                corpus=changed,
                detector_spec=spec,
            )

    def test_detector_parameter_change_invalidates_plan(self):
        spec = detector()
        c = corpus()
        p = plan(c, spec)
        changed = detector(alarm_threshold=0.60)
        self.assertNotEqual(spec.digest, changed.digest)
        with self.assertRaisesRegex(
            ValueError,
            "detector spec digest mismatch",
        ):
            qualify_calibration(
                plan=p,
                corpus=c,
                detector_spec=changed,
            )

    def test_acceptance_change_moves_plan_digest(self):
        spec = detector()
        c = corpus()
        original = plan(c, spec)
        changed_policy = replace(
            original.family_policies[0],
            minimum_detection_rate=0.90,
        )
        changed = replace(
            original,
            family_policies=(changed_policy,),
        )
        self.assertNotEqual(original.digest, changed.digest)

    def test_corpus_trajectory_order_is_canonical(self):
        c = corpus(n=3)
        reordered = replace(
            c,
            trajectories=tuple(reversed(c.trajectories)),
        )
        self.assertEqual(c.digest, reordered.digest)

    def test_family_coverage_must_be_exact(self):
        spec = detector()
        c = corpus(families=("one", "two"))
        incomplete = CalibrationPlan(
            "incomplete",
            spec.digest,
            c.digest,
            c.role,
            (family_policy("one"),),
        )
        with self.assertRaisesRegex(
            ValueError,
            "families must exactly match",
        ):
            qualify_calibration(
                plan=incomplete,
                corpus=c,
                detector_spec=spec,
            )

    def test_minimum_trajectory_counts_are_enforced(self):
        spec = detector()
        c = corpus(n=10)
        receipt = qualify_calibration(
            plan=plan(c, spec, min_count=20),
            corpus=c,
            detector_spec=spec,
        )
        self.assertEqual(CalibrationDisposition.FAIL, receipt.disposition)
        self.assertIn(
            "iid-like:insufficient_stable_trajectories",
            receipt.reasons,
        )
        self.assertIn(
            "iid-like:insufficient_shifted_trajectories",
            receipt.reasons,
        )

    def test_stable_alarm_run_length_is_preserved(self):
        spec = detector()
        rows = [
            stable_trajectory(index, value=0.80)
            for index in range(25)
        ] + [
            shifted_trajectory(index)
            for index in range(25)
        ]
        c = CalibrationCorpus(
            "alarm-run-length",
            "1",
            CalibrationCorpusRole.HOLDOUT_QUALIFICATION,
            tuple(rows),
        )
        receipt = qualify_calibration(
            plan=plan(c, spec),
            corpus=c,
            detector_spec=spec,
        )
        metrics = receipt.family_metrics[0]
        self.assertTrue(metrics.stable_alarm_run_lengths)
        self.assertTrue(
            all(
                run_length == 1
                for run_length in metrics.stable_alarm_run_lengths
            )
        )

    def test_binomial_estimate_exposes_uncertainty(self):
        estimate = BinomialEstimate.from_counts(0, 3)
        self.assertEqual(0.0, estimate.rate)
        self.assertGreater(estimate.wilson_high_95, 0.50)

    def test_receipt_digest_binds_family_results(self):
        spec = detector()
        c = corpus()
        receipt = qualify_calibration(
            plan=plan(c, spec),
            corpus=c,
            detector_spec=spec,
        )
        self.assertEqual(64, len(receipt.digest))


if __name__ == "__main__":
    unittest.main()
