from contextlib import closing
import os
import tempfile
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
from driftguard.ledger import CommitResult, DriftLedger
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


class RecoveryWindowQualificationTests(unittest.TestCase):
    def _seed_ledger(
        self,
        ledger: DriftLedger,
        initial: BehavioralRecoveryReceipt,
        commits,
        *,
        session_id: str = "session",
        initial_decision: Decision = Decision.STABLE,
        initial_reload_required: bool = False,
        initial_aggregate_drift: float | None = 0.0,
        initial_reasons: tuple[str, ...] = ("durable-seed",),
    ) -> None:
        commits = tuple(commits)
        last_turn = (
            commits[-1].evaluation.turn_index
            if commits
            else initial.replay_turn_index
        )
        last_generation = (
            commits[-1].successor_generation
            if commits
            else initial.replay_generation + 1
        )
        last_digest = (
            commits[-1].evaluation.digest
            if commits
            else initial.replay_evaluation_digest
        )
        with closing(ledger._connect()) as db, db:
            db.execute(
                """INSERT INTO sessions(
                    session_id,state_digest,generation,first_turn,last_turn,
                    restore_anchor_turn,last_reload_decision_turn,
                    last_evaluation_digest
                ) VALUES(?,?,?,?,?,?,?,?)""",
                (
                    session_id,
                    initial.state_digest,
                    last_generation,
                    initial.acknowledgement_turn_index,
                    last_turn,
                    initial.acknowledgement_turn_index,
                    initial.acknowledgement_turn_index,
                    last_digest,
                ),
            )
            db.execute(
                """INSERT INTO reload_acknowledgements(
                    ack_id,session_id,generation_before,generation_after,
                    evaluation_digest,state_digest,turn_index
                ) VALUES(?,?,?,?,?,?,?)""",
                (
                    initial.ack_id,
                    session_id,
                    initial.replay_generation - 1,
                    initial.replay_generation,
                    initial.acknowledged_evaluation_digest,
                    initial.state_digest,
                    initial.acknowledgement_turn_index,
                ),
            )
            db.execute(
                """INSERT INTO evaluation_events(
                    session_id,generation_before,generation_after,turn_index,
                    state_digest,observation_digest,evidence_digest,
                    evaluation_digest,decision,reload_required,
                    aggregate_drift,reasons
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    session_id,
                    initial.replay_generation,
                    initial.replay_generation + 1,
                    initial.replay_turn_index,
                    initial.state_digest,
                    initial.replay_observation_digest,
                    initial.replay_evidence_digest,
                    initial.replay_evaluation_digest,
                    initial_decision.value,
                    int(initial_reload_required),
                    initial_aggregate_drift,
                    "|".join(initial_reasons),
                ),
            )
            for item in commits:
                e = item.evaluation
                db.execute(
                    """INSERT INTO evaluation_events(
                        session_id,generation_before,generation_after,turn_index,
                        state_digest,observation_digest,evidence_digest,
                        evaluation_digest,decision,reload_required,
                        aggregate_drift,reasons
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        session_id,
                        e.generation,
                        item.successor_generation,
                        e.turn_index,
                        e.state_digest,
                        e.observation_digest,
                        e.evidence_digest,
                        e.digest,
                        e.decision.value,
                        int(e.reload_required),
                        e.aggregate_drift,
                        "|".join(e.reasons),
                    ),
                )

    def qualify(
        self,
        *commits,
        state: SaveState = STATE_OBJ,
        policy: RecoveryWindowPolicy = RecoveryWindowPolicy(),
        session_id: str = "session",
        initial_decision: Decision = Decision.STABLE,
        initial_reload_required: bool = False,
        initial_aggregate_drift: float | None = 0.0,
        initial_reasons: tuple[str, ...] = ("durable-seed",),
    ):
        initial = initial_recovery()
        commits = tuple(commits)
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.close()
        try:
            ledger = DriftLedger(handle.name)
            self._seed_ledger(
                ledger,
                initial,
                commits,
                session_id=session_id,
                initial_decision=initial_decision,
                initial_reload_required=initial_reload_required,
                initial_aggregate_drift=initial_aggregate_drift,
                initial_reasons=initial_reasons,
            )
            return qualify_recovery_window(
                session_id=session_id,
                state=state,
                initial_recovery=initial,
                subsequent_commits=commits,
                ledger=ledger,
                policy=policy,
            )
        finally:
            os.unlink(handle.name)

    def test_multiple_stable_checkpoints_over_precommitted_span_are_sustained(self):
        receipt = self.qualify(
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
        receipt = self.qualify()
        self.assertEqual(
            RecoveryWindowDisposition.PENDING_MORE_OBSERVATION,
            receipt.disposition,
        )

    def test_stable_count_without_required_turn_span_is_pending(self):
        receipt = self.qualify(
            commit(turn=7, generation=4),
            commit(turn=8, generation=5),
        )
        self.assertEqual(
            RecoveryWindowDisposition.PENDING_MORE_OBSERVATION,
            receipt.disposition,
        )

    def test_warn_is_bounded_degradation(self):
        receipt = self.qualify(
            commit(turn=8, generation=4),
            commit(turn=10, generation=5, decision=Decision.WARN),
        )
        self.assertEqual(
            RecoveryWindowDisposition.DEGRADED_DRIFT_RETURNED,
            receipt.disposition,
        )
        self.assertEqual("DEGRADED", receipt.behavioral_trace[-1])

    def test_unknown_blocks_sustained_recovery_claim(self):
        receipt = self.qualify(
            commit(turn=8, generation=4),
            commit(turn=10, generation=5, decision=Decision.UNKNOWN),
        )
        self.assertEqual(
            RecoveryWindowDisposition.INDETERMINATE_EVIDENCE,
            receipt.disposition,
        )
        self.assertEqual("INDETERMINATE", receipt.behavioral_trace[-1])

    def test_unknown_with_critical_breach_is_behavioral_relapse(self):
        receipt = self.qualify(
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
        receipt = self.qualify(
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
        receipt = self.qualify(
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
        receipt = self.qualify(
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

    def test_behavior_above_reload_threshold_is_relapse_even_when_effect_suppressed(self):
        receipt = self.qualify(
            commit(
                turn=8,
                generation=4,
                decision=Decision.WARN,
                reload_required=False,
                aggregate_drift=0.60,
                reasons=(
                    "aggregate_reload_threshold",
                    "reload_suppressed_by_cooldown",
                ),
            ),
        )
        self.assertEqual(
            RecoveryWindowDisposition.RELAPSE_BEHAVIORAL_DRIFT,
            receipt.disposition,
        )

    def test_periodic_initial_replay_preserves_operational_trace_but_is_behaviorally_stable(self):
        receipt = self.qualify(
            commit(turn=8, generation=4),
            commit(turn=10, generation=5),
            initial_decision=Decision.RELOAD,
            initial_reload_required=True,
            initial_aggregate_drift=0.0,
            initial_reasons=("periodic_reload_due",),
        )
        self.assertEqual(
            RecoveryWindowDisposition.SUSTAINED_BOUNDED_RECOVERY,
            receipt.disposition,
        )
        self.assertEqual(Decision.RELOAD.value, receipt.decision_trace[0])
        self.assertTrue(receipt.reload_required_trace[0])
        self.assertEqual("STABLE", receipt.behavioral_trace[0])

    def test_warn_level_periodic_initial_replay_cannot_seed_recovery_window(self):
        with self.assertRaisesRegex(ValueError, "DEGRADED"):
            self.qualify(
                initial_decision=Decision.RELOAD,
                initial_reload_required=True,
                initial_aggregate_drift=0.30,
                initial_reasons=("periodic_reload_due",),
            )

    def test_state_change_cannot_launder_recovery_into_new_baseline(self):
        with self.assertRaisesRegex(ValueError, "baseline mutation"):
            self.qualify(
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
            self.qualify(state=other)

    def test_generation_gap_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "generation is not contiguous"):
            self.qualify(commit(turn=8, generation=5))

    def test_non_monotonic_turn_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "advance turn_index"):
            self.qualify(commit(turn=6, generation=4))

    def test_zero_ledger_forged_subject_cannot_qualify(self):
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.close()
        try:
            ledger = DriftLedger(handle.name)
            with self.assertRaisesRegex(
                ValueError,
                "durable ledger acknowledgement",
            ):
                qualify_recovery_window(
                    session_id="session",
                    state=STATE_OBJ,
                    initial_recovery=initial_recovery(),
                    subsequent_commits=(
                        commit(turn=8, generation=4),
                        commit(turn=10, generation=5),
                    ),
                    ledger=ledger,
                )
        finally:
            os.unlink(handle.name)

    def test_cross_session_durable_rows_cannot_qualify(self):
        initial = initial_recovery()
        commits = (
            commit(turn=8, generation=4),
            commit(turn=10, generation=5),
        )
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.close()
        try:
            ledger = DriftLedger(handle.name)
            self._seed_ledger(
                ledger,
                initial,
                commits,
                session_id="other",
            )
            with self.assertRaisesRegex(ValueError, "durable acknowledgement"):
                qualify_recovery_window(
                    session_id="session",
                    state=STATE_OBJ,
                    initial_recovery=initial,
                    subsequent_commits=commits,
                    ledger=ledger,
                )
        finally:
            os.unlink(handle.name)

    def test_durable_checkpoint_fields_must_match_commit(self):
        item = commit(turn=8, generation=4)
        initial = initial_recovery()
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.close()
        try:
            ledger = DriftLedger(handle.name)
            self._seed_ledger(ledger, initial, (item,))
            with closing(ledger._connect()) as db, db:
                db.execute(
                    """UPDATE evaluation_events
                          SET aggregate_drift=0.99
                        WHERE session_id='session'
                          AND evaluation_digest=?""",
                    (item.evaluation.digest,),
                )
            with self.assertRaisesRegex(ValueError, "durable ledger"):
                qualify_recovery_window(
                    session_id="session",
                    state=STATE_OBJ,
                    initial_recovery=initial,
                    subsequent_commits=(item,),
                    ledger=ledger,
                )
        finally:
            os.unlink(handle.name)

    def test_policy_is_digest_bound_to_receipt(self):
        narrow = self.qualify(
            commit(turn=8, generation=4),
            commit(turn=10, generation=5),
            policy=RecoveryWindowPolicy(3, 4),
        )
        wide = self.qualify(
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
