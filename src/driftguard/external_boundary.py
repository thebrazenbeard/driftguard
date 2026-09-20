from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .ledger import AcknowledgementResult, CommitResult, DriftLedger
from .model import (
    DriftEvidence,
    EvidenceIndependence,
    ReloadAcknowledgement,
    SaveState,
    SourceBinding,
    canonical_digest,
    raw_bytes_digest,
    require_sha256_digest,
)


EVALUATOR_REQUEST_SCHEMA = "DRIFTGUARD_EVALUATOR_REQUEST_V1"
EVALUATOR_RESPONSE_SCHEMA = "DRIFTGUARD_EVALUATOR_RESPONSE_V1"
RELOAD_ATTEMPT_SCHEMA = "DRIFTGUARD_RELOAD_ATTEMPT_V1"
ACTUATOR_RECEIPT_SCHEMA = "DRIFTGUARD_ACTUATOR_RECEIPT_V1"

__all__ = [
    "ACTUATOR_RECEIPT_SCHEMA",
    "EVALUATOR_REQUEST_SCHEMA",
    "EVALUATOR_RESPONSE_SCHEMA",
    "RELOAD_ATTEMPT_SCHEMA",
    "ActuatorOutcome",
    "ActuatorReceipt",
    "EvaluatorRequest",
    "ReloadAttempt",
    "RetryDisposition",
    "acknowledgement_from_actuator_receipt",
    "acknowledgement_result_claim_ceiling",
    "admit_actuator_receipt",
    "admit_evaluator_response",
]


class ActuatorOutcome(StrEnum):
    CONSUMED_UNVERIFIED = "CONSUMED_UNVERIFIED"
    REJECTED = "REJECTED"
    AMBIGUOUS = "AMBIGUOUS"


class RetryDisposition(StrEnum):
    NO_AUTOMATIC_RETRY = "NO_AUTOMATIC_RETRY"
    RECONCILE_BEFORE_RETRY = "RECONCILE_BEFORE_RETRY"
    EFFECT_ALREADY_ASSERTED_DO_NOT_RETRY = "EFFECT_ALREADY_ASSERTED_DO_NOT_RETRY"


def _require_exact_nonempty_str(value: Any, label: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{label} must be a non-empty exact string")
    return value


def _require_exact_keys(data: Any, expected: set[str], label: str) -> dict[str, Any]:
    if type(data) is not dict:
        raise ValueError(f"{label} must be an object")
    if set(data) != expected:
        missing = sorted(expected - set(data))
        unknown = sorted(set(data) - expected)
        raise ValueError(
            f"{label} shape mismatch: missing={missing}, unknown={unknown}"
        )
    return data


@dataclass(frozen=True)
class EvaluatorRequest:
    source_binding: SourceBinding
    dimension_id: str
    max_independence: EvidenceIndependence
    min_independence: EvidenceIndependence
    state_digest: str
    observation_digest: str
    turn_index: int

    def __post_init__(self) -> None:
        if type(self.source_binding) is not SourceBinding:
            raise ValueError("source_binding must be exact SourceBinding")
        _require_exact_nonempty_str(self.dimension_id, "dimension_id")
        if type(self.max_independence) is not EvidenceIndependence:
            raise ValueError("max_independence must be EvidenceIndependence")
        if type(self.min_independence) is not EvidenceIndependence:
            raise ValueError("min_independence must be EvidenceIndependence")
        if self.max_independence < self.min_independence:
            raise ValueError("source cannot satisfy dimension independence requirement")
        require_sha256_digest(self.state_digest, "state_digest")
        require_sha256_digest(self.observation_digest, "observation_digest")
        if type(self.turn_index) is not int or self.turn_index < 0:
            raise ValueError("turn_index must be a non-negative integer")

    @classmethod
    def from_state(
        cls,
        *,
        state: SaveState,
        source_binding: SourceBinding,
        dimension_id: str,
        observation_digest: str,
        turn_index: int,
    ) -> "EvaluatorRequest":
        if type(state) is not SaveState:
            raise ValueError("state must be exact SaveState")
        if type(source_binding) is not SourceBinding:
            raise ValueError("source_binding must be exact SourceBinding")
        source = next(
            (
                item
                for item in state.probe_sources
                if item.binding == source_binding
            ),
            None,
        )
        if source is None:
            raise ValueError("source_binding is not governed by this save-state")
        if dimension_id not in source.dimensions:
            raise ValueError("source_binding is not authorized for dimension")
        dimension = next(
            (
                item
                for item in state.dimensions
                if item.dimension_id == dimension_id
            ),
            None,
        )
        if dimension is None:
            raise ValueError("dimension is not governed by this save-state")
        return cls(
            source_binding=source_binding,
            dimension_id=dimension_id,
            max_independence=source.max_independence,
            min_independence=dimension.min_independence,
            state_digest=state.digest,
            observation_digest=observation_digest,
            turn_index=turn_index,
        )

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema": EVALUATOR_REQUEST_SCHEMA,
            "source": {
                "ref": self.source_binding.ref,
                "version": self.source_binding.version,
            },
            "dimension_id": self.dimension_id,
            "max_independence": self.max_independence.name,
            "min_independence": self.min_independence.name,
            "state_digest": self.state_digest,
            "observation_digest": self.observation_digest,
            "turn_index": self.turn_index,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.canonical_payload())


