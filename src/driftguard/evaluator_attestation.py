"""Optional evaluator-response authentication for DriftGuard.

This layer authenticates an exact external evaluator request/response subject
against a governed key policy.  V1 uses HMAC-SHA256 as a dependency-free
reference mechanism.

A successful verification proves only possession of the configured key for the
exact signed subject.  It does not prove provider honesty, evaluator
independence, model identity, or semantic correctness.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
import hmac
import json
from typing import Any

from .external_boundary import (
    ExternalEvaluatorRequest,
    ExternalEvaluatorResponse,
    commit_evaluator_response,
    validate_evaluator_response,
)
from .ledger import (
    CommitResult,
    DriftLedger,
    EvaluatorAttestationEventReceipt,
)
from .model import SaveState, SourceBinding, canonical_digest, require_sha256_digest


def _nonempty(value: Any, label: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{label} must be a non-empty exact string")
    return value


def _require_key_material(value: bytes) -> bytes:
    if type(value) is not bytes:
        raise ValueError("key material must be exact bytes")
    if len(value) < 32:
        raise ValueError("key material must contain at least 32 bytes")
    return value


def key_fingerprint_sha256(key_material: bytes) -> str:
    key = _require_key_material(key_material)
    return sha256(key).hexdigest()


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


class EvaluatorAttestationAlgorithm(StrEnum):
    HMAC_SHA256_V1 = "HMAC_SHA256_V1"


_VERIFIED_ATTESTATION_TOKEN = object()
_ATTESTED_COMMIT_TOKEN = object()


@dataclass(frozen=True)
class EvaluatorAttestationPolicy:
    policy_id: str
    key_id: str
    key_fingerprint_sha256: str
    key_epoch: int
    algorithm: EvaluatorAttestationAlgorithm
    authorized_sources: tuple[SourceBinding, ...]
    policy_claim: str = (
        "KEY_POLICY_INPUT_ONLY_NOT_PROVIDER_OR_EVALUATOR_AUTHORITY"
    )

    def __post_init__(self) -> None:
        _nonempty(self.policy_id, "policy_id")
        _nonempty(self.key_id, "key_id")
        require_sha256_digest(
            self.key_fingerprint_sha256,
            "key_fingerprint_sha256",
        )
        if (
            type(self.key_epoch) is not int
            or isinstance(self.key_epoch, bool)
            or self.key_epoch < 1
        ):
            raise ValueError("key_epoch must be a positive exact integer")
        if type(self.algorithm) is not EvaluatorAttestationAlgorithm:
            raise ValueError(
                "algorithm must be exact EvaluatorAttestationAlgorithm"
            )
        if (
            type(self.authorized_sources) is not tuple
            or not self.authorized_sources
        ):
            raise ValueError("authorized_sources must be a non-empty tuple")
        if any(
            type(item) is not SourceBinding for item in self.authorized_sources
        ):
            raise ValueError(
                "authorized_sources must contain exact SourceBinding values"
            )
        if len(self.authorized_sources) != len(set(self.authorized_sources)):
            raise ValueError("authorized_sources must be unique")
        if self.policy_claim != (
            "KEY_POLICY_INPUT_ONLY_NOT_PROVIDER_OR_EVALUATOR_AUTHORITY"
        ):
            raise ValueError("unsupported attestation policy claim")

    def payload(self) -> dict[str, Any]:
        return {
            "schema": "DRIFTGUARD_EVALUATOR_ATTESTATION_POLICY_V1",
            "policy_id": self.policy_id,
            "key_id": self.key_id,
            "key_fingerprint_sha256": self.key_fingerprint_sha256,
            "key_epoch": self.key_epoch,
            "algorithm": self.algorithm.value,
            "authorized_sources": [
                {"ref": item.ref, "version": item.version}
                for item in sorted(self.authorized_sources)
            ],
            "policy_claim": self.policy_claim,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.payload())


@dataclass(frozen=True)
class EvaluatorAttestation:
    request_digest: str
    response_digest: str
    policy_digest: str
    key_id: str
    key_fingerprint_sha256: str
    key_epoch: int
    algorithm: EvaluatorAttestationAlgorithm
    signature_hex: str
    attestation_claim: str = "DETACHED_KEY_POSSESSION_TAG_ONLY"

    def __post_init__(self) -> None:
        require_sha256_digest(self.request_digest, "request_digest")
        require_sha256_digest(self.response_digest, "response_digest")
        require_sha256_digest(self.policy_digest, "policy_digest")
        _nonempty(self.key_id, "key_id")
        require_sha256_digest(
            self.key_fingerprint_sha256,
            "key_fingerprint_sha256",
        )
        if (
            type(self.key_epoch) is not int
            or isinstance(self.key_epoch, bool)
            or self.key_epoch < 1
        ):
            raise ValueError("key_epoch must be a positive exact integer")
        if type(self.algorithm) is not EvaluatorAttestationAlgorithm:
            raise ValueError(
                "algorithm must be exact EvaluatorAttestationAlgorithm"
            )
        require_sha256_digest(self.signature_hex, "signature_hex")
        if self.attestation_claim != "DETACHED_KEY_POSSESSION_TAG_ONLY":
            raise ValueError("unsupported evaluator attestation claim")

    def subject_payload(self) -> dict[str, Any]:
        return {
            "schema": "DRIFTGUARD_EVALUATOR_ATTESTATION_SUBJECT_V1",
            "request_digest": self.request_digest,
            "response_digest": self.response_digest,
            "policy_digest": self.policy_digest,
            "key_id": self.key_id,
            "key_fingerprint_sha256": self.key_fingerprint_sha256,
            "key_epoch": self.key_epoch,
            "algorithm": self.algorithm.value,
        }


@dataclass(frozen=True, init=False)
class EvaluatorAttestationVerification:
    request_digest: str
    response_digest: str
    policy_digest: str
    key_id: str
    key_fingerprint_sha256: str
    key_epoch: int
    algorithm: EvaluatorAttestationAlgorithm
    signature_sha256: str
    covered_sources: tuple[SourceBinding, ...]
    verification_claim: str

    def __init__(
        self,
        *,
        request_digest: str,
        response_digest: str,
        policy_digest: str,
        key_id: str,
        key_fingerprint_sha256: str,
        key_epoch: int,
        algorithm: EvaluatorAttestationAlgorithm,
        signature_sha256: str,
        covered_sources: tuple[SourceBinding, ...],
        _verified_token: object | None = None,
    ) -> None:
        if _verified_token is not _VERIFIED_ATTESTATION_TOKEN:
            raise ValueError(
                "EvaluatorAttestationVerification must come from verifier"
            )
        object.__setattr__(self, "request_digest", request_digest)
        object.__setattr__(self, "response_digest", response_digest)
        object.__setattr__(self, "policy_digest", policy_digest)
        object.__setattr__(self, "key_id", key_id)
        object.__setattr__(
            self,
            "key_fingerprint_sha256",
            key_fingerprint_sha256,
        )
        object.__setattr__(self, "key_epoch", key_epoch)
        object.__setattr__(self, "algorithm", algorithm)
        object.__setattr__(self, "signature_sha256", signature_sha256)
        object.__setattr__(self, "covered_sources", covered_sources)
        object.__setattr__(
            self,
            "verification_claim",
            "KEY_POSSESSION_VERIFIED_NOT_PROVIDER_HONESTY_OR_INDEPENDENCE",
        )
        self.__post_init__()

    def __post_init__(self) -> None:
        for value, label in (
            (self.request_digest, "request_digest"),
            (self.response_digest, "response_digest"),
            (self.policy_digest, "policy_digest"),
            (self.signature_sha256, "signature_sha256"),
        ):
            require_sha256_digest(value, label)
        _nonempty(self.key_id, "key_id")
        require_sha256_digest(
            self.key_fingerprint_sha256,
            "key_fingerprint_sha256",
        )
        if (
            type(self.key_epoch) is not int
            or isinstance(self.key_epoch, bool)
            or self.key_epoch < 1
        ):
            raise ValueError("key_epoch must be a positive exact integer")
        if type(self.algorithm) is not EvaluatorAttestationAlgorithm:
            raise ValueError(
                "algorithm must be exact EvaluatorAttestationAlgorithm"
            )
        if type(self.covered_sources) is not tuple:
            raise ValueError("covered_sources must be an exact tuple")
        if any(type(item) is not SourceBinding for item in self.covered_sources):
            raise ValueError(
                "covered_sources must contain exact SourceBinding values"
            )
        if len(self.covered_sources) != len(set(self.covered_sources)):
            raise ValueError("covered_sources must be unique")
        if self.verification_claim != (
            "KEY_POSSESSION_VERIFIED_NOT_PROVIDER_HONESTY_OR_INDEPENDENCE"
        ):
            raise ValueError("unsupported attestation verification claim")

    def payload(self) -> dict[str, Any]:
        return {
            "schema": "DRIFTGUARD_EVALUATOR_ATTESTATION_VERIFICATION_V1",
            "request_digest": self.request_digest,
            "response_digest": self.response_digest,
            "policy_digest": self.policy_digest,
            "key_id": self.key_id,
            "key_fingerprint_sha256": self.key_fingerprint_sha256,
            "key_epoch": self.key_epoch,
            "algorithm": self.algorithm.value,
            "signature_sha256": self.signature_sha256,
            "covered_sources": [
                {"ref": item.ref, "version": item.version}
                for item in sorted(self.covered_sources)
            ],
            "verification_claim": self.verification_claim,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.payload())


@dataclass(frozen=True, init=False)
class AttestedEvaluatorCommit:
    commit: CommitResult
    attestation: EvaluatorAttestationVerification
    durable_receipt: EvaluatorAttestationEventReceipt
    commit_claim: str

    def __init__(
        self,
        *,
        commit: CommitResult,
        attestation: EvaluatorAttestationVerification,
        durable_receipt: EvaluatorAttestationEventReceipt,
        _commit_token: object | None = None,
    ) -> None:
        if _commit_token is not _ATTESTED_COMMIT_TOKEN:
            raise ValueError(
                "AttestedEvaluatorCommit must come from durable commit path"
            )
        object.__setattr__(self, "commit", commit)
        object.__setattr__(self, "attestation", attestation)
        object.__setattr__(self, "durable_receipt", durable_receipt)
        object.__setattr__(
            self,
            "commit_claim",
            "STRUCTURAL_EVALUATION_COMMIT_PLUS_DURABLE_KEY_POSSESSION_VERIFICATION",
        )
        self.__post_init__()

    def __post_init__(self) -> None:
        if type(self.commit) is not CommitResult:
            raise ValueError("commit must be exact CommitResult")
        if type(self.attestation) is not EvaluatorAttestationVerification:
            raise ValueError(
                "attestation must be exact EvaluatorAttestationVerification"
            )
        if type(self.durable_receipt) is not EvaluatorAttestationEventReceipt:
            raise ValueError(
                "durable_receipt must be exact EvaluatorAttestationEventReceipt"
            )
        if self.durable_receipt.evaluation_digest != self.commit.evaluation.digest:
            raise ValueError("durable attestation evaluation mismatch")
        if self.durable_receipt.verification_digest != self.attestation.digest:
            raise ValueError("durable attestation verification mismatch")
        if self.durable_receipt.request_digest != self.attestation.request_digest:
            raise ValueError("durable attestation request mismatch")
        if self.durable_receipt.response_digest != self.attestation.response_digest:
            raise ValueError("durable attestation response mismatch")
        if self.durable_receipt.policy_digest != self.attestation.policy_digest:
            raise ValueError("durable attestation policy mismatch")
        if self.durable_receipt.key_id != self.attestation.key_id:
            raise ValueError("durable attestation key id mismatch")
        if (
            self.durable_receipt.key_fingerprint_sha256
            != self.attestation.key_fingerprint_sha256
        ):
            raise ValueError("durable attestation key fingerprint mismatch")
        if self.durable_receipt.key_epoch != self.attestation.key_epoch:
            raise ValueError("durable attestation key epoch mismatch")
        if self.durable_receipt.algorithm != self.attestation.algorithm.value:
            raise ValueError("durable attestation algorithm mismatch")
        if (
            self.durable_receipt.signature_sha256
            != self.attestation.signature_sha256
        ):
            raise ValueError("durable attestation signature mismatch")
        if self.durable_receipt.covered_sources != self.attestation.covered_sources:
            raise ValueError("durable attestation covered-source mismatch")
        if self.commit_claim != (
            "STRUCTURAL_EVALUATION_COMMIT_PLUS_DURABLE_KEY_POSSESSION_VERIFICATION"
        ):
            raise ValueError("unsupported attested commit claim")


def _response_sources(
    response: ExternalEvaluatorResponse,
) -> tuple[SourceBinding, ...]:
    return tuple(
        sorted(
            {
                source
                for evidence in response.evidence
                for source in evidence.source_bindings
            }
        )
    )


def _attestation_subject(
    *,
    request: ExternalEvaluatorRequest,
    response: ExternalEvaluatorResponse,
    policy: EvaluatorAttestationPolicy,
) -> dict[str, Any]:
    return {
        "schema": "DRIFTGUARD_EVALUATOR_ATTESTATION_SUBJECT_V1",
        "request_digest": request.digest,
        "response_digest": response.digest,
        "policy_digest": policy.digest,
        "key_id": policy.key_id,
        "key_fingerprint_sha256": policy.key_fingerprint_sha256,
        "key_epoch": policy.key_epoch,
        "algorithm": policy.algorithm.value,
    }


def _verify_policy_coverage(
    *,
    request: ExternalEvaluatorRequest,
    response: ExternalEvaluatorResponse,
    policy: EvaluatorAttestationPolicy,
) -> tuple[SourceBinding, ...]:
    validate_evaluator_response(request, response)
    response_sources = _response_sources(response)
    authorized = set(policy.authorized_sources)
    if not set(response_sources).issubset(authorized):
        raise ValueError(
            "evaluator attestation policy does not authorize every response source"
        )
    requested = {item.binding for item in request.probe_contract}
    if not authorized.issubset(requested):
        raise ValueError(
            "evaluator attestation policy contains source outside request contract"
        )
    return response_sources


def build_hmac_evaluator_attestation(
    *,
    request: ExternalEvaluatorRequest,
    response: ExternalEvaluatorResponse,
    policy: EvaluatorAttestationPolicy,
    key_material: bytes,
) -> EvaluatorAttestation:
    if type(request) is not ExternalEvaluatorRequest:
        raise ValueError("request must be exact ExternalEvaluatorRequest")
    if type(response) is not ExternalEvaluatorResponse:
        raise ValueError("response must be exact ExternalEvaluatorResponse")
    if type(policy) is not EvaluatorAttestationPolicy:
        raise ValueError("policy must be exact EvaluatorAttestationPolicy")
    key = _require_key_material(key_material)
    observed_fingerprint = key_fingerprint_sha256(key)
    if observed_fingerprint != policy.key_fingerprint_sha256:
        raise ValueError("key material fingerprint mismatch")
    _verify_policy_coverage(
        request=request,
        response=response,
        policy=policy,
    )
    subject = _attestation_subject(
        request=request,
        response=response,
        policy=policy,
    )
    signature = hmac.new(
        key,
        _canonical_bytes(subject),
        sha256,
    ).hexdigest()
    return EvaluatorAttestation(
        request_digest=request.digest,
        response_digest=response.digest,
        policy_digest=policy.digest,
        key_id=policy.key_id,
        key_fingerprint_sha256=policy.key_fingerprint_sha256,
        key_epoch=policy.key_epoch,
        algorithm=policy.algorithm,
        signature_hex=signature,
    )


def verify_evaluator_attestation(
    *,
    request: ExternalEvaluatorRequest,
    response: ExternalEvaluatorResponse,
    policy: EvaluatorAttestationPolicy,
    attestation: EvaluatorAttestation,
    key_material: bytes,
) -> EvaluatorAttestationVerification:
    if type(request) is not ExternalEvaluatorRequest:
        raise ValueError("request must be exact ExternalEvaluatorRequest")
    if type(response) is not ExternalEvaluatorResponse:
        raise ValueError("response must be exact ExternalEvaluatorResponse")
    if type(policy) is not EvaluatorAttestationPolicy:
        raise ValueError("policy must be exact EvaluatorAttestationPolicy")
    if type(attestation) is not EvaluatorAttestation:
        raise ValueError("attestation must be exact EvaluatorAttestation")
    key = _require_key_material(key_material)
    observed_fingerprint = key_fingerprint_sha256(key)
    if observed_fingerprint != policy.key_fingerprint_sha256:
        raise ValueError("key material fingerprint mismatch")

    response_sources = _verify_policy_coverage(
        request=request,
        response=response,
        policy=policy,
    )

    if attestation.request_digest != request.digest:
        raise ValueError("evaluator attestation request digest mismatch")
    if attestation.response_digest != response.digest:
        raise ValueError("evaluator attestation response digest mismatch")
    if attestation.policy_digest != policy.digest:
        raise ValueError("evaluator attestation policy digest mismatch")
    if attestation.key_id != policy.key_id:
        raise ValueError("evaluator attestation key id mismatch")
    if attestation.key_fingerprint_sha256 != policy.key_fingerprint_sha256:
        raise ValueError("evaluator attestation key fingerprint mismatch")
    if attestation.key_epoch != policy.key_epoch:
        raise ValueError("evaluator attestation key epoch mismatch")
    if attestation.algorithm is not policy.algorithm:
        raise ValueError("evaluator attestation algorithm mismatch")

    subject = _attestation_subject(
        request=request,
        response=response,
        policy=policy,
    )
    expected = hmac.new(
        key,
        _canonical_bytes(subject),
        sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, attestation.signature_hex):
        raise ValueError("evaluator attestation signature mismatch")

    return EvaluatorAttestationVerification(
        request_digest=request.digest,
        response_digest=response.digest,
        policy_digest=policy.digest,
        key_id=policy.key_id,
        key_fingerprint_sha256=policy.key_fingerprint_sha256,
        key_epoch=policy.key_epoch,
        algorithm=policy.algorithm,
        signature_sha256=sha256(
            bytes.fromhex(attestation.signature_hex)
        ).hexdigest(),
        covered_sources=response_sources,
        _verified_token=_VERIFIED_ATTESTATION_TOKEN,
    )


def commit_attested_evaluator_response(
    *,
    request: ExternalEvaluatorRequest,
    state: SaveState,
    response: ExternalEvaluatorResponse,
    policy: EvaluatorAttestationPolicy,
    attestation: EvaluatorAttestation,
    key_material: bytes,
    ledger: DriftLedger,
) -> AttestedEvaluatorCommit:
    verification = verify_evaluator_attestation(
        request=request,
        response=response,
        policy=policy,
        attestation=attestation,
        key_material=key_material,
    )
    commit = commit_evaluator_response(
        request=request,
        state=state,
        response=response,
        ledger=ledger,
    )
    durable_receipt = ledger.record_evaluator_attestation(
        session_id=request.session_id,
        evaluation_digest=commit.evaluation.digest,
        verification_digest=verification.digest,
        request_digest=verification.request_digest,
        response_digest=verification.response_digest,
        policy_digest=verification.policy_digest,
        key_id=verification.key_id,
        key_fingerprint_sha256=verification.key_fingerprint_sha256,
        key_epoch=verification.key_epoch,
        algorithm=verification.algorithm.value,
        signature_sha256=verification.signature_sha256,
        covered_sources=verification.covered_sources,
    )
    return AttestedEvaluatorCommit(
        commit=commit,
        attestation=verification,
        durable_receipt=durable_receipt,
        _commit_token=_ATTESTED_COMMIT_TOKEN,
    )


__all__ = [
    "AttestedEvaluatorCommit",
    "EvaluatorAttestation",
    "EvaluatorAttestationAlgorithm",
    "EvaluatorAttestationPolicy",
    "EvaluatorAttestationVerification",
    "build_hmac_evaluator_attestation",
    "commit_attested_evaluator_response",
    "verify_evaluator_attestation",
]
