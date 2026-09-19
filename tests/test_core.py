import unittest

from driftguard import (
    BehaviorDimension,
    Decision,
    DriftEvidence,
    DriftGuardEngine,
    DriftPolicy,
    EvidenceIndependence,
    SaveState,
    SourceBinding,
)


SOURCE = SourceBinding("probe://review", "v1")


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
        allowed_probe_sources=(SOURCE,),
        policy=DriftPolicy(**policy_overrides),
    )


def evidence(
    truth=0.0,
    style=0.0,
    independence=EvidenceIndependence.SEPARATE_CONTEXT,
):
    return (
        DriftEvidence(
            "e-truth",
            "truthfulness",
            truth,
            independence,
            (SOURCE,),
            "run-truth",
        ),
        DriftEvidence(
            "e-style",
            "style",
            style,
            independence,
            (SOURCE,),
            "run-style",
        ),
    )


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = DriftGuardEngine()

    def test_stable_when_all_dimensions_are_low(self):
        result = self.engine.evaluate(
            state=state(max_turns_without_reload=100),
            evidence=evidence(0.05, 0.10),
            turn_index=3,
            generation=0,
            last_reload_turn=0,
        )
        self.assertEqual(result.decision, Decision.STABLE)

    def test_critical_dimension_forces_reload_through_cooldown(self):
        result = self.engine.evaluate(
            state=state(max_turns_without_reload=100),
            evidence=evidence(0.5, 0.0),
            turn_index=3,
            generation=0,
            last_reload_turn=2,
        )
        self.assertEqual(result.decision, Decision.RELOAD)
        self.assertIn("critical_dimension_breach", result.reasons)
        self.assertTrue(result.restore_packet.startswith("DRIFTGUARD_RESTORE"))

    def test_noncritical_reload_is_suppressed_during_cooldown(self):
        result = self.engine.evaluate(
            state=state(max_turns_without_reload=100, reload_threshold=0.45),
            evidence=evidence(0.39, 0.90),
            turn_index=3,
            generation=0,
            last_reload_turn=2,
        )
        self.assertEqual(result.decision, Decision.WARN)
        self.assertIn("reload_suppressed_by_cooldown", result.reasons)

    def test_periodic_reload_occurs_after_interval(self):
        result = self.engine.evaluate(
            state=state(max_turns_without_reload=5, reload_cooldown_turns=2),
            evidence=evidence(0.0, 0.0),
            turn_index=5,
            generation=0,
            last_reload_turn=0,
        )
        self.assertEqual(result.decision, Decision.RELOAD)
        self.assertIn("periodic_reload_due", result.reasons)

    def test_missing_dimension_fails_closed(self):
        result = self.engine.evaluate(
            state=state(max_turns_without_reload=100),
            evidence=evidence()[:1],
            turn_index=1,
            generation=0,
            last_reload_turn=0,
        )
        self.assertEqual(result.decision, Decision.UNKNOWN)
        self.assertIn("missing_evidence:style", result.reasons)

    def test_self_report_cannot_satisfy_independent_dimension(self):
        result = self.engine.evaluate(
            state=state(max_turns_without_reload=100),
            evidence=evidence(independence=EvidenceIndependence.SELF),
            turn_index=1,
            generation=0,
            last_reload_turn=0,
        )
        self.assertEqual(result.decision, Decision.UNKNOWN)
        self.assertTrue(any(
            reason.startswith("insufficient_independence")
            for reason in result.reasons
        ))

    def test_ungoverned_probe_source_fails_closed(self):
        rogue = SourceBinding("probe://rogue", "v1")
        rows = list(evidence())
        rows[0] = DriftEvidence(
            "e-truth",
            "truthfulness",
            0.0,
            EvidenceIndependence.EXTERNAL,
            (rogue,),
            "run-truth",
        )
        result = self.engine.evaluate(
            state=state(max_turns_without_reload=100),
            evidence=tuple(rows),
            turn_index=1,
            generation=0,
            last_reload_turn=0,
        )
        self.assertEqual(result.decision, Decision.UNKNOWN)
        self.assertIn("ungoverned_source:truthfulness", result.reasons)

    def test_duplicate_execution_identity_fails_closed(self):
        rows = list(evidence())
        rows[1] = DriftEvidence(
            "e-style",
            "style",
            0.0,
            EvidenceIndependence.SEPARATE_CONTEXT,
            (SOURCE,),
            "run-truth",
        )
        result = self.engine.evaluate(
            state=state(max_turns_without_reload=100),
            evidence=tuple(rows),
            turn_index=1,
            generation=0,
            last_reload_turn=0,
        )
        self.assertEqual(result.decision, Decision.UNKNOWN)
        self.assertIn("duplicate_execution_id:run-truth", result.reasons)

    def test_restore_packet_is_digest_bound(self):
        s = state(max_turns_without_reload=100)
        packet = self.engine.restore_packet(s)
        self.assertIn(s.digest, packet)
        self.assertIn(s.restore_text, packet)


if __name__ == "__main__":
    unittest.main()
