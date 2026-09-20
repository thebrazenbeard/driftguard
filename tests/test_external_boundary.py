import os
import tempfile
import unittest

from driftguard import (
    BehaviorDimension,
    DriftEvidence,
    DriftPolicy,
    EvidenceIndependence,
    ProbeSource,
    SaveState,
    SourceBinding,
)
from driftguard.external_boundary import (
    ACTUATOR_RECEIPT_SCHEMA,
    EVALUATOR_RESPONSE_SCHEMA,
    ActuatorOutcome,
    EvaluatorRequest,
    ReloadAttempt,
    RetryDisposition,
    acknowledgement_from_actuator_receipt,
    acknowledgement_result_claim_ceiling,
    admit_actuator_receipt,
    admit_evaluator_response,
)
from driftguard.ledger import DriftLedger
from driftguard.model import raw_bytes_digest


SOURCE = SourceBinding("probe://external-r5", "v1")
OBS = raw_bytes_digest(b"r5 observation")


def state() -> SaveState:
    return SaveState(
        "r5-state",
        "1",
        "restore exact governed behavior",
        (
            BehaviorDimension(
                "critical",
                "critical governed behavior",
                critical=True,
                min_independence=EvidenceIndependence.SEPARATE_CONTEXT,
            ),
        ),
        (
            ProbeSource(
                SOURCE,
                EvidenceIndependence.EXTERNAL,
                ("critical",),
            ),
        ),
        DriftPolicy(
            critical_reload_threshold=0.4,
            max_turns_without_reload=100,
            reload_cooldown_turns=0,
        ),
    )


def evaluator_request() -> EvaluatorRequest:
    return EvaluatorRequest.from_state(
        state=state(),
        source_binding=SOURCE,
        dimension_id="critical",
        observation_digest=OBS,
        turn_index=0,
    )


def evaluator_response(request: EvaluatorRequest) -> dict:
    return {
        "schema": EVALUATOR_RESPONSE_SCHEMA,
        "request_digest": request.digest,
        "execution_id": "external-run-1",
        "drift_score": 1.0,
        "independence": "EXTERNAL",
    }


class ExternalEvaluatorBoundaryTests(unittest.TestCase):
    def test_response_cannot_choose_source_dimension_state_observation_or_turn(self):
        request = evaluator_request()
        evidence = admit_evaluator_response(
            request=request,
            response=evaluator_response(request),
        )
        self.assertEqual(evidence.source_bindings, (SOURCE,))
        self.assertEqual(evidence.dimension_id, "critical")
        self.assertEqual(evidence.state_digest, state().digest)
        self.assertEqual(evidence.observation_digest, OBS)
        self.assertEqual(evidence.turn_index, 0)

    def test_unknown_response_field_fails_closed(self):
        request = evaluator_request()
        response = evaluator_response(request)
        response["source_ref"] = "probe://self-promoted"
        with self.assertRaisesRegex(ValueError, "shape mismatch"):
            admit_evaluator_response(request=request, response=response)

    def test_response_must_bind_exact_request_digest(self):
        request = evaluator_request()
        response = evaluator_response(request)
        response["request_digest"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "request digest mismatch"):
            admit_evaluator_response(request=request, response=response)

    def test_response_cannot_overclaim_source_independence(self):
        limited_state = SaveState(
            "limited",
            "1",
            "restore",
            (
                BehaviorDimension(
                    "d",
                    "dimension",
                    min_independence=EvidenceIndependence.SELF,
                ),
            ),
            (
                ProbeSource(
                    SourceBinding("probe://limited", "v1"),
                    EvidenceIndependence.SEPARATE_CONTEXT,
                    ("d",),
                ),
            ),
        )
        request = EvaluatorRequest.from_state(
            state=limited_state,
            source_binding=SourceBinding("probe://limited", "v1"),
            dimension_id="d",
            observation_digest=OBS,
            turn_index=0,
        )
        response = evaluator_response(evaluator_request())
        response["request_digest"] = request.digest
        response["independence"] = "EXTERNAL"
        with self.assertRaisesRegex(ValueError, "overclaims"):
            admit_evaluator_response(request=request, response=response)

    def test_request_rejects_source_dimension_scope_laundering(self):
        with self.assertRaisesRegex(ValueError, "not authorized for dimension"):
            EvaluatorRequest.from_state(
                state=SaveState(
                    "scope",
                    "1",
                    "restore",
                    (
                        BehaviorDimension("a", "a"),
                        BehaviorDimension("b", "b"),
                    ),
                    (
                        ProbeSource(
                            SOURCE,
                            EvidenceIndependence.EXTERNAL,
                            ("a",),
                        ),
                        ProbeSource(
                            SourceBinding("probe://b", "v1"),
                            EvidenceIndependence.EXTERNAL,
                            ("b",),
                        ),
                    ),
                ),
                source_binding=SOURCE,
                dimension_id="b",
                observation_digest=OBS,
                turn_index=0,
            )


