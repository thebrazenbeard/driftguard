from dataclasses import replace
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
from driftguard.evaluator_attestation import (
    AttestedEvaluatorCommit,
    EvaluatorAttestationAlgorithm,
    EvaluatorAttestationPolicy,
    EvaluatorAttestationVerification,
    build_hmac_evaluator_attestation,
    commit_attested_evaluator_response,
    key_fingerprint_sha256,
    verify_evaluator_attestation,
)
from driftguard.external_boundary import (
    ExternalEvaluatorResponse,
    build_evaluator_request,
)
from driftguard.ledger import DriftLedger
from driftguard.model import raw_bytes_digest


SOURCE_A = SourceBinding("probe://attested-a", "v1")
SOURCE_B = SourceBinding("probe://attested-b", "v1")
OBS = raw_bytes_digest(b"attested observation")
KEY = b"a" * 32
OTHER_KEY = b"b" * 32


def state(*, include_b: bool = False) -> SaveState:
    sources = [
        ProbeSource(
            SOURCE_A,
            EvidenceIndependence.EXTERNAL,
            ("d",),
        )
    ]
    if include_b:
        sources.append(
            ProbeSource(
                SOURCE_B,
                EvidenceIndependence.EXTERNAL,
                ("d",),
            )
        )
    return SaveState(
        "attestation-state",
        "1",
        "restore governed behavior",
        (
            BehaviorDimension(
                "d",
                "attested behavior",
                min_independence=EvidenceIndependence.EXTERNAL,
            ),
        ),
        tuple(sources),
        DriftPolicy(),
    )


def evidence(
    s: SaveState,
    *,
    source: SourceBinding = SOURCE_A,
    turn: int = 0,
    score: float = 0.0,
) -> tuple[DriftEvidence, ...]:
    return (
        DriftEvidence(
            f"e-{source.ref}-{turn}-{score}",
            "d",
            score,
            EvidenceIndependence.EXTERNAL,
            (source,),
            f"run-{source.ref}-{turn}-{score}",
            s.digest,
            OBS,
            turn,
        ),
    )


def request_for(
    s: SaveState,
    *,
    generation: int = 0,
    turn: int = 0,
):
    return build_evaluator_request(
        session_id="session",
        state=s,
        observation_digest=OBS,
        turn_index=turn,
        expected_generation=generation,
    )


def response_for(request, rows) -> ExternalEvaluatorResponse:
    return ExternalEvaluatorResponse(request.digest, tuple(rows))


def policy(
    *sources: SourceBinding,
    key_id: str = "attestation-key-1",
    key_material: bytes = KEY,
    key_epoch: int = 1,
    key_fingerprint: str | None = None,
) -> EvaluatorAttestationPolicy:
    return EvaluatorAttestationPolicy(
        policy_id="attestation-policy-1",
        key_id=key_id,
        key_fingerprint_sha256=(
            key_fingerprint
            if key_fingerprint is not None
            else key_fingerprint_sha256(key_material)
        ),
        key_epoch=key_epoch,
        algorithm=EvaluatorAttestationAlgorithm.HMAC_SHA256_V1,
        authorized_sources=tuple(sources or (SOURCE_A,)),
    )


