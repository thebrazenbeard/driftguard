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


CRITICAL_SOURCE = SourceBinding("probe://critical", "v1")
OTHER_SOURCE = SourceBinding("probe://other", "v1")


class R3HostileTests(unittest.TestCase):
    def test_unrelated_missing_evidence_cannot_suppress_valid_critical_reload(self):
        state = SaveState(
            "state-r3",
            "1",
            "restore",
            (
                BehaviorDimension(
                    "critical",
                    "critical invariant",
                    critical=True,
                    min_independence=EvidenceIndependence.SEPARATE_CONTEXT,
                ),
                BehaviorDimension(
                    "other",
                    "unrelated invariant",
                    min_independence=EvidenceIndependence.SEPARATE_CONTEXT,
                ),
            ),
            (
                ProbeSource(
                    CRITICAL_SOURCE,
                    EvidenceIndependence.SEPARATE_CONTEXT,
                    ("critical",),
                ),
                ProbeSource(
                    OTHER_SOURCE,
                    EvidenceIndependence.SEPARATE_CONTEXT,
                    ("other",),
                ),
            ),
            DriftPolicy(
                critical_reload_threshold=0.40,
                max_turns_without_reload=100,
                reload_cooldown_turns=10,
            ),
        )
        observation_digest = raw_bytes_digest(b"critical breach")
        evidence = (
            DriftEvidence(
                "critical-evidence",
                "critical",
                1.0,
                EvidenceIndependence.SEPARATE_CONTEXT,
                (CRITICAL_SOURCE,),
                "critical-run",
                state.digest,
                observation_digest,
                0,
            ),
        )

        result = DriftGuardEngine().evaluate(
            state=state,
            evidence=evidence,
            observation_digest=observation_digest,
            turn_index=0,
            generation=0,
            restore_anchor_turn=0,
            last_reload_decision_turn=None,
        )

        self.assertEqual(Decision.UNKNOWN, result.decision)
        self.assertIn("missing_evidence:other", result.reasons)
        self.assertIn("critical_dimension_breach", result.reasons)
        self.assertTrue(
            result.reload_required,
            "valid admitted critical evidence must still force a reload even when "
            "unrelated evidence is missing and epistemic status is UNKNOWN",
        )
        self.assertIsNotNone(result.restore_packet)


    def test_unknown_critical_breach_bypasses_reload_decision_cooldown(self):
        state = SaveState(
            "state-r3-cooldown",
            "1",
            "restore",
            (
                BehaviorDimension(
                    "critical",
                    "critical invariant",
                    critical=True,
                    min_independence=EvidenceIndependence.SEPARATE_CONTEXT,
                ),
                BehaviorDimension(
                    "other",
                    "unrelated invariant",
                    min_independence=EvidenceIndependence.SEPARATE_CONTEXT,
                ),
            ),
            (
                ProbeSource(
                    CRITICAL_SOURCE,
                    EvidenceIndependence.SEPARATE_CONTEXT,
                    ("critical",),
                ),
                ProbeSource(
                    OTHER_SOURCE,
                    EvidenceIndependence.SEPARATE_CONTEXT,
                    ("other",),
                ),
            ),
            DriftPolicy(
                critical_reload_threshold=0.40,
                max_turns_without_reload=100,
                reload_cooldown_turns=10,
            ),
        )
        observation_digest = raw_bytes_digest(b"critical breach in cooldown")
        evidence = (
            DriftEvidence(
                "critical-evidence-cooldown",
                "critical",
                1.0,
                EvidenceIndependence.SEPARATE_CONTEXT,
                (CRITICAL_SOURCE,),
                "critical-run-cooldown",
                state.digest,
                observation_digest,
                1,
            ),
        )

        result = DriftGuardEngine().evaluate(
            state=state,
            evidence=evidence,
            observation_digest=observation_digest,
            turn_index=1,
            generation=1,
            restore_anchor_turn=0,
            last_reload_decision_turn=0,
        )

        self.assertEqual(Decision.UNKNOWN, result.decision)
        self.assertTrue(result.reload_required)
        self.assertIn("critical_dimension_breach", result.reasons)
        self.assertNotIn("reload_suppressed_by_cooldown", result.reasons)


if __name__ == "__main__":
    unittest.main()
