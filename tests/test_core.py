import unittest

from driftguard import (
    BehaviorDimension,
    Decision,
    DriftEvidence,
    DriftGuardEngine,
    DriftPolicy,
    EvidenceIndependence,
    ProbeSource,
    SaveState,
    SourceBinding,
)
from driftguard.model import raw_bytes_digest


TRUTH_SOURCE = SourceBinding("probe://truth-review", "v1")
STYLE_SOURCE = SourceBinding("probe://style-review", "v1")
OBS = raw_bytes_digest(b"observation-v1")


def state(**policy_overrides):
    return SaveState(
        state_id="example-behavior",
        version="1",
        restore_text="Preserve evidence distinctions and explicit authority boundaries.",
        dimensions=(
            BehaviorDimension(
                "truthfulness",
                "Do not claim unsupported effects or evidence.",
                weight=2.0,
                critical=True,
                min_independence=EvidenceIndependence.SEPARATE_CONTEXT,
            ),
            BehaviorDimension(
                "style",
                "Remain direct and concise.",
                weight=1.0,
                min_independence=EvidenceIndependence.SEPARATE_CONTEXT,
            ),
        ),
        probe_sources=(
            ProbeSource(
                TRUTH_SOURCE,
                EvidenceIndependence.EXTERNAL,
                ("truthfulness",),
            ),
            ProbeSource(
                STYLE_SOURCE,
                EvidenceIndependence.SEPARATE_CONTEXT,
                ("style",),
            ),
        ),
        policy=DriftPolicy(**policy_overrides),
    )


