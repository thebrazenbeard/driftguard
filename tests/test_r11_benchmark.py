from dataclasses import replace
from hashlib import sha256
import unittest

from driftguard.calibration import (
    CalibrationCorpus,
    CalibrationCorpusRole,
    CalibrationFamilyPolicy,
    CalibrationTrajectory,
    CalibrationTrajectoryRegime,
)
from driftguard.comparison import (
    DetectorAlgorithm,
    DetectorCandidate,
    EwmaDimensionPolicy,
    PageHinkleyDimensionPolicy,
)
from driftguard.benchmark import (
    BenchmarkCorpusManifest,
    BenchmarkFamilyManifest,
    BenchmarkPhenomenon,
    BenchmarkPrecommitPlan,
    BenchmarkRunReceipt,
    HoldoutCorpusSeal,
    HoldoutRevealReceipt,
    PRECOMMIT_CLAIM,
    REVEAL_CLAIM,
    RUN_CLAIM,
    canonical_corpus_artifact_bytes,
    reveal_holdout,
    run_precommitted_holdout,
)
from driftguard.model import SourceBinding, raw_bytes_digest
from driftguard.sequential import CusumDimensionPolicy, SequentialDetectorSpec


CAL = SourceBinding("calibration://r11-cusum", "v1")
CAL_DIGEST = raw_bytes_digest(b"r11-cusum-calibration")
PH_PARAMS = SourceBinding("comparison://r11-page-hinkley", "v1")
PH_DIGEST = raw_bytes_digest(b"r11-page-hinkley")
EWMA_PARAMS = SourceBinding("comparison://r11-ewma", "v1")
EWMA_DIGEST = raw_bytes_digest(b"r11-ewma")
DIMENSIONS = ("collateral", "target")

FAMILY_ROWS = (
    ("01-low-noise", BenchmarkPhenomenon.STABLE_LOW_NOISE),
    ("02-autocorrelated", BenchmarkPhenomenon.STABLE_AUTOCORRELATED),
    ("03-heavy-tail", BenchmarkPhenomenon.STABLE_HEAVY_TAIL),
    ("04-context-stress", BenchmarkPhenomenon.CONTEXT_STRESS),
    ("05-evaluator-shift", BenchmarkPhenomenon.EVALUATOR_SHIFT),
    ("06-subject-shift", BenchmarkPhenomenon.SUBJECT_BEHAVIOR_SHIFT),
    (
        "07-nontarget-distribution",
        BenchmarkPhenomenon.NON_TARGET_DISTRIBUTION_SHIFT,
    ),
    (
        "08-mixed-target-collateral",
        BenchmarkPhenomenon.MIXED_TARGET_COLLATERAL_SHIFT,
    ),
)


def cusum_spec():
    return SequentialDetectorSpec(
        detector_id="r11-cusum",
        session_id="r11-session",
        state_digest=raw_bytes_digest(b"r11-state"),
        measurement_digest=raw_bytes_digest(b"r11-measurement"),
        subject_digest=raw_bytes_digest(b"r11-subject"),
        subject_epoch=0,
        calibration=CAL,
        calibration_digest=CAL_DIGEST,
        max_consecutive_unknown=1,
        max_turn_gap=2,
        dimensions=(
            CusumDimensionPolicy(
                "collateral",
                baseline_mean=0.10,
                allowance=0.05,
                alarm_threshold=0.50,
            ),
            CusumDimensionPolicy(
                "target",
                baseline_mean=0.10,
                allowance=0.05,
                alarm_threshold=0.50,
            ),
        ),
    )


def candidates(spec):
    return (
        DetectorCandidate(
            candidate_id="cusum",
            algorithm=DetectorAlgorithm.CUSUM,
            cusum_spec_digest=spec.digest,
        ),
        DetectorCandidate(
            candidate_id="ewma",
            algorithm=DetectorAlgorithm.EWMA,
            parameterization=EWMA_PARAMS,
            parameterization_digest=EWMA_DIGEST,
            ewma=(
                EwmaDimensionPolicy(
                    "collateral",
                    baseline_mean=0.10,
                    smoothing=0.80,
                    alarm_threshold=0.50,
                    burn_in=1,
                ),
                EwmaDimensionPolicy(
                    "target",
                    baseline_mean=0.10,
                    smoothing=0.80,
                    alarm_threshold=0.50,
                    burn_in=1,
                ),
            ),
        ),
        DetectorCandidate(
            candidate_id="page-hinkley",
            algorithm=DetectorAlgorithm.PAGE_HINKLEY,
            parameterization=PH_PARAMS,
            parameterization_digest=PH_DIGEST,
            page_hinkley=(
                PageHinkleyDimensionPolicy(
                    "collateral",
                    delta=0.01,
                    alarm_threshold=0.50,
                    burn_in=1,
                ),
                PageHinkleyDimensionPolicy(
                    "target",
                    delta=0.01,
                    alarm_threshold=0.50,
                    burn_in=1,
                ),
            ),
        ),
    )