def admit_evaluator_response(
    *,
    request: EvaluatorRequest,
    response: dict[str, Any],
) -> DriftEvidence:
    if type(request) is not EvaluatorRequest:
        raise ValueError("request must be exact EvaluatorRequest")
    response = _require_exact_keys(
        response,
        {
            "schema",
            "request_digest",
            "execution_id",
            "drift_score",
            "independence",
        },
        "evaluator response",
    )
    if response["schema"] != EVALUATOR_RESPONSE_SCHEMA:
        raise ValueError("evaluator response schema mismatch")
    require_sha256_digest(response["request_digest"], "request_digest")
    if response["request_digest"] != request.digest:
        raise ValueError("evaluator response request digest mismatch")
    execution_id = _require_exact_nonempty_str(
        response["execution_id"], "execution_id"
    )
    independence = EvidenceIndependence.parse(response["independence"])
    if independence > request.max_independence:
        raise ValueError("evaluator response overclaims source independence")
    if independence < request.min_independence:
        raise ValueError("evaluator response does not meet dimension independence")
    drift_score = response["drift_score"]
    evidence_id = canonical_digest(
        {
            "schema": EVALUATOR_RESPONSE_SCHEMA,
            "request_digest": request.digest,
            "execution_id": execution_id,
            "drift_score": drift_score,
            "independence": independence.name,
        }
    )
    return DriftEvidence(
        evidence_id=evidence_id,
        dimension_id=request.dimension_id,
        drift_score=drift_score,
        independence=independence,
        source_bindings=(request.source_binding,),
        execution_id=execution_id,
        state_digest=request.state_digest,
        observation_digest=request.observation_digest,
        turn_index=request.turn_index,
    )


