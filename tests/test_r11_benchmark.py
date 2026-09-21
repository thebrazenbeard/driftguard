from dataclasses import replace
from hashlib import sha256
import os
import tempfile
import unittest

from driftguard.benchmark import (
    BenchmarkAttemptLedger,
    BenchmarkAttemptReceipt,
    BenchmarkAttemptStatus,
    BenchmarkCorpusManifest,
    BenchmarkExecutionBinding,
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
    current_execution_binding,
    reveal_holdout,
    run_precommitted_holdout,
    trajectory_content_digest,
)
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
from driftguard.model import SourceBinding, raw_bytes_digest
from driftguard.sequential import CusumDimensionPolicy, SequentialDetectorSpec


CAL = SourceBinding("calibration://r11-cusum", "v1")
CAL_DIGEST = raw_bytes_digest(b"r11-cusum-calibration")
PH_PARAMS = SourceBinding("comparison://r11-page-hinkley", "v1")
PH_DIGEST = raw_bytes_digest(b"r11-page-hinkley")
EWMA_PARAMS = SourceBinding("comparison://r11-ewma", "v1")
EWMA_DIGEST = raw_bytes_digest(b"r11-ewma")
PRIOR_R10_HOLDOUT = raw_bytes_digest(b"historical-r9-r10-holdout")
DIMENSIONS = ("collateral", "target")
TEST_COMMIT = "a" * 40

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
        trajectory_content_digest=trajectory_content_digest(c),
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


def execution_binding():
    return current_execution_binding(
        repository="thebrazenbeard/driftguard",
        commit_sha=TEST_COMMIT,
    )


def make_precommit(
    *,
    study_id="study-r11",
    attempt_id="attempt-1",
    precommit_id="precommit-1",
    predecessor_attempt_digests=(),
    predecessor_holdout_digests=(PRIOR_R10_HOLDOUT,),
    holdout_label="holdout-1",
    holdout_offset=0.01,
):
    spec = cusum_spec()
    design = corpus(
        CalibrationCorpusRole.DESIGN,
        label=f"design-{attempt_id}",
        offset=0.0,
    )
    holdout = corpus(
        CalibrationCorpusRole.HOLDOUT_QUALIFICATION,
        label=holdout_label,
        offset=holdout_offset,
    )
    plan = BenchmarkPrecommitPlan(
        study_id=study_id,
        attempt_id=attempt_id,
        precommit_id=precommit_id,
        predecessor_attempt_digests=tuple(
            sorted(predecessor_attempt_digests)
        ),
        predecessor_holdout_digests=tuple(
            sorted(predecessor_holdout_digests)
        ),
        execution_binding=execution_binding(),
        design_manifest=manifest(
            design,
            label=f"design-{attempt_id}",
        ),
        holdout_seal=HoldoutCorpusSeal(
            seal_id=f"seal-{attempt_id}",
            manifest=manifest(holdout, label=holdout_label),
        ),
        cusum_spec_digest=spec.digest,
        family_policies=family_policies(),
        candidates=candidates(spec),
        calibration_plan_id=f"calibration-{attempt_id}",
        comparison_id=f"comparison-{attempt_id}",
        precommit_artifact=SourceBinding(
            f"precommit://{attempt_id}",
            "v1",
        ),
        precommit_artifact_digest=raw_bytes_digest(
            f"precommit:{attempt_id}".encode("utf-8")
        ),
    )
    return plan, spec, holdout


