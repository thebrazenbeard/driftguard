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
    StaleGenerationError,
)
from driftguard.ledger import DriftLedger


SOURCE = SourceBinding("probe://test", "v1")


def state(version="1", max_turns=100, cooldown=6):
    return SaveState(
        "state",
        version,
        "restore",
        (BehaviorDimension("d", "dimension"),),
        (SOURCE,),
        DriftPolicy(
            max_turns_without_reload=max_turns,
            reload_cooldown_turns=cooldown,
        ),
    )


def evidence(score=0.0):
    return (
        DriftEvidence(
            "e",
            "d",
            score,
            EvidenceIndependence.SEPARATE_CONTEXT,
            (SOURCE,),
            "run",
        ),
    )


class LedgerTests(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.close()
        self.path = handle.name
        self.ledger = DriftLedger(self.path)

    def tearDown(self):
        os.unlink(self.path)

    def test_generation_compare_and_swap(self):
        result = self.ledger.evaluate_and_commit(
            session_id="s",
            state=state(),
            evidence=evidence(),
            turn_index=0,
            expected_generation=0,
        )
        self.assertEqual(result.successor_generation, 1)
        with self.assertRaises(StaleGenerationError):
            self.ledger.evaluate_and_commit(
                session_id="s",
                state=state(),
                evidence=evidence(),
                turn_index=1,
                expected_generation=0,
            )

    def test_state_digest_cannot_change_mid_session(self):
        self.ledger.evaluate_and_commit(
            session_id="s",
            state=state("1"),
            evidence=evidence(),
            turn_index=0,
            expected_generation=0,
        )
        with self.assertRaises(StaleGenerationError):
            self.ledger.evaluate_and_commit(
                session_id="s",
                state=state("2"),
                evidence=evidence(),
                turn_index=1,
                expected_generation=1,
            )

    def test_turns_cannot_replay(self):
        self.ledger.evaluate_and_commit(
            session_id="s",
            state=state(),
            evidence=evidence(),
            turn_index=2,
            expected_generation=0,
        )
        with self.assertRaises(StaleGenerationError):
            self.ledger.evaluate_and_commit(
                session_id="s",
                state=state(),
                evidence=evidence(),
                turn_index=2,
                expected_generation=1,
            )

    def test_new_session_anchors_periodic_clock_without_immediate_reload(self):
        first = self.ledger.evaluate_and_commit(
            session_id="s",
            state=state(max_turns=5, cooldown=2),
            evidence=evidence(),
            turn_index=10,
            expected_generation=0,
        )
        self.assertEqual(first.evaluation.decision, Decision.STABLE)
        row = self.ledger.session_row("s")
        self.assertEqual(row["last_reload_turn"], 10)

        due = self.ledger.evaluate_and_commit(
            session_id="s",
            state=state(max_turns=5, cooldown=2),
            evidence=evidence(),
            turn_index=15,
            expected_generation=1,
        )
        self.assertEqual(due.evaluation.decision, Decision.RELOAD)

    def test_events_are_append_only_receipts(self):
        self.ledger.evaluate_and_commit(
            session_id="s",
            state=state(),
            evidence=evidence(),
            turn_index=0,
            expected_generation=0,
        )
        self.ledger.evaluate_and_commit(
            session_id="s",
            state=state(),
            evidence=evidence(),
            turn_index=1,
            expected_generation=1,
        )
        events = self.ledger.events("s")
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["generation_before"], 0)
        self.assertEqual(events[1]["generation_before"], 1)


if __name__ == "__main__":
    unittest.main()
