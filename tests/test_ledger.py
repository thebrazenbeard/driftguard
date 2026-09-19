import os
import sqlite3
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
    StaleGenerationError,
)
from driftguard.ledger import DriftLedger
from driftguard.model import raw_bytes_digest


SOURCE = SourceBinding("probe://test", "v1")
OBS = raw_bytes_digest(b"observation")


def state(version="1", max_turns=100, cooldown=6):
    return SaveState(
        "state",
        version,
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
            max_turns_without_reload=max_turns,
            reload_cooldown_turns=cooldown,
        ),
    )


def evidence(s, turn, score=0.0, observation_digest=OBS):
    return (
        DriftEvidence(
            f"e-{turn}",
            "d",
            score,
            EvidenceIndependence.SEPARATE_CONTEXT,
            (SOURCE,),
            f"run-{turn}",
            s.digest,
            observation_digest,
            turn,
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

    def evaluate(self, *, s, turn, generation, score=0.0):
        return self.ledger.evaluate_and_commit(
            session_id="s",
            state=s,
            evidence=evidence(s, turn, score),
            observation_digest=OBS,
            turn_index=turn,
            expected_generation=generation,
        )

    def test_generation_compare_and_swap(self):
        s = state()
        result = self.evaluate(s=s, turn=0, generation=0)
        self.assertEqual(result.successor_generation, 1)
        with self.assertRaises(StaleGenerationError):
            self.evaluate(s=s, turn=1, generation=0)

    def test_state_digest_cannot_change_mid_session(self):
        first = state("1")
        self.evaluate(s=first, turn=0, generation=0)
        with self.assertRaises(StaleGenerationError):
            self.evaluate(s=state("2"), turn=1, generation=1)

    def test_turns_cannot_replay(self):
        s = state()
        self.evaluate(s=s, turn=2, generation=0)
        with self.assertRaises(StaleGenerationError):
            self.evaluate(s=s, turn=2, generation=1)

    def test_new_session_anchors_periodic_clock_without_immediate_reload(self):
        s = state(max_turns=5, cooldown=2)
        first = self.evaluate(s=s, turn=10, generation=0)
        self.assertEqual(first.evaluation.decision, Decision.STABLE)
        row = self.ledger.session_row("s")
        self.assertEqual(row["restore_anchor_turn"], 10)
        self.assertIsNone(row["last_reload_decision_turn"])

        due = self.evaluate(s=s, turn=15, generation=1)
        self.assertEqual(due.evaluation.decision, Decision.RELOAD)
        row = self.ledger.session_row("s")
        self.assertEqual(
            row["restore_anchor_turn"],
            10,
            "a reload decision must not claim a restore effect",
        )
        self.assertEqual(row["last_reload_decision_turn"], 15)

    def test_reload_acknowledgement_advances_restore_anchor(self):
        s = state(max_turns=5, cooldown=2)
        self.evaluate(s=s, turn=0, generation=0)
        due = self.evaluate(s=s, turn=5, generation=1)
        ack = ReloadAcknowledgement(
            ack_id="ack-1",
            evaluation_digest=due.evaluation.digest,
            state_digest=s.digest,
            turn_index=5,
        )
        receipt = self.ledger.acknowledge_reload(
            session_id="s",
            state=s,
            acknowledgement=ack,
            expected_generation=2,
        )
        self.assertEqual(receipt.successor_generation, 3)
        self.assertEqual(receipt.restore_anchor_turn, 5)
        row = self.ledger.session_row("s")
        self.assertEqual(row["restore_anchor_turn"], 5)
        self.assertEqual(len(self.ledger.acknowledgements("s")), 1)

    def test_non_reload_evaluation_cannot_be_acknowledged(self):
        s = state()
        stable = self.evaluate(s=s, turn=0, generation=0)
        ack = ReloadAcknowledgement(
            ack_id="ack-stable",
            evaluation_digest=stable.evaluation.digest,
            state_digest=s.digest,
            turn_index=0,
        )
        with self.assertRaises(StaleGenerationError):
            self.ledger.acknowledge_reload(
                session_id="s",
                state=s,
                acknowledgement=ack,
                expected_generation=1,
            )

    def test_reload_decision_cannot_be_acknowledged_twice(self):
        s = state(max_turns=5, cooldown=2)
        self.evaluate(s=s, turn=0, generation=0)
        due = self.evaluate(s=s, turn=5, generation=1)
        first = ReloadAcknowledgement(
            "ack-1", due.evaluation.digest, s.digest, 5
        )
        self.ledger.acknowledge_reload(
            session_id="s",
            state=s,
            acknowledgement=first,
            expected_generation=2,
        )
        second = ReloadAcknowledgement(
            "ack-2", due.evaluation.digest, s.digest, 5
        )
        with self.assertRaises(StaleGenerationError):
            self.ledger.acknowledge_reload(
                session_id="s",
                state=s,
                acknowledgement=second,
                expected_generation=3,
            )

    def test_stale_ack_generation_fails_closed(self):
        s = state(max_turns=5, cooldown=2)
        self.evaluate(s=s, turn=0, generation=0)
        due = self.evaluate(s=s, turn=5, generation=1)
        ack = ReloadAcknowledgement(
            "ack", due.evaluation.digest, s.digest, 5
        )
        with self.assertRaises(StaleGenerationError):
            self.ledger.acknowledge_reload(
                session_id="s",
                state=s,
                acknowledgement=ack,
                expected_generation=1,
            )

    def test_events_are_append_only_receipts(self):
        s = state()
        self.evaluate(s=s, turn=0, generation=0)
        self.evaluate(s=s, turn=1, generation=1)
        events = self.ledger.events("s")
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["generation_before"], 0)
        self.assertEqual(events[1]["generation_before"], 1)
        self.assertEqual(events[0]["observation_digest"], OBS)


class LegacyMigrationTests(unittest.TestCase):
    def test_legacy_conflated_reload_clock_is_not_promoted_to_restore_effect(self):
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.close()
        try:
            db = sqlite3.connect(handle.name)
            db.executescript(
                """
                CREATE TABLE sessions (
                    session_id TEXT PRIMARY KEY,
                    state_digest TEXT NOT NULL,
                    generation INTEGER NOT NULL,
                    first_turn INTEGER NOT NULL,
                    last_turn INTEGER NOT NULL,
                    last_reload_turn INTEGER NOT NULL,
                    last_evaluation_digest TEXT NULL
                );
                CREATE TABLE evaluation_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    generation_before INTEGER NOT NULL,
                    generation_after INTEGER NOT NULL,
                    turn_index INTEGER NOT NULL,
                    state_digest TEXT NOT NULL,
                    evidence_digest TEXT NOT NULL,
                    evaluation_digest TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    aggregate_drift REAL NULL,
                    reasons TEXT NOT NULL
                );
                """
            )
            db.execute(
                """
                INSERT INTO sessions VALUES(
                    's','digest',2,0,5,5,'evaluation'
                )
                """
            )
            db.commit()
            db.close()

            ledger = DriftLedger(handle.name)
            row = ledger.session_row("s")
            self.assertEqual(row["restore_anchor_turn"], 0)
            self.assertEqual(row["last_reload_decision_turn"], 5)
        finally:
            os.unlink(handle.name)


if __name__ == "__main__":
    unittest.main()
