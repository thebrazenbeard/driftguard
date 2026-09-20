import unittest

from driftguard.external_boundary import BehavioralRecoveryReceipt
from driftguard.ledger import CommitResult
from driftguard.model import Decision, Evaluation, canonical_digest
from driftguard.recovery_qualification import (
    RecoveryWindowDisposition,
    RecoveryWindowPolicy,
    qualify_recovery_window,
)


STATE = "a" * 64


def digest(label: str) -> str:
    return canonical_digest({"label": label})


def initial_recovery() -> BehavioralRecoveryReceipt:
    return BehavioralRecoveryReceipt(
        ack_id="ack-1",
        acknowledged_evaluation_digest=digest("acknowledged"),
        state_digest=STATE,
        acknowledgement_turn_index=5,
        replay_evaluation_digest=digest("replay-evaluation"),
        replay_observation_digest=digest("replay-observation"),
        replay_evidence_digest=digest("replay-evidence"),
        replay_turn_index=6,
        replay_generation=3,
    )


def commit(
    *,
    turn: int,
    generation: int,
    decision: Decision = Decision.STABLE,
    reload_required: bool = False,
    state_digest: str = STATE,
) -> CommitResult:
    evaluation = Evaluation(
        decision=decision,
        reload_required=reload_required,
        aggregate_drift=0.0 if decision is Decision.STABLE else 0.3,
        dimension_scores=(("d", 0.0 if decision is Decision.STABLE else 0.3),),
        reasons=("qualification-test",),
        state_digest=state_digest,
        observation_digest=digest(f"observation-{turn}-{generation}"),
        evidence_digest=digest(f"evidence-{turn}-{generation}"),
        turn_index=turn,
        generation=generation,
        restore_packet="restore" if reload_required else None,
    )
    return CommitResult(evaluation, generation + 1)


class RecoveryWindowQualificationTests(unittest.TestCase):
    def test_multiple_stable_checkpoints_over_precommitted_span_are_sustained(self):
        receipt = qualify_recovery_window(
            initial_recovery=initial_recovery(),
            subsequent_commits=(
                commit(turn=8, generation=4),
                commit(turn=10, generation=5),
            ),
        )
        self.assertEqual(
            RecoveryWindowDisposition.SUSTAINED_BOUNDED_RECOVERY,
            receipt.disposition,
        )
        self.assertEqual(3, receipt.checkpoint_count)
        self.assertEqual(3, receipt.stable_checkpoint_count)

    def test_one_clean_replay_is_not_sustained_recovery(self):
        receipt = qualify_recovery_window(
            initial_recovery=initial_recovery(),
            subsequent_commits=(),
        )
        self.assertEqual(
            RecoveryWindowDisposition.PENDING_MORE_OBSERVATION,
            receipt.disposition,
        )

    def test_stable_count_without_required_turn_span_is_pending(self):
        receipt = qualify_recovery_window(
            initial_recovery=initial_recovery(),
            subsequent_commits=(
                commit(turn=7, generation=4),
                commit(turn=8, generation=5),
            ),
        )
        self.assertEqual(
            RecoveryWindowDisposition.PENDING_MORE_OBSERVATION,
            receipt.disposition,
        )

    def test_warn_is_bounded_degradation(self):
        receipt = qualify_recovery_window(
            initial_recovery=initial_recovery(),
            subsequent_commits=(
                commit(turn=8, generation=4),
                commit(turn=10, generation=5, decision=Decision.WARN),
            ),
        )
        self.assertEqual(
            RecoveryWindowDisposition.DEGRADED_DRIFT_RETURNED,
            receipt.disposition,
        )

    def test_unknown_blocks_sustained_recovery_claim(self):
        receipt = qualify_recovery_window(
            initial_recovery=initial_recovery(),
            subsequent_commits=(
                commit(turn=8, generation=4),
                commit(turn=10, generation=5, decision=Decision.UNKNOWN),
            ),
        )
        self.assertEqual(
            RecoveryWindowDisposition.INDETERMINATE_EVIDENCE,
            receipt.disposition,
        )

    def test_unknown_with_reload_required_is_relapse(self):
        receipt = qualify_recovery_window(
            initial_recovery=initial_recovery(),
            subsequent_commits=(
                commit(
                    turn=8,
                    generation=4,
                    decision=Decision.UNKNOWN,
                    reload_required=True,
                ),
            ),
        )
        self.assertEqual(
            RecoveryWindowDisposition.RELAPSE_RELOAD_REQUIRED,
            receipt.disposition,
        )

    def test_state_change_cannot_launder_recovery_into_new_baseline(self):
        with self.assertRaisesRegex(ValueError, "baseline mutation"):
            qualify_recovery_window(
                initial_recovery=initial_recovery(),
                subsequent_commits=(
                    commit(turn=8, generation=4, state_digest="b" * 64),
                ),
            )

    def test_generation_gap_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "generation is not contiguous"):
            qualify_recovery_window(
                initial_recovery=initial_recovery(),
                subsequent_commits=(commit(turn=8, generation=5),),
            )

    def test_non_monotonic_turn_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "advance turn_index"):
            qualify_recovery_window(
                initial_recovery=initial_recovery(),
                subsequent_commits=(commit(turn=6, generation=4),),
            )

    def test_policy_is_digest_bound_to_receipt(self):
        narrow = qualify_recovery_window(
            initial_recovery=initial_recovery(),
            subsequent_commits=(
                commit(turn=8, generation=4),
                commit(turn=10, generation=5),
            ),
            policy=RecoveryWindowPolicy(3, 4),
        )
        wide = qualify_recovery_window(
            initial_recovery=initial_recovery(),
            subsequent_commits=(
                commit(turn=8, generation=4),
                commit(turn=10, generation=5),
            ),
            policy=RecoveryWindowPolicy(3, 5),
        )
        self.assertNotEqual(narrow.policy_digest, wide.policy_digest)
        self.assertNotEqual(narrow.digest, wide.digest)
        self.assertEqual(
            RecoveryWindowDisposition.SUSTAINED_BOUNDED_RECOVERY,
            narrow.disposition,
        )
        self.assertEqual(
            RecoveryWindowDisposition.PENDING_MORE_OBSERVATION,
            wide.disposition,
        )


if __name__ == "__main__":
    unittest.main()