def evidence(
    s,
    truth=0.0,
    style=0.0,
    independence=EvidenceIndependence.SEPARATE_CONTEXT,
    observation_digest=OBS,
    turn_index=3,
):
    return (
        DriftEvidence(
            "e-truth",
            "truthfulness",
            truth,
            independence,
            (TRUTH_SOURCE,),
            "run-truth",
            s.digest,
            observation_digest,
            turn_index,
        ),
        DriftEvidence(
            "e-style",
            "style",
            style,
            independence,
            (STYLE_SOURCE,),
            "run-style",
            s.digest,
            observation_digest,
            turn_index,
        ),
    )


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = DriftGuardEngine()

    def evaluate(self, s, rows, *, turn=3, anchor=0, last_decision=None):
        return self.engine.evaluate(
            state=s,
            evidence=rows,
            observation_digest=OBS,
            turn_index=turn,
            generation=0,
            restore_anchor_turn=anchor,
            last_reload_decision_turn=last_decision,
        )

    def test_stable_when_all_dimensions_are_low(self):
        s = state(max_turns_without_reload=100)
        result = self.evaluate(s, evidence(s, 0.05, 0.10))
        self.assertEqual(result.decision, Decision.STABLE)

    def test_critical_dimension_forces_reload_through_cooldown(self):
        s = state(max_turns_without_reload=100)
        result = self.evaluate(
            s,
            evidence(s, 0.5, 0.0),
            last_decision=2,
        )
        self.assertEqual(result.decision, Decision.RELOAD)
        self.assertIn("critical_dimension_breach", result.reasons)
        self.assertTrue(result.restore_packet.startswith("DRIFTGUARD_RESTORE"))

    def test_noncritical_reload_is_suppressed_during_decision_cooldown(self):
        s = state(max_turns_without_reload=100, reload_threshold=0.45)
        result = self.evaluate(
            s,
            evidence(s, 0.39, 0.90),
            last_decision=2,
        )
        self.assertEqual(result.decision, Decision.WARN)
        self.assertIn("reload_suppressed_by_cooldown", result.reasons)

    def test_periodic_reload_uses_restore_anchor_not_last_decision(self):
        s = state(max_turns_without_reload=5, reload_cooldown_turns=2)
        rows = evidence(s, turn_index=5)
        result = self.engine.evaluate(
            state=s,
            evidence=rows,
            observation_digest=OBS,
            turn_index=5,
            generation=0,
            restore_anchor_turn=0,
            last_reload_decision_turn=2,
        )
        self.assertEqual(result.decision, Decision.RELOAD)
        self.assertIn("periodic_reload_due", result.reasons)

    def test_missing_dimension_fails_closed(self):
        s = state(max_turns_without_reload=100)
        result = self.evaluate(s, evidence(s)[:1])
        self.assertEqual(result.decision, Decision.UNKNOWN)
        self.assertIn("missing_evidence:style", result.reasons)

    def test_self_report_cannot_satisfy_independent_dimension(self):
        s = state(max_turns_without_reload=100)
        result = self.evaluate(
            s,
            evidence(s, independence=EvidenceIndependence.SELF),
        )
        self.assertEqual(result.decision, Decision.UNKNOWN)
        self.assertTrue(any(
            reason.startswith("insufficient_independence")
            for reason in result.reasons
        ))

    def test_ungoverned_probe_source_fails_closed(self):
        s = state(max_turns_without_reload=100)
        rogue = SourceBinding("probe://rogue", "v1")
        rows = list(evidence(s))
        rows[0] = DriftEvidence(
            "e-truth",
            "truthfulness",
            0.0,
            EvidenceIndependence.EXTERNAL,
            (rogue,),
            "run-truth",
            s.digest,
            OBS,
            3,
        )
        result = self.evaluate(s, tuple(rows))
        self.assertEqual(result.decision, Decision.UNKNOWN)
        self.assertIn("ungoverned_source:truthfulness", result.reasons)

    def test_duplicate_execution_identity_fails_closed(self):
        s = state(max_turns_without_reload=100)
        rows = list(evidence(s))
        rows[1] = DriftEvidence(
            "e-style",
            "style",
            0.0,
            EvidenceIndependence.SEPARATE_CONTEXT,
            (STYLE_SOURCE,),
            "run-truth",
            s.digest,
            OBS,
            3,
        )
        result = self.evaluate(s, tuple(rows))
        self.assertEqual(result.decision, Decision.UNKNOWN)
        self.assertIn("duplicate_execution_id:run-truth", result.reasons)

    def test_state_bound_evidence_cannot_replay_after_state_change(self):
        old = state(max_turns_without_reload=100)
        new = SaveState(
            old.state_id,
            "2",
            old.restore_text + " changed",
            old.dimensions,
            old.probe_sources,
            old.policy,
        )
        rows = evidence(old)
        result = self.evaluate(new, rows)
        self.assertEqual(result.decision, Decision.UNKNOWN)
        self.assertTrue(any(
            reason.startswith("state_binding_mismatch")
            for reason in result.reasons
        ))

    def test_observation_bound_evidence_cannot_replay_on_new_observation(self):
        s = state(max_turns_without_reload=100)
        rows = evidence(
            s,
            observation_digest=raw_bytes_digest(b"old-observation"),
        )
        result = self.evaluate(s, rows)
        self.assertEqual(result.decision, Decision.UNKNOWN)
        self.assertTrue(any(
            reason.startswith("observation_binding_mismatch")
            for reason in result.reasons
        ))

    def test_turn_bound_evidence_cannot_replay_on_later_turn(self):
        s = state(max_turns_without_reload=100)
        rows = evidence(s, turn_index=2)
        result = self.evaluate(s, rows, turn=3)
        self.assertEqual(result.decision, Decision.UNKNOWN)
        self.assertTrue(any(
            reason.startswith("turn_binding_mismatch")
            for reason in result.reasons
        ))

    def test_source_cannot_judge_dimension_outside_its_scope(self):
        s = state(max_turns_without_reload=100)
        rows = list(evidence(s))
        rows[0] = DriftEvidence(
            "e-truth",
            "truthfulness",
            0.0,
            EvidenceIndependence.SEPARATE_CONTEXT,
            (STYLE_SOURCE,),
            "run-truth",
            s.digest,
            OBS,
            3,
        )
        result = self.evaluate(s, tuple(rows))
        self.assertEqual(result.decision, Decision.UNKNOWN)
        self.assertIn("source_scope_violation:truthfulness", result.reasons)

    def test_source_cannot_overclaim_independence_class(self):
        s = state(max_turns_without_reload=100)
        rows = list(evidence(s))
        rows[1] = DriftEvidence(
            "e-style",
            "style",
            0.0,
            EvidenceIndependence.EXTERNAL,
            (STYLE_SOURCE,),
            "run-style",
            s.digest,
            OBS,
            3,
        )
        result = self.evaluate(s, tuple(rows))
        self.assertEqual(result.decision, Decision.UNKNOWN)
        self.assertIn("independence_overclaim:style", result.reasons)

    def test_periodic_reload_survives_unknown_evidence(self):
        s = state(max_turns_without_reload=3, reload_cooldown_turns=1)
        rows = evidence(s, turn_index=3)[:1]
        result = self.engine.evaluate(
            state=s,
            evidence=rows,
            observation_digest=OBS,
            turn_index=3,
            generation=0,
            restore_anchor_turn=0,
            last_reload_decision_turn=None,
        )
        self.assertEqual(result.decision, Decision.UNKNOWN)
        self.assertTrue(result.reload_required)
        self.assertIn("periodic_reload_due", result.reasons)
        self.assertIsNotNone(result.restore_packet)

    def test_probe_dimensions_require_json_array_shape(self):
        with self.assertRaisesRegex(ValueError, "JSON array"):
            ProbeSource.from_mapping(
                {
                    "ref": "probe://bad-shape",
                    "version": "v1",
                    "max_independence": "EXTERNAL",
                    "dimensions": "truthfulness",
                }
            )

    def test_restore_packet_is_digest_bound(self):
        s = state(max_turns_without_reload=100)
        packet = self.engine.restore_packet(s)
        self.assertIn(s.digest, packet)
        self.assertIn(s.restore_text, packet)


if __name__ == "__main__":
    unittest.main()
