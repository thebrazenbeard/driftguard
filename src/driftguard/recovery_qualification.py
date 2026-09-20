from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable

from .external_boundary import BehavioralRecoveryReceipt
from .ledger import CommitResult
from .model import Decision, Evaluation, canonical_digest, require_sha256_digest


class RecoveryWindowDisposition(StrEnum):
    PENDING_MORE_OBSERVATION = "PENDING_MORE_OBSERVATION"
    SUSTAINED_BOUNDED_RECOVERY = "SUSTAINED_BOUNDED_RECOVERY"
    DEGRADED_DRIFT_RETURNED = "DEGRADED_DRIFT_RETURNED"
    RELAPSE_RELOAD_REQUIRED = "RELAPSE_RELOAD_REQUIRED"
    INDETERMINATE_EVIDENCE = "INDETERMINATE_EVIDENCE"


@dataclass(frozen=True)
class RecoveryWindowPolicy:
    minimum_stable_checkpoints: int = 3
    minimum_turn_span: int = 4

    def __post_init__(self) -> None:
        if type(self.minimum_stable_checkpoints) is not int or self.minimum_stable_checkpoints < 2:
            raise ValueError("minimum_stable_checkpoints must be an integer >= 2")
        if type(self.minimum_turn_span) is not int or self.minimum_turn_span < 1:
            raise ValueError("minimum_turn_span must be an integer >= 1")

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "minimum_stable_checkpoints": self.minimum_stable_checkpoints,
                "minimum_turn_span": self.minimum_turn_span,
            }
        )


@dataclass(frozen=True)
class RecoveryWindowReceipt:
    initial_recovery_digest: str
    state_digest: str
    policy_digest: str
    first_turn_index: int
    last_turn_index: int
    checkpoint_count: int
    stable_checkpoint_count: int
    disposition: RecoveryWindowDisposition
    evaluation_digests: tuple[str, ...]
    decision_trace: tuple[str, ...]
    reload_required_trace: tuple[bool, ...]

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "schema": "DRIFTGUARD_RECOVERY_WINDOW_RECEIPT_V1",
                "initial_recovery_digest": self.initial_recovery_digest,
                "state_digest": self.state_digest,
                "policy_digest": self.policy_digest,
                "first_turn_index": self.first_turn_index,
                "last_turn_index": self.last_turn_index,
                "checkpoint_count": self.checkpoint_count,
                "stable_checkpoint_count": self.stable_checkpoint_count,
                "disposition": self.disposition.value,
                "evaluation_digests": list(self.evaluation_digests),
                "decision_trace": list(self.decision_trace),
                "reload_required_trace": list(self.reload_required_trace),
            }
        )


def _validate_commit(
    commit: CommitResult,
    *,
    state_digest: str,
    previous_turn: int,
    expected_generation: int,
) -> Evaluation:
    if type(commit) is not CommitResult:
        raise ValueError("subsequent_commits must contain exact CommitResult values")
    evaluation = commit.evaluation
    if type(evaluation) is not Evaluation:
        raise ValueError("commit evaluation must be exact Evaluation")
    if type(evaluation.decision) is not Decision:
        raise ValueError("evaluation decision must be exact Decision")
    if type(evaluation.reload_required) is not bool:
        raise ValueError("evaluation reload_required must be exact bool")
    if evaluation.state_digest != state_digest:
        raise ValueError(
            "save-state digest changed inside recovery window; "
            "baseline mutation cannot qualify prior recovery"
        )
    require_sha256_digest(evaluation.observation_digest, "observation digest")
    require_sha256_digest(evaluation.evidence_digest, "evidence digest")
    if type(evaluation.turn_index) is not int or evaluation.turn_index <= previous_turn:
        raise ValueError("recovery checkpoints must advance turn_index strictly")
    if type(evaluation.generation) is not int or evaluation.generation != expected_generation:
        raise ValueError("recovery checkpoint generation is not contiguous")
    if type(commit.successor_generation) is not int or commit.successor_generation != evaluation.generation + 1:
        raise ValueError("recovery checkpoint successor generation mismatch")
    if evaluation.decision is Decision.STABLE and evaluation.reload_required:
        raise ValueError("STABLE evaluation cannot require reload")
    if evaluation.decision is Decision.WARN and evaluation.reload_required:
        raise ValueError("WARN evaluation cannot require reload")
    if evaluation.decision is Decision.RELOAD and not evaluation.reload_required:
        raise ValueError("RELOAD evaluation must require reload")
    return evaluation


