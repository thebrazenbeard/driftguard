import unittest

from driftguard import (
    BehaviorDimension,
    DriftPolicy,
    EvidenceIndependence,
    ProbeSource,
    SaveState,
    SourceBinding,
)
from driftguard.external_boundary import BehavioralRecoveryReceipt
from driftguard.ledger import CommitResult
from driftguard.model import Decision, Evaluation, canonical_digest
from driftguard.recovery_qualification import (
    RecoveryWindowDisposition,
    RecoveryWindowPolicy,
    qualify_recovery_window,
)


SOURCE = SourceBinding("probe://recovery-window", "v1")
STATE_OBJ = SaveState(
    "recovery-window",
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
        max_turns_without_reload=5,
        reload_cooldown_turns=0,
    ),
)
STATE = STATE_OBJ.digest


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
    aggregate_drift: float | None = None,
    reasons: tuple[str, ...] = ("qualification-test",),
) -> CommitResult:
    if aggregate_drift is None:
        if decision is Decision.STABLE:
            aggregate_drift = 0.0
        elif decision is Decision.WARN:
            aggregate_drift = 0.30
        elif decision is Decision.RELOAD:
            aggregate_drift = 0.60
    dimension_score = (
        0.0 if aggregate_drift is None else float(aggregate_drift)
    )
    evaluation = Evaluation(
        decision=decision,
        reload_required=reload_required,
        aggregate_drift=aggregate_drift,
        dimension_scores=(("d", dimension_score),),
        reasons=reasons,
        state_digest=state_digest,
        observation_digest=digest(f"observation-{turn}-{generation}"),
        evidence_digest=digest(f"evidence-{turn}-{generation}"),
        turn_index=turn,
        generation=generation,
        restore_packet="restore" if reload_required else None,
    )
    return CommitResult(evaluation, generation + 1)


def qualify(*commits, policy=RecoveryWindowPolicy()):
    return qualify_recovery_window(
        state=STATE_OBJ,
        initial_recovery=initial_recovery(),
        subsequent_commits=commits,
        policy=policy,
    )