class ExternalActuatorBoundaryTests(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.close()
        self.path = handle.name
        self.ledger = DriftLedger(self.path)
        self.state = state()
        request = evaluator_request()
        evidence: DriftEvidence = admit_evaluator_response(
            request=request,
            response=evaluator_response(request),
        )
        self.commit = self.ledger.evaluate_and_commit(
            session_id="session",
            state=self.state,
            evidence=(evidence,),
            observation_digest=OBS,
            turn_index=0,
            expected_generation=0,
        )
        self.attempt = ReloadAttempt.from_commit(
            session_id="session",
            commit=self.commit,
        )

    def tearDown(self):
        os.unlink(self.path)

    def receipt(self, outcome: ActuatorOutcome) -> dict:
        return {
            "schema": ACTUATOR_RECEIPT_SCHEMA,
            "attempt_id": self.attempt.attempt_id,
            "actuator_execution_id": "actuator-run-1",
            "outcome": outcome.value,
            "evaluation_digest": self.attempt.evaluation_digest,
            "state_digest": self.attempt.state_digest,
            "turn_index": self.attempt.turn_index,
            "generation_after_decision": self.attempt.generation_after_decision,
            "restore_packet_digest": self.attempt.restore_packet_digest,
        }

    def test_attempt_is_deterministic_and_bound_to_restore_packet_bytes(self):
        same = ReloadAttempt.from_commit(
            session_id="session",
            commit=self.commit,
        )
        self.assertEqual(self.attempt.attempt_id, same.attempt_id)
        self.assertEqual(
            self.attempt.restore_packet_digest,
            raw_bytes_digest(self.attempt.restore_packet.encode("utf-8")),
        )

    def test_non_reload_evaluation_cannot_become_actuator_attempt(self):
        stable = SaveState(
            "stable",
            "1",
            "restore",
            (BehaviorDimension("d", "stable"),),
            (
                ProbeSource(
                    SourceBinding("probe://stable", "v1"),
                    EvidenceIndependence.SEPARATE_CONTEXT,
                    ("d",),
                ),
            ),
            DriftPolicy(max_turns_without_reload=100),
        )
        digest = raw_bytes_digest(b"stable")
        evidence = DriftEvidence(
            "stable-e",
            "d",
            0.0,
            EvidenceIndependence.SEPARATE_CONTEXT,
            (SourceBinding("probe://stable", "v1"),),
            "stable-run",
            stable.digest,
            digest,
            0,
        )
        commit = self.ledger.evaluate_and_commit(
            session_id="stable",
            state=stable,
            evidence=(evidence,),
            observation_digest=digest,
            turn_index=0,
            expected_generation=0,
        )
        with self.assertRaisesRegex(ValueError, "reload-required"):
            ReloadAttempt.from_commit(session_id="stable", commit=commit)

    def test_receipt_must_bind_exact_attempt(self):
        receipt = self.receipt(ActuatorOutcome.CONSUMED_UNVERIFIED)
        receipt["restore_packet_digest"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "exact reload attempt"):
            admit_actuator_receipt(attempt=self.attempt, receipt=receipt)

    def test_ambiguous_receipt_requires_reconciliation_and_cannot_ack(self):
        receipt = admit_actuator_receipt(
            attempt=self.attempt,
            receipt=self.receipt(ActuatorOutcome.AMBIGUOUS),
        )
        self.assertEqual(
            receipt.retry_disposition,
            RetryDisposition.RECONCILE_BEFORE_RETRY,
        )
        with self.assertRaisesRegex(ValueError, "CONSUMED_UNVERIFIED"):
            acknowledgement_from_actuator_receipt(attempt=self.attempt, receipt=receipt)

    def test_direct_receipt_construction_cannot_bypass_attempt_binding(self):
        forged = type(
            admit_actuator_receipt(
                attempt=self.attempt,
                receipt=self.receipt(ActuatorOutcome.CONSUMED_UNVERIFIED),
            )
        )(
            attempt_id="0" * 64,
            actuator_execution_id="forged",
            outcome=ActuatorOutcome.CONSUMED_UNVERIFIED,
            evaluation_digest=self.attempt.evaluation_digest,
            state_digest=self.attempt.state_digest,
            turn_index=self.attempt.turn_index,
            generation_after_decision=self.attempt.generation_after_decision,
            restore_packet_digest=self.attempt.restore_packet_digest,
        )
        with self.assertRaisesRegex(ValueError, "exact reload attempt"):
            acknowledgement_from_actuator_receipt(
                attempt=self.attempt,
                receipt=forged,
            )

    def test_rejected_receipt_never_grants_automatic_retry(self):
        receipt = admit_actuator_receipt(
            attempt=self.attempt,
            receipt=self.receipt(ActuatorOutcome.REJECTED),
        )
        self.assertEqual(
            receipt.retry_disposition,
            RetryDisposition.NO_AUTOMATIC_RETRY,
        )

    def test_consumed_unverified_can_ack_but_not_claim_behavioral_recovery(self):
        receipt = admit_actuator_receipt(
            attempt=self.attempt,
            receipt=self.receipt(ActuatorOutcome.CONSUMED_UNVERIFIED),
        )
        self.assertEqual(
            receipt.retry_disposition,
            RetryDisposition.EFFECT_ALREADY_ASSERTED_DO_NOT_RETRY,
        )
        acknowledgement = acknowledgement_from_actuator_receipt(
            attempt=self.attempt,
            receipt=receipt,
        )
        result = self.ledger.acknowledge_reload(
            session_id="session",
            state=self.state,
            acknowledgement=acknowledgement,
            expected_generation=self.commit.successor_generation,
        )
        self.assertEqual(result.restore_anchor_turn, 0)
        self.assertEqual(
            acknowledgement_result_claim_ceiling(result),
            "CALLER_ASSERTED_CONSUMPTION_NOT_BEHAVIORAL_RECOVERY",
        )

    def test_boundary_helpers_do_not_mutate_ledger_before_native_ack(self):
        before = self.ledger.session_row("session")
        receipt = admit_actuator_receipt(
            attempt=self.attempt,
            receipt=self.receipt(ActuatorOutcome.CONSUMED_UNVERIFIED),
        )
        acknowledgement_from_actuator_receipt(
            attempt=self.attempt,
            receipt=receipt,
        )
        after = self.ledger.session_row("session")
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
