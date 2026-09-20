from dataclasses import replace
import os
import tempfile
import unittest

from driftguard import (
    BehaviorDimension,
    Decision,
    DriftEvidence,
    DriftGuardEngine,
    EvidenceIndependence,
    MonitoredSubject,
    ProbeSource,
    SaveState,
    SourceBinding,
    StaleGenerationError,
    SubjectComponent,
)
from driftguard.external_boundary import (
    ExternalEvaluatorResponse,
    build_evaluator_request,
    build_reload_directive,
    commit_evaluator_response,
    validate_evaluator_response,
)
from driftguard.ledger import DriftLedger
from driftguard.model import raw_bytes_digest


OBS = raw_bytes_digest(b"r7-observation")
PROBE = SourceBinding("probe://r7", "v1")
REQUIRED = (
    "provider",
    "model",
    "instructions",
    "tools",
    "retrieval",
    "memory",
    "inference",
    "harness",
)


def component(component_id, version="v1", payload=None):
    payload = payload if payload is not None else f"{component_id}:{version}"
    return SubjectComponent(
        component_id=component_id,
        binding=SourceBinding(f"subject://{component_id}", version),
        digest=raw_bytes_digest(payload.encode("utf-8")),
    )


def subject(*, epoch=0, overrides=None, order=REQUIRED):
    overrides = overrides or {}
    rows = []
    for component_id in order:
        rows.append(
            overrides.get(component_id)
            or component(component_id)
        )
    return MonitoredSubject(
        subject_id="runtime-under-test",
        epoch=epoch,
        components=tuple(rows),
    )


def state():
    return SaveState(
        "r7-state",
        "1",
        "restore",
        (BehaviorDimension("d", "dimension"),),
        (
            ProbeSource(
                PROBE,
                EvidenceIndependence.SEPARATE_CONTEXT,
                ("d",),
            ),
        ),
    )


def evidence(s, monitored, *, turn=0, score=0.0, bound=True):
    return (
        DriftEvidence(
            f"e-{turn}",
            "d",
            score,
            EvidenceIndependence.SEPARATE_CONTEXT,
            (PROBE,),
            f"run-{turn}",
            s.digest,
            OBS,
            turn,
            (
                monitored.configuration_digest
                if bound and monitored is not None
                else None
            ),
            monitored.epoch if bound and monitored is not None else None,
        ),
    )


class SubjectManifestTests(unittest.TestCase):
    def test_manifest_requires_all_runtime_surfaces(self):
        with self.assertRaisesRegex(
            ValueError,
            "missing required components",
        ):
            MonitoredSubject(
                "incomplete",
                0,
                tuple(component(item) for item in REQUIRED[:-1]),
            )

    def test_component_order_does_not_change_configuration_identity(self):
        first = subject()
        second = subject(order=tuple(reversed(REQUIRED)))
        self.assertEqual(
            first.configuration_digest,
            second.configuration_digest,
        )

    def test_same_label_but_changed_component_bytes_moves_identity(self):
        first = subject()
        changed_model = component(
            "model",
            version="v1",
            payload="different-provider-observed-model-identity",
        )
        second = subject(overrides={"model": changed_model})
        self.assertNotEqual(
            first.configuration_digest,
            second.configuration_digest,
        )

    def test_epoch_segments_same_configuration_without_relabeling_it(self):
        first = subject(epoch=0)
        second = subject(epoch=1)
        self.assertEqual(
            first.configuration_digest,
            second.configuration_digest,
        )
        self.assertNotEqual(first.epoch_digest, second.epoch_digest)