class RecoveryWindowQualificationTests(unittest.TestCase):
    def test_multiple_stable_checkpoints_over_precommitted_span_are_sustained(self):
        receipt = qualify(
            commit(turn=8, generation=4),
            commit(turn=10, generation=5),
        )
        self.assertEqual(
            RecoveryWindowDisposition.SUSTAINED_BOUNDED_RECOVERY,
            receipt.disposition,
        )
        self.assertEqual(3, receipt.checkpoint_count)
        self.assertEqual(3, receipt.stable_checkpoint_count)
        self.assertEqual(("STABLE", "STABLE", "STABLE"), receipt.behavioral_trace)

    def test_one_clean_replay_is_not_sustained_recovery(self):
        receipt = qualify()
        self.assertEqual(
            RecoveryWindowDisposition.PENDING_MORE_OBSERVATION,
            receipt.disposition,
        )

    def test_stable_count_without_required_turn_span_is_pending(self):
        receipt = qualify(
            commit(turn=7, generation=4),
            commit(turn=8, generation=5),
        )
        self.assertEqual(
            RecoveryWindowDisposition.PENDING_MORE_OBSERVATION,
            receipt.disposition,
        )

    def test_warn_is_bounded_degradation(self):
        receipt = qualify(
            commit(turn=8, generation=4),
            commit(turn=10, generation=5, decision=Decision.WARN),
        )
        self.assertEqual(
            RecoveryWindowDisposition.DEGRADED_DRIFT_RETURNED,
            receipt.disposition,
        )
        self.assertEqual("DEGRADED", receipt.behavioral_trace[-1])

    def test_unknown_blocks_sustained_recovery_claim(self):
        receipt = qualify(
            commit(turn=8, generation=4),
            commit(turn=10, generation=5, decision=Decision.UNKNOWN),
        )
        self.assertEqual(
            RecoveryWindowDisposition.INDETERMINATE_EVIDENCE,
            receipt.disposition,
        )
        self.assertEqual("INDETERMINATE", receipt.behavioral_trace[-1])

    def test_unknown_with_critical_breach_is_behavioral_relapse(self):
        receipt = qualify(
            commit(
                turn=8,
                generation=4,
                decision=Decision.UNKNOWN,
                reload_required=True,
                aggregate_drift=None,
                reasons=(
                    "missing_evidence:other",
                    "critical_dimension_breach",
                ),
            ),
        )
        self.assertEqual(
            RecoveryWindowDisposition.RELAPSE_BEHAVIORAL_DRIFT,
            receipt.disposition,
        )
        self.assertEqual("RELAPSE", receipt.behavioral_trace[-1])

    def test_unknown_with_periodic_reload_only_is_indeterminate(self):
        receipt = qualify(
            commit(
                turn=8,
                generation=4,
                decision=Decision.UNKNOWN,
                reload_required=True,
                aggregate_drift=None,
                reasons=(
                    "missing_evidence:d",
                    "periodic_reload_due",
                ),
            ),
        )
        self.assertEqual(
            RecoveryWindowDisposition.INDETERMINATE_EVIDENCE,
            receipt.disposition,
        )
        self.assertEqual((False, True), receipt.reload_required_trace)
        self.assertEqual(
            ("STABLE", "INDETERMINATE"),
            receipt.behavioral_trace,
        )

    def test_periodic_only_reload_with_low_drift_counts_as_stable_checkpoint(self):
        receipt = qualify(
            commit(
                turn=8,
                generation=4,
                decision=Decision.RELOAD,
                reload_required=True,
                aggregate_drift=0.0,
                reasons=("periodic_reload_due",),
            ),
            commit(turn=10, generation=5),
        )
        self.assertEqual(
            RecoveryWindowDisposition.SUSTAINED_BOUNDED_RECOVERY,
            receipt.disposition,
        )
        self.assertEqual(3, receipt.stable_checkpoint_count)
        self.assertEqual((False, True, False), receipt.reload_required_trace)
        self.assertEqual(
            ("STABLE", "STABLE", "STABLE"),
            receipt.behavioral_trace,
        )

    def test_periodic_reload_does_not_hide_warn_level_behavioral_drift(self):
        receipt = qualify(
            commit(
                turn=8,
                generation=4,
                decision=Decision.RELOAD,
                reload_required=True,
                aggregate_drift=0.30,
                reasons=("periodic_reload_due",),
            ),
        )
        self.assertEqual(
            RecoveryWindowDisposition.DEGRADED_DRIFT_RETURNED,
            receipt.disposition,
        )
        self.assertEqual("DEGRADED", receipt.behavioral_trace[-1])

    def test_behavior_above_reload_threshold_is_relapse_even_without_reload_flag(self):
        receipt = qualify(
            commit(
                turn=8,
                generation=4,
                decision=Decision.WARN,
                reload_required=False,
                aggregate_drift=0.60,
                reasons=("reload_suppressed_by_cooldown",),
            ),
        )
        self.assertEqual(
            RecoveryWindowDisposition.RELAPSE_BEHAVIORAL_DRIFT,
            receipt.disposition,
        )

    def test_state_change_cannot_launder_recovery_into_new_baseline(self):
        with self.assertRaisesRegex(ValueError, "baseline mutation"):
            qualify(
                commit(turn=8, generation=4, state_digest="b" * 64),
            )

    def test_qualification_state_must_match_initial_recovery(self):
        other = SaveState(
            "other",
            "1",
            "restore",
            (BehaviorDimension("d", "d"),),
            (
                ProbeSource(
                    SOURCE,
                    EvidenceIndependence.SEPARATE_CONTEXT,
                    ("d",),
                ),
            ),
        )
        with self.assertRaisesRegex(ValueError, "state digest mismatch"):
            qualify_recovery_window(
                state=other,
                initial_recovery=initial_recovery(),
                subsequent_commits=(),
            )

    def test_generation_gap_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "generation is not contiguous"):
            qualify(commit(turn=8, generation=5))

    def test_non_monotonic_turn_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "advance turn_index"):
            qualify(commit(turn=6, generation=4))

    def test_policy_is_digest_bound_to_receipt(self):
        narrow = qualify(
            commit(turn=8, generation=4),
            commit(turn=10, generation=5),
            policy=RecoveryWindowPolicy(3, 4),
        )
        wide = qualify(
            commit(turn=8, generation=4),
            commit(turn=10, generation=5),
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