@dataclass(frozen=True)
class ReloadAttempt:
    session_id: str
    evaluation_digest: str
    state_digest: str
    turn_index: int
    generation_after_decision: int
    restore_packet: str
    restore_packet_digest: str

    def __post_init__(self) -> None:
        _require_exact_nonempty_str(self.session_id, "session_id")
        require_sha256_digest(self.evaluation_digest, "evaluation_digest")
        require_sha256_digest(self.state_digest, "state_digest")
        if type(self.turn_index) is not int or self.turn_index < 0:
            raise ValueError("turn_index must be a non-negative integer")
        if (
            type(self.generation_after_decision) is not int
            or self.generation_after_decision < 1
        ):
            raise ValueError("generation_after_decision must be a positive integer")
        _require_exact_nonempty_str(self.restore_packet, "restore_packet")
        require_sha256_digest(self.restore_packet_digest, "restore_packet_digest")
        if raw_bytes_digest(self.restore_packet.encode("utf-8")) != self.restore_packet_digest:
            raise ValueError("restore_packet_digest does not match restore_packet bytes")

    @classmethod
    def from_commit(
        cls,
        *,
        ledger: DriftLedger,
        session_id: str,
        commit: CommitResult,
    ) -> "ReloadAttempt":
        if type(ledger) is not DriftLedger:
            raise ValueError("ledger must be exact DriftLedger")
        if type(commit) is not CommitResult:
            raise ValueError("commit must be exact CommitResult")
        evaluation = commit.evaluation
        if not evaluation.reload_required or evaluation.restore_packet is None:
            raise ValueError("reload attempt requires a reload-required evaluation")

        session = ledger.session_row(session_id)
        if session is None:
            raise ValueError("reload attempt requires a durable session")
        if int(session["generation"]) != commit.successor_generation:
            raise ValueError("reload attempt commit is not current durable generation")
        if session["last_evaluation_digest"] != evaluation.digest:
            raise ValueError("reload attempt is not the current durable evaluation")

        event = next(
            (
                item
                for item in ledger.events(session_id)
                if item["evaluation_digest"] == evaluation.digest
            ),
            None,
        )
        if event is None:
            raise ValueError("reload attempt requires a durable evaluation event")
        if (
            int(event["generation_after"]) != commit.successor_generation
            or int(event["turn_index"]) != evaluation.turn_index
            or event["state_digest"] != evaluation.state_digest
            or int(event["reload_required"]) != 1
        ):
            raise ValueError("durable evaluation event does not match reload commit")

        packet_digest = raw_bytes_digest(evaluation.restore_packet.encode("utf-8"))
        return cls(
            session_id=session_id,
            evaluation_digest=evaluation.digest,
            state_digest=evaluation.state_digest,
            turn_index=evaluation.turn_index,
            generation_after_decision=commit.successor_generation,
            restore_packet=evaluation.restore_packet,
            restore_packet_digest=packet_digest,
        )

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema": RELOAD_ATTEMPT_SCHEMA,
            "session_id": self.session_id,
            "evaluation_digest": self.evaluation_digest,
            "state_digest": self.state_digest,
            "turn_index": self.turn_index,
            "generation_after_decision": self.generation_after_decision,
            "restore_packet_digest": self.restore_packet_digest,
        }

    @property
    def attempt_id(self) -> str:
        return canonical_digest(self.canonical_payload())

    def transport_payload(self) -> dict[str, Any]:
        return {
            **self.canonical_payload(),
            "attempt_id": self.attempt_id,
            "restore_packet": self.restore_packet,
        }


@dataclass(frozen=True)
class ActuatorReceipt:
    attempt_id: str
    actuator_execution_id: str
    outcome: ActuatorOutcome
    evaluation_digest: str
    state_digest: str
    turn_index: int
    generation_after_decision: int
    restore_packet_digest: str

    def __post_init__(self) -> None:
        require_sha256_digest(self.attempt_id, "attempt_id")
        _require_exact_nonempty_str(
            self.actuator_execution_id, "actuator_execution_id"
        )
        if type(self.outcome) is not ActuatorOutcome:
            raise ValueError("outcome must be exact ActuatorOutcome")
        require_sha256_digest(self.evaluation_digest, "evaluation_digest")
        require_sha256_digest(self.state_digest, "state_digest")
        if type(self.turn_index) is not int or self.turn_index < 0:
            raise ValueError("turn_index must be a non-negative integer")
        if (
            type(self.generation_after_decision) is not int
            or self.generation_after_decision < 1
        ):
            raise ValueError(
                "generation_after_decision must be a positive integer"
            )
        require_sha256_digest(
            self.restore_packet_digest, "restore_packet_digest"
        )

    @property
    def retry_disposition(self) -> RetryDisposition:
        if self.outcome is ActuatorOutcome.AMBIGUOUS:
            return RetryDisposition.RECONCILE_BEFORE_RETRY
        if self.outcome is ActuatorOutcome.CONSUMED_UNVERIFIED:
            return RetryDisposition.EFFECT_ALREADY_ASSERTED_DO_NOT_RETRY
        return RetryDisposition.NO_AUTOMATIC_RETRY

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema": ACTUATOR_RECEIPT_SCHEMA,
            "attempt_id": self.attempt_id,
            "actuator_execution_id": self.actuator_execution_id,
            "outcome": self.outcome.value,
            "evaluation_digest": self.evaluation_digest,
            "state_digest": self.state_digest,
            "turn_index": self.turn_index,
            "generation_after_decision": self.generation_after_decision,
            "restore_packet_digest": self.restore_packet_digest,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.canonical_payload())


