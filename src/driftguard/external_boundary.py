from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import Any, Iterable

from .ledger import AcknowledgementResult, CommitResult, DriftLedger
from .model import (
    Decision,
    DriftEvidence,
    ReloadAcknowledgement,
    SaveState,
    SourceBinding,
    canonical_digest,
    evidence_set_digest,
    require_sha256_digest,
)


def _nonempty(value: Any, label: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{label} must be a non-empty exact string")
    return value


@dataclass(frozen=True, order=True)
class EvaluatorProbeContract:
    source_ref: str
    source_version: str
    max_independence: str
    dimensions: tuple[str, ...]

    def __post_init__(self) -> None:
        _nonempty(self.source_ref, "source_ref")
        _nonempty(self.source_version, "source_version")
        _nonempty(self.max_independence, "max_independence")
        if type(self.dimensions) is not tuple or not self.dimensions:
            raise ValueError("dimensions must be a non-empty tuple")
        if any(type(item) is not str or not item for item in self.dimensions):
            raise ValueError("dimensions must contain non-empty exact strings")
        if len(self.dimensions) != len(set(self.dimensions)):
            raise ValueError("dimensions must be unique")

    @property
    def binding(self) -> SourceBinding:
        return SourceBinding(self.source_ref, self.source_version)

    def payload(self) -> dict[str, Any]:
        return {
            "source_ref": self.source_ref,
            "source_version": self.source_version,
            "max_independence": self.max_independence,
            "dimensions": list(self.dimensions),
        }


@dataclass(frozen=True)
class ExternalEvaluatorRequest:
    session_id: str
    state_digest: str
    observation_digest: str
    turn_index: int
    expected_generation: int
    probe_contract: tuple[EvaluatorProbeContract, ...]

    def __post_init__(self) -> None:
        _nonempty(self.session_id, "session_id")
        require_sha256_digest(self.state_digest, "state_digest")
        require_sha256_digest(self.observation_digest, "observation_digest")
        if type(self.turn_index) is not int or self.turn_index < 0:
            raise ValueError("turn_index must be a non-negative integer")
        if type(self.expected_generation) is not int or self.expected_generation < 0:
            raise ValueError("expected_generation must be a non-negative integer")
        if type(self.probe_contract) is not tuple or not self.probe_contract:
            raise ValueError("probe_contract must be a non-empty tuple")
        if any(type(item) is not EvaluatorProbeContract for item in self.probe_contract):
            raise ValueError("probe_contract values must be exact EvaluatorProbeContract")
        bindings = [item.binding for item in self.probe_contract]
        if len(bindings) != len(set(bindings)):
            raise ValueError("probe contract bindings must be unique")

    def payload(self) -> dict[str, Any]:
        return {
            "schema": "DRIFTGUARD_EXTERNAL_EVALUATOR_REQUEST_V1",
            "session_id": self.session_id,
            "state_digest": self.state_digest,
            "observation_digest": self.observation_digest,
            "turn_index": self.turn_index,
            "expected_generation": self.expected_generation,
            "probe_contract": [item.payload() for item in self.probe_contract],
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.payload())

    @property
    def request_id(self) -> str:
        return f"driftguard-evaluator:{self.digest}"


def build_evaluator_request(
    *,
    session_id: str,
    state: SaveState,
    observation_digest: str,
    turn_index: int,
    expected_generation: int,
) -> ExternalEvaluatorRequest:
    if type(state) is not SaveState:
        raise ValueError("state must be exact SaveState")
    contracts = tuple(
        sorted(
            (
                EvaluatorProbeContract(
                    source.binding.ref,
                    source.binding.version,
                    source.max_independence.name,
                    source.dimensions,
                )
                for source in state.probe_sources
            ),
            key=lambda item: (item.source_ref, item.source_version),
        )
    )
    return ExternalEvaluatorRequest(
        session_id=session_id,
        state_digest=state.digest,
        observation_digest=observation_digest,
        turn_index=turn_index,
        expected_generation=expected_generation,
        probe_contract=contracts,
    )


def validate_evaluator_response(
    request: ExternalEvaluatorRequest,
    evidence: Iterable[DriftEvidence],
) -> str:
    if type(request) is not ExternalEvaluatorRequest:
        raise ValueError("request must be exact ExternalEvaluatorRequest")
    rows = tuple(evidence)
    allowed_bindings = {item.binding for item in request.probe_contract}
    for item in rows:
        if type(item) is not DriftEvidence:
            raise ValueError("evidence must contain exact DriftEvidence values")
        if item.state_digest != request.state_digest:
            raise ValueError("external evidence state digest mismatch")
        if item.observation_digest != request.observation_digest:
            raise ValueError("external evidence observation digest mismatch")
        if item.turn_index != request.turn_index:
            raise ValueError("external evidence turn mismatch")
        if not set(item.source_bindings).issubset(allowed_bindings):
            raise ValueError("external evidence contains unrequested source binding")
    return evidence_set_digest(rows)


@dataclass(frozen=True)
class ReloadDirective:
    session_id: str
    evaluation_digest: str
    state_digest: str
    turn_index: int
    expected_generation: int
    restore_packet: str
    restore_packet_sha256: str

    def __post_init__(self) -> None:
        _nonempty(self.session_id, "session_id")
        require_sha256_digest(self.evaluation_digest, "evaluation_digest")
        require_sha256_digest(self.state_digest, "state_digest")
        if type(self.turn_index) is not int or self.turn_index < 0:
            raise ValueError("turn_index must be a non-negative integer")
        if type(self.expected_generation) is not int or self.expected_generation < 0:
            raise ValueError("expected_generation must be a non-negative integer")
        _nonempty(self.restore_packet, "restore_packet")
        require_sha256_digest(self.restore_packet_sha256, "restore_packet_sha256")
        actual = sha256(self.restore_packet.encode("utf-8")).hexdigest()
        if actual != self.restore_packet_sha256:
            raise ValueError("restore packet digest mismatch")

    def payload(self) -> dict[str, Any]:
        return {
            "schema": "DRIFTGUARD_RELOAD_DIRECTIVE_V1",
            "session_id": self.session_id,
            "evaluation_digest": self.evaluation_digest,
            "state_digest": self.state_digest,
            "turn_index": self.turn_index,
            "expected_generation": self.expected_generation,
            "restore_packet": self.restore_packet,
            "restore_packet_sha256": self.restore_packet_sha256,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.payload())

    @property
    def directive_id(self) -> str:
        return f"driftguard-reload:{self.digest}"


def build_reload_directive(
    *,
    session_id: str,
    commit: CommitResult,
    ledger: DriftLedger,
) -> ReloadDirective:
    if type(commit) is not CommitResult:
        raise ValueError("commit must be exact CommitResult")
    if type(ledger) is not DriftLedger:
        raise ValueError("ledger must be exact DriftLedger")
    evaluation = commit.evaluation
    if evaluation.reload_required is not True:
        raise ValueError("reload directive requires reload-required evaluation")
    if type(evaluation.restore_packet) is not str or not evaluation.restore_packet:
        raise ValueError("reload-required evaluation is missing restore packet")
    if commit.successor_generation != evaluation.generation + 1:
        raise ValueError("commit generation does not bind evaluation generation")
    receipt = ledger.evaluation_receipt(
        session_id=session_id,
        evaluation_digest=evaluation.digest,
    )
    if receipt is None:
        raise ValueError("reload directive requires durable ledger evaluation receipt")
    if (
        receipt.generation_before != evaluation.generation
        or receipt.generation_after != commit.successor_generation
        or receipt.turn_index != evaluation.turn_index
        or receipt.state_digest != evaluation.state_digest
        or receipt.observation_digest != evaluation.observation_digest
        or receipt.evidence_digest != evaluation.evidence_digest
        or receipt.evaluation_digest != evaluation.digest
        or receipt.decision is not evaluation.decision
        or receipt.reload_required is not True
    ):
        raise ValueError("reload directive commit does not match durable ledger receipt")
    return ReloadDirective(
        session_id=session_id,
        evaluation_digest=evaluation.digest,
        state_digest=evaluation.state_digest,
        turn_index=evaluation.turn_index,
        expected_generation=commit.successor_generation,
        restore_packet=evaluation.restore_packet,
        restore_packet_sha256=sha256(
            evaluation.restore_packet.encode("utf-8")
        ).hexdigest(),
    )


class ActuatorDeliveryStatus(StrEnum):
    APPLIED = "APPLIED"
    NOT_APPLIED = "NOT_APPLIED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ActuatorReceipt:
    directive_id: str
    directive_digest: str
    status: ActuatorDeliveryStatus
    provider_operation_id: str
    provider_receipt_sha256: str

    def __post_init__(self) -> None:
        _nonempty(self.directive_id, "directive_id")
        require_sha256_digest(self.directive_digest, "directive_digest")
        if type(self.status) is not ActuatorDeliveryStatus:
            raise ValueError("status must be exact ActuatorDeliveryStatus")
        _nonempty(self.provider_operation_id, "provider_operation_id")
        require_sha256_digest(
            self.provider_receipt_sha256, "provider_receipt_sha256"
        )

    def payload(self) -> dict[str, Any]:
        return {
            "schema": "DRIFTGUARD_ACTUATOR_RECEIPT_V1",
            "directive_id": self.directive_id,
            "directive_digest": self.directive_digest,
            "status": self.status.value,
            "provider_operation_id": self.provider_operation_id,
            "provider_receipt_sha256": self.provider_receipt_sha256,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.payload())


class ActuatorDisposition(StrEnum):
    ACKNOWLEDGE = "ACKNOWLEDGE"
    RETRY_ALLOWED = "RETRY_ALLOWED"
    READBACK_REQUIRED = "READBACK_REQUIRED"


@dataclass(frozen=True)
class ActuatorReconciliation:
    disposition: ActuatorDisposition
    acknowledgement: ReloadAcknowledgement | None


def reconcile_actuator_receipt(
    *,
    directive: ReloadDirective,
    receipt: ActuatorReceipt,
) -> ActuatorReconciliation:
    if type(directive) is not ReloadDirective:
        raise ValueError("directive must be exact ReloadDirective")
    if type(receipt) is not ActuatorReceipt:
        raise ValueError("receipt must be exact ActuatorReceipt")
    if receipt.directive_id != directive.directive_id:
        raise ValueError("actuator receipt directive id mismatch")
    if receipt.directive_digest != directive.digest:
        raise ValueError("actuator receipt directive digest mismatch")

    if receipt.status is ActuatorDeliveryStatus.UNKNOWN:
        return ActuatorReconciliation(
            ActuatorDisposition.READBACK_REQUIRED,
            None,
        )
    if receipt.status is ActuatorDeliveryStatus.NOT_APPLIED:
        return ActuatorReconciliation(
            ActuatorDisposition.RETRY_ALLOWED,
            None,
        )

    ack_id = "actuator:" + canonical_digest(
        {
            "directive_digest": directive.digest,
            "provider_operation_id": receipt.provider_operation_id,
            "provider_receipt_sha256": receipt.provider_receipt_sha256,
        }
    )
    return ActuatorReconciliation(
        ActuatorDisposition.ACKNOWLEDGE,
        ReloadAcknowledgement(
            ack_id=ack_id,
            evaluation_digest=directive.evaluation_digest,
            state_digest=directive.state_digest,
            turn_index=directive.turn_index,
        ),
    )


@dataclass(frozen=True)
class BehavioralRecoveryReceipt:
    ack_id: str
    acknowledged_evaluation_digest: str
    state_digest: str
    acknowledgement_turn_index: int
    replay_evaluation_digest: str
    replay_observation_digest: str
    replay_evidence_digest: str
    replay_turn_index: int
    replay_generation: int
    result: str = "POST_RELOAD_BEHAVIORAL_REPLAY_PASS"

    def __post_init__(self) -> None:
        _nonempty(self.ack_id, "ack_id")
        require_sha256_digest(
            self.acknowledged_evaluation_digest,
            "acknowledged_evaluation_digest",
        )
        require_sha256_digest(self.state_digest, "state_digest")
        require_sha256_digest(
            self.replay_evaluation_digest, "replay_evaluation_digest"
        )
        require_sha256_digest(
            self.replay_observation_digest, "replay_observation_digest"
        )
        require_sha256_digest(
            self.replay_evidence_digest, "replay_evidence_digest"
        )
        if (
            type(self.acknowledgement_turn_index) is not int
            or self.acknowledgement_turn_index < 0
        ):
            raise ValueError("acknowledgement_turn_index must be non-negative int")
        if type(self.replay_turn_index) is not int or self.replay_turn_index < 0:
            raise ValueError("replay_turn_index must be non-negative int")
        if self.replay_turn_index <= self.acknowledgement_turn_index:
            raise ValueError("behavioral replay must occur after acknowledgement turn")
        if type(self.replay_generation) is not int or self.replay_generation < 0:
            raise ValueError("replay_generation must be non-negative int")
        if self.result != "POST_RELOAD_BEHAVIORAL_REPLAY_PASS":
            raise ValueError("unsupported behavioral recovery result")

    def payload(self) -> dict[str, Any]:
        return {
            "schema": "DRIFTGUARD_BEHAVIORAL_RECOVERY_RECEIPT_V1",
            "ack_id": self.ack_id,
            "acknowledged_evaluation_digest": self.acknowledged_evaluation_digest,
            "state_digest": self.state_digest,
            "acknowledgement_turn_index": self.acknowledgement_turn_index,
            "replay_evaluation_digest": self.replay_evaluation_digest,
            "replay_observation_digest": self.replay_observation_digest,
            "replay_evidence_digest": self.replay_evidence_digest,
            "replay_turn_index": self.replay_turn_index,
            "replay_generation": self.replay_generation,
            "result": self.result,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.payload())


def qualify_post_reload_behavior(
    *,
    session_id: str,
    acknowledgement: ReloadAcknowledgement,
    acknowledgement_result: AcknowledgementResult,
    replay_commit: CommitResult,
    ledger: DriftLedger,
) -> BehavioralRecoveryReceipt:
    if type(acknowledgement) is not ReloadAcknowledgement:
        raise ValueError("acknowledgement must be exact ReloadAcknowledgement")
    if type(acknowledgement_result) is not AcknowledgementResult:
        raise ValueError("acknowledgement_result must be exact AcknowledgementResult")
    if type(replay_commit) is not CommitResult:
        raise ValueError("replay_commit must be exact CommitResult")
    if type(ledger) is not DriftLedger:
        raise ValueError("ledger must be exact DriftLedger")
    if type(session_id) is not str or not session_id.strip():
        raise ValueError("session_id must be a non-empty exact string")
    if acknowledgement_result.ack_id != acknowledgement.ack_id:
        raise ValueError("acknowledgement/result id mismatch")
    if acknowledgement_result.restore_anchor_turn != acknowledgement.turn_index:
        raise ValueError("acknowledgement/result turn mismatch")

    ack_receipt = ledger.acknowledgement_receipt(ack_id=acknowledgement.ack_id)
    if ack_receipt is None:
        raise ValueError("behavioral recovery requires durable ledger acknowledgement receipt")
    if (
        ack_receipt.session_id != session_id
        or ack_receipt.generation_after != acknowledgement_result.successor_generation
        or ack_receipt.evaluation_digest != acknowledgement.evaluation_digest
        or ack_receipt.state_digest != acknowledgement.state_digest
        or ack_receipt.turn_index != acknowledgement.turn_index
    ):
        raise ValueError("acknowledgement does not match durable ledger receipt")

    replay = replay_commit.evaluation
    replay_receipt = ledger.evaluation_receipt(
        session_id=session_id,
        evaluation_digest=replay.digest,
    )
    if replay_receipt is None:
        raise ValueError("behavioral recovery requires durable ledger replay receipt")
    if (
        replay_receipt.generation_before != replay.generation
        or replay_receipt.generation_after != replay_commit.successor_generation
        or replay_receipt.turn_index != replay.turn_index
        or replay_receipt.state_digest != replay.state_digest
        or replay_receipt.observation_digest != replay.observation_digest
        or replay_receipt.evidence_digest != replay.evidence_digest
        or replay_receipt.evaluation_digest != replay.digest
        or replay_receipt.decision is not replay.decision
        or replay_receipt.reload_required is not replay.reload_required
    ):
        raise ValueError("behavioral replay does not match durable ledger receipt")
    if replay.state_digest != acknowledgement.state_digest:
        raise ValueError("behavioral replay state digest mismatch")
    if replay.turn_index <= acknowledgement.turn_index:
        raise ValueError("behavioral replay must occur after acknowledgement")
    if replay.generation != acknowledgement_result.successor_generation:
        raise ValueError("behavioral replay generation does not follow acknowledgement")
    if replay_commit.successor_generation != replay.generation + 1:
        raise ValueError("behavioral replay commit generation mismatch")
    if replay.decision is not Decision.STABLE or replay.reload_required is not False:
        raise ValueError("behavioral replay did not establish stable bounded recovery")

    return BehavioralRecoveryReceipt(
        ack_id=acknowledgement.ack_id,
        acknowledged_evaluation_digest=acknowledgement.evaluation_digest,
        state_digest=acknowledgement.state_digest,
        acknowledgement_turn_index=acknowledgement.turn_index,
        replay_evaluation_digest=replay.digest,
        replay_observation_digest=replay.observation_digest,
        replay_evidence_digest=replay.evidence_digest,
        replay_turn_index=replay.turn_index,
        replay_generation=replay.generation,
    )


@dataclass(frozen=True)
class ExternalReceiptChainEntry:
    sequence: int
    previous_digest: str | None
    subject_kind: str
    subject_digest: str

    def __post_init__(self) -> None:
        if type(self.sequence) is not int or self.sequence < 0:
            raise ValueError("sequence must be a non-negative integer")
        if self.sequence == 0:
            if self.previous_digest is not None:
                raise ValueError("genesis receipt entry must not have previous_digest")
        else:
            require_sha256_digest(self.previous_digest, "previous_digest")
        _nonempty(self.subject_kind, "subject_kind")
        require_sha256_digest(self.subject_digest, "subject_digest")

    def payload(self) -> dict[str, Any]:
        return {
            "schema": "DRIFTGUARD_EXTERNAL_RECEIPT_CHAIN_V1",
            "sequence": self.sequence,
            "previous_digest": self.previous_digest,
            "subject_kind": self.subject_kind,
            "subject_digest": self.subject_digest,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.payload())


def append_external_receipt(
    *,
    sequence: int,
    previous_digest: str | None,
    subject_kind: str,
    subject_digest: str,
) -> ExternalReceiptChainEntry:
    return ExternalReceiptChainEntry(
        sequence=sequence,
        previous_digest=previous_digest,
        subject_kind=subject_kind,
        subject_digest=subject_digest,
    )


__all__ = [
    "ActuatorDeliveryStatus",
    "ActuatorDisposition",
    "ActuatorReceipt",
    "ActuatorReconciliation",
    "BehavioralRecoveryReceipt",
    "EvaluatorProbeContract",
    "ExternalEvaluatorRequest",
    "ExternalReceiptChainEntry",
    "ReloadDirective",
    "append_external_receipt",
    "build_evaluator_request",
    "build_reload_directive",
    "qualify_post_reload_behavior",
    "reconcile_actuator_receipt",
    "validate_evaluator_response",
]
