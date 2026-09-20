from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import Any, Iterable

from .ledger import AcknowledgementResult, CommitResult, DriftLedger
from .model import (
    Decision,
    DriftEvidence,
    Evaluation,
    MeasurementMode,
    MonitoredSubject,
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
    calibration_ref: str | None = None
    calibration_version: str | None = None
    calibration_digest: str | None = None
    correlation_group: str | None = None
    score_scale: str | None = None

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
        if (self.calibration_ref is None) != (self.calibration_version is None):
            raise ValueError(
                "calibration_ref and calibration_version must be supplied together"
            )
        if self.calibration_ref is not None:
            _nonempty(self.calibration_ref, "calibration_ref")
            _nonempty(self.calibration_version, "calibration_version")
        if self.calibration_digest is not None:
            require_sha256_digest(
                self.calibration_digest,
                "calibration_digest",
            )
        if self.correlation_group is not None:
            _nonempty(self.correlation_group, "correlation_group")
        if self.score_scale is not None:
            _nonempty(self.score_scale, "score_scale")

    @property
    def binding(self) -> SourceBinding:
        return SourceBinding(self.source_ref, self.source_version)

    def payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "source_ref": self.source_ref,
            "source_version": self.source_version,
            "max_independence": self.max_independence,
            "dimensions": list(self.dimensions),
        }
        if self.calibration_ref is not None:
            payload["calibration"] = {
                "ref": self.calibration_ref,
                "version": self.calibration_version,
            }
        if self.calibration_digest is not None:
            payload["calibration_digest"] = self.calibration_digest
        if self.correlation_group is not None:
            payload["correlation_group"] = self.correlation_group
        if self.score_scale is not None:
            payload["score_scale"] = self.score_scale
        return payload


@dataclass(frozen=True)
class ExternalEvaluatorRequest:
    session_id: str
    state_digest: str
    observation_digest: str
    turn_index: int
    expected_generation: int
    probe_contract: tuple[EvaluatorProbeContract, ...]
    behavior_digest: str | None = None
    measurement_digest: str | None = None
    detection_policy_digest: str | None = None
    subject_digest: str | None = None
    subject_epoch: int | None = None

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
        digest_fields = (
            self.behavior_digest,
            self.measurement_digest,
            self.detection_policy_digest,
        )
        if any(value is not None for value in digest_fields):
            if any(value is None for value in digest_fields):
                raise ValueError(
                    "behavior, measurement, and detection-policy digests "
                    "must be supplied together"
                )
            require_sha256_digest(self.behavior_digest, "behavior_digest")
            require_sha256_digest(self.measurement_digest, "measurement_digest")
            require_sha256_digest(
                self.detection_policy_digest,
                "detection_policy_digest",
            )
        if (self.subject_digest is None) != (self.subject_epoch is None):
            raise ValueError(
                "subject_digest and subject_epoch must be supplied together"
            )
        if self.subject_digest is not None:
            require_sha256_digest(self.subject_digest, "subject_digest")
            if (
                type(self.subject_epoch) is not int
                or isinstance(self.subject_epoch, bool)
                or self.subject_epoch < 0
            ):
                raise ValueError(
                    "subject_epoch must be a non-negative integer"
                )

    def payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": (
                "DRIFTGUARD_EXTERNAL_EVALUATOR_REQUEST_V3"
                if self.subject_digest is not None
                else (
                    "DRIFTGUARD_EXTERNAL_EVALUATOR_REQUEST_V2"
                    if self.behavior_digest is not None
                    else "DRIFTGUARD_EXTERNAL_EVALUATOR_REQUEST_V1"
                )
            ),
            "session_id": self.session_id,
            "state_digest": self.state_digest,
            "observation_digest": self.observation_digest,
            "turn_index": self.turn_index,
            "expected_generation": self.expected_generation,
            "probe_contract": [item.payload() for item in self.probe_contract],
        }
        if self.behavior_digest is not None:
            payload["behavior_digest"] = self.behavior_digest
            payload["measurement_digest"] = self.measurement_digest
            payload["detection_policy_digest"] = self.detection_policy_digest
        if self.subject_digest is not None:
            payload["subject_digest"] = self.subject_digest
            payload["subject_epoch"] = self.subject_epoch
        return payload

    @property
    def digest(self) -> str:
        return canonical_digest(self.payload())

    @property
    def request_id(self) -> str:
        return f"driftguard-evaluator:{self.digest}"


@dataclass(frozen=True)
class ExternalEvaluatorResponse:
    request_digest: str
    evidence: tuple[DriftEvidence, ...]

    def __post_init__(self) -> None:
        require_sha256_digest(self.request_digest, "request_digest")
        if type(self.evidence) is not tuple:
            raise ValueError("evidence must be an exact tuple")
        if any(type(item) is not DriftEvidence for item in self.evidence):
            raise ValueError("evidence must contain exact DriftEvidence values")

    @property
    def evidence_digest(self) -> str:
        return evidence_set_digest(self.evidence)

    def payload(self) -> dict[str, Any]:
        return {
            "schema": "DRIFTGUARD_EXTERNAL_EVALUATOR_RESPONSE_V1",
            "request_digest": self.request_digest,
            "evidence_digest": self.evidence_digest,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.payload())