def qualify_recovery_window(
    *,
    initial_recovery: BehavioralRecoveryReceipt,
    subsequent_commits: Iterable[CommitResult],
    policy: RecoveryWindowPolicy = RecoveryWindowPolicy(),
) -> RecoveryWindowReceipt:
    if type(initial_recovery) is not BehavioralRecoveryReceipt:
        raise ValueError("initial_recovery must be exact BehavioralRecoveryReceipt")
    if type(policy) is not RecoveryWindowPolicy:
        raise ValueError("policy must be exact RecoveryWindowPolicy")

    require_sha256_digest(initial_recovery.digest, "initial recovery digest")
    require_sha256_digest(initial_recovery.state_digest, "state digest")

    evaluation_digests = [initial_recovery.replay_evaluation_digest]
    decision_trace = [Decision.STABLE.value]
    reload_trace = [False]
    previous_turn = initial_recovery.replay_turn_index
    expected_generation = initial_recovery.replay_generation + 1
    stable_count = 1
    saw_warn = False
    saw_unknown = False
    saw_reload = False

    for commit in tuple(subsequent_commits):
        evaluation = _validate_commit(
            commit,
            state_digest=initial_recovery.state_digest,
            previous_turn=previous_turn,
            expected_generation=expected_generation,
        )
        if evaluation.digest in evaluation_digests:
            raise ValueError("recovery checkpoint evaluation digest was replayed")

        evaluation_digests.append(evaluation.digest)
        decision_trace.append(evaluation.decision.value)
        reload_trace.append(evaluation.reload_required)

        if evaluation.reload_required:
            saw_reload = True
        elif evaluation.decision is Decision.WARN:
            saw_warn = True
        elif evaluation.decision is Decision.UNKNOWN:
            saw_unknown = True
        elif evaluation.decision is Decision.STABLE:
            stable_count += 1

        previous_turn = evaluation.turn_index
        expected_generation = commit.successor_generation

    checkpoint_count = len(evaluation_digests)
    turn_span = previous_turn - initial_recovery.replay_turn_index

    if saw_reload:
        disposition = RecoveryWindowDisposition.RELAPSE_RELOAD_REQUIRED
    elif saw_warn:
        disposition = RecoveryWindowDisposition.DEGRADED_DRIFT_RETURNED
    elif saw_unknown:
        disposition = RecoveryWindowDisposition.INDETERMINATE_EVIDENCE
    elif (
        stable_count < policy.minimum_stable_checkpoints
        or turn_span < policy.minimum_turn_span
    ):
        disposition = RecoveryWindowDisposition.PENDING_MORE_OBSERVATION
    else:
        disposition = RecoveryWindowDisposition.SUSTAINED_BOUNDED_RECOVERY

    return RecoveryWindowReceipt(
        initial_recovery_digest=initial_recovery.digest,
        state_digest=initial_recovery.state_digest,
        policy_digest=policy.digest,
        first_turn_index=initial_recovery.replay_turn_index,
        last_turn_index=previous_turn,
        checkpoint_count=checkpoint_count,
        stable_checkpoint_count=stable_count,
        disposition=disposition,
        evaluation_digests=tuple(evaluation_digests),
        decision_trace=tuple(decision_trace),
        reload_required_trace=tuple(reload_trace),
    )


__all__ = [
    "RecoveryWindowDisposition",
    "RecoveryWindowPolicy",
    "RecoveryWindowReceipt",
    "qualify_recovery_window",
]
