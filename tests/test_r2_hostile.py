import os
import tempfile
import unittest

from driftguard import (
    BehaviorDimension,
    Decision,
    DriftEvidence,
    DriftPolicy,
    EvidenceIndependence,
    ProbeSource,
    ReloadAcknowledgement,
    SaveState,
    SourceBinding,
)
from driftguard.ledger import DriftLedger
from driftguard.model import raw_bytes_digest


SOURCE = SourceBinding("probe://r2", "v1")


def make_state():
    return SaveState(
        "state",
        "1",
        "restore",
        (BehaviorDimension("d", "dimension"),),
        (
            ProbeSource(
                SOURCE,
                EvidenceIndependence.SEPARATE_CONTEXT,
                ("d",),
            ),
        ),
        DriftPolicy(
            max_turns_without_reload=5,
            reload_cooldown_turns=2,
        ),
    )


def evidence(state, turn, observation_digest):
    return (
        DriftEvidence(
            f"e-{turn}",
            "d",
            0.0,
            EvidenceIndependence.SEPARATE_CONTEXT,
            (SOURCE,),
            f"run-{turn}",
            state.digest,
            observation_digest,
            turn,
        ),
    )


class R2HostileTests(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.close()
        self.path = handle.name
        self.ledger = DriftLedger(self.path)
        self.state = make_state()

    def tearDown(self):
        os.unlink(self.path)

    def evaluate(self, turn, generation, observation=b"observation"):
        digest = raw_bytes_digest(observation)
        return self.ledger.evaluate_and_commit(
            session_id="s",
            state=self.state,
            evidence=evidence(self.state, turn, digest),
            observation_digest=digest,
            turn_index=turn,
            expected_generation=generation,
        )

    def test_reload_decision_does_not_prove_restore_effect(self):
        first = self.evaluate(0, 0)
        self.assertEqual(first.evaluation.decision, Decision.STABLE)

        due = self.evaluate(5, 1)
        self.assertEqual(due.evaluation.decision, Decision.RELOAD)
        row = self.ledger.session_row("s")
        self.assertEqual(
            row["restore_anchor_turn"],
            0,
            "a reload decision must not reset the confirmed restore clock",
        )
        self.assertEqual(row["last_reload_decision_turn"], 5)

    def test_periodic_reload_repeats_after_cooldown_until_acknowledged(self):
        self.evaluate(0, 0)
        self.evaluate(5, 1)

        suppressed = self.evaluate(6, 2)
        self.assertEqual(suppressed.evaluation.decision, Decision.WARN)
        self.assertIn(
            "reload_suppressed_by_cooldown",
            suppressed.evaluation.reasons,
        )

        repeated = self.evaluate(7, 3)
        self.assertEqual(repeated.evaluation.decision, Decision.RELOAD)
        self.assertIn("periodic_reload_due", repeated.evaluation.reasons)

    def test_acknowledgement_is_the_only_path_that_moves_restore_anchor(self):
        self.evaluate(0, 0)
        due = self.evaluate(5, 1)
        self.ledger.acknowledge_reload(
            session_id="s",
            state=self.state,
            acknowledgement=ReloadAcknowledgement(
                "ack-r2",
                due.evaluation.digest,
                self.state.digest,
                5,
            ),
            expected_generation=2,
        )
        row = self.ledger.session_row("s")
        self.assertEqual(row["restore_anchor_turn"], 5)

        after = self.evaluate(6, 3)
        self.assertEqual(after.evaluation.decision, Decision.STABLE)

    def test_clean_evidence_from_old_observation_cannot_be_replayed(self):
        old_digest = raw_bytes_digest(b"old")
        new_digest = raw_bytes_digest(b"new")
        rows = evidence(self.state, 0, old_digest)
        result = self.ledger.evaluate_and_commit(
            session_id="s",
            state=self.state,
            evidence=rows,
            observation_digest=new_digest,
            turn_index=0,
            expected_generation=0,
        )
        self.assertEqual(result.evaluation.decision, Decision.UNKNOWN)
        self.assertIn(
            "observation_binding_mismatch:d",
            result.evaluation.reasons,
        )


if __name__ == "__main__":
    unittest.main()
