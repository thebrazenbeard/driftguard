from dataclasses import replace
import os
import tempfile
import unittest

from driftguard import (
    BehaviorDimension,
    Decision,
    DriftEvidence,
    DriftGuardEngine,
    DriftPolicy,
    EvidenceIndependence,
    MeasurementMode,
    ProbeSource,
    SaveState,
    SourceBinding,
)
from driftguard.external_boundary import build_evaluator_request
from driftguard.ledger import DriftLedger
from driftguard.model import raw_bytes_digest


OBS = raw_bytes_digest(b"r6-measurement-observation")
CAL_A = SourceBinding("calibration://judge-a", "2026-09-20")
CAL_B = SourceBinding("calibration://judge-b", "2026-09-20")
CAL_DIGEST_A = raw_bytes_digest(b"calibration-artifact-a")
CAL_DIGEST_B = raw_bytes_digest(b"calibration-artifact-b")
SRC_A = SourceBinding("probe://judge-a", "v2")
SRC_B = SourceBinding("probe://judge-b", "v2")


def strict_single_dimension(*, same_group=False, min_sources=2, min_groups=2):
    return SaveState(
        state_id="strict-single",
        version="1",
        restore_text="Preserve governed behavior.",
        dimensions=(
            BehaviorDimension(
                "truthfulness",
                "Keep claims evidence-bounded.",
                critical=True,
                min_independence=EvidenceIndependence.SEPARATE_CONTEXT,
                min_sources=min_sources,
                min_correlation_groups=min_groups,
                score_scale="calibrated-drift-v1",
                warn_threshold=0.25,
                reload_threshold=0.45,
                critical_reload_threshold=0.40,
            ),
        ),
        probe_sources=(
            ProbeSource(
                SRC_A,
                EvidenceIndependence.EXTERNAL,
                ("truthfulness",),
                calibration=CAL_A,
                calibration_digest=CAL_DIGEST_A,
                correlation_group="root-a",
                score_scale="calibrated-drift-v1",
            ),
            ProbeSource(
                SRC_B,
                EvidenceIndependence.EXTERNAL,
                ("truthfulness",),
                calibration=CAL_B,
                calibration_digest=CAL_DIGEST_B,
                correlation_group="root-a" if same_group else "root-b",
                score_scale="calibrated-drift-v1",
            ),
        ),
        policy=DriftPolicy(
            warn_threshold=0.25,
            reload_threshold=0.45,
            critical_reload_threshold=0.40,
            max_turns_without_reload=100,
            reload_cooldown_turns=0,
        ),
        measurement_mode=MeasurementMode.CALIBRATED_QUORUM,
    )


def rows(state, values=(0.10, 0.20), turn=3):
    sources = (SRC_A, SRC_B)
    return tuple(
        DriftEvidence(
            f"e-{index}",
            "truthfulness",
            value,
            EvidenceIndependence.EXTERNAL,
            (source,),
            f"run-{index}",
            state.digest,
            OBS,
            turn,
        )
        for index, (source, value) in enumerate(zip(sources, values), 1)
    )


def strict_two_dimension():
    truth = SourceBinding("probe://truth", "v2")
    style = SourceBinding("probe://style", "v2")
    return SaveState(
        "strict-two",
        "1",
        "Preserve truth discipline and direct style.",
        (
            BehaviorDimension(
                "truth",
                "Truth discipline.",
                score_scale="calibrated-drift-v1",
                warn_threshold=0.20,
                reload_threshold=0.50,
            ),
            BehaviorDimension(
                "style",
                "Direct style.",
                score_scale="calibrated-drift-v1",
                warn_threshold=0.25,
                reload_threshold=0.60,
            ),
        ),
        (
            ProbeSource(
                truth,
                EvidenceIndependence.SEPARATE_CONTEXT,
                ("truth",),
                calibration=SourceBinding("calibration://truth", "v1"),
                calibration_digest=raw_bytes_digest(b"truth-calibration"),
                correlation_group="truth-root",
                score_scale="calibrated-drift-v1",
            ),
            ProbeSource(
                style,
                EvidenceIndependence.SEPARATE_CONTEXT,
                ("style",),
                calibration=SourceBinding("calibration://style", "v1"),
                calibration_digest=raw_bytes_digest(b"style-calibration"),
                correlation_group="style-root",
                score_scale="calibrated-drift-v1",
            ),
        ),
        DriftPolicy(max_turns_without_reload=100, reload_cooldown_turns=0),
        MeasurementMode.CALIBRATED_QUORUM,
    )


