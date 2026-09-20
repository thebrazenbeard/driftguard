import unittest
from hashlib import sha256

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
from driftguard.external_boundary import (
    ActuatorDeliveryStatus,
    ActuatorDisposition,
    ActuatorReceipt,
    append_external_receipt,
    build_evaluator_request,
    build_reload_directive,
    qualify_post_reload_behavior,
    reconcile_actuator_receipt,
    validate_evaluator_response,
)
from driftguard.ledger import AcknowledgementResult, CommitResult
from driftguard.model import Evaluation, canonical_digest, raw_bytes_digest


SOURCE = SourceBinding("probe://external", "v1")
OBS = raw_bytes_digest(b"external observation")


def state() -> SaveState:
    return SaveState(
        "external-boundary",
        "1",
        "restore this exact behavior",
        (
            BehaviorDimension(
                "d",
                "behavioral dimension",
                min_independence=EvidenceIndependence.EXTERNAL,
            ),
        ),
        (
            ProbeSource(
                SOURCE,
                EvidenceIndependence.EXTERNAL,
                ("d",),
            ),
        ),
        DriftPolicy(max_turns_without_reload=5, reload_cooldown_turns=0),
    )


def evidence(s: SaveState, turn: int, score: float = 0.0) -> DriftEvidence:
    return DriftEvidence(
        f"e-{turn}",
        "d",
        score,
        EvidenceIndependence.EXTERNAL,
        (SOURCE,),
        f"external-run-{turn}",
        s.digest,
        OBS,
        turn,
    )


def evaluation(
    *,
    s: SaveState,
    turn: int,
    generation: int,
    decision: Decision,
    reload_required: bool,
    restore_packet: str | None,
) -> Evaluation:
    rows = (evidence(s, turn, 1.0 if reload_required else 0.0),)
    return Evaluation(
        decision=decision,
        reload_required=reload_required,
        aggregate_drift=1.0 if reload_required else 0.0,
        dimension_scores=(("d", 1.0 if reload_required else 0.0),),
        reasons=("test",),
        state_digest=s.digest,
        observation_digest=OBS,
        evidence_digest=canonical_digest([
            {
                "evidence_id": rows[0].evidence_id,
                "dimension_id": rows[0].dimension_id,
                "drift_score": float(rows[0].drift_score),
                "independence": rows[0].independence.name,
                "source_bindings": [
                    {"ref": SOURCE.ref, "version": SOURCE.version}
                ],
                "execution_id": rows[0].execution_id,
                "state_digest": s.digest,
                "observation_digest": OBS,
                "turn_index": turn,
            }
        ]),
        turn_index=turn,
        generation=generation,
        restore_packet=restore_packet,
    )


class ExternalEvaluatorBoundaryTests(unittest.TestCase):
    def test_request_binds_state_observation_turn_generation_and_probe_provenance(self):
        s = state()
        req = build_evaluator_request(
            session_id="session",
            state=s,
            observation_digest=OBS,
            turn_index=7,
            expected_generation=3,
        )
        self.assertEqual(s.digest, req.state_digest)
        self.assertEqual(OBS, req.observation_digest)
        self.assertEqual(7, req.turn_index)
        self.assertEqual(3, req.expected_generation)
        self.assertEqual("probe://external", req.probe_contract[0].source_ref)
        self.assertEqual("v1", req.probe_contract[0].source_version)
        self.assertEqual("EXTERNAL", req.probe_contract[0].max_independence)
        self.assertEqual(("d",), req.probe_contract[0].dimensions)
        self.assertEqual(f"driftguard-evaluator:{req.digest}", req.request_id)

    def test_request_digest_moves_when_generation_moves(self):
        s = state()
        first = build_evaluator_request(
            session_id="session",
            state=s,
            observation_digest=OBS,
            turn_index=7,
            expected_generation=3,
        )
        second = build_evaluator_request(
            session_id="session",
            state=s,
            observation_digest=OBS,
            turn_index=7,
            expected_generation=4,
        )
        self.assertNotEqual(first.digest, second.digest)

    def test_external_response_rejects_wrong_observation_or_unrequested_source(self):
        s = state()
        req = build_evaluator_request(
            session_id="session",
            state=s,
            observation_digest=OBS,
            turn_index=7,
            expected_generation=3,
        )
        wrong_obs = DriftEvidence(
            "wrong",
            "d",
            0.0,
            EvidenceIndependence.EXTERNAL,
            (SOURCE,),
            "run",
            s.digest,
            raw_bytes_digest(b"wrong"),
            7,
        )
        with self.assertRaisesRegex(ValueError, "observation digest mismatch"):
            validate_evaluator_response(req, (wrong_obs,))

        other = SourceBinding("probe://not-requested", "v1")
        wrong_source = DriftEvidence(
            "wrong-source",
            "d",
            0.0,
            EvidenceIndependence.EXTERNAL,
            (other,),
            "run-2",
            s.digest,
            OBS,
            7,
        )
        with self.assertRaisesRegex(ValueError, "unrequested source binding"):
            validate_evaluator_response(req, (wrong_source,))


