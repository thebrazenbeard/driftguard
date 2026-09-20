import os
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from hashlib import sha256

from driftguard import (
    BehaviorDimension,
    Decision,
    DriftEvidence,
    DriftPolicy,
    EvidenceIndependence,
    MonitoredSubject,
    ProbeSource,
    ReloadAcknowledgement,
    SaveState,
    SourceBinding,
    StaleGenerationError,
    SubjectComponent,
    SubjectEpochTransition,
)
from driftguard.external_boundary import (
    ActuatorDeliveryStatus,
    ActuatorDisposition,
    ActuatorReceipt,
    ExternalEvaluatorResponse,
    ReloadDirective,
    append_external_receipt,
    build_evaluator_request,
    commit_evaluator_response,
    build_reload_directive,
    qualify_post_reload_behavior,
    reconcile_actuator_receipt,
    validate_evaluator_response,
    validate_reload_directive,
)
from driftguard.ledger import CommitResult, DriftLedger
from driftguard.model import raw_bytes_digest


SOURCE = SourceBinding("probe://external", "v1")
OBS = raw_bytes_digest(b"external observation")
REQUIRED_SUBJECT_COMPONENTS = (
    "provider",
    "model",
    "instructions",
    "tools",
    "retrieval",
    "memory",
    "inference",
    "harness",
)


def monitored_subject(*, epoch: int = 0, model_payload: str = "model-v1"):
    return MonitoredSubject(
        subject_id="external-runtime",
        epoch=epoch,
        components=tuple(
            SubjectComponent(
                component_id=component_id,
                binding=SourceBinding(
                    f"subject://external/{component_id}",
                    "v1",
                ),
                digest=raw_bytes_digest(
                    (
                        model_payload
                        if component_id == "model"
                        else f"{component_id}:v1"
                    ).encode("utf-8")
                ),
            )
            for component_id in REQUIRED_SUBJECT_COMPONENTS
        ),
    )


def state(*, max_turns: int = 5) -> SaveState:
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
        DriftPolicy(max_turns_without_reload=max_turns, reload_cooldown_turns=0),
    )


def evidence(
    s: SaveState,
    turn: int,
    score: float = 0.0,
    observation_digest: str = OBS,
) -> tuple[DriftEvidence, ...]:
    return (
        DriftEvidence(
            f"e-{turn}",
            "d",
            score,
            EvidenceIndependence.EXTERNAL,
            (SOURCE,),
            f"external-run-{turn}",
            s.digest,
            observation_digest,
            turn,
        ),
    )


def response(request, rows):
    return ExternalEvaluatorResponse(request.digest, tuple(rows))