class R6MeasurementValidityTests(unittest.TestCase):
    def setUp(self):
        self.engine = DriftGuardEngine()

    def evaluate(self, state, evidence):
        return self.engine.evaluate(
            state=state,
            evidence=evidence,
            observation_digest=OBS,
            turn_index=3,
            generation=0,
            restore_anchor_turn=0,
            last_reload_decision_turn=None,
        )

    def test_strict_mode_accepts_real_multi_source_quorum(self):
        state = strict_single_dimension()
        result = self.evaluate(state, rows(state))
        self.assertEqual(Decision.STABLE, result.decision)
        self.assertEqual(Decision.STABLE, result.behavioral_decision)
        self.assertIsNone(result.aggregate_drift)
        self.assertEqual("truthfulness", result.dimension_scores[0][0])
        self.assertAlmostEqual(0.15, result.dimension_scores[0][1])

    def test_missing_second_source_fails_closed(self):
        state = strict_single_dimension()
        result = self.evaluate(state, rows(state)[:1])
        self.assertEqual(Decision.UNKNOWN, result.decision)
        self.assertIn(
            "insufficient_source_quorum:truthfulness",
            result.reasons,
        )

    def test_two_sources_with_same_root_do_not_fake_independence(self):
        state = strict_single_dimension(same_group=True, min_groups=1)
        strict_dimension = BehaviorDimension(
            "truthfulness",
            "Keep claims evidence-bounded.",
            critical=True,
            min_independence=EvidenceIndependence.SEPARATE_CONTEXT,
            min_sources=2,
            min_correlation_groups=2,
            score_scale="calibrated-drift-v1",
            warn_threshold=0.25,
            reload_threshold=0.45,
            critical_reload_threshold=0.40,
        )
        with self.assertRaisesRegex(
            ValueError,
            "insufficient eligible correlation groups",
        ):
            SaveState(
                state.state_id,
                state.version,
                state.restore_text,
                (strict_dimension,),
                state.probe_sources,
                state.policy,
                MeasurementMode.CALIBRATED_QUORUM,
            )

    def test_runtime_quorum_rejects_missing_correlation_diversity(self):
        state = strict_single_dimension(min_sources=2, min_groups=2)
        bad_sources = (
            ProbeSource(
                SRC_A,
                EvidenceIndependence.EXTERNAL,
                ("truthfulness",),
                calibration=CAL_A,
                calibration_digest=CAL_DIGEST_A,
                correlation_group="root-a",
                score_scale="calibrated-drift-v1",
            ),
            ProbeSource(
                SRC_B,
                EvidenceIndependence.EXTERNAL,
                ("truthfulness",),
                calibration=CAL_B,
                calibration_digest=CAL_DIGEST_B,
                correlation_group="root-b",
                score_scale="calibrated-drift-v1",
            ),
        )
        # State construction proves two independent roots exist. Supplying only
        # one root at runtime cannot satisfy the observation quorum.
        self.assertEqual(2, len({s.correlation_group for s in bad_sources}))
        result = self.evaluate(state, rows(state)[:1])
        self.assertIn(
            "insufficient_correlation_quorum:truthfulness",
            result.reasons,
        )

    def test_strict_mode_requires_calibration_binding(self):
        with self.assertRaisesRegex(ValueError, "require calibration"):
            SaveState(
                "uncalibrated",
                "1",
                "Preserve behavior.",
                (
                    BehaviorDimension(
                        "d",
                        "dimension",
                        score_scale="scale-v1",
                        warn_threshold=0.25,
                        reload_threshold=0.45,
                    ),
                ),
                (
                    ProbeSource(
                        SourceBinding("probe://uncalibrated", "v1"),
                        EvidenceIndependence.SEPARATE_CONTEXT,
                        ("d",),
                        correlation_group="root",
                        score_scale="scale-v1",
                    ),
                ),
                measurement_mode=MeasurementMode.CALIBRATED_QUORUM,
            )

    def test_strict_mode_rejects_mismatched_score_scales(self):
        with self.assertRaisesRegex(ValueError, "score_scale must match"):
            SaveState(
                "bad-scale",
                "1",
                "Preserve behavior.",
                (
                    BehaviorDimension(
                        "d",
                        "dimension",
                        score_scale="scale-a",
                        warn_threshold=0.25,
                        reload_threshold=0.45,
                    ),
                ),
                (
                    ProbeSource(
                        SourceBinding("probe://scale", "v1"),
                        EvidenceIndependence.SEPARATE_CONTEXT,
                        ("d",),
                        calibration=SourceBinding("calibration://scale", "v1"),
                        calibration_digest=raw_bytes_digest(b"scale-calibration"),
                        correlation_group="root",
                        score_scale="scale-b",
                    ),
                ),
                measurement_mode=MeasurementMode.CALIBRATED_QUORUM,
            )

    def test_strict_mode_does_not_average_unrelated_dimensions(self):
        state = strict_two_dimension()
        truth_source = state.probe_sources[0].binding
        style_source = state.probe_sources[1].binding
        evidence = (
            DriftEvidence(
                "truth",
                "truth",
                0.10,
                EvidenceIndependence.SEPARATE_CONTEXT,
                (truth_source,),
                "run-truth",
                state.digest,
                OBS,
                3,
            ),
            DriftEvidence(
                "style",
                "style",
                0.30,
                EvidenceIndependence.SEPARATE_CONTEXT,
                (style_source,),
                "run-style",
                state.digest,
                OBS,
                3,
            ),
        )
        result = self.evaluate(state, evidence)
        self.assertEqual(Decision.WARN, result.decision)
        self.assertEqual(Decision.WARN, result.behavioral_decision)
        self.assertIsNone(result.aggregate_drift)
        self.assertIn("dimension_warn_threshold:style", result.reasons)

    def test_dimension_thresholds_replace_global_numeric_thresholds(self):
        state = strict_two_dimension()
        truth_source = state.probe_sources[0].binding
        style_source = state.probe_sources[1].binding
        evidence = (
            DriftEvidence(
                "truth",
                "truth",
                0.22,
                EvidenceIndependence.SEPARATE_CONTEXT,
                (truth_source,),
                "run-truth",
                state.digest,
                OBS,
                3,
            ),
            DriftEvidence(
                "style",
                "style",
                0.10,
                EvidenceIndependence.SEPARATE_CONTEXT,
                (style_source,),
                "run-style",
                state.digest,
                OBS,
                3,
            ),
        )
        result = self.evaluate(state, evidence)
        self.assertLess(0.22, state.policy.warn_threshold)
        self.assertEqual(Decision.WARN, result.behavioral_decision)
        self.assertIn("dimension_warn_threshold:truth", result.reasons)

    def test_threshold_change_only_moves_detection_policy_identity(self):
        state = strict_two_dimension()
        changed = replace(
            state,
            dimensions=(
                replace(state.dimensions[0], warn_threshold=0.21),
                state.dimensions[1],
            ),
        )
        self.assertEqual(state.behavior_digest, changed.behavior_digest)
        self.assertEqual(state.measurement_digest, changed.measurement_digest)
        self.assertNotEqual(
            state.detection_policy_digest,
            changed.detection_policy_digest,
        )
        self.assertNotEqual(state.digest, changed.digest)

    def test_single_critical_source_cannot_bypass_strict_quorum(self):
        state = strict_single_dimension()
        result = self.evaluate(state, rows(state, values=(0.90, 0.10))[:1])
        self.assertEqual(Decision.UNKNOWN, result.decision)
        self.assertEqual(Decision.UNKNOWN, result.behavioral_decision)
        self.assertFalse(result.reload_required)
        self.assertNotIn("critical_dimension_breach", result.reasons)

    def test_critical_source_with_full_quorum_remains_fail_safe(self):
        state = strict_single_dimension()
        result = self.evaluate(state, rows(state, values=(0.41, 0.00)))
        self.assertEqual(Decision.RELOAD, result.decision)
        self.assertEqual(Decision.RELOAD, result.behavioral_decision)
        self.assertTrue(result.reload_required)
        self.assertIn("critical_dimension_breach", result.reasons)

    def test_strict_mode_rejects_legacy_dimension_weights(self):
        with self.assertRaisesRegex(ValueError, "do not permit legacy weights"):
            state = strict_single_dimension()
            SaveState(
                state.state_id,
                state.version,
                state.restore_text,
                (replace(state.dimensions[0], weight=2.0),),
                state.probe_sources,
                state.policy,
                MeasurementMode.CALIBRATED_QUORUM,
            )

    def test_restore_text_change_moves_control_not_behavior_identity(self):
        state = strict_two_dimension()
        changed = replace(
            state,
            restore_text=state.restore_text + " More explicit control wording.",
        )
        self.assertEqual(state.behavior_digest, changed.behavior_digest)
        self.assertEqual(state.measurement_digest, changed.measurement_digest)
        self.assertEqual(
            state.detection_policy_digest,
            changed.detection_policy_digest,
        )
        self.assertNotEqual(
            state.control_policy_digest,
            changed.control_policy_digest,
        )
        self.assertNotEqual(state.digest, changed.digest)

    def test_evaluator_request_binds_split_measurement_subjects(self):
        state = strict_single_dimension()
        request = build_evaluator_request(
            session_id="s",
            state=state,
            observation_digest=OBS,
            turn_index=3,
            expected_generation=0,
        )
        self.assertEqual(state.behavior_digest, request.behavior_digest)
        self.assertEqual(state.measurement_digest, request.measurement_digest)
        self.assertEqual(
            state.detection_policy_digest,
            request.detection_policy_digest,
        )
        self.assertEqual(
            "DRIFTGUARD_EXTERNAL_EVALUATOR_REQUEST_V2",
            request.payload()["schema"],
        )
        self.assertEqual(
            "calibration://judge-a",
            request.probe_contract[0].calibration_ref,
        )
        self.assertEqual(
            CAL_DIGEST_A,
            request.probe_contract[0].calibration_digest,
        )

    def test_typed_behavioral_decision_survives_ledger_round_trip(self):
        state = strict_single_dimension()
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.close()
        try:
            ledger = DriftLedger(handle.name)
            commit = ledger.evaluate_and_commit(
                session_id="strict",
                state=state,
                evidence=rows(state),
                observation_digest=OBS,
                turn_index=3,
                expected_generation=0,
            )
            receipt = ledger.evaluation_receipt(
                session_id="strict",
                evaluation_digest=commit.evaluation.digest,
            )
            self.assertIsNotNone(receipt)
            self.assertEqual(
                Decision.STABLE,
                receipt.behavioral_decision,
            )
            self.assertIsNone(receipt.aggregate_drift)
        finally:
            os.unlink(handle.name)


if __name__ == "__main__":
    unittest.main()
