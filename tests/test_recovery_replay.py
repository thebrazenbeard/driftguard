import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from driftguard import (
    BehaviorDimension,
    Decision,
    DriftEvidence,
    DriftPolicy,
    EvidenceIndependence,
    ProbeSource,
    RecoveryStatus,
    ReloadAcknowledgement,
    SaveState,
    SourceBinding,
    StaleGenerationError,
)
from driftguard.cli import main
from driftguard.ledger import DriftLedger
from driftguard.model import raw_bytes_digest


SOURCE = SourceBinding("probe://recovery-replay", "v1")
OBS = raw_bytes_digest(b"post-reload-observation")


def state(*, max_turns: int = 5, cooldown: int = 0) -> SaveState:
    return SaveState(
        "recovery-state",
        "1",
        "restore exact governed behavior",
        (BehaviorDimension("d", "governed dimension"),),
        (
            ProbeSource(
                SOURCE,
                EvidenceIndependence.SEPARATE_CONTEXT,
                ("d",),
            ),
        ),
        DriftPolicy(
            warn_threshold=0.25,
            reload_threshold=0.45,
            critical_reload_threshold=0.40,
            max_turns_without_reload=max_turns,
            reload_cooldown_turns=cooldown,
        ),
    )


def evidence(
    s: SaveState,
    turn: int,
    score: float = 0.0,
    *,
    observation_digest: str = OBS,
) -> tuple[DriftEvidence, ...]:
    return (
        DriftEvidence(
            f"e-{turn}-{score}",
            "d",
            score,
            EvidenceIndependence.SEPARATE_CONTEXT,
            (SOURCE,),
            f"run-{turn}-{score}",
            s.digest,
            observation_digest,
            turn,
        ),
    )