class ExternalActuatorBoundaryTests(unittest.TestCase):
    def reload_commit(self) -> CommitResult:
        s = state()
        ev = evaluation(
            s=s,
            turn=5,
            generation=1,
            decision=Decision.RELOAD,
            reload_required=True,
            restore_packet="restore this exact behavior",
        )
        return CommitResult(ev, 2)

    def receipt(self, directive, status):
        return ActuatorReceipt(
            directive.directive_id,
            directive.digest,
            status,
            "provider-op-1",
            sha256(b"provider receipt").hexdigest(),
        )

    def test_reload_directive_is_exactly_bound_and_stable_is_rejected(self):
        commit = self.reload_commit()
        directive = build_reload_directive(
            session_id="session",
            commit=commit,
        )
        self.assertEqual(commit.evaluation.digest, directive.evaluation_digest)
        self.assertEqual(commit.successor_generation, directive.expected_generation)
        self.assertEqual(
            sha256(directive.restore_packet.encode("utf-8")).hexdigest(),
            directive.restore_packet_sha256,
        )

        s = state()
        stable = CommitResult(
            evaluation(
                s=s,
                turn=1,
                generation=0,
                decision=Decision.STABLE,
                reload_required=False,
                restore_packet=None,
            ),
            1,
        )
        with self.assertRaisesRegex(ValueError, "reload-required"):
            build_reload_directive(session_id="session", commit=stable)

    def test_applied_receipt_yields_acknowledgement(self):
        directive = build_reload_directive(
            session_id="session",
            commit=self.reload_commit(),
        )
        result = reconcile_actuator_receipt(
            directive=directive,
            receipt=self.receipt(directive, ActuatorDeliveryStatus.APPLIED),
        )
        self.assertEqual(ActuatorDisposition.ACKNOWLEDGE, result.disposition)
        self.assertIsInstance(result.acknowledgement, ReloadAcknowledgement)
        self.assertEqual(
            directive.evaluation_digest,
            result.acknowledgement.evaluation_digest,
        )
        self.assertEqual(directive.state_digest, result.acknowledgement.state_digest)
        self.assertEqual(directive.turn_index, result.acknowledgement.turn_index)

    def test_ambiguous_delivery_requires_readback_and_forbids_blind_retry(self):
        directive = build_reload_directive(
            session_id="session",
            commit=self.reload_commit(),
        )
        result = reconcile_actuator_receipt(
            directive=directive,
            receipt=self.receipt(directive, ActuatorDeliveryStatus.UNKNOWN),
        )
        self.assertEqual(
            ActuatorDisposition.READBACK_REQUIRED,
            result.disposition,
        )
        self.assertIsNone(result.acknowledgement)

    def test_confirmed_not_applied_is_retryable(self):
        directive = build_reload_directive(
            session_id="session",
            commit=self.reload_commit(),
        )
        result = reconcile_actuator_receipt(
            directive=directive,
            receipt=self.receipt(directive, ActuatorDeliveryStatus.NOT_APPLIED),
        )
        self.assertEqual(ActuatorDisposition.RETRY_ALLOWED, result.disposition)
        self.assertIsNone(result.acknowledgement)

    def test_receipt_cannot_rebind_to_another_directive(self):
        directive = build_reload_directive(
            session_id="session",
            commit=self.reload_commit(),
        )
        receipt = ActuatorReceipt(
            "wrong",
            directive.digest,
            ActuatorDeliveryStatus.APPLIED,
            "provider-op-1",
            sha256(b"provider receipt").hexdigest(),
        )
        with self.assertRaisesRegex(ValueError, "directive id mismatch"):
            reconcile_actuator_receipt(directive=directive, receipt=receipt)


class BehavioralRecoveryBoundaryTests(unittest.TestCase):
    def test_acknowledgement_is_not_recovery_but_later_stable_replay_can_qualify(self):
        s = state()
        ack = ReloadAcknowledgement(
            "ack",
            "a" * 64,
            s.digest,
            5,
        )
        ack_result = AcknowledgementResult(
            ack_id="ack",
            successor_generation=3,
            restore_anchor_turn=5,
        )
        replay = CommitResult(
            evaluation(
                s=s,
                turn=6,
                generation=3,
                decision=Decision.STABLE,
                reload_required=False,
                restore_packet=None,
            ),
            4,
        )
        receipt = qualify_post_reload_behavior(
            acknowledgement=ack,
            acknowledgement_result=ack_result,
            replay_commit=replay,
        )
        self.assertEqual("POST_RELOAD_BEHAVIORAL_REPLAY_PASS", receipt.result)
        self.assertEqual(6, receipt.replay_turn_index)
        self.assertEqual(replay.evaluation.digest, receipt.replay_evaluation_digest)

    def test_reload_or_unknown_replay_cannot_be_called_recovery(self):
        s = state()
        ack = ReloadAcknowledgement("ack", "a" * 64, s.digest, 5)
        ack_result = AcknowledgementResult("ack", 3, 5)
        for decision, reload_required, packet in (
            (Decision.UNKNOWN, False, None),
            (Decision.RELOAD, True, "restore"),
        ):
            replay = CommitResult(
                evaluation(
                    s=s,
                    turn=6,
                    generation=3,
                    decision=decision,
                    reload_required=reload_required,
                    restore_packet=packet,
                ),
                4,
            )
            with self.subTest(decision=decision):
                with self.assertRaisesRegex(ValueError, "stable bounded recovery"):
                    qualify_post_reload_behavior(
                        acknowledgement=ack,
                        acknowledgement_result=ack_result,
                        replay_commit=replay,
                    )

    def test_external_receipt_chain_is_hash_linked(self):
        first = append_external_receipt(
            sequence=0,
            previous_digest=None,
            subject_kind="ACTUATOR_RECEIPT",
            subject_digest="b" * 64,
        )
        second = append_external_receipt(
            sequence=1,
            previous_digest=first.digest,
            subject_kind="BEHAVIORAL_RECOVERY_RECEIPT",
            subject_digest="c" * 64,
        )
        self.assertEqual(first.digest, second.previous_digest)
        changed = append_external_receipt(
            sequence=1,
            previous_digest=first.digest,
            subject_kind="BEHAVIORAL_RECOVERY_RECEIPT",
            subject_digest="d" * 64,
        )
        self.assertNotEqual(second.digest, changed.digest)


if __name__ == "__main__":
    unittest.main()