def _shift_dimensions(phenomenon):
    if phenomenon is BenchmarkPhenomenon.NON_TARGET_DISTRIBUTION_SHIFT:
        return ("collateral",)
    return ("target",)


def _post_shift_scores(phenomenon, *, offset=0.0):
    low = 0.10 + offset
    high = 0.90 + offset
    if phenomenon is BenchmarkPhenomenon.NON_TARGET_DISTRIBUTION_SHIFT:
        return (("collateral", high), ("target", low))
    if phenomenon is BenchmarkPhenomenon.MIXED_TARGET_COLLATERAL_SHIFT:
        return (("collateral", high), ("target", high))
    return (("collateral", low), ("target", high))


def corpus(role, *, label, offset=0.0, n=3):
    rows = []
    low = 0.10 + offset
    baseline = (("collateral", low), ("target", low))
    for family_id, phenomenon in FAMILY_ROWS:
        for index in range(n):
            rows.append(
                CalibrationTrajectory(
                    trajectory_id=f"{label}-{family_id}-stable-{index}",
                    family_id=family_id,
                    regime=CalibrationTrajectoryRegime.STABLE,
                    samples=tuple(baseline for _ in range(8)),
                )
            )
            rows.append(
                CalibrationTrajectory(
                    trajectory_id=f"{label}-{family_id}-shifted-{index}",
                    family_id=family_id,
                    regime=CalibrationTrajectoryRegime.SHIFTED,
                    samples=(
                        tuple(baseline for _ in range(4))
                        + tuple(
                            _post_shift_scores(
                                phenomenon,
                                offset=offset,
                            )
                            for _ in range(4)
                        )
                    ),
                    shift_index=4,
                    shift_dimensions=_shift_dimensions(phenomenon),
                )
            )
    return CalibrationCorpus(
        corpus_id=f"r11-{label}",
        version="1",
        role=role,
        trajectories=tuple(rows),
    )


def manifest(c, *, label):
    artifact_bytes = canonical_corpus_artifact_bytes(c)
    families = tuple(
        BenchmarkFamilyManifest(
            family_id=family_id,
            phenomenon=phenomenon,
            provenance=SourceBinding(
                f"benchmark://{label}/{family_id}",
                "v1",
            ),
            provenance_digest=raw_bytes_digest(
                f"{label}:{family_id}:provenance".encode("utf-8")
            ),
            dimension_ids=DIMENSIONS,
            expected_shift_dimensions=_shift_dimensions(phenomenon),
        )
        for family_id, phenomenon in FAMILY_ROWS
    )
    return BenchmarkCorpusManifest(
        manifest_id=f"manifest-{label}",
        corpus_id=c.corpus_id,
        corpus_version=c.version,
        corpus_role=c.role,
        corpus_digest=c.digest,
        artifact=SourceBinding(f"benchmark://{label}/corpus", "v1"),
        artifact_digest=sha256(artifact_bytes).hexdigest(),
        families=families,
    )


def family_policies():
    return tuple(
        CalibrationFamilyPolicy(
            family_id=family_id,
            minimum_stable_trajectories=2,
            minimum_shifted_trajectories=2,
            stable_horizon_observations=8,
            pre_shift_horizon_observations=4,
            post_shift_horizon_observations=4,
            maximum_stable_false_alarm_rate=1.0,
            maximum_pre_shift_false_alarm_rate=1.0,
            maximum_wrong_dimension_alarm_rate=1.0,
            minimum_detection_rate=0.0,
            maximum_mean_detection_delay=8.0,
        )
        for family_id, _ in FAMILY_ROWS
    )


def precommit():
    spec = cusum_spec()
    design = corpus(CalibrationCorpusRole.DESIGN, label="design", offset=0.0)
    holdout = corpus(
        CalibrationCorpusRole.HOLDOUT_QUALIFICATION,
        label="holdout",
        offset=0.01,
    )
    design_manifest = manifest(design, label="design")
    holdout_manifest = manifest(holdout, label="holdout")
    plan = BenchmarkPrecommitPlan(
        precommit_id="r11-precommit",
        design_manifest=design_manifest,
        holdout_seal=HoldoutCorpusSeal(
            seal_id="r11-holdout-seal",
            manifest=holdout_manifest,
        ),
        cusum_spec_digest=spec.digest,
        family_policies=family_policies(),
        candidates=candidates(spec),
        calibration_plan_id="r11-holdout-calibration",
        comparison_id="r11-holdout-comparison",
        precommit_artifact=SourceBinding("precommit://r11", "v1"),
        precommit_artifact_digest=raw_bytes_digest(b"r11-precommit-artifact"),
    )
    return plan, spec, design, holdout