def build_evaluator_request(
    *,
    session_id: str,
    state: SaveState,
    observation_digest: str,
    turn_index: int,
    expected_generation: int,
    subject: MonitoredSubject | None = None,
) -> ExternalEvaluatorRequest:
    if type(state) is not SaveState:
        raise ValueError("state must be exact SaveState")
    if subject is not None and type(subject) is not MonitoredSubject:
        raise ValueError("subject must be exact MonitoredSubject or None")
    contracts = tuple(
        sorted(
            (
                EvaluatorProbeContract(
                    source.binding.ref,
                    source.binding.version,
                    source.max_independence.name,
                    source.dimensions,
                    (
                        source.calibration.ref
                        if source.calibration is not None
                        else None
                    ),
                    (
                        source.calibration.version
                        if source.calibration is not None
                        else None
                    ),
                    source.calibration_digest,
                    source.correlation_group,
                    source.score_scale,
                )
                for source in state.probe_sources
            ),
            key=lambda item: (item.source_ref, item.source_version),
        )
    )
    strict = state.measurement_mode is MeasurementMode.CALIBRATED_QUORUM
    return ExternalEvaluatorRequest(
        session_id=session_id,
        state_digest=state.digest,
        observation_digest=observation_digest,
        turn_index=turn_index,
        expected_generation=expected_generation,
        probe_contract=contracts,
        behavior_digest=state.behavior_digest if strict else None,
        measurement_digest=state.measurement_digest if strict else None,
        detection_policy_digest=state.detection_policy_digest if strict else None,
        subject_digest=(
            subject.configuration_digest if subject is not None else None
        ),
        subject_epoch=subject.epoch if subject is not None else None,
    )


def validate_evaluator_response(
    request: ExternalEvaluatorRequest,
    response: ExternalEvaluatorResponse,
) -> str:
    if type(request) is not ExternalEvaluatorRequest:
        raise ValueError("request must be exact ExternalEvaluatorRequest")
    if type(response) is not ExternalEvaluatorResponse:
        raise ValueError("response must be exact ExternalEvaluatorResponse")
    if response.request_digest != request.digest:
        raise ValueError("external evaluator response request digest mismatch")
    rows = response.evidence
    allowed_bindings = {item.binding for item in request.probe_contract}
    for item in rows:
        if item.state_digest != request.state_digest:
            raise ValueError("external evidence state digest mismatch")
        if item.observation_digest != request.observation_digest:
            raise ValueError("external evidence observation digest mismatch")
        if item.turn_index != request.turn_index:
            raise ValueError("external evidence turn mismatch")
        if item.subject_digest != request.subject_digest:
            raise ValueError("external evidence subject digest mismatch")
        if item.subject_epoch != request.subject_epoch:
            raise ValueError("external evidence subject epoch mismatch")
        if not set(item.source_bindings).issubset(allowed_bindings):
            raise ValueError("external evidence contains unrequested source binding")
    return response.evidence_digest


def commit_evaluator_response(
    *,
    request: ExternalEvaluatorRequest,
    state: SaveState,
    response: ExternalEvaluatorResponse,
    ledger: DriftLedger,
    subject: MonitoredSubject | None = None,
) -> CommitResult:
    if type(request) is not ExternalEvaluatorRequest:
        raise ValueError("request must be exact ExternalEvaluatorRequest")
    if type(state) is not SaveState:
        raise ValueError("state must be exact SaveState")
    if type(response) is not ExternalEvaluatorResponse:
        raise ValueError("response must be exact ExternalEvaluatorResponse")
    if type(ledger) is not DriftLedger:
        raise ValueError("ledger must be exact DriftLedger")
    if subject is not None and type(subject) is not MonitoredSubject:
        raise ValueError("subject must be exact MonitoredSubject or None")
    expected_subject_digest = (
        subject.configuration_digest if subject is not None else None
    )
    expected_subject_epoch = subject.epoch if subject is not None else None
    if request.subject_digest != expected_subject_digest:
        raise ValueError("evaluator request subject digest no longer matches subject")
    if request.subject_epoch != expected_subject_epoch:
        raise ValueError("evaluator request subject epoch no longer matches subject")
    if state.digest != request.state_digest:
        raise ValueError("evaluator request state digest no longer matches state")
    validate_evaluator_response(request, response)
    return ledger.evaluate_and_commit(
        session_id=request.session_id,
        state=state,
        evidence=response.evidence,
        observation_digest=request.observation_digest,
        turn_index=request.turn_index,
        expected_generation=request.expected_generation,
        subject=subject,
    )


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
    session = ledger.session_row(session_id)
    if session is None:
        raise ValueError("reload directive requires current durable session")
    if int(session["generation"]) != commit.successor_generation:
        raise ValueError("reload directive commit is not current durable generation")
    if session["last_evaluation_digest"] != evaluation.digest:
        raise ValueError("reload directive commit is not current durable evaluation")
    if session["state_digest"] != evaluation.state_digest:
        raise ValueError("reload directive current session state mismatch")
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
    READBACK_REQUIRED = "READBACK_REQUIRED"


