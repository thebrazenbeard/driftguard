import os
import tempfile
import unittest

from driftguard import (
    BehaviorDimension,
    Decision,
    DriftEvidence,
    DriftPolicy,
    EvidenceIndependence,
    SaveState,
    SourceBinding,
)
from driftguard.ledger import DriftLedger


SOURCE = SourceBinding("probe://r2", "v1")


class R2HostileTests(unittest.TestCase):
    def test_reload_decision_does_not_prove_restore_effect(self):
        state = SaveState(
            "state",
            "1",
            "restore",
            (BehaviorDimension("d", "dimension"),),
            (SOURCE,),
            DriftPolicy(
                max_turns_without_reload=5,
                reload_cooldown_turns=2,
            ),
        )
        evidence = (
            DriftEvidence(
                "e",
                "d",
                0.0,
                EvidenceIndependence.SEPARATE_CONTEXT,
                (SOURCE,),
                "run",
            ),
        )
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.close()
        try:
            ledger = DriftLedger(handle.name)
            first = ledger.evaluate_and_commit(
                session_id="s",
                state=state,
                evidence=evidence,
                turn_index=0,
                expected_generation=0,
            )
            self.assertEqual(first.evaluation.decision, Decision.STABLE)
            due = ledger.evaluate_and_commit(
                session_id="s",
                state=state,
                evidence=evidence,
                turn_index=5,
                expected_generation=1,
            )
            self.assertEqual(due.evaluation.decision, Decision.RELOAD)
            row = ledger.session_row("s")
            self.assertEqual(
                row["last_reload_turn"],
                0,
                "a reload decision must not reset the confirmed reload clock",
            )
        finally:
            os.unlink(handle.name)


if __name__ == "__main__":
    unittest.main()