class R11BenchmarkTests(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.close()
        self.path = handle.name
        self.registry = BenchmarkAttemptLedger(self.path)

    def tearDown(self):
        os.unlink(self.path)

    def seal(self, **kwargs):
        plan, spec, holdout = make_precommit(**kwargs)
        receipt = self.registry.seal_precommit(precommit=plan)
        return plan, spec, holdout, receipt

    def reveal(self, plan, holdout):
        return reveal_holdout(
            registry=self.registry,
            precommit=plan,
            execution_binding=plan.execution_binding,
            manifest=plan.holdout_seal.manifest,
            corpus=holdout,
            artifact_bytes=canonical_corpus_artifact_bytes(holdout),
        )

    def run(self, plan, spec, holdout, reveal):
        return run_precommitted_holdout(
            registry=self.registry,
            precommit=plan,
            execution_binding=plan.execution_binding,
            reveal=reveal,
            manifest=plan.holdout_seal.manifest,
            corpus=holdout,
            cusum_spec=spec,
        )

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

    def test_design_and_holdout_cannot_reuse_identical_trajectory_content(self):
        spec = cusum_spec()
        design = corpus(CalibrationCorpusRole.DESIGN, label="same")
        holdout = CalibrationCorpus(
            corpus_id="same-holdout",
            version="1",
            role=CalibrationCorpusRole.HOLDOUT_QUALIFICATION,
            trajectories=design.trajectories,
        )
        with self.assertRaisesRegex(
            ValueError,
            "cannot reuse identical trajectory content",
        ):
            BenchmarkPrecommitPlan(
                study_id="same-study",
                attempt_id="same-attempt",
                precommit_id="same-precommit",
                predecessor_attempt_digests=(),
                predecessor_holdout_digests=(PRIOR_R10_HOLDOUT,),
                execution_binding=execution_binding(),
                design_manifest=manifest(design, label="same-design"),
                holdout_seal=HoldoutCorpusSeal(
                    seal_id="same-seal",
                    manifest=manifest(holdout, label="same-holdout"),
                ),
                cusum_spec_digest=spec.digest,
                family_policies=family_policies(),
                candidates=candidates(spec),
                calibration_plan_id="same-cal",
                comparison_id="same-cmp",
                precommit_artifact=SourceBinding("precommit://same", "v1"),
                precommit_artifact_digest=raw_bytes_digest(b"same"),
            )

    def test_r11_holdout_cannot_reuse_declared_r9_r10_holdout(self):
        plan, _, holdout = make_precommit()
        with self.assertRaisesRegex(
            ValueError,
            "cannot reuse a predecessor R9/R10",
        ):
            replace(
                plan,
                predecessor_holdout_digests=tuple(
                    sorted(
                        {
                            PRIOR_R10_HOLDOUT,
                            holdout.digest,
                        }
                    )
                ),
            )

    def test_precommit_binds_exact_future_r9_r10_and_execution_subject(self):
        plan, spec, _ = make_precommit()
        self.assertEqual(
            spec.digest,
            plan.holdout_calibration_plan.detector_spec_digest,
        )
        self.assertEqual(
            plan.holdout_calibration_plan.digest,
            plan.holdout_comparison_plan.calibration_plan_digest,
        )
        self.assertEqual(
            execution_binding().digest,
            plan.execution_binding.digest,
        )
        self.assertEqual(PRECOMMIT_CLAIM, plan.precommit_claim)

    def test_forged_execution_source_binding_is_rejected_before_seal(self):
        plan, _, _ = make_precommit()
        forged = replace(
            plan.execution_binding,
            benchmark_source_digest=raw_bytes_digest(b"changed-benchmark-code"),
        )
        with self.assertRaisesRegex(
            ValueError,
            "runtime source digests do not match",
        ):
            self.registry.seal_precommit(
                precommit=replace(plan, execution_binding=forged),
            )

    def test_second_active_attempt_for_same_study_is_rejected(self):
        self.seal()
        second, _, _ = make_precommit(
            attempt_id="attempt-2",
            precommit_id="precommit-2",
            holdout_label="holdout-2",
            holdout_offset=0.02,
        )
        with self.assertRaisesRegex(
            ValueError,
            "already has an active benchmark attempt",
        ):
            self.registry.seal_precommit(precommit=second)

    def test_same_precommit_id_cannot_bind_divergent_digest(self):
        first, _, _, _ = self.seal()
        changed, _, _ = make_precommit(
            attempt_id="attempt-2",
            precommit_id=first.precommit_id,
            holdout_label="holdout-2",
            holdout_offset=0.02,
        )
        with self.assertRaisesRegex(
            ValueError,
            "same precommit_id cannot bind divergent",
        ):
            self.registry.seal_precommit(precommit=changed)

    def test_reveal_requires_durable_seal(self):
        plan, _, holdout = make_precommit()
        with self.assertRaisesRegex(
            ValueError,
            "must be durably sealed",
        ):
            self.reveal(plan, holdout)

    def test_reveal_replay_is_rejected_and_first_reveal_remains_durable(self):
        plan, _, holdout, _ = self.seal()
        reveal = self.reveal(plan, holdout)
        durable = self.registry.attempt_receipt(
            attempt_id=plan.attempt_id,
        )
        self.assertEqual(BenchmarkAttemptStatus.REVEALED, durable.status)
        self.assertEqual(reveal.digest, durable.reveal_digest)
        with self.assertRaisesRegex(
            ValueError,
            "must be SEALED",
        ):
            self.reveal(plan, holdout)

    def test_run_replay_is_rejected(self):
        plan, spec, holdout, _ = self.seal()
        reveal = self.reveal(plan, holdout)
        result = self.run(plan, spec, holdout, reveal)
        durable = self.registry.attempt_receipt(
            attempt_id=plan.attempt_id,
        )
        self.assertEqual(BenchmarkAttemptStatus.EXECUTED, durable.status)
        self.assertEqual(result.receipt.digest, durable.run_digest)
        with self.assertRaisesRegex(
            ValueError,
            "must be REVEALED",
        ):
            self.run(plan, spec, holdout, reveal)

    def test_revealed_attempt_can_be_aborted_but_history_remains(self):
        plan, _, holdout, _ = self.seal()
        reveal = self.reveal(plan, holdout)
        aborted = self.registry.abort_attempt(
            attempt_id=plan.attempt_id,
            reason="external custody anomaly",
        )
        self.assertEqual(BenchmarkAttemptStatus.ABORTED, aborted.status)
        self.assertEqual(reveal.digest, aborted.reveal_digest)
        reopened = BenchmarkAttemptLedger(self.path)
        readback = reopened.attempt_receipt(attempt_id=plan.attempt_id)
        self.assertEqual(aborted, readback)

    def test_successor_attempt_without_predecessor_reference_is_rejected(self):
        first, _, first_holdout, _ = self.seal()
        self.registry.abort_attempt(
            attempt_id=first.attempt_id,
            reason="first attempt intentionally abandoned",
        )
        second, _, _ = make_precommit(
            attempt_id="attempt-2",
            precommit_id="precommit-2",
            predecessor_attempt_digests=(),
            predecessor_holdout_digests=(
                PRIOR_R10_HOLDOUT,
                first_holdout.digest,
            ),
            holdout_label="holdout-2",
            holdout_offset=0.02,
        )
        with self.assertRaisesRegex(
            ValueError,
            "reference every prior terminal attempt digest",
        ):
            self.registry.seal_precommit(precommit=second)

    def test_successor_attempt_must_disclose_prior_holdout_and_can_chain_exactly(self):
        first, _, first_holdout, _ = self.seal()
        terminal = self.registry.abort_attempt(
            attempt_id=first.attempt_id,
            reason="documented abort",
        )
        missing_holdout, _, _ = make_precommit(
            attempt_id="attempt-2",
            precommit_id="precommit-2",
            predecessor_attempt_digests=(terminal.digest,),
            predecessor_holdout_digests=(PRIOR_R10_HOLDOUT,),
            holdout_label="holdout-2",
            holdout_offset=0.02,
        )
        with self.assertRaisesRegex(
            ValueError,
            "disclose every prior attempt holdout digest",
        ):
            self.registry.seal_precommit(precommit=missing_holdout)

        valid, _, _ = make_precommit(
            attempt_id="attempt-3",
            precommit_id="precommit-3",
            predecessor_attempt_digests=(terminal.digest,),
            predecessor_holdout_digests=tuple(
                sorted(
                    {
                        PRIOR_R10_HOLDOUT,
                        first_holdout.digest,
                    }
                )
            ),
            holdout_label="holdout-3",
            holdout_offset=0.03,
        )
        sealed = self.registry.seal_precommit(precommit=valid)
        self.assertEqual(
            (terminal.digest,),
            sealed.predecessor_attempt_digests,
        )

    def test_execution_binding_change_after_seal_blocks_reveal(self):
        plan, _, holdout, _ = self.seal()
        changed = replace(
            plan.execution_binding,
            commit_sha="b" * 40,
        )
        with self.assertRaisesRegex(
            ValueError,
            "does not match precommit",
        ):
            reveal_holdout(
                registry=self.registry,
                precommit=plan,
                execution_binding=changed,
                manifest=plan.holdout_seal.manifest,
                corpus=holdout,
                artifact_bytes=canonical_corpus_artifact_bytes(holdout),
            )

    def test_reveal_requires_exact_canonical_artifact_bytes(self):
        plan, _, holdout, _ = self.seal()
        with self.assertRaisesRegex(
            ValueError,
            "do not canonically encode corpus",
        ):
            reveal_holdout(
                registry=self.registry,
                precommit=plan,
                execution_binding=plan.execution_binding,
                manifest=plan.holdout_seal.manifest,
                corpus=holdout,
                artifact_bytes=b"not-the-corpus",
            )

    def test_exact_precommitted_holdout_executes_r10_without_promotion(self):
        plan, spec, holdout, _ = self.seal()
        reveal = self.reveal(plan, holdout)
        result = self.run(plan, spec, holdout, reveal)
        self.assertFalse(result.receipt.promotion_authorized)
        self.assertFalse(result.comparison.promotion_authorized)
        self.assertEqual(RUN_CLAIM, result.receipt.run_claim)
        self.assertEqual(plan.study_id, result.receipt.study_id)
        self.assertEqual(plan.attempt_id, result.receipt.attempt_id)
        self.assertEqual(
            plan.execution_binding.digest,
            result.receipt.execution_binding_digest,
        )

    def test_changed_cusum_spec_after_reveal_fails_and_attempt_remains_revealed(self):
        plan, spec, holdout, _ = self.seal()
        reveal = self.reveal(plan, holdout)
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
            self.run(plan, changed_spec, holdout, reveal)
        durable = self.registry.attempt_receipt(
            attempt_id=plan.attempt_id,
        )
        self.assertEqual(BenchmarkAttemptStatus.REVEALED, durable.status)
        self.assertEqual(reveal.digest, durable.reveal_digest)

    def test_direct_attempt_receipt_construction_is_rejected(self):
        plan, _, _, _ = self.seal()
        with self.assertRaisesRegex(
            ValueError,
            "must come from BenchmarkAttemptLedger",
        ):
            BenchmarkAttemptReceipt(
                study_id=plan.study_id,
                attempt_id=plan.attempt_id,
                precommit_id=plan.precommit_id,
                precommit_digest=plan.digest,
                seal_digest=plan.holdout_seal.digest,
                holdout_corpus_digest=plan.holdout_seal.manifest.corpus_digest,
                execution_binding_digest=plan.execution_binding.digest,
                predecessor_attempt_digests=(),
                status=BenchmarkAttemptStatus.SEALED,
                reveal_digest=None,
                run_digest=None,
                reason=None,
            )

    def test_direct_reveal_receipt_construction_is_rejected(self):
        plan, _, _, _ = self.seal()
        with self.assertRaisesRegex(
            ValueError,
            "must come from reveal_holdout",
        ):
            HoldoutRevealReceipt(
                study_id=plan.study_id,
                attempt_id=plan.attempt_id,
                precommit_digest=plan.digest,
                execution_binding_digest=plan.execution_binding.digest,
                seal_digest=plan.holdout_seal.digest,
                manifest_digest=plan.holdout_seal.manifest.digest,
                corpus_digest=plan.holdout_seal.manifest.corpus_digest,
                artifact_digest=plan.holdout_seal.manifest.artifact_digest,
                reveal_claim=REVEAL_CLAIM,
            )

    def test_direct_run_receipt_construction_is_rejected(self):
        plan, _, _, _ = self.seal()
        with self.assertRaisesRegex(
            ValueError,
            "must come from run_precommitted_holdout",
        ):
            BenchmarkRunReceipt(
                study_id=plan.study_id,
                attempt_id=plan.attempt_id,
                precommit_digest=plan.digest,
                execution_binding_digest=plan.execution_binding.digest,
                reveal_digest=raw_bytes_digest(b"reveal"),
                calibration_plan_digest=plan.holdout_calibration_plan.digest,
                comparison_plan_digest=plan.holdout_comparison_plan.digest,
                comparison_receipt_digest=raw_bytes_digest(b"comparison"),
                promotion_authorized=False,
                run_claim=RUN_CLAIM,
            )

    def test_precommit_claim_explicitly_denies_nonaccess_and_trusted_time(self):
        plan, _, _ = make_precommit()
        self.assertEqual(PRECOMMIT_CLAIM, plan.precommit_claim)
        self.assertIn("NOT_PROOF_OF_NONACCESS", plan.precommit_claim)
        self.assertIn("TRUSTED_TIME", plan.precommit_claim)


if __name__ == "__main__":
    unittest.main()