class SubjectLedgerTests(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.close()
        self.path = handle.name
        self.ledger = DriftLedger(self.path)
        self.state = state()
        self.subject = subject()

    def tearDown(self):
        os.unlink(self.path)

    def commit(self, monitored, *, turn, generation, rows=None, score=0.0):
        return self.ledger.evaluate_and_commit(
            session_id="subject-session",
            state=self.state,
            evidence=(
                rows
                if rows is not None
                else evidence(
                    self.state,
                    monitored,
                    turn=turn,
                    score=score,
                )
            ),
            observation_digest=OBS,
            turn_index=turn,
            expected_generation=generation,
            subject=monitored,
        )

    def test_subject_bound_evaluation_and_receipt_round_trip(self):
        result = self.commit(self.subject, turn=0, generation=0)
        self.assertEqual(Decision.STABLE, result.evaluation.decision)
        self.assertEqual(
            self.subject.configuration_digest,
            result.evaluation.subject_digest,
        )
        self.assertEqual(0, result.evaluation.subject_epoch)
        receipt = self.ledger.evaluation_receipt(
            session_id="subject-session",
            evaluation_digest=result.evaluation.digest,
        )
        self.assertEqual(
            self.subject.configuration_digest,
            receipt.subject_digest,
        )
        self.assertEqual(0, receipt.subject_epoch)
        row = self.ledger.session_row("subject-session")
        self.assertEqual(
            self.subject.configuration_digest,
            row["subject_digest"],
        )
        self.assertEqual(0, row["subject_epoch"])

    def test_changed_model_identity_cannot_continue_same_session(self):
        self.commit(self.subject, turn=0, generation=0)
        changed = subject(
            overrides={
                "model": component(
                    "model",
                    version="v2",
                    payload="model-v2",
                )
            }
        )
        with self.assertRaisesRegex(
            StaleGenerationError,
            "monitored subject changed",
        ):
            self.commit(changed, turn=1, generation=1)

    def test_changed_tool_identity_cannot_continue_same_session(self):
        self.commit(self.subject, turn=0, generation=0)
        changed = subject(
            overrides={
                "tools": component(
                    "tools",
                    version="v2",
                    payload="tool-contract-v2",
                )
            }
        )
        with self.assertRaisesRegex(
            StaleGenerationError,
            "monitored subject changed",
        ):
            self.commit(changed, turn=1, generation=1)

    def test_epoch_change_requires_new_session_boundary(self):
        self.commit(self.subject, turn=0, generation=0)
        with self.assertRaisesRegex(
            StaleGenerationError,
            "subject epoch changed",
        ):
            self.commit(
                subject(epoch=1),
                turn=1,
                generation=1,
            )

    def test_subject_metadata_cannot_be_removed_mid_session(self):
        self.commit(self.subject, turn=0, generation=0)
        with self.assertRaisesRegex(
            StaleGenerationError,
            "monitored subject changed",
        ):
            self.commit(
                None,
                turn=1,
                generation=1,
                rows=evidence(
                    self.state,
                    None,
                    turn=1,
                    bound=False,
                ),
            )

    def test_legacy_session_cannot_late_attach_subject_identity(self):
        self.commit(
            None,
            turn=0,
            generation=0,
            rows=evidence(
                self.state,
                None,
                turn=0,
                bound=False,
            ),
        )
        with self.assertRaisesRegex(
            StaleGenerationError,
            "monitored subject changed",
        ):
            self.commit(self.subject, turn=1, generation=1)

    def test_prior_epoch_evidence_is_rejected_on_new_epoch(self):
        current = subject(epoch=1)
        stale = evidence(
            self.state,
            subject(epoch=0),
            turn=0,
        )
        result = self.ledger.evaluate_and_commit(
            session_id="new-epoch-session",
            state=self.state,
            evidence=stale,
            observation_digest=OBS,
            turn_index=0,
            expected_generation=0,
            subject=current,
        )
        self.assertEqual(Decision.UNKNOWN, result.evaluation.decision)
        self.assertIn("subject_epoch_mismatch:d", result.evaluation.reasons)

    def test_unbound_evidence_is_rejected_when_subject_is_required(self):
        rows = evidence(
            self.state,
            None,
            turn=0,
            bound=False,
        )
        result = self.commit(
            self.subject,
            turn=0,
            generation=0,
            rows=rows,
        )
        self.assertEqual(Decision.UNKNOWN, result.evaluation.decision)
        self.assertIn("subject_binding_mismatch:d", result.evaluation.reasons)


class SubjectExternalBoundaryTests(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.close()
        self.path = handle.name
        self.ledger = DriftLedger(self.path)
        self.state = state()
        self.subject = subject()

    def tearDown(self):
        os.unlink(self.path)

    def request(self, *, turn=0, generation=0):
        return build_evaluator_request(
            session_id="external-subject",
            state=self.state,
            observation_digest=OBS,
            turn_index=turn,
            expected_generation=generation,
            subject=self.subject,
        )

    def test_external_request_v3_binds_subject_configuration_and_epoch(self):
        request = self.request()
        self.assertEqual(
            "DRIFTGUARD_EXTERNAL_EVALUATOR_REQUEST_V3",
            request.payload()["schema"],
        )
        self.assertEqual(
            self.subject.configuration_digest,
            request.subject_digest,
        )
        self.assertEqual(0, request.subject_epoch)

    def test_external_response_rejects_evidence_from_other_epoch(self):
        request = self.request()
        stale = evidence(
            self.state,
            subject(epoch=1),
            turn=0,
        )
        response = ExternalEvaluatorResponse(request.digest, stale)
        with self.assertRaisesRegex(
            ValueError,
            "subject epoch mismatch",
        ):
            validate_evaluator_response(request, response)

    def test_external_commit_requires_same_subject_as_request(self):
        request = self.request()
        response = ExternalEvaluatorResponse(
            request.digest,
            evidence(self.state, self.subject, turn=0),
        )
        changed = subject(
            overrides={
                "instructions": component(
                    "instructions",
                    version="v2",
                    payload="changed-instructions",
                )
            }
        )
        with self.assertRaisesRegex(
            ValueError,
            "subject digest no longer matches",
        ):
            commit_evaluator_response(
                request=request,
                state=self.state,
                response=response,
                ledger=self.ledger,
                subject=changed,
            )

    def test_reload_directive_explicitly_binds_subject_epoch(self):
        result = self.ledger.evaluate_and_commit(
            session_id="reload-subject",
            state=self.state,
            evidence=evidence(
                self.state,
                self.subject,
                turn=0,
                score=0.90,
            ),
            observation_digest=OBS,
            turn_index=0,
            expected_generation=0,
            subject=self.subject,
        )
        directive = build_reload_directive(
            session_id="reload-subject",
            commit=result,
            ledger=self.ledger,
        )
        self.assertEqual(
            "DRIFTGUARD_RELOAD_DIRECTIVE_V2",
            directive.payload()["schema"],
        )
        self.assertEqual(
            self.subject.configuration_digest,
            directive.subject_digest,
        )
        self.assertEqual(0, directive.subject_epoch)


class SubjectEngineCompatibilityTests(unittest.TestCase):
    def test_legacy_evaluation_digest_is_unchanged_by_explicit_none(self):
        s = state()
        rows = evidence(s, None, turn=0, bound=False)
        engine = DriftGuardEngine()
        implicit = engine.evaluate(
            state=s,
            evidence=rows,
            observation_digest=OBS,
            turn_index=0,
            generation=0,
            restore_anchor_turn=0,
            last_reload_decision_turn=None,
        )
        explicit = engine.evaluate(
            state=s,
            evidence=rows,
            observation_digest=OBS,
            turn_index=0,
            generation=0,
            restore_anchor_turn=0,
            last_reload_decision_turn=None,
            subject=None,
        )
        self.assertEqual(implicit.digest, explicit.digest)


if __name__ == "__main__":
    unittest.main()