class LedgerHarness(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.close()
        self.path = handle.name
        self.ledger = DriftLedger(self.path)
        self.s = state()

    def tearDown(self):
        os.unlink(self.path)

    def commit(self, *, turn: int, generation: int, score: float = 0.0, rows=True):
        return self.ledger.evaluate_and_commit(
            session_id="session",
            state=self.s,
            evidence=evidence(self.s, turn, score) if rows else (),
            observation_digest=OBS,
            turn_index=turn,
            expected_generation=generation,
        )

    def reload_commit(self):
        first = self.commit(turn=0, generation=0, score=0.0)
        self.assertEqual(Decision.STABLE, first.evaluation.decision)
        reload_commit = self.commit(turn=5, generation=1, score=1.0)
        self.assertTrue(reload_commit.evaluation.reload_required)
        return reload_commit


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
        wrong_obs = evidence(
            s, 7, observation_digest=raw_bytes_digest(b"wrong")
        )[0]
        with self.assertRaisesRegex(ValueError, "observation digest mismatch"):
            validate_evaluator_response(req, response(req, (wrong_obs,)))

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
            validate_evaluator_response(req, response(req, (wrong_source,)))

    def test_external_response_is_bound_to_exact_request_and_session(self):
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.close()
        try:
            ledger = DriftLedger(handle.name)
            s = state()
            request_a = build_evaluator_request(
                session_id="A",
                state=s,
                observation_digest=OBS,
                turn_index=0,
                expected_generation=0,
            )
            request_b = build_evaluator_request(
                session_id="B",
                state=s,
                observation_digest=OBS,
                turn_index=0,
                expected_generation=0,
            )
            response_a = response(request_a, evidence(s, 0, 0.0))
            commit_evaluator_response(
                request=request_a,
                state=s,
                response=response_a,
                ledger=ledger,
            )
            with self.assertRaisesRegex(ValueError, "request digest mismatch"):
                commit_evaluator_response(
                    request=request_b,
                    state=s,
                    response=response_a,
                    ledger=ledger,
                )
        finally:
            os.unlink(handle.name)

    def test_external_response_commit_enforces_request_generation(self):
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.close()
        try:
            ledger = DriftLedger(handle.name)
            s = state()
            stale_request = build_evaluator_request(
                session_id="session",
                state=s,
                observation_digest=OBS,
                turn_index=1,
                expected_generation=0,
            )
            ledger.evaluate_and_commit(
                session_id="session",
                state=s,
                evidence=evidence(s, 0, 0.0),
                observation_digest=OBS,
                turn_index=0,
                expected_generation=0,
            )
            with self.assertRaisesRegex(Exception, "expected generation 0, observed 1"):
                commit_evaluator_response(
                    request=stale_request,
                    state=s,
                    response=response(stale_request, evidence(s, 1, 0.0)),
                    ledger=ledger,
                )
        finally:
            os.unlink(handle.name)


class ExternalActuatorBoundaryTests(LedgerHarness):
    def receipt(self, directive, status):
        return ActuatorReceipt(
            directive.directive_id,
            directive.digest,
            status,
            "provider-op-1",
            sha256(b"provider receipt").hexdigest(),
        )

    def test_reload_directive_requires_durable_ledger_receipt(self):
        commit = self.reload_commit()
        directive = build_reload_directive(
            session_id="session",
            commit=commit,
            ledger=self.ledger,
        )
        self.assertEqual(commit.evaluation.digest, directive.evaluation_digest)
        self.assertEqual(commit.successor_generation, directive.expected_generation)

        other_handle = tempfile.NamedTemporaryFile(delete=False)
        other_handle.close()
        try:
            empty_ledger = DriftLedger(other_handle.name)
            with self.assertRaisesRegex(ValueError, "durable ledger evaluation receipt"):
                build_reload_directive(
                    session_id="session",
                    commit=commit,
                    ledger=empty_ledger,
                )
        finally:
            os.unlink(other_handle.name)

    def test_reload_directive_rejects_historical_commit_after_generation_moves(self):
        commit = self.reload_commit()
        acknowledgement = ReloadAcknowledgement(
            "ack-stale-directive",
            commit.evaluation.digest,
            self.s.digest,
            commit.evaluation.turn_index,
        )
        self.ledger.acknowledge_reload(
            session_id="session",
            state=self.s,
            acknowledgement=acknowledgement,
            expected_generation=commit.successor_generation,
        )
        with self.assertRaisesRegex(ValueError, "current durable generation"):
            build_reload_directive(
                session_id="session",
                commit=commit,
                ledger=self.ledger,
            )

    def test_stable_commit_cannot_create_reload_directive(self):
        stable = self.commit(turn=0, generation=0, score=0.0)
        with self.assertRaisesRegex(ValueError, "reload-required"):
            build_reload_directive(
                session_id="session",
                commit=stable,
                ledger=self.ledger,
            )

    def test_applied_receipt_requires_readback_without_verified_effect_proof(self):
        directive = build_reload_directive(
            session_id="session",
            commit=self.reload_commit(),
            ledger=self.ledger,
        )
        result = reconcile_actuator_receipt(
            directive=directive,
            receipt=self.receipt(directive, ActuatorDeliveryStatus.APPLIED),
            state=self.s,
            ledger=self.ledger,
        )
        self.assertEqual(
            ActuatorDisposition.READBACK_REQUIRED,
            result.disposition,
        )
        self.assertIsNone(result.acknowledgement)

    def test_forged_applied_receipt_cannot_manufacture_acknowledgement(self):
        directive = build_reload_directive(
            session_id="session",
            commit=self.reload_commit(),
            ledger=self.ledger,
        )
        forged = ActuatorReceipt(
            directive.directive_id,
            directive.digest,
            ActuatorDeliveryStatus.APPLIED,
            "fabricated-provider-operation",
            sha256(b"fabricated provider receipt").hexdigest(),
        )
        result = reconcile_actuator_receipt(
            directive=directive,
            receipt=forged,
            state=self.s,
            ledger=self.ledger,
        )
        self.assertEqual(
            ActuatorDisposition.READBACK_REQUIRED,
            result.disposition,
        )
        self.assertIsNone(result.acknowledgement)

    def test_ambiguous_delivery_requires_readback_and_forbids_blind_retry(self):
        directive = build_reload_directive(
            session_id="session",
            commit=self.reload_commit(),
            ledger=self.ledger,
        )
        result = reconcile_actuator_receipt(
            directive=directive,
            receipt=self.receipt(directive, ActuatorDeliveryStatus.UNKNOWN),
            state=self.s,
            ledger=self.ledger,
        )
        self.assertEqual(ActuatorDisposition.READBACK_REQUIRED, result.disposition)
        self.assertIsNone(result.acknowledgement)

    def test_not_applied_requires_readback_before_any_retry(self):
        directive = build_reload_directive(
            session_id="session",
            commit=self.reload_commit(),
            ledger=self.ledger,
        )
        result = reconcile_actuator_receipt(
            directive=directive,
            receipt=self.receipt(directive, ActuatorDeliveryStatus.NOT_APPLIED),
            state=self.s,
            ledger=self.ledger,
        )
        self.assertEqual(ActuatorDisposition.READBACK_REQUIRED, result.disposition)
        self.assertIsNone(result.acknowledgement)

    def test_direct_constructor_cannot_bypass_durable_reload_provenance(self):
        commit = self.reload_commit()
        forged = ReloadDirective(
            session_id="session",
            evaluation_digest="0" * 64,
            state_digest=self.s.digest,
            turn_index=commit.evaluation.turn_index,
            expected_generation=commit.successor_generation,
            restore_packet=commit.evaluation.restore_packet,
            restore_packet_sha256=sha256(
                commit.evaluation.restore_packet.encode("utf-8")
            ).hexdigest(),
        )
        forged_receipt = self.receipt(forged, ActuatorDeliveryStatus.APPLIED)
        with self.assertRaisesRegex(ValueError, "durable ledger evaluation receipt"):
            reconcile_actuator_receipt(
                directive=forged,
                receipt=forged_receipt,
                state=self.s,
                ledger=self.ledger,
            )

    def test_direct_constructor_cannot_substitute_restore_packet(self):
        commit = self.reload_commit()
        malicious_packet = "DRIFTGUARD_RESTORE\nmalicious"
        forged = ReloadDirective(
            session_id="session",
            evaluation_digest=commit.evaluation.digest,
            state_digest=self.s.digest,
            turn_index=commit.evaluation.turn_index,
            expected_generation=commit.successor_generation,
            restore_packet=malicious_packet,
            restore_packet_sha256=sha256(
                malicious_packet.encode("utf-8")
            ).hexdigest(),
        )
        forged_receipt = self.receipt(forged, ActuatorDeliveryStatus.APPLIED)
        with self.assertRaisesRegex(ValueError, "does not match pinned state"):
            reconcile_actuator_receipt(
                directive=forged,
                receipt=forged_receipt,
                state=self.s,
                ledger=self.ledger,
            )

    def test_once_valid_directive_cannot_reconcile_after_generation_moves(self):
        commit = self.reload_commit()
        directive = build_reload_directive(
            session_id="session",
            commit=commit,
            ledger=self.ledger,
        )
        self.ledger.acknowledge_reload(
            session_id="session",
            state=self.s,
            acknowledgement=ReloadAcknowledgement(
                "ack-move",
                commit.evaluation.digest,
                self.s.digest,
                commit.evaluation.turn_index,
            ),
            expected_generation=commit.successor_generation,
        )
        with self.assertRaisesRegex(ValueError, "current durable generation"):
            reconcile_actuator_receipt(
                directive=directive,
                receipt=self.receipt(
                    directive,
                    ActuatorDeliveryStatus.APPLIED,
                ),
                state=self.s,
                ledger=self.ledger,
            )

    def test_validate_reload_directive_accepts_factory_directive(self):
        directive = build_reload_directive(
            session_id="session",
            commit=self.reload_commit(),
            ledger=self.ledger,
        )
        self.assertEqual(
            directive.digest,
            validate_reload_directive(
                directive=directive,
                state=self.s,
                ledger=self.ledger,
            ),
        )

    def test_receipt_cannot_rebind_to_another_directive(self):
        directive = build_reload_directive(
            session_id="session",
            commit=self.reload_commit(),
            ledger=self.ledger,
        )
        receipt = ActuatorReceipt(
            "wrong",
            directive.digest,
            ActuatorDeliveryStatus.APPLIED,
            "provider-op-1",
            sha256(b"provider receipt").hexdigest(),
        )
        with self.assertRaisesRegex(ValueError, "directive id mismatch"):
            reconcile_actuator_receipt(
                directive=directive,
                receipt=receipt,
                state=self.s,
                ledger=self.ledger,
            )


class SubjectEffectCompositionTests(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.close()
        self.path = handle.name
        self.ledger = DriftLedger(self.path)
        self.s = state()
        self.subject = monitored_subject()
        self.ledger.register_subject_epoch(self.subject)

    def tearDown(self):
        os.unlink(self.path)

    def bound_evidence(self, turn, score):
        return (
            DriftEvidence(
                f"subject-e-{turn}",
                "d",
                score,
                EvidenceIndependence.EXTERNAL,
                (SOURCE,),
                f"subject-run-{turn}",
                self.s.digest,
                OBS,
                turn,
                self.subject.configuration_digest,
                self.subject.epoch,
            ),
        )

    def reload_commit(self):
        first = self.ledger.evaluate_and_commit(
            session_id="subject-session",
            state=self.s,
            evidence=self.bound_evidence(0, 0.0),
            observation_digest=OBS,
            turn_index=0,
            expected_generation=0,
            subject=self.subject,
        )
        self.assertEqual(Decision.STABLE, first.evaluation.decision)
        result = self.ledger.evaluate_and_commit(
            session_id="subject-session",
            state=self.s,
            evidence=self.bound_evidence(5, 1.0),
            observation_digest=OBS,
            turn_index=5,
            expected_generation=1,
            subject=self.subject,
        )
        self.assertTrue(result.evaluation.reload_required)
        return result

    def directive(self):
        return build_reload_directive(
            session_id="subject-session",
            commit=self.reload_commit(),
            ledger=self.ledger,
            subject=self.subject,
        )

    @staticmethod
    def applied_receipt(directive):
        return ActuatorReceipt(
            directive.directive_id,
            directive.digest,
            ActuatorDeliveryStatus.APPLIED,
            "subject-provider-op",
            sha256(b"subject provider receipt").hexdigest(),
        )

    def test_current_subject_generic_applied_still_requires_readback(self):
        directive = self.directive()
        result = reconcile_actuator_receipt(
            directive=directive,
            receipt=self.applied_receipt(directive),
            state=self.s,
            ledger=self.ledger,
            subject=self.subject,
        )
        self.assertEqual(
            ActuatorDisposition.READBACK_REQUIRED,
            result.disposition,
        )
        self.assertIsNone(result.acknowledgement)

    def test_superseded_subject_invalidates_existing_directive(self):
        directive = self.directive()
        successor = monitored_subject(epoch=1)
        transition = SubjectEpochTransition(
            transition_id="effect-subject-transition",
            subject_id=self.subject.subject_id,
            predecessor_epoch=0,
            predecessor_digest=self.subject.configuration_digest,
            successor_epoch=1,
            successor_digest=successor.configuration_digest,
            reason="supersede old reload directive",
        )
        self.ledger.transition_subject_epoch(
            predecessor=self.subject,
            successor=successor,
            transition=transition,
        )
        with self.assertRaisesRegex(
            StaleGenerationError,
            "epoch has been superseded",
        ):
            validate_reload_directive(
                directive=directive,
                state=self.s,
                ledger=self.ledger,
                subject=self.subject,
            )

    def test_directive_subject_digest_tamper_fails(self):
        directive = self.directive()
        forged = replace(
            directive,
            subject_digest=raw_bytes_digest(b"other-subject"),
        )
        with self.assertRaisesRegex(ValueError, "subject digest mismatch"):
            validate_reload_directive(
                directive=forged,
                state=self.s,
                ledger=self.ledger,
                subject=self.subject,
            )

    def test_directive_subject_epoch_tamper_fails(self):
        directive = self.directive()
        forged = replace(directive, subject_epoch=1)
        with self.assertRaisesRegex(ValueError, "subject epoch mismatch"):
            validate_reload_directive(
                directive=forged,
                state=self.s,
                ledger=self.ledger,
                subject=self.subject,
            )

    def test_durable_evaluation_subject_mismatch_fails(self):
        directive = self.directive()
        with sqlite3.connect(self.path) as db:
            db.execute(
                "UPDATE evaluation_events SET subject_digest=? "
                "WHERE session_id=? AND evaluation_digest=?",
                (
                    raw_bytes_digest(b"tampered-event-subject"),
                    directive.session_id,
                    directive.evaluation_digest,
                ),
            )
        with self.assertRaisesRegex(
            ValueError,
            "durable reload-required evaluation",
        ):
            validate_reload_directive(
                directive=directive,
                state=self.s,
                ledger=self.ledger,
                subject=self.subject,
            )

    def test_durable_session_subject_mismatch_fails(self):
        directive = self.directive()
        with sqlite3.connect(self.path) as db:
            db.execute(
                "UPDATE sessions SET subject_epoch=? WHERE session_id=?",
                (9, directive.session_id),
            )
        with self.assertRaisesRegex(
            ValueError,
            "current session subject epoch mismatch",
        ):
            validate_reload_directive(
                directive=directive,
                state=self.s,
                ledger=self.ledger,
                subject=self.subject,
            )

    def test_subject_bound_directive_requires_subject_readback(self):
        directive = self.directive()
        with self.assertRaisesRegex(ValueError, "subject digest mismatch"):
            validate_reload_directive(
                directive=directive,
                state=self.s,
                ledger=self.ledger,
            )

    def test_legacy_v1_directive_rejects_nonnull_subject(self):
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.close()
        try:
            ledger = DriftLedger(handle.name)
            first = ledger.evaluate_and_commit(
                session_id="legacy",
                state=self.s,
                evidence=evidence(self.s, 0, 0.0),
                observation_digest=OBS,
                turn_index=0,
                expected_generation=0,
            )
            self.assertEqual(Decision.STABLE, first.evaluation.decision)
            reload_commit = ledger.evaluate_and_commit(
                session_id="legacy",
                state=self.s,
                evidence=evidence(self.s, 5, 1.0),
                observation_digest=OBS,
                turn_index=5,
                expected_generation=1,
            )
            directive = build_reload_directive(
                session_id="legacy",
                commit=reload_commit,
                ledger=ledger,
            )
            self.assertIsNone(directive.subject_digest)
            self.assertEqual(
                directive.digest,
                validate_reload_directive(
                    directive=directive,
                    state=self.s,
                    ledger=ledger,
                ),
            )
            with self.assertRaisesRegex(
                ValueError,
                "subject digest mismatch",
            ):
                validate_reload_directive(
                    directive=directive,
                    state=self.s,
                    ledger=ledger,
                    subject=self.subject,
                )
        finally:
            os.unlink(handle.name)


class BehavioralRecoveryBoundaryTests(LedgerHarness):
    def applied_ack(self):
        commit = self.reload_commit()
        directive = build_reload_directive(
            session_id="session",
            commit=commit,
            ledger=self.ledger,
        )
        external = reconcile_actuator_receipt(
            directive=directive,
            receipt=ActuatorReceipt(
                directive.directive_id,
                directive.digest,
                ActuatorDeliveryStatus.APPLIED,
                "provider-op-1",
                sha256(b"provider receipt").hexdigest(),
            ),
            state=self.s,
            ledger=self.ledger,
        )
        self.assertEqual(
            ActuatorDisposition.READBACK_REQUIRED,
            external.disposition,
        )
        self.assertIsNone(external.acknowledgement)

        # Recovery tests begin after independently established effect proof.
        # The ledger validates durable evaluation/currentness provenance but does
        # not itself prove provider application.
        ack = ReloadAcknowledgement(
            "externally-verified-effect:provider-op-1",
            directive.evaluation_digest,
            directive.state_digest,
            directive.turn_index,
        )
        result = self.ledger.acknowledge_reload(
            session_id="session",
            state=self.s,
            acknowledgement=ack,
            expected_generation=commit.successor_generation,
        )
        return ack, result

    def test_acknowledgement_is_not_recovery_but_later_stable_replay_can_qualify(self):
        ack, ack_result = self.applied_ack()
        replay = self.commit(
            turn=6,
            generation=ack_result.successor_generation,
            score=0.0,
        )
        receipt = qualify_post_reload_behavior(
            session_id="session",
            state=self.s,
            acknowledgement=ack,
            acknowledgement_result=ack_result,
            replay_commit=replay,
            ledger=self.ledger,
        )
        self.assertEqual("POST_RELOAD_BEHAVIORAL_REPLAY_PASS", receipt.result)
        self.assertEqual(6, receipt.replay_turn_index)
        self.assertEqual(replay.evaluation.digest, receipt.replay_evaluation_digest)

    def test_forged_replay_without_ledger_event_cannot_qualify(self):
        ack, ack_result = self.applied_ack()
        replay = self.commit(
            turn=6,
            generation=ack_result.successor_generation,
            score=0.0,
        )
        other_handle = tempfile.NamedTemporaryFile(delete=False)
        other_handle.close()
        try:
            empty_ledger = DriftLedger(other_handle.name)
            with self.assertRaisesRegex(ValueError, "ledger acknowledgement receipt"):
                qualify_post_reload_behavior(
                    session_id="session",
                    state=self.s,
                    acknowledgement=ack,
                    acknowledgement_result=ack_result,
                    replay_commit=replay,
                    ledger=empty_ledger,
                )
        finally:
            os.unlink(other_handle.name)

    def test_periodic_reload_due_does_not_negate_clean_behavioral_replay(self):
        self.s = state(max_turns=1)
        ack, ack_result = self.applied_ack()
        replay = self.commit(
            turn=6,
            generation=ack_result.successor_generation,
            score=0.0,
        )
        self.assertEqual(Decision.RELOAD, replay.evaluation.decision)
        self.assertTrue(replay.evaluation.reload_required)
        self.assertEqual(0.0, replay.evaluation.aggregate_drift)
        self.assertEqual(("periodic_reload_due",), replay.evaluation.reasons)

        receipt = qualify_post_reload_behavior(
            session_id="session",
            state=self.s,
            acknowledgement=ack,
            acknowledgement_result=ack_result,
            replay_commit=replay,
            ledger=self.ledger,
        )
        self.assertEqual(
            "POST_RELOAD_BEHAVIORAL_REPLAY_PASS",
            receipt.result,
        )

    def test_periodic_reload_does_not_hide_warn_level_behavioral_drift(self):
        self.s = state(max_turns=1)
        ack, ack_result = self.applied_ack()
        replay = self.commit(
            turn=6,
            generation=ack_result.successor_generation,
            score=0.30,
        )
        self.assertEqual(Decision.RELOAD, replay.evaluation.decision)
        self.assertTrue(replay.evaluation.reload_required)
        self.assertAlmostEqual(0.30, replay.evaluation.aggregate_drift)
        with self.assertRaisesRegex(ValueError, "DEGRADED"):
            qualify_post_reload_behavior(
                session_id="session",
                state=self.s,
                acknowledgement=ack,
                acknowledgement_result=ack_result,
                replay_commit=replay,
                ledger=self.ledger,
            )

    def test_unknown_replay_cannot_be_called_recovery(self):
        ack, ack_result = self.applied_ack()
        replay = self.commit(
            turn=6,
            generation=ack_result.successor_generation,
            rows=False,
        )
        self.assertEqual(Decision.UNKNOWN, replay.evaluation.decision)
        with self.assertRaisesRegex(ValueError, "stable bounded recovery"):
            qualify_post_reload_behavior(
                session_id="session",
                state=self.s,
                acknowledgement=ack,
                acknowledgement_result=ack_result,
                replay_commit=replay,
                ledger=self.ledger,
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