class RecoveryReplayTests(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.close()
        self.path = handle.name
        self.ledger = DriftLedger(self.path)
        self.state = state()

    def tearDown(self):
        os.unlink(self.path)

    def evaluate(
        self,
        *,
        turn: int,
        generation: int,
        score: float = 0.0,
        rows: tuple[DriftEvidence, ...] | None = None,
    ):
        return self.ledger.evaluate_and_commit(
            session_id="s",
            state=self.state,
            evidence=(
                evidence(self.state, turn, score)
                if rows is None
                else rows
            ),
            observation_digest=OBS,
            turn_index=turn,
            expected_generation=generation,
        )

    def acknowledged_reload(self):
        first = self.evaluate(turn=0, generation=0)
        self.assertEqual(first.evaluation.decision, Decision.STABLE)
        due = self.evaluate(turn=5, generation=1)
        self.assertTrue(due.evaluation.reload_required)
        acknowledgement = ReloadAcknowledgement(
            "ack-recovery",
            due.evaluation.digest,
            self.state.digest,
            5,
        )
        ack_result = self.ledger.acknowledge_reload(
            session_id="s",
            state=self.state,
            acknowledgement=acknowledgement,
            expected_generation=2,
        )
        self.assertEqual(ack_result.successor_generation, 3)
        return due, acknowledgement, ack_result

    def verify(self, *, replay_digest: str, generation: int):
        return self.ledger.verify_recovery(
            session_id="s",
            state=self.state,
            ack_id="ack-recovery",
            replay_evaluation_digest=replay_digest,
            expected_generation=generation,
        )

    def test_first_stable_replay_is_verified_without_claiming_causality(self):
        due, _, _ = self.acknowledged_reload()
        replay = self.evaluate(turn=6, generation=3, score=0.0)
        result = self.verify(
            replay_digest=replay.evaluation.digest,
            generation=4,
        )

        verification = result.verification
        self.assertEqual(
            verification.status,
            RecoveryStatus.VERIFIED_STABLE,
        )
        self.assertEqual(
            verification.acknowledged_evaluation_digest,
            due.evaluation.digest,
        )
        self.assertEqual(
            verification.replay_evaluation_digest,
            replay.evaluation.digest,
        )
        self.assertEqual(verification.observation_digest, OBS)
        self.assertEqual(verification.turn_index, 6)
        self.assertEqual(verification.generation, 4)
        self.assertEqual(result.successor_generation, 5)
        self.assertIn(
            "first_post_reload_replay_behaviorally_stable",
            verification.reasons,
        )
        self.assertNotIn("reload_caused_recovery", verification.reasons)

        row = self.ledger.session_row("s")
        self.assertEqual(row["restore_anchor_turn"], 5)
        self.assertEqual(row["last_reload_decision_turn"], 5)
        receipts = self.ledger.recoveries("s")
        self.assertEqual(len(receipts), 1)
        self.assertEqual(
            receipts[0]["verification_digest"],
            verification.digest,
        )

    def test_periodic_reload_clock_does_not_negate_stable_recovery(self):
        self.state = state(max_turns=1, cooldown=0)
        self.acknowledged_reload()
        replay = self.evaluate(turn=6, generation=3, score=0.0)
        self.assertEqual(replay.evaluation.decision, Decision.RELOAD)
        self.assertTrue(replay.evaluation.reload_required)
        self.assertIn("periodic_reload_due", replay.evaluation.reasons)

        result = self.verify(
            replay_digest=replay.evaluation.digest,
            generation=4,
        )
        self.assertEqual(
            result.verification.status,
            RecoveryStatus.VERIFIED_STABLE,
        )
        self.assertIn(
            "first_post_reload_replay_behaviorally_stable",
            result.verification.reasons,
        )

    def test_incomplete_first_replay_remains_unknown(self):
        self.acknowledged_reload()
        replay = self.evaluate(
            turn=6,
            generation=3,
            rows=(),
        )
        self.assertEqual(replay.evaluation.decision, Decision.UNKNOWN)
        result = self.verify(
            replay_digest=replay.evaluation.digest,
            generation=4,
        )
        self.assertEqual(
            result.verification.status,
            RecoveryStatus.UNKNOWN,
        )

    def test_warn_first_replay_is_not_stable(self):
        self.acknowledged_reload()
        replay = self.evaluate(turn=6, generation=3, score=0.30)
        self.assertEqual(replay.evaluation.decision, Decision.WARN)
        result = self.verify(
            replay_digest=replay.evaluation.digest,
            generation=4,
        )
        self.assertEqual(
            result.verification.status,
            RecoveryStatus.NOT_STABLE,
        )

    def test_reload_first_replay_is_not_stable(self):
        self.acknowledged_reload()
        replay = self.evaluate(turn=6, generation=3, score=0.80)
        self.assertEqual(replay.evaluation.decision, Decision.RELOAD)
        result = self.verify(
            replay_digest=replay.evaluation.digest,
            generation=4,
        )
        self.assertEqual(
            result.verification.status,
            RecoveryStatus.NOT_STABLE,
        )

    def test_cannot_cherry_pick_later_stable_replay(self):
        self.acknowledged_reload()
        first = self.evaluate(turn=6, generation=3, score=0.30)
        self.assertEqual(first.evaluation.decision, Decision.WARN)
        later = self.evaluate(turn=7, generation=4, score=0.0)
        self.assertEqual(later.evaluation.decision, Decision.STABLE)

        with self.assertRaisesRegex(
            StaleGenerationError,
            "first ledger mutation",
        ):
            self.verify(
                replay_digest=later.evaluation.digest,
                generation=5,
            )

    def test_acknowledged_reload_evaluation_is_not_post_reload_replay(self):
        due, _, ack_result = self.acknowledged_reload()
        with self.assertRaisesRegex(
            StaleGenerationError,
            "after acknowledgement turn",
        ):
            self.verify(
                replay_digest=due.evaluation.digest,
                generation=ack_result.successor_generation,
            )

    def test_replay_must_still_be_latest_when_verified(self):
        self.acknowledged_reload()
        replay = self.evaluate(turn=6, generation=3, score=0.0)
        self.evaluate(turn=7, generation=4, score=0.0)

        with self.assertRaisesRegex(
            StaleGenerationError,
            "latest committed ledger mutation",
        ):
            self.verify(
                replay_digest=replay.evaluation.digest,
                generation=5,
            )

    def test_recovery_acknowledgement_can_only_be_verified_once(self):
        self.acknowledged_reload()
        replay = self.evaluate(turn=6, generation=3, score=0.0)
        first = self.verify(
            replay_digest=replay.evaluation.digest,
            generation=4,
        )
        self.assertEqual(first.successor_generation, 5)

        with self.assertRaisesRegex(
            StaleGenerationError,
            "already verified",
        ):
            self.verify(
                replay_digest=replay.evaluation.digest,
                generation=5,
            )

    def test_stale_generation_fails_closed(self):
        self.acknowledged_reload()
        replay = self.evaluate(turn=6, generation=3, score=0.0)
        with self.assertRaisesRegex(
            StaleGenerationError,
            "expected generation",
        ):
            self.verify(
                replay_digest=replay.evaluation.digest,
                generation=3,
            )


    def test_verify_recovery_cli_emits_digest_bound_receipt(self):
        self.acknowledged_reload()
        replay = self.evaluate(turn=6, generation=3, score=0.0)
        state_file = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            delete=False,
            suffix=".json",
        )
        try:
            json.dump(self.state.canonical_payload(), state_file)
            state_file.close()
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = main(
                    [
                        "verify-recovery",
                        "--state",
                        state_file.name,
                        "--db",
                        self.path,
                        "--session",
                        "s",
                        "--ack-id",
                        "ack-recovery",
                        "--replay-evaluation-digest",
                        replay.evaluation.digest,
                        "--expected-generation",
                        "4",
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["status"], "VERIFIED_STABLE")
            self.assertEqual(
                payload["replay_evaluation_digest"],
                replay.evaluation.digest,
            )
            self.assertEqual(payload["generation_before"], 4)
            self.assertEqual(payload["generation_after"], 5)
            self.assertEqual(len(payload["verification_digest"]), 64)
        finally:
            if not state_file.closed:
                state_file.close()
            os.unlink(state_file.name)


if __name__ == "__main__":
    unittest.main()