class EvaluatorAttestationTests(unittest.TestCase):
    def test_valid_hmac_attestation_binds_exact_request_response_and_policy(self):
        s = state()
        req = request_for(s)
        resp = response_for(req, evidence(s))
        pol = policy()

        attestation = build_hmac_evaluator_attestation(
            request=req,
            response=resp,
            policy=pol,
            key_material=KEY,
        )
        verification = verify_evaluator_attestation(
            request=req,
            response=resp,
            policy=pol,
            attestation=attestation,
            key_material=KEY,
        )

        self.assertEqual(req.digest, verification.request_digest)
        self.assertEqual(resp.digest, verification.response_digest)
        self.assertEqual(pol.digest, verification.policy_digest)
        self.assertEqual(pol.key_id, verification.key_id)
        self.assertEqual((SOURCE_A,), verification.covered_sources)
        self.assertEqual(
            "KEY_POSSESSION_VERIFIED_NOT_PROVIDER_HONESTY_OR_INDEPENDENCE",
            verification.verification_claim,
        )
        self.assertEqual(64, len(verification.digest))

    def test_wrong_key_fails_closed(self):
        s = state()
        req = request_for(s)
        resp = response_for(req, evidence(s))
        pol = policy()
        attestation = build_hmac_evaluator_attestation(
            request=req,
            response=resp,
            policy=pol,
            key_material=KEY,
        )

        with self.assertRaisesRegex(ValueError, "fingerprint mismatch"):
            verify_evaluator_attestation(
                request=req,
                response=resp,
                policy=pol,
                attestation=attestation,
                key_material=OTHER_KEY,
            )

    def test_weak_key_material_is_rejected(self):
        s = state()
        req = request_for(s)
        resp = response_for(req, evidence(s))
        with self.assertRaisesRegex(ValueError, "at least 32 bytes"):
            build_hmac_evaluator_attestation(
                request=req,
                response=resp,
                policy=policy(),
                key_material=b"weak",
            )

    def test_signature_cannot_be_replayed_to_different_request_generation(self):
        s = state()
        first = request_for(s, generation=0)
        first_response = response_for(first, evidence(s))
        pol = policy()
        attestation = build_hmac_evaluator_attestation(
            request=first,
            response=first_response,
            policy=pol,
            key_material=KEY,
        )

        second = request_for(s, generation=1)
        second_response = response_for(second, evidence(s))

        with self.assertRaisesRegex(ValueError, "request digest mismatch"):
            verify_evaluator_attestation(
                request=second,
                response=second_response,
                policy=pol,
                attestation=attestation,
                key_material=KEY,
            )

    def test_response_mutation_after_signing_fails_closed(self):
        s = state()
        req = request_for(s)
        original = response_for(req, evidence(s, score=0.0))
        changed = response_for(req, evidence(s, score=0.5))
        pol = policy()
        attestation = build_hmac_evaluator_attestation(
            request=req,
            response=original,
            policy=pol,
            key_material=KEY,
        )

        with self.assertRaisesRegex(ValueError, "response digest mismatch"):
            verify_evaluator_attestation(
                request=req,
                response=changed,
                policy=pol,
                attestation=attestation,
                key_material=KEY,
            )

    def test_forged_signature_is_rejected_even_when_metadata_matches(self):
        s = state()
        req = request_for(s)
        resp = response_for(req, evidence(s))
        pol = policy()
        attestation = build_hmac_evaluator_attestation(
            request=req,
            response=resp,
            policy=pol,
            key_material=KEY,
        )
        forged = replace(attestation, signature_hex="0" * 64)

        with self.assertRaisesRegex(ValueError, "signature mismatch"):
            verify_evaluator_attestation(
                request=req,
                response=resp,
                policy=pol,
                attestation=forged,
                key_material=KEY,
            )

    def test_policy_cannot_authorize_source_outside_request_contract(self):
        s = state()
        req = request_for(s)
        resp = response_for(req, evidence(s))
        bad_policy = policy(SOURCE_A, SOURCE_B)

        with self.assertRaisesRegex(ValueError, "outside request contract"):
            build_hmac_evaluator_attestation(
                request=req,
                response=resp,
                policy=bad_policy,
                key_material=KEY,
            )

    def test_response_source_must_be_covered_by_attestation_policy(self):
        s = state(include_b=True)
        req = request_for(s)
        resp = response_for(req, evidence(s, source=SOURCE_B))
        only_a = policy(SOURCE_A)

        with self.assertRaisesRegex(ValueError, "does not authorize every"):
            build_hmac_evaluator_attestation(
                request=req,
                response=resp,
                policy=only_a,
                key_material=KEY,
            )

    def test_policy_digest_moves_with_key_identity_fingerprint_and_epoch(self):
        base = policy(SOURCE_A, key_id="key-a", key_material=KEY, key_epoch=1)
        renamed = policy(SOURCE_A, key_id="key-b", key_material=KEY, key_epoch=1)
        rotated = policy(
            SOURCE_A,
            key_id="key-a",
            key_material=OTHER_KEY,
            key_epoch=2,
        )
        epoch_only = policy(
            SOURCE_A,
            key_id="key-a",
            key_material=KEY,
            key_epoch=2,
        )
        self.assertNotEqual(base.digest, renamed.digest)
        self.assertNotEqual(base.digest, rotated.digest)
        self.assertNotEqual(base.digest, epoch_only.digest)
        self.assertNotEqual(
            base.key_fingerprint_sha256,
            rotated.key_fingerprint_sha256,
        )

    def test_same_key_id_with_different_key_material_fails_before_signature_check(self):
        s = state()
        req = request_for(s)
        resp = response_for(req, evidence(s))
        pol = policy(key_material=KEY)
        attestation = build_hmac_evaluator_attestation(
            request=req,
            response=resp,
            policy=pol,
            key_material=KEY,
        )
        with self.assertRaisesRegex(ValueError, "fingerprint mismatch"):
            verify_evaluator_attestation(
                request=req,
                response=resp,
                policy=pol,
                attestation=attestation,
                key_material=OTHER_KEY,
            )

    def test_attestation_cannot_rebind_key_epoch(self):
        s = state()
        req = request_for(s)
        resp = response_for(req, evidence(s))
        pol = policy(key_epoch=1)
        attestation = build_hmac_evaluator_attestation(
            request=req,
            response=resp,
            policy=pol,
            key_material=KEY,
        )
        forged = replace(attestation, key_epoch=2)
        with self.assertRaisesRegex(ValueError, "key epoch mismatch"):
            verify_evaluator_attestation(
                request=req,
                response=resp,
                policy=pol,
                attestation=forged,
                key_material=KEY,
            )

    def test_policy_source_order_is_canonical(self):
        first = policy(SOURCE_A, SOURCE_B)
        second = policy(SOURCE_B, SOURCE_A)
        self.assertEqual(first.digest, second.digest)

    def test_duplicate_policy_sources_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "must be unique"):
            policy(SOURCE_A, SOURCE_A)

    def test_attestation_does_not_claim_provider_honesty_or_independence(self):
        s = state()
        req = request_for(s)
        resp = response_for(req, evidence(s))
        pol = policy()
        attestation = build_hmac_evaluator_attestation(
            request=req,
            response=resp,
            policy=pol,
            key_material=KEY,
        )
        verification = verify_evaluator_attestation(
            request=req,
            response=resp,
            policy=pol,
            attestation=attestation,
            key_material=KEY,
        )

        self.assertNotIn("PROVIDER_HONEST", verification.payload())
        self.assertFalse(hasattr(verification, "provider_honest"))
        self.assertFalse(hasattr(verification, "independence_proven"))

    def test_verification_object_cannot_be_directly_constructed(self):
        with self.assertRaisesRegex(ValueError, "must come from verifier"):
            EvaluatorAttestationVerification(
                session_id="session",
                state_digest="0" * 64,
                observation_digest="1" * 64,
                turn_index=0,
                generation_before=0,
                evidence_digest="2" * 64,
                request_digest="3" * 64,
                response_digest="4" * 64,
                policy_digest="5" * 64,
                key_id="key",
                key_fingerprint_sha256="4" * 64,
                key_epoch=1,
                algorithm=EvaluatorAttestationAlgorithm.HMAC_SHA256_V1,
                signature_sha256="5" * 64,
                covered_sources=(SOURCE_A,),
            )

    def test_attested_commit_cannot_be_directly_constructed(self):
        s = state()
        req = request_for(s)
        resp = response_for(req, evidence(s))
        pol = policy()
        attestation = build_hmac_evaluator_attestation(
            request=req,
            response=resp,
            policy=pol,
            key_material=KEY,
        )
        verification = verify_evaluator_attestation(
            request=req,
            response=resp,
            policy=pol,
            attestation=attestation,
            key_material=KEY,
        )
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.close()
        try:
            ledger = DriftLedger(handle.name)
            from driftguard.external_boundary import commit_evaluator_response

            commit = commit_evaluator_response(
                request=req,
                state=s,
                response=resp,
                ledger=ledger,
            )
            receipt = ledger._record_verified_evaluator_attestation(
                evaluation_digest=commit.evaluation.digest,
                verification=verification,
            )
            with self.assertRaisesRegex(ValueError, "durable commit path"):
                AttestedEvaluatorCommit(
                    commit=commit,
                    attestation=verification,
                    durable_receipt=receipt,
                )
        finally:
            os.unlink(handle.name)

    def test_attested_commit_preserves_existing_ledger_admission(self):
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.close()
        try:
            ledger = DriftLedger(handle.name)
            s = state()
            req = request_for(s)
            resp = response_for(req, evidence(s))
            pol = policy()
            attestation = build_hmac_evaluator_attestation(
                request=req,
                response=resp,
                policy=pol,
                key_material=KEY,
            )

            result = commit_attested_evaluator_response(
                request=req,
                state=s,
                response=resp,
                policy=pol,
                attestation=attestation,
                key_material=KEY,
                ledger=ledger,
            )

            self.assertEqual(1, result.commit.successor_generation)
            self.assertEqual(req.digest, result.attestation.request_digest)
            self.assertEqual(
                "STRUCTURAL_EVALUATION_COMMIT_PLUS_DURABLE_KEY_POSSESSION_VERIFICATION",
                result.commit_claim,
            )
            row = ledger.session_row("session")
            self.assertEqual(1, row["generation"])
            self.assertEqual(
                result.commit.evaluation.digest,
                row["last_evaluation_digest"],
            )
            self.assertEqual(
                result.attestation.digest,
                result.durable_receipt.verification_digest,
            )
            self.assertEqual(
                result.commit.evaluation.digest,
                result.durable_receipt.evaluation_digest,
            )
            self.assertEqual(
                pol.key_fingerprint_sha256,
                result.durable_receipt.key_fingerprint_sha256,
            )
            self.assertEqual(
                pol.key_epoch,
                result.durable_receipt.key_epoch,
            )

            reopened = DriftLedger(handle.name)
            readback = reopened.evaluator_attestation_receipt(
                session_id="session",
                evaluation_digest=result.commit.evaluation.digest,
            )
            self.assertEqual(result.durable_receipt, readback)
        finally:
            os.unlink(handle.name)


    def test_ordinary_evaluator_commit_has_no_attestation_receipt(self):
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.close()
        try:
            ledger = DriftLedger(handle.name)
            s = state()
            req = request_for(s)
            resp = response_for(req, evidence(s))
            from driftguard.external_boundary import commit_evaluator_response

            commit = commit_evaluator_response(
                request=req,
                state=s,
                response=resp,
                ledger=ledger,
            )
            self.assertIsNone(
                ledger.evaluator_attestation_receipt(
                    session_id="session",
                    evaluation_digest=commit.evaluation.digest,
                )
            )
        finally:
            os.unlink(handle.name)

    def test_free_form_public_attestation_writer_is_absent(self):
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.close()
        try:
            ledger = DriftLedger(handle.name)
            self.assertFalse(hasattr(ledger, "record_evaluator_attestation"))
        finally:
            os.unlink(handle.name)

    def test_verified_attestation_cannot_be_rebound_for_same_evaluation(self):
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.close()
        try:
            ledger = DriftLedger(handle.name)
            s = state()
            req = request_for(s)
            resp = response_for(req, evidence(s))
            first_policy = policy(
                key_id="key-a",
                key_material=KEY,
                key_epoch=1,
            )
            first_attestation = build_hmac_evaluator_attestation(
                request=req,
                response=resp,
                policy=first_policy,
                key_material=KEY,
            )
            result = commit_attested_evaluator_response(
                request=req,
                state=s,
                response=resp,
                policy=first_policy,
                attestation=first_attestation,
                key_material=KEY,
                ledger=ledger,
            )

            second_policy = policy(
                key_id="key-b",
                key_material=OTHER_KEY,
                key_epoch=2,
            )
            second_attestation = build_hmac_evaluator_attestation(
                request=req,
                response=resp,
                policy=second_policy,
                key_material=OTHER_KEY,
            )
            second_verification = verify_evaluator_attestation(
                request=req,
                response=resp,
                policy=second_policy,
                attestation=second_attestation,
                key_material=OTHER_KEY,
            )
            with self.assertRaisesRegex(ValueError, "diverges"):
                ledger._record_verified_evaluator_attestation(
                    evaluation_digest=result.commit.evaluation.digest,
                    verification=second_verification,
                )
        finally:
            os.unlink(handle.name)


if __name__ == "__main__":
    unittest.main()