def admit_actuator_receipt(
    *,
    attempt: ReloadAttempt,
    receipt: dict[str, Any],
) -> ActuatorReceipt:
    if type(attempt) is not ReloadAttempt:
        raise ValueError("attempt must be exact ReloadAttempt")
    receipt = _require_exact_keys(
        receipt,
        {
            "schema",
            "attempt_id",
            "actuator_execution_id",
            "outcome",
            "evaluation_digest",
            "state_digest",
            "turn_index",
            "generation_after_decision",
            "restore_packet_digest",
        },
        "actuator receipt",
    )
    if receipt["schema"] != ACTUATOR_RECEIPT_SCHEMA:
        raise ValueError("actuator receipt schema mismatch")
    outcome = ActuatorOutcome(receipt["outcome"])
    admitted = ActuatorReceipt(
        attempt_id=receipt["attempt_id"],
        actuator_execution_id=_require_exact_nonempty_str(
            receipt["actuator_execution_id"], "actuator_execution_id"
        ),
        outcome=outcome,
        evaluation_digest=receipt["evaluation_digest"],
        state_digest=receipt["state_digest"],
        turn_index=receipt["turn_index"],
        generation_after_decision=receipt["generation_after_decision"],
        restore_packet_digest=receipt["restore_packet_digest"],
    )
    expected = {
        "attempt_id": attempt.attempt_id,
        "evaluation_digest": attempt.evaluation_digest,
        "state_digest": attempt.state_digest,
        "turn_index": attempt.turn_index,
        "generation_after_decision": attempt.generation_after_decision,
        "restore_packet_digest": attempt.restore_packet_digest,
    }
    observed = {
        "attempt_id": admitted.attempt_id,
        "evaluation_digest": admitted.evaluation_digest,
        "state_digest": admitted.state_digest,
        "turn_index": admitted.turn_index,
        "generation_after_decision": admitted.generation_after_decision,
        "restore_packet_digest": admitted.restore_packet_digest,
    }
    if observed != expected:
        raise ValueError("actuator receipt does not bind exact reload attempt")
    return admitted


def acknowledgement_from_actuator_receipt(
    *,
    attempt: ReloadAttempt,
    receipt: ActuatorReceipt,
) -> ReloadAcknowledgement:
    if type(attempt) is not ReloadAttempt:
        raise ValueError("attempt must be exact ReloadAttempt")
    if type(receipt) is not ActuatorReceipt:
        raise ValueError("receipt must be exact ActuatorReceipt")
    expected = {
        "attempt_id": attempt.attempt_id,
        "evaluation_digest": attempt.evaluation_digest,
        "state_digest": attempt.state_digest,
        "turn_index": attempt.turn_index,
        "generation_after_decision": attempt.generation_after_decision,
        "restore_packet_digest": attempt.restore_packet_digest,
    }
    observed = {
        "attempt_id": receipt.attempt_id,
        "evaluation_digest": receipt.evaluation_digest,
        "state_digest": receipt.state_digest,
        "turn_index": receipt.turn_index,
        "generation_after_decision": receipt.generation_after_decision,
        "restore_packet_digest": receipt.restore_packet_digest,
    }
    if observed != expected:
        raise ValueError("actuator receipt does not bind exact reload attempt")
    if receipt.outcome is not ActuatorOutcome.CONSUMED_UNVERIFIED:
        raise ValueError(
            "only CONSUMED_UNVERIFIED may mint a reload acknowledgement"
        )
    return ReloadAcknowledgement(
        ack_id=receipt.digest,
        evaluation_digest=receipt.evaluation_digest,
        state_digest=receipt.state_digest,
        turn_index=receipt.turn_index,
    )


def acknowledgement_result_claim_ceiling(
    result: AcknowledgementResult,
) -> str:
    if type(result) is not AcknowledgementResult:
        raise ValueError("result must be exact AcknowledgementResult")
    return "CALLER_ASSERTED_CONSUMPTION_NOT_BEHAVIORAL_RECOVERY"