class BehavioralReplayDisposition(StrEnum):
    STABLE = "STABLE"
    DEGRADED = "DEGRADED"
    RELAPSE = "RELAPSE"
    INDETERMINATE = "INDETERMINATE"


def classify_behavioral_fields(
    *,
    state: SaveState,
    decision: Decision,
    aggregate_drift: float | None,
    reasons: tuple[str, ...],
    behavioral_decision: Decision | None = None,
) -> BehavioralReplayDisposition:
    """Classify observed behavior independently of reload scheduling."""
    if type(state) is not SaveState:
        raise ValueError("state must be exact SaveState")
    if type(decision) is not Decision:
        raise ValueError("decision must be exact Decision")
    if behavioral_decision is not None and type(behavioral_decision) is not Decision:
        raise ValueError("behavioral_decision must be exact Decision or None")
    if type(reasons) is not tuple or any(
        type(item) is not str or not item for item in reasons
    ):
        raise ValueError("reasons must be a tuple of non-empty strings")

    if behavioral_decision is not None:
        if behavioral_decision is Decision.UNKNOWN:
            return BehavioralReplayDisposition.INDETERMINATE
        if behavioral_decision is Decision.RELOAD:
            return BehavioralReplayDisposition.RELAPSE
        if behavioral_decision is Decision.WARN:
            return BehavioralReplayDisposition.DEGRADED
        return BehavioralReplayDisposition.STABLE

    # Legacy V1 compatibility: historical receipts did not carry a typed
    # behavioral disposition, so bounded replay remains reason/aggregate based.
    if "critical_dimension_breach" in reasons:
        return BehavioralReplayDisposition.RELAPSE
    if decision is Decision.UNKNOWN or aggregate_drift is None:
        return BehavioralReplayDisposition.INDETERMINATE

    aggregate = float(aggregate_drift)
    if aggregate >= state.policy.reload_threshold:
        return BehavioralReplayDisposition.RELAPSE
    if aggregate >= state.policy.warn_threshold:
        return BehavioralReplayDisposition.DEGRADED
    return BehavioralReplayDisposition.STABLE


def classify_behavioral_evaluation(
    *,
    state: SaveState,
    evaluation: Evaluation,
) -> BehavioralReplayDisposition:
    if type(evaluation) is not Evaluation:
        raise ValueError("evaluation must be exact Evaluation")
    if evaluation.state_digest != state.digest:
        raise ValueError("behavioral evaluation state digest mismatch")
    return classify_behavioral_fields(
        state=state,
        decision=evaluation.decision,
        aggregate_drift=evaluation.aggregate_drift,
        reasons=evaluation.reasons,
        behavioral_decision=evaluation.behavioral_decision,
    )


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
            ActuatorDisposition.READBACK_REQUIRED,
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
    state: SaveState,
    acknowledgement: ReloadAcknowledgement,
    acknowledgement_result: AcknowledgementResult,
    replay_commit: CommitResult,
    ledger: DriftLedger,
) -> BehavioralRecoveryReceipt:
    if type(state) is not SaveState:
        raise ValueError("state must be exact SaveState")
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
    if state.digest != acknowledgement.state_digest:
        raise ValueError("behavioral recovery state does not match acknowledgement")
    if replay.state_digest != acknowledgement.state_digest:
        raise ValueError("behavioral replay state digest mismatch")
    if replay.turn_index <= acknowledgement.turn_index:
        raise ValueError("behavioral replay must occur after acknowledgement")
    if replay.generation != acknowledgement_result.successor_generation:
        raise ValueError("behavioral replay generation does not follow acknowledgement")
    if replay_commit.successor_generation != replay.generation + 1:
        raise ValueError("behavioral replay commit generation mismatch")
    behavioral = classify_behavioral_evaluation(
        state=state,
        evaluation=replay,
    )
    if behavioral is not BehavioralReplayDisposition.STABLE:
        raise ValueError(
            "behavioral replay did not establish stable bounded recovery: "
            f"{behavioral.value}"
        )

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
    "BehavioralReplayDisposition",
    "EvaluatorProbeContract",
    "ExternalEvaluatorRequest",
    "ExternalEvaluatorResponse",
    "ExternalReceiptChainEntry",
    "ReloadDirective",
    "append_external_receipt",
    "build_evaluator_request",
    "commit_evaluator_response",
    "build_reload_directive",
    "classify_behavioral_evaluation",
    "classify_behavioral_fields",
    "qualify_post_reload_behavior",
    "reconcile_actuator_receipt",
    "validate_evaluator_response",
]