class R11BenchmarkTests(unittest.TestCase):
    def test_core_manifest_requires_every_phenomenon_exactly_once(self):
        c = corpus(CalibrationCorpusRole.DESIGN, label="design")
        good = manifest(c, label="design")
        with self.assertRaisesRegex(
            ValueError,
            "cover every required phenomenon exactly once",
        ):
            replace(good, families=good.families[:-1])

    def test_family_dimension_contract_is_global_and_exact(self):
        c = corpus(CalibrationCorpusRole.DESIGN, label="design")
        good = manifest(c, label="design")
        changed = replace(
            good.families[0],
            dimension_ids=("target",),
            expected_shift_dimensions=("target",),
        )
        with self.assertRaisesRegex(
            ValueError,
            "one exact detector dimension set",
        ):
            replace(good, families=(changed, *good.families[1:]))

    def test_manifest_validates_exact_corpus_and_shift_labels(self):
        c = corpus(CalibrationCorpusRole.HOLDOUT_QUALIFICATION, label="holdout")
        m = manifest(c, label="holdout")
        m.validate_corpus(c)
        shifted = next(
            item
            for item in c.trajectories
            if item.regime is CalibrationTrajectoryRegime.SHIFTED
        )
        changed = replace(
            shifted,
            shift_dimensions=(
                "collateral",
                "target",
            ),
        )
        changed_corpus = replace(
            c,
            trajectories=tuple(
                changed if item.trajectory_id == shifted.trajectory_id else item
                for item in c.trajectories
            ),
        )
        with self.assertRaisesRegex(
            ValueError,
            "corpus digest mismatch",
        ):
            m.validate_corpus(changed_corpus)

    def test_design_and_holdout_portfolio_contracts_match(self):
        plan, _, _, _ = precommit()
        self.assertEqual(
            plan.design_manifest.portfolio_digest,
            plan.holdout_seal.manifest.portfolio_digest,
        )

    def test_precommit_binds_exact_future_r9_and_r10_plan_digests(self):
        plan, spec, _, _ = precommit()
        self.assertEqual(
            spec.digest,
            plan.holdout_calibration_plan.detector_spec_digest,
        )
        self.assertEqual(
            plan.holdout_calibration_plan.digest,
            plan.holdout_comparison_plan.calibration_plan_digest,
        )
        self.assertEqual(
            plan.holdout_seal.manifest.corpus_digest,
            plan.holdout_comparison_plan.corpus_digest,
        )

    def test_holdout_candidate_mutation_moves_precommit_identity(self):
        plan, spec, _, _ = precommit()
        changed = list(plan.candidates)
        ewma = next(
            item
            for item in changed
            if item.algorithm is DetectorAlgorithm.EWMA
        )
        changed_ewma = replace(
            ewma,
            ewma=tuple(
                replace(row, alarm_threshold=0.60)
                for row in ewma.ewma
            ),
        )
        changed = tuple(
            changed_ewma if item.algorithm is DetectorAlgorithm.EWMA else item
            for item in changed
        )
        changed = tuple(sorted(changed, key=lambda row: row.candidate_id))
        other = replace(plan, candidates=changed)
        self.assertNotEqual(plan.digest, other.digest)
        self.assertNotEqual(
            plan.holdout_comparison_plan.digest,
            other.holdout_comparison_plan.digest,
        )
        self.assertEqual(spec.digest, other.cusum_spec_digest)

    def test_holdout_policy_mutation_moves_precommit_identity(self):
        plan, _, _, _ = precommit()
        changed_policy = replace(
            plan.family_policies[0],
            minimum_detection_rate=0.50,
        )
        changed = replace(
            plan,
            family_policies=(
                changed_policy,
                *plan.family_policies[1:],
            ),
        )
        self.assertNotEqual(plan.digest, changed.digest)
        self.assertNotEqual(
            plan.holdout_calibration_plan.digest,
            changed.holdout_calibration_plan.digest,
        )

    def test_reveal_requires_canonical_artifact_bytes_for_exact_corpus(self):
        plan, _, _, holdout = precommit()
        m = plan.holdout_seal.manifest
        receipt = reveal_holdout(
            precommit=plan,
            manifest=m,
            corpus=holdout,
            artifact_bytes=canonical_corpus_artifact_bytes(holdout),
        )
        self.assertEqual(REVEAL_CLAIM, receipt.reveal_claim)
        with self.assertRaisesRegex(
            ValueError,
            "do not canonically encode corpus",
        ):
            reveal_holdout(
                precommit=plan,
                manifest=m,
                corpus=holdout,
                artifact_bytes=b"not-the-corpus",
            )

    def test_reveal_rejects_changed_holdout_corpus(self):
        plan, _, _, holdout = precommit()
        first = holdout.trajectories[0]
        sample = list(first.samples)
        sample[0] = (("collateral", 0.12), ("target", 0.11))
        changed = replace(
            holdout,
            trajectories=(
                replace(first, samples=tuple(sample)),
                *holdout.trajectories[1:],
            ),
        )
        with self.assertRaisesRegex(ValueError, "corpus digest mismatch"):
            reveal_holdout(
                precommit=plan,
                manifest=plan.holdout_seal.manifest,
                corpus=changed,
                artifact_bytes=canonical_corpus_artifact_bytes(changed),
            )

    def test_reveal_receipt_cannot_be_directly_constructed(self):
        plan, _, _, _ = precommit()
        with self.assertRaisesRegex(
            ValueError,
            "must come from reveal_holdout",
        ):
            HoldoutRevealReceipt(
                precommit_digest=plan.digest,
                seal_digest=plan.holdout_seal.digest,
                manifest_digest=plan.holdout_seal.manifest.digest,
                corpus_digest=plan.holdout_seal.manifest.corpus_digest,
                artifact_digest=plan.holdout_seal.manifest.artifact_digest,
                reveal_claim=REVEAL_CLAIM,
            )

    def test_precommit_claim_does_not_pretend_nonaccess_or_trusted_time(self):
        plan, _, _, _ = precommit()
        self.assertEqual(PRECOMMIT_CLAIM, plan.precommit_claim)
        self.assertIn("NOT_PROOF_OF_NONACCESS", plan.precommit_claim)
        self.assertIn("TRUSTED_TIME", plan.precommit_claim)

    def test_exact_precommitted_holdout_executes_r10_without_promotion(self):
        plan, spec, _, holdout = precommit()
        m = plan.holdout_seal.manifest
        reveal = reveal_holdout(
            precommit=plan,
            manifest=m,
            corpus=holdout,
            artifact_bytes=canonical_corpus_artifact_bytes(holdout),
        )
        result = run_precommitted_holdout(
            precommit=plan,
            reveal=reveal,
            manifest=m,
            corpus=holdout,
            cusum_spec=spec,
        )
        self.assertFalse(result.receipt.promotion_authorized)
        self.assertFalse(result.comparison.promotion_authorized)
        self.assertEqual(RUN_CLAIM, result.receipt.run_claim)
        self.assertEqual(
            plan.holdout_calibration_plan.digest,
            result.receipt.calibration_plan_digest,
        )
        self.assertEqual(
            plan.holdout_comparison_plan.digest,
            result.receipt.comparison_plan_digest,
        )
        self.assertEqual(
            result.comparison.digest,
            result.receipt.comparison_receipt_digest,
        )

    def test_run_rejects_changed_cusum_spec(self):
        plan, spec, _, holdout = precommit()
        m = plan.holdout_seal.manifest
        reveal = reveal_holdout(
            precommit=plan,
            manifest=m,
            corpus=holdout,
            artifact_bytes=canonical_corpus_artifact_bytes(holdout),
        )
        changed_spec = replace(
            spec,
            dimensions=tuple(
                replace(row, alarm_threshold=0.60)
                if row.dimension_id == "target"
                else row
                for row in spec.dimensions
            ),
        )
        with self.assertRaisesRegex(
            ValueError,
            "CUSUM spec digest mismatch",
        ):
            run_precommitted_holdout(
                precommit=plan,
                reveal=reveal,
                manifest=m,
                corpus=holdout,
                cusum_spec=changed_spec,
            )

    def test_run_receipt_cannot_be_directly_constructed(self):
        plan, _, _, _ = precommit()
        with self.assertRaisesRegex(
            ValueError,
            "must come from run_precommitted_holdout",
        ):
            BenchmarkRunReceipt(
                precommit_digest=plan.digest,
                reveal_digest=raw_bytes_digest(b"reveal"),
                calibration_plan_digest=plan.holdout_calibration_plan.digest,
                comparison_plan_digest=plan.holdout_comparison_plan.digest,
                comparison_receipt_digest=raw_bytes_digest(b"comparison"),
                promotion_authorized=False,
                run_claim=RUN_CLAIM,
            )

    def test_holdout_seal_rejects_design_manifest(self):
        design = corpus(CalibrationCorpusRole.DESIGN, label="design")
        with self.assertRaisesRegex(
            ValueError,
            "requires HOLDOUT_QUALIFICATION",
        ):
            HoldoutCorpusSeal(
                seal_id="bad-seal",
                manifest=manifest(design, label="design"),
            )


if __name__ == "__main__":
    unittest.main()
