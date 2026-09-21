from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import sqlite3
from typing import Any

from .benchmark import (
    BenchmarkAttemptStatus,
    BenchmarkCorpusManifest,
    BenchmarkExecutionBinding,
    BenchmarkPrecommitPlan,
    BenchmarkRunResult,
    canonical_corpus_artifact_bytes,
    current_execution_binding,
)
from .calibration import (
    CalibrationCorpus,
    CalibrationCorpusRole,
    CalibrationFamilyPolicy,
    CalibrationPlan,
)
from .comparison import (
    DetectorAlgorithm,
    DetectorCandidate,
    DetectorCandidateResult,
    qualify_detector_candidate,
)
from .model import SourceBinding, canonical_digest, require_sha256_digest
from .sequential import SequentialDetectorSpec


_SELECTION_TOKEN = object()
_REVEAL_TOKEN = object()
_QUALIFICATION_TOKEN = object()
_ATTEMPT_TOKEN = object()
_SEMANTIC_FAILURE_TOKEN = object()

SELECTION_CLAIM = (
    "FIRST_HOLDOUT_SELECTION_REQUIRES_FRESH_PROMOTION_HOLDOUT"
)
PROMOTION_CLAIM = (
    "FRESH_SINGLE_CANDIDATE_HOLDOUT_QUALIFICATION_NOT_DEPLOYMENT_AUTHORITY"
)


def _nonempty(value: Any, label: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{label} must be a non-empty exact string")
    return value


@dataclass(frozen=True)
class PromotionExecutionBinding:
    benchmark_binding: BenchmarkExecutionBinding
    promotion_source_digest: str

    def __post_init__(self) -> None:
        if type(self.benchmark_binding) is not BenchmarkExecutionBinding:
            raise ValueError(
                "benchmark_binding must be exact BenchmarkExecutionBinding"
            )
        require_sha256_digest(
            self.promotion_source_digest,
            "promotion.py source digest",
        )

    def payload(self) -> dict[str, Any]:
        return {
            "schema": "DRIFTGUARD_PROMOTION_EXECUTION_BINDING_V1",
            "benchmark_binding": self.benchmark_binding.payload(),
            "promotion_source_digest": self.promotion_source_digest,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.payload())

    def assert_runtime_sources_match(self) -> None:
        self.benchmark_binding.assert_runtime_sources_match()
        observed = sha256(Path(__file__).read_bytes()).hexdigest()
        if observed != self.promotion_source_digest:
            raise ValueError(
                "promotion runtime source digest does not match precommitted binding"
            )


def current_promotion_execution_binding(
    *,
    repository: str,
    commit_sha: str,
) -> PromotionExecutionBinding:
    return PromotionExecutionBinding(
        benchmark_binding=current_execution_binding(
            repository=repository,
            commit_sha=commit_sha,
        ),
        promotion_source_digest=sha256(Path(__file__).read_bytes()).hexdigest(),
    )


@dataclass(frozen=True, init=False)
class CandidateNominationReceipt:
    source_study_id: str
    source_attempt_id: str
    source_precommit_digest: str
    source_run_receipt_digest: str
    source_comparison_receipt_digest: str
    source_holdout_digest: str
    consumed_holdout_digests: tuple[str, ...]
    candidate_id: str
    candidate_algorithm: DetectorAlgorithm
    candidate_digest: str
    selection_claim: str

    def __init__(
        self,
        *,
        source_study_id: str,
        source_attempt_id: str,
        source_precommit_digest: str,
        source_run_receipt_digest: str,
        source_comparison_receipt_digest: str,
        source_holdout_digest: str,
        consumed_holdout_digests: tuple[str, ...],
        candidate_id: str,
        candidate_algorithm: DetectorAlgorithm,
        candidate_digest: str,
        selection_claim: str,
        _selection_token: object | None = None,
    ) -> None:
        if _selection_token is not _SELECTION_TOKEN:
            raise ValueError(
                "CandidateNominationReceipt must come from nominate_candidate"
            )
        object.__setattr__(self, "source_study_id", source_study_id)
        object.__setattr__(self, "source_attempt_id", source_attempt_id)
        object.__setattr__(
            self,
            "source_precommit_digest",
            source_precommit_digest,
        )
        object.__setattr__(
            self,
            "source_run_receipt_digest",
            source_run_receipt_digest,
        )
        object.__setattr__(
            self,
            "source_comparison_receipt_digest",
            source_comparison_receipt_digest,
        )
        object.__setattr__(
            self,
            "source_holdout_digest",
            source_holdout_digest,
        )
        object.__setattr__(
            self,
            "consumed_holdout_digests",
            consumed_holdout_digests,
        )
        object.__setattr__(self, "candidate_id", candidate_id)
        object.__setattr__(
            self,
            "candidate_algorithm",
            candidate_algorithm,
        )
        object.__setattr__(self, "candidate_digest", candidate_digest)
        object.__setattr__(self, "selection_claim", selection_claim)
        self.__post_init__()

    def __post_init__(self) -> None:
        _nonempty(self.source_study_id, "nomination source study id")
        _nonempty(self.source_attempt_id, "nomination source attempt id")
        _nonempty(self.candidate_id, "nomination candidate id")
        for value, label in (
            (
                self.source_precommit_digest,
                "nomination source precommit digest",
            ),
            (
                self.source_run_receipt_digest,
                "nomination source run receipt digest",
            ),
            (
                self.source_comparison_receipt_digest,
                "nomination source comparison receipt digest",
            ),
            (
                self.source_holdout_digest,
                "nomination source holdout digest",
            ),
            (self.candidate_digest, "nomination candidate digest"),
        ):
            require_sha256_digest(value, label)
        if type(self.candidate_algorithm) is not DetectorAlgorithm:
            raise ValueError(
                "nomination candidate algorithm must be exact DetectorAlgorithm"
            )
        if (
            type(self.consumed_holdout_digests) is not tuple
            or not self.consumed_holdout_digests
            or self.consumed_holdout_digests
            != tuple(sorted(set(self.consumed_holdout_digests)))
        ):
            raise ValueError(
                "consumed holdout digests must be non-empty canonical unique tuple"
            )
        for item in self.consumed_holdout_digests:
            require_sha256_digest(item, "consumed holdout digest")
        if self.source_holdout_digest not in self.consumed_holdout_digests:
            raise ValueError(
                "source holdout digest must be included in consumed holdouts"
            )
        if self.selection_claim != SELECTION_CLAIM:
            raise ValueError("unsupported nomination selection claim")

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "schema": "DRIFTGUARD_CANDIDATE_NOMINATION_V1",
                "source_study_id": self.source_study_id,
                "source_attempt_id": self.source_attempt_id,
                "source_precommit_digest": self.source_precommit_digest,
                "source_run_receipt_digest": self.source_run_receipt_digest,
                "source_comparison_receipt_digest": (
                    self.source_comparison_receipt_digest
                ),
                "source_holdout_digest": self.source_holdout_digest,
                "consumed_holdout_digests": list(
                    self.consumed_holdout_digests
                ),
                "candidate_id": self.candidate_id,
                "candidate_algorithm": self.candidate_algorithm.value,
                "candidate_digest": self.candidate_digest,
                "selection_claim": self.selection_claim,
            }
        )


def nominate_candidate(
    *,
    precommit: BenchmarkPrecommitPlan,
    run_result: BenchmarkRunResult,
    candidate_id: str,
) -> CandidateNominationReceipt:
    if type(precommit) is not BenchmarkPrecommitPlan:
        raise ValueError("precommit must be exact BenchmarkPrecommitPlan")
    if type(run_result) is not BenchmarkRunResult:
        raise ValueError("run_result must be exact BenchmarkRunResult")
    _nonempty(candidate_id, "candidate_id")

    receipt = run_result.receipt
    comparison = run_result.comparison
    if receipt.study_id != precommit.study_id:
        raise ValueError("nomination source study id mismatch")
    if receipt.attempt_id != precommit.attempt_id:
        raise ValueError("nomination source attempt id mismatch")
    if receipt.precommit_digest != precommit.digest:
        raise ValueError("nomination source precommit digest mismatch")
    if (
        receipt.execution_binding_digest
        != precommit.execution_binding.digest
    ):
        raise ValueError("nomination source execution binding mismatch")
    if receipt.comparison_receipt_digest != comparison.digest:
        raise ValueError("nomination comparison receipt digest mismatch")
    if comparison.promotion_authorized:
        raise ValueError(
            "R11 source comparison unexpectedly authorized promotion"
        )
    if comparison.corpus_digest != precommit.holdout_seal.manifest.corpus_digest:
        raise ValueError("nomination source holdout digest mismatch")
    if candidate_id not in comparison.qualified_candidate_ids:
        raise ValueError(
            "only a candidate qualified on the source comparison may be nominated"
        )

    candidate = next(
        (
            item
            for item in precommit.candidates
            if item.candidate_id == candidate_id
        ),
        None,
    )
    if candidate is None:
        raise ValueError("nominated candidate is absent from source precommit")
    result = next(
        (
            item
            for item in comparison.candidate_results
            if item.candidate_id == candidate_id
        ),
        None,
    )
    if result is None:
        raise ValueError("nominated candidate result is absent")
    if result.candidate_digest != candidate.digest:
        raise ValueError("nominated candidate/result digest mismatch")
    if result.algorithm is not candidate.algorithm:
        raise ValueError("nominated candidate/result algorithm mismatch")

    source_holdout = precommit.holdout_seal.manifest.corpus_digest
    consumed = tuple(
        sorted(
            set(precommit.predecessor_holdout_digests)
            | {source_holdout}
        )
    )
    return CandidateNominationReceipt(
        source_study_id=precommit.study_id,
        source_attempt_id=precommit.attempt_id,
        source_precommit_digest=precommit.digest,
        source_run_receipt_digest=receipt.digest,
        source_comparison_receipt_digest=comparison.digest,
        source_holdout_digest=source_holdout,
        consumed_holdout_digests=consumed,
        candidate_id=candidate.candidate_id,
        candidate_algorithm=candidate.algorithm,
        candidate_digest=candidate.digest,
        selection_claim=SELECTION_CLAIM,
        _selection_token=_SELECTION_TOKEN,
    )


@dataclass(frozen=True)
class PromotionQualificationPlan:
    study_id: str
    attempt_id: str
    plan_id: str
    predecessor_attempt_digests: tuple[str, ...]
    predecessor_holdout_digests: tuple[str, ...]
    nomination: CandidateNominationReceipt
    candidate: DetectorCandidate
    qualification_manifest: BenchmarkCorpusManifest
    execution_binding: PromotionExecutionBinding
    reference_cusum_spec_digest: str
    family_policies: tuple[CalibrationFamilyPolicy, ...]
    plan_artifact: SourceBinding
    plan_artifact_digest: str

    def __post_init__(self) -> None:
        _nonempty(self.study_id, "promotion study id")
        _nonempty(self.attempt_id, "promotion attempt id")
        _nonempty(self.plan_id, "promotion plan id")
        if type(self.nomination) is not CandidateNominationReceipt:
            raise ValueError(
                "nomination must be exact CandidateNominationReceipt"
            )
        if type(self.candidate) is not DetectorCandidate:
            raise ValueError("candidate must be exact DetectorCandidate")
        if self.candidate.candidate_id != self.nomination.candidate_id:
            raise ValueError("promotion candidate id/nomination mismatch")
        if self.candidate.algorithm is not self.nomination.candidate_algorithm:
            raise ValueError(
                "promotion candidate algorithm/nomination mismatch"
            )
        if self.candidate.digest != self.nomination.candidate_digest:
            raise ValueError(
                "promotion candidate digest/nomination mismatch"
            )
        if type(self.qualification_manifest) is not BenchmarkCorpusManifest:
            raise ValueError(
                "qualification_manifest must be exact BenchmarkCorpusManifest"
            )
        if (
            self.qualification_manifest.corpus_role
            is not CalibrationCorpusRole.HOLDOUT_QUALIFICATION
        ):
            raise ValueError(
                "promotion qualification requires HOLDOUT_QUALIFICATION manifest"
            )
        if (
            self.qualification_manifest.corpus_digest
            in self.nomination.consumed_holdout_digests
        ):
            raise ValueError(
                "promotion holdout must differ from every source consumed holdout"
            )
        if type(self.execution_binding) is not PromotionExecutionBinding:
            raise ValueError(
                "execution_binding must be exact PromotionExecutionBinding"
            )
        require_sha256_digest(
            self.reference_cusum_spec_digest,
            "promotion reference CUSUM spec digest",
        )
        if (
            self.candidate.algorithm is DetectorAlgorithm.CUSUM
            and self.candidate.cusum_spec_digest
            != self.reference_cusum_spec_digest
        ):
            raise ValueError(
                "promotion CUSUM candidate/reference spec digest mismatch"
            )
        if (
            type(self.family_policies) is not tuple
            or not self.family_policies
            or any(
                type(item) is not CalibrationFamilyPolicy
                for item in self.family_policies
            )
        ):
            raise ValueError(
                "promotion family policies must contain exact CalibrationFamilyPolicy"
            )
        policy_ids = [item.family_id for item in self.family_policies]
        manifest_ids = [
            item.family_id for item in self.qualification_manifest.families
        ]
        if policy_ids != sorted(policy_ids) or len(policy_ids) != len(set(policy_ids)):
            raise ValueError(
                "promotion family policy ids must be unique and canonical"
            )
        if policy_ids != manifest_ids:
            raise ValueError(
                "promotion family policies must exactly match qualification families"
            )
        if (
            type(self.predecessor_attempt_digests) is not tuple
            or self.predecessor_attempt_digests
            != tuple(sorted(set(self.predecessor_attempt_digests)))
        ):
            raise ValueError(
                "promotion predecessor attempt digests must be canonical/unique"
            )
        for item in self.predecessor_attempt_digests:
            require_sha256_digest(item, "promotion predecessor attempt digest")
        if (
            type(self.predecessor_holdout_digests) is not tuple
            or self.predecessor_holdout_digests
            != tuple(sorted(set(self.predecessor_holdout_digests)))
        ):
            raise ValueError(
                "promotion predecessor holdout digests must be canonical/unique"
            )
        for item in self.predecessor_holdout_digests:
            require_sha256_digest(item, "promotion predecessor holdout digest")
        if not set(self.nomination.consumed_holdout_digests).issubset(
            set(self.predecessor_holdout_digests)
        ):
            raise ValueError(
                "promotion plan must disclose every holdout consumed before nomination"
            )
        if (
            self.qualification_manifest.corpus_digest
            in self.predecessor_holdout_digests
        ):
            raise ValueError(
                "promotion qualification holdout was already consumed"
            )
        if type(self.plan_artifact) is not SourceBinding:
            raise ValueError(
                "promotion plan artifact must be exact SourceBinding"
            )
        require_sha256_digest(
            self.plan_artifact_digest,
            "promotion plan artifact digest",
        )

    @property
    def calibration_plan(self) -> CalibrationPlan:
        return CalibrationPlan(
            plan_id=f"{self.plan_id}:candidate-qualification",
            detector_spec_digest=self.reference_cusum_spec_digest,
            corpus_digest=self.qualification_manifest.corpus_digest,
            corpus_role=CalibrationCorpusRole.HOLDOUT_QUALIFICATION,
            family_policies=self.family_policies,
        )

    def payload(self) -> dict[str, Any]:
        return {
            "schema": "DRIFTGUARD_PROMOTION_QUALIFICATION_PLAN_V1",
            "study_id": self.study_id,
            "attempt_id": self.attempt_id,
            "plan_id": self.plan_id,
            "predecessor_attempt_digests": list(
                self.predecessor_attempt_digests
            ),
            "predecessor_holdout_digests": list(
                self.predecessor_holdout_digests
            ),
            "nomination_digest": self.nomination.digest,
            "candidate": self.candidate.payload(),
            "qualification_manifest_digest": (
                self.qualification_manifest.digest
            ),
            "qualification_holdout_digest": (
                self.qualification_manifest.corpus_digest
            ),
            "execution_binding": self.execution_binding.payload(),
            "reference_cusum_spec_digest": self.reference_cusum_spec_digest,
            "family_policies": [
                item.payload() for item in self.family_policies
            ],
            "calibration_plan_digest": self.calibration_plan.digest,
            "plan_artifact": {
                "ref": self.plan_artifact.ref,
                "version": self.plan_artifact.version,
            },
            "plan_artifact_digest": self.plan_artifact_digest,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.payload())


@dataclass(frozen=True, init=False)
class PromotionRevealReceipt:
    study_id: str
    attempt_id: str
    plan_digest: str
    execution_binding_digest: str
    manifest_digest: str
    corpus_digest: str
    artifact_digest: str

    def __init__(
        self,
        *,
        study_id: str,
        attempt_id: str,
        plan_digest: str,
        execution_binding_digest: str,
        manifest_digest: str,
        corpus_digest: str,
        artifact_digest: str,
        _reveal_token: object | None = None,
    ) -> None:
        if _reveal_token is not _REVEAL_TOKEN:
            raise ValueError(
                "PromotionRevealReceipt must come from reveal_promotion_holdout"
            )
        object.__setattr__(self, "study_id", study_id)
        object.__setattr__(self, "attempt_id", attempt_id)
        object.__setattr__(self, "plan_digest", plan_digest)
        object.__setattr__(
            self,
            "execution_binding_digest",
            execution_binding_digest,
        )
        object.__setattr__(self, "manifest_digest", manifest_digest)
        object.__setattr__(self, "corpus_digest", corpus_digest)
        object.__setattr__(self, "artifact_digest", artifact_digest)
        self.__post_init__()

    def __post_init__(self) -> None:
        _nonempty(self.study_id, "promotion reveal study id")
        _nonempty(self.attempt_id, "promotion reveal attempt id")
        for value, label in (
            (self.plan_digest, "promotion reveal plan digest"),
            (
                self.execution_binding_digest,
                "promotion reveal execution binding digest",
            ),
            (self.manifest_digest, "promotion reveal manifest digest"),
            (self.corpus_digest, "promotion reveal corpus digest"),
            (self.artifact_digest, "promotion reveal artifact digest"),
        ):
            require_sha256_digest(value, label)

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "schema": "DRIFTGUARD_PROMOTION_REVEAL_RECEIPT_V1",
                "study_id": self.study_id,
                "attempt_id": self.attempt_id,
                "plan_digest": self.plan_digest,
                "execution_binding_digest": self.execution_binding_digest,
                "manifest_digest": self.manifest_digest,
                "corpus_digest": self.corpus_digest,
                "artifact_digest": self.artifact_digest,
            }
        )


@dataclass(frozen=True, init=False)
class PromotionQualificationReceipt:
    study_id: str
    attempt_id: str
    plan_digest: str
    nomination_digest: str
    candidate_digest: str
    reveal_digest: str
    candidate_result_digest: str
    qualification_passed: bool
    promotion_eligible: bool
    deployment_authorized: bool
    promotion_claim: str

    def __init__(
        self,
        *,
        study_id: str,
        attempt_id: str,
        plan_digest: str,
        nomination_digest: str,
        candidate_digest: str,
        reveal_digest: str,
        candidate_result_digest: str,
        qualification_passed: bool,
        promotion_eligible: bool,
        deployment_authorized: bool,
        promotion_claim: str,
        _qualification_token: object | None = None,
    ) -> None:
        if _qualification_token is not _QUALIFICATION_TOKEN:
            raise ValueError(
                "PromotionQualificationReceipt must come from qualify_promotion_candidate"
            )
        object.__setattr__(self, "study_id", study_id)
        object.__setattr__(self, "attempt_id", attempt_id)
        object.__setattr__(self, "plan_digest", plan_digest)
        object.__setattr__(self, "nomination_digest", nomination_digest)
        object.__setattr__(self, "candidate_digest", candidate_digest)
        object.__setattr__(self, "reveal_digest", reveal_digest)
        object.__setattr__(
            self,
            "candidate_result_digest",
            candidate_result_digest,
        )
        object.__setattr__(
            self,
            "qualification_passed",
            qualification_passed,
        )
        object.__setattr__(
            self,
            "promotion_eligible",
            promotion_eligible,
        )
        object.__setattr__(
            self,
            "deployment_authorized",
            deployment_authorized,
        )
        object.__setattr__(self, "promotion_claim", promotion_claim)
        self.__post_init__()

    def __post_init__(self) -> None:
        _nonempty(self.study_id, "promotion receipt study id")
        _nonempty(self.attempt_id, "promotion receipt attempt id")
        for value, label in (
            (self.plan_digest, "promotion receipt plan digest"),
            (self.nomination_digest, "promotion receipt nomination digest"),
            (self.candidate_digest, "promotion receipt candidate digest"),
            (self.reveal_digest, "promotion receipt reveal digest"),
            (
                self.candidate_result_digest,
                "promotion receipt candidate result digest",
            ),
        ):
            require_sha256_digest(value, label)
        for value, label in (
            (self.qualification_passed, "qualification_passed"),
            (self.promotion_eligible, "promotion_eligible"),
            (self.deployment_authorized, "deployment_authorized"),
        ):
            if type(value) is not bool:
                raise ValueError(f"{label} must be exact bool")
        if self.promotion_eligible != self.qualification_passed:
            raise ValueError(
                "promotion eligibility must exactly match fresh holdout qualification"
            )
        if self.deployment_authorized:
            raise ValueError(
                "R12 statistical promotion qualification cannot authorize deployment"
            )
        if self.promotion_claim != PROMOTION_CLAIM:
            raise ValueError("unsupported promotion qualification claim")

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "schema": "DRIFTGUARD_PROMOTION_QUALIFICATION_RECEIPT_V1",
                "study_id": self.study_id,
                "attempt_id": self.attempt_id,
                "plan_digest": self.plan_digest,
                "nomination_digest": self.nomination_digest,
                "candidate_digest": self.candidate_digest,
                "reveal_digest": self.reveal_digest,
                "candidate_result_digest": self.candidate_result_digest,
                "qualification_passed": self.qualification_passed,
                "promotion_eligible": self.promotion_eligible,
                "deployment_authorized": self.deployment_authorized,
                "promotion_claim": self.promotion_claim,
            }
        )


@dataclass(frozen=True)
class PromotionQualificationResult:
    receipt: PromotionQualificationReceipt
    candidate_result: DetectorCandidateResult

    def __post_init__(self) -> None:
        if type(self.receipt) is not PromotionQualificationReceipt:
            raise ValueError(
                "promotion result receipt must be PromotionQualificationReceipt"
            )
        if type(self.candidate_result) is not DetectorCandidateResult:
            raise ValueError(
                "promotion result candidate_result must be DetectorCandidateResult"
            )
        if self.receipt.candidate_result_digest != canonical_digest(
            self.candidate_result.payload()
        ):
            raise ValueError(
                "promotion receipt/candidate result digest mismatch"
            )
        if (
            self.receipt.qualification_passed
            is not self.candidate_result.qualified
        ):
            raise ValueError(
                "promotion receipt qualification does not match candidate result"
            )


@dataclass(frozen=True, init=False)
class PromotionAttemptReceipt:
    study_id: str
    attempt_id: str
    plan_id: str
    plan_digest: str
    nomination_digest: str
    candidate_digest: str
    holdout_digest: str
    execution_binding_digest: str
    predecessor_attempt_digests: tuple[str, ...]
    status: BenchmarkAttemptStatus
    reveal_digest: str | None
    result_digest: str | None
    reason: str | None

    def __init__(
        self,
        *,
        study_id: str,
        attempt_id: str,
        plan_id: str,
        plan_digest: str,
        nomination_digest: str,
        candidate_digest: str,
        holdout_digest: str,
        execution_binding_digest: str,
        predecessor_attempt_digests: tuple[str, ...],
        status: BenchmarkAttemptStatus,
        reveal_digest: str | None,
        result_digest: str | None,
        reason: str | None,
        _attempt_token: object | None = None,
    ) -> None:
        if _attempt_token is not _ATTEMPT_TOKEN:
            raise ValueError(
                "PromotionAttemptReceipt must come from PromotionAttemptLedger"
            )
        object.__setattr__(self, "study_id", study_id)
        object.__setattr__(self, "attempt_id", attempt_id)
        object.__setattr__(self, "plan_id", plan_id)
        object.__setattr__(self, "plan_digest", plan_digest)
        object.__setattr__(self, "nomination_digest", nomination_digest)
        object.__setattr__(self, "candidate_digest", candidate_digest)
        object.__setattr__(self, "holdout_digest", holdout_digest)
        object.__setattr__(
            self,
            "execution_binding_digest",
            execution_binding_digest,
        )
        object.__setattr__(
            self,
            "predecessor_attempt_digests",
            predecessor_attempt_digests,
        )
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "reveal_digest", reveal_digest)
        object.__setattr__(self, "result_digest", result_digest)
        object.__setattr__(self, "reason", reason)
        self.__post_init__()

    def __post_init__(self) -> None:
        _nonempty(self.study_id, "promotion attempt study id")
        _nonempty(self.attempt_id, "promotion attempt id")
        _nonempty(self.plan_id, "promotion attempt plan id")
        for value, label in (
            (self.plan_digest, "promotion attempt plan digest"),
            (self.nomination_digest, "promotion attempt nomination digest"),
            (self.candidate_digest, "promotion attempt candidate digest"),
            (self.holdout_digest, "promotion attempt holdout digest"),
            (
                self.execution_binding_digest,
                "promotion attempt execution binding digest",
            ),
        ):
            require_sha256_digest(value, label)
        if (
            type(self.predecessor_attempt_digests) is not tuple
            or self.predecessor_attempt_digests
            != tuple(sorted(set(self.predecessor_attempt_digests)))
        ):
            raise ValueError(
                "promotion attempt predecessor digests must be canonical/unique"
            )
        for item in self.predecessor_attempt_digests:
            require_sha256_digest(item, "promotion attempt predecessor digest")
        if type(self.status) is not BenchmarkAttemptStatus:
            raise ValueError(
                "promotion attempt status must be exact BenchmarkAttemptStatus"
            )
        if self.reveal_digest is not None:
            require_sha256_digest(
                self.reveal_digest,
                "promotion attempt reveal digest",
            )
        if self.result_digest is not None:
            require_sha256_digest(
                self.result_digest,
                "promotion attempt result digest",
            )
        if self.status is BenchmarkAttemptStatus.SEALED:
            if self.reveal_digest is not None or self.result_digest is not None:
                raise ValueError("SEALED promotion attempt cannot have reveal/result")
            if self.reason is not None:
                raise ValueError("SEALED promotion attempt cannot have reason")
        elif self.status is BenchmarkAttemptStatus.REVEALED:
            if self.reveal_digest is None or self.result_digest is not None:
                raise ValueError(
                    "REVEALED promotion attempt requires reveal and no result"
                )
            if self.reason is not None:
                raise ValueError("REVEALED promotion attempt cannot have reason")
        elif self.status is BenchmarkAttemptStatus.EXECUTING:
            if self.reveal_digest is None or self.result_digest is not None:
                raise ValueError(
                    "EXECUTING promotion attempt requires reveal and no result"
                )
            if self.reason is not None:
                raise ValueError("EXECUTING promotion attempt cannot have reason")
        elif self.status is BenchmarkAttemptStatus.EXECUTED:
            if self.reveal_digest is None or self.result_digest is None:
                raise ValueError(
                    "EXECUTED promotion attempt requires reveal and result"
                )
            if self.reason is not None:
                raise ValueError("EXECUTED promotion attempt cannot have reason")
        else:
            if type(self.reason) is not str or not self.reason.strip():
                raise ValueError(
                    "terminal promotion attempt requires non-empty reason"
                )

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "schema": "DRIFTGUARD_PROMOTION_ATTEMPT_RECEIPT_V1",
                "study_id": self.study_id,
                "attempt_id": self.attempt_id,
                "plan_id": self.plan_id,
                "plan_digest": self.plan_digest,
                "nomination_digest": self.nomination_digest,
                "candidate_digest": self.candidate_digest,
                "holdout_digest": self.holdout_digest,
                "execution_binding_digest": self.execution_binding_digest,
                "predecessor_attempt_digests": list(
                    self.predecessor_attempt_digests
                ),
                "status": self.status.value,
                "reveal_digest": self.reveal_digest,
                "result_digest": self.result_digest,
                "reason": self.reason,
            }
        )


class PromotionAttemptLedger:
    def __init__(self, path: str) -> None:
        _nonempty(path, "promotion attempt ledger path")
        self.path = path
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS promotion_attempts (
                    attempt_id TEXT PRIMARY KEY,
                    study_id TEXT NOT NULL,
                    plan_id TEXT NOT NULL UNIQUE,
                    plan_digest TEXT NOT NULL,
                    nomination_digest TEXT NOT NULL,
                    candidate_digest TEXT NOT NULL,
                    holdout_digest TEXT NOT NULL,
                    execution_binding_digest TEXT NOT NULL,
                    predecessor_attempt_digests_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reveal_digest TEXT NULL,
                    result_digest TEXT NULL,
                    reason TEXT NULL
                )
                """
            )
            db.execute(
                """
                CREATE INDEX IF NOT EXISTS promotion_attempts_study_idx
                    ON promotion_attempts(study_id)
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS promotion_attempt_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    attempt_id TEXT NOT NULL,
                    study_id TEXT NOT NULL,
                    plan_digest TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reveal_digest TEXT NULL,
                    result_digest TEXT NULL,
                    reason TEXT NULL
                )
                """
            )

    @staticmethod
    def _row_to_receipt(row: sqlite3.Row) -> PromotionAttemptReceipt:
        predecessors = json_load_tuple(
            str(row["predecessor_attempt_digests_json"])
        )
        return PromotionAttemptReceipt(
            study_id=str(row["study_id"]),
            attempt_id=str(row["attempt_id"]),
            plan_id=str(row["plan_id"]),
            plan_digest=str(row["plan_digest"]),
            nomination_digest=str(row["nomination_digest"]),
            candidate_digest=str(row["candidate_digest"]),
            holdout_digest=str(row["holdout_digest"]),
            execution_binding_digest=str(
                row["execution_binding_digest"]
            ),
            predecessor_attempt_digests=predecessors,
            status=BenchmarkAttemptStatus(str(row["status"])),
            reveal_digest=(
                str(row["reveal_digest"])
                if row["reveal_digest"] is not None
                else None
            ),
            result_digest=(
                str(row["result_digest"])
                if row["result_digest"] is not None
                else None
            ),
            reason=(
                str(row["reason"])
                if row["reason"] is not None
                else None
            ),
            _attempt_token=_ATTEMPT_TOKEN,
        )

    @staticmethod
    def _append_event(
        db: sqlite3.Connection,
        *,
        receipt: PromotionAttemptReceipt,
    ) -> None:
        db.execute(
            """
            INSERT INTO promotion_attempt_events(
                attempt_id,study_id,plan_digest,status,
                reveal_digest,result_digest,reason
            ) VALUES(?,?,?,?,?,?,?)
            """,
            (
                receipt.attempt_id,
                receipt.study_id,
                receipt.plan_digest,
                receipt.status.value,
                receipt.reveal_digest,
                receipt.result_digest,
                receipt.reason,
            ),
        )

    def attempt_receipt(
        self,
        *,
        attempt_id: str,
    ) -> PromotionAttemptReceipt | None:
        _nonempty(attempt_id, "promotion attempt id")
        with closing(sqlite3.connect(self.path)) as db:
            db.row_factory = sqlite3.Row
            row = db.execute(
                "SELECT * FROM promotion_attempts WHERE attempt_id=?",
                (attempt_id,),
            ).fetchone()
        return self._row_to_receipt(row) if row is not None else None

    def study_attempts(
        self,
        *,
        study_id: str,
    ) -> tuple[PromotionAttemptReceipt, ...]:
        _nonempty(study_id, "promotion study id")
        with closing(sqlite3.connect(self.path)) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                """
                SELECT * FROM promotion_attempts
                 WHERE study_id=?
                 ORDER BY rowid
                """,
                (study_id,),
            ).fetchall()
        return tuple(self._row_to_receipt(row) for row in rows)

    def seal_plan(
        self,
        *,
        plan: PromotionQualificationPlan,
    ) -> PromotionAttemptReceipt:
        if type(plan) is not PromotionQualificationPlan:
            raise ValueError(
                "plan must be exact PromotionQualificationPlan"
            )
        plan.execution_binding.assert_runtime_sources_match()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT * FROM promotion_attempts WHERE attempt_id=?",
                (plan.attempt_id,),
            ).fetchone()
            if existing is not None:
                receipt = self._row_to_receipt(existing)
                if receipt.plan_digest != plan.digest:
                    raise ValueError(
                        "same promotion attempt id cannot bind divergent plan"
                    )
                return receipt

            by_plan = db.execute(
                "SELECT * FROM promotion_attempts WHERE plan_id=?",
                (plan.plan_id,),
            ).fetchone()
            if by_plan is not None:
                receipt = self._row_to_receipt(by_plan)
                if receipt.plan_digest != plan.digest:
                    raise ValueError(
                        "same promotion plan id cannot bind divergent plan"
                    )
                raise ValueError(
                    "promotion plan id is already registered to another attempt"
                )

            rows = db.execute(
                """
                SELECT * FROM promotion_attempts
                 WHERE study_id=?
                 ORDER BY rowid
                """,
                (plan.study_id,),
            ).fetchall()
            receipts = tuple(self._row_to_receipt(row) for row in rows)
            active = tuple(
                item
                for item in receipts
                if item.status
                in {
                    BenchmarkAttemptStatus.SEALED,
                    BenchmarkAttemptStatus.REVEALED,
                    BenchmarkAttemptStatus.EXECUTING,
                }
            )
            if active:
                raise ValueError(
                    "promotion study already has an active attempt"
                )
            expected_predecessors = tuple(
                sorted(item.digest for item in receipts)
            )
            if plan.predecessor_attempt_digests != expected_predecessors:
                raise ValueError(
                    "promotion successor must reference every prior terminal attempt"
                )
            prior_holdouts = {item.holdout_digest for item in receipts}
            if not prior_holdouts.issubset(
                set(plan.predecessor_holdout_digests)
            ):
                raise ValueError(
                    "promotion successor must disclose every prior promotion holdout"
                )

            db.execute(
                """
                INSERT INTO promotion_attempts(
                    attempt_id,study_id,plan_id,plan_digest,
                    nomination_digest,candidate_digest,holdout_digest,
                    execution_binding_digest,
                    predecessor_attempt_digests_json,status,
                    reveal_digest,result_digest,reason
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    plan.attempt_id,
                    plan.study_id,
                    plan.plan_id,
                    plan.digest,
                    plan.nomination.digest,
                    plan.candidate.digest,
                    plan.qualification_manifest.corpus_digest,
                    plan.execution_binding.digest,
                    encode_tuple(plan.predecessor_attempt_digests),
                    BenchmarkAttemptStatus.SEALED.value,
                    None,
                    None,
                    None,
                ),
            )
            row = db.execute(
                "SELECT * FROM promotion_attempts WHERE attempt_id=?",
                (plan.attempt_id,),
            ).fetchone()
            receipt = self._row_to_receipt(row)
            self._append_event(db, receipt=receipt)
            return receipt

    def _assert_exact_plan(
        self,
        *,
        plan: PromotionQualificationPlan,
        status: BenchmarkAttemptStatus,
    ) -> PromotionAttemptReceipt:
        receipt = self.attempt_receipt(attempt_id=plan.attempt_id)
        if receipt is None:
            raise ValueError(
                "promotion attempt must be durably sealed before use"
            )
        if receipt.study_id != plan.study_id:
            raise ValueError("promotion attempt study id mismatch")
        if receipt.plan_id != plan.plan_id:
            raise ValueError("promotion attempt plan id mismatch")
        if receipt.plan_digest != plan.digest:
            raise ValueError("promotion attempt plan digest mismatch")
        if receipt.nomination_digest != plan.nomination.digest:
            raise ValueError("promotion attempt nomination digest mismatch")
        if receipt.candidate_digest != plan.candidate.digest:
            raise ValueError("promotion attempt candidate digest mismatch")
        if (
            receipt.holdout_digest
            != plan.qualification_manifest.corpus_digest
        ):
            raise ValueError("promotion attempt holdout digest mismatch")
        if (
            receipt.execution_binding_digest
            != plan.execution_binding.digest
        ):
            raise ValueError(
                "promotion attempt execution binding mismatch"
            )
        if receipt.status is not status:
            raise ValueError(
                f"promotion attempt must be {status.value}"
            )
        return receipt

    def mark_revealed(
        self,
        *,
        plan: PromotionQualificationPlan,
        reveal: PromotionRevealReceipt,
    ) -> PromotionAttemptReceipt:
        current = self._assert_exact_plan(
            plan=plan,
            status=BenchmarkAttemptStatus.SEALED,
        )
        if reveal.study_id != plan.study_id:
            raise ValueError("promotion reveal study id mismatch")
        if reveal.attempt_id != plan.attempt_id:
            raise ValueError("promotion reveal attempt id mismatch")
        if reveal.plan_digest != plan.digest:
            raise ValueError("promotion reveal plan digest mismatch")
        if (
            reveal.execution_binding_digest
            != plan.execution_binding.digest
        ):
            raise ValueError("promotion reveal execution binding mismatch")
        if (
            reveal.corpus_digest
            != plan.qualification_manifest.corpus_digest
        ):
            raise ValueError("promotion reveal corpus digest mismatch")
        with closing(sqlite3.connect(self.path)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN IMMEDIATE")
            updated = db.execute(
                """
                UPDATE promotion_attempts
                   SET status=?, reveal_digest=?
                 WHERE attempt_id=?
                   AND plan_digest=?
                   AND status=?
                   AND reveal_digest IS NULL
                   AND result_digest IS NULL
                """,
                (
                    BenchmarkAttemptStatus.REVEALED.value,
                    reveal.digest,
                    plan.attempt_id,
                    plan.digest,
                    BenchmarkAttemptStatus.SEALED.value,
                ),
            )
            if updated.rowcount != 1:
                raise ValueError(
                    "promotion reveal is single-use or attempt is stale"
                )
            row = db.execute(
                "SELECT * FROM promotion_attempts WHERE attempt_id=?",
                (plan.attempt_id,),
            ).fetchone()
            receipt = self._row_to_receipt(row)
            self._append_event(db, receipt=receipt)
            return receipt

    def begin_execution(
        self,
        *,
        plan: PromotionQualificationPlan,
        reveal: PromotionRevealReceipt,
    ) -> PromotionAttemptReceipt:
        current = self._assert_exact_plan(
            plan=plan,
            status=BenchmarkAttemptStatus.REVEALED,
        )
        if current.reveal_digest != reveal.digest:
            raise ValueError("promotion attempt reveal digest mismatch")
        with closing(sqlite3.connect(self.path)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN IMMEDIATE")
            updated = db.execute(
                """
                UPDATE promotion_attempts
                   SET status=?
                 WHERE attempt_id=?
                   AND plan_digest=?
                   AND status=?
                   AND reveal_digest=?
                   AND result_digest IS NULL
                """,
                (
                    BenchmarkAttemptStatus.EXECUTING.value,
                    plan.attempt_id,
                    plan.digest,
                    BenchmarkAttemptStatus.REVEALED.value,
                    reveal.digest,
                ),
            )
            if updated.rowcount != 1:
                raise ValueError(
                    "promotion execution is single-use or attempt is stale"
                )
            row = db.execute(
                "SELECT * FROM promotion_attempts WHERE attempt_id=?",
                (plan.attempt_id,),
            ).fetchone()
            receipt = self._row_to_receipt(row)
            self._append_event(db, receipt=receipt)
            return receipt

    def mark_executed(
        self,
        *,
        plan: PromotionQualificationPlan,
        reveal: PromotionRevealReceipt,
        result: PromotionQualificationReceipt,
    ) -> PromotionAttemptReceipt:
        current = self._assert_exact_plan(
            plan=plan,
            status=BenchmarkAttemptStatus.EXECUTING,
        )
        if current.reveal_digest != reveal.digest:
            raise ValueError("promotion execution reveal digest mismatch")
        if result.study_id != plan.study_id:
            raise ValueError("promotion result study id mismatch")
        if result.attempt_id != plan.attempt_id:
            raise ValueError("promotion result attempt id mismatch")
        if result.plan_digest != plan.digest:
            raise ValueError("promotion result plan digest mismatch")
        if result.nomination_digest != plan.nomination.digest:
            raise ValueError("promotion result nomination digest mismatch")
        if result.candidate_digest != plan.candidate.digest:
            raise ValueError("promotion result candidate digest mismatch")
        if result.reveal_digest != reveal.digest:
            raise ValueError("promotion result reveal digest mismatch")
        with closing(sqlite3.connect(self.path)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN IMMEDIATE")
            updated = db.execute(
                """
                UPDATE promotion_attempts
                   SET status=?, result_digest=?
                 WHERE attempt_id=?
                   AND plan_digest=?
                   AND status=?
                   AND reveal_digest=?
                   AND result_digest IS NULL
                """,
                (
                    BenchmarkAttemptStatus.EXECUTED.value,
                    result.digest,
                    plan.attempt_id,
                    plan.digest,
                    BenchmarkAttemptStatus.EXECUTING.value,
                    reveal.digest,
                ),
            )
            if updated.rowcount != 1:
                raise ValueError(
                    "promotion completion is stale or already consumed"
                )
            row = db.execute(
                "SELECT * FROM promotion_attempts WHERE attempt_id=?",
                (plan.attempt_id,),
            ).fetchone()
            receipt = self._row_to_receipt(row)
            self._append_event(db, receipt=receipt)
            return receipt

    def abort_attempt(
        self,
        *,
        attempt_id: str,
        reason: str,
    ) -> PromotionAttemptReceipt:
        _nonempty(reason, "promotion abort reason")
        with closing(sqlite3.connect(self.path)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM promotion_attempts WHERE attempt_id=?",
                (attempt_id,),
            ).fetchone()
            if row is None:
                raise ValueError("promotion attempt not found")
            current = self._row_to_receipt(row)
            if current.status is BenchmarkAttemptStatus.EXECUTING:
                raise ValueError(
                    "EXECUTING promotion attempt cannot be operator-aborted"
                )
            if current.status not in {
                BenchmarkAttemptStatus.SEALED,
                BenchmarkAttemptStatus.REVEALED,
            }:
                raise ValueError(
                    "only pre-execution promotion attempt can be aborted"
                )
            db.execute(
                """
                UPDATE promotion_attempts
                   SET status=?, reason=?
                 WHERE attempt_id=?
                """,
                (
                    BenchmarkAttemptStatus.ABORTED.value,
                    reason,
                    attempt_id,
                ),
            )
            row = db.execute(
                "SELECT * FROM promotion_attempts WHERE attempt_id=?",
                (attempt_id,),
            ).fetchone()
            receipt = self._row_to_receipt(row)
            self._append_event(db, receipt=receipt)
            return receipt

    def _invalidate_semantic_failure(
        self,
        *,
        plan: PromotionQualificationPlan,
        reveal: PromotionRevealReceipt,
        reason: str,
        _failure_token: object | None = None,
    ) -> PromotionAttemptReceipt:
        if _failure_token is not _SEMANTIC_FAILURE_TOKEN:
            raise ValueError(
                "promotion semantic invalidation requires governed execution capability"
            )
        _nonempty(reason, "promotion semantic failure reason")
        plan.execution_binding.assert_runtime_sources_match()
        current = self._assert_exact_plan(
            plan=plan,
            status=BenchmarkAttemptStatus.EXECUTING,
        )
        if current.reveal_digest != reveal.digest:
            raise ValueError("promotion semantic failure reveal mismatch")
        with closing(sqlite3.connect(self.path)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN IMMEDIATE")
            updated = db.execute(
                """
                UPDATE promotion_attempts
                   SET status=?, reason=?
                 WHERE attempt_id=?
                   AND plan_digest=?
                   AND status=?
                   AND reveal_digest=?
                   AND result_digest IS NULL
                """,
                (
                    BenchmarkAttemptStatus.INVALIDATED.value,
                    reason,
                    plan.attempt_id,
                    plan.digest,
                    BenchmarkAttemptStatus.EXECUTING.value,
                    reveal.digest,
                ),
            )
            if updated.rowcount != 1:
                raise ValueError(
                    "promotion semantic invalidation is stale or mismatched"
                )
            row = db.execute(
                "SELECT * FROM promotion_attempts WHERE attempt_id=?",
                (plan.attempt_id,),
            ).fetchone()
            receipt = self._row_to_receipt(row)
            self._append_event(db, receipt=receipt)
            return receipt


def encode_tuple(values: tuple[str, ...]) -> str:
    import json

    return json.dumps(list(values), separators=(",", ":"))


def json_load_tuple(value: str) -> tuple[str, ...]:
    import json

    raw = json.loads(value)
    if type(raw) is not list or any(type(item) is not str for item in raw):
        raise ValueError("stored promotion predecessor digests are invalid")
    return tuple(raw)


def reveal_promotion_holdout(
    *,
    registry: PromotionAttemptLedger,
    plan: PromotionQualificationPlan,
    execution_binding: PromotionExecutionBinding,
    manifest: BenchmarkCorpusManifest,
    corpus: CalibrationCorpus,
    artifact_bytes: bytes,
) -> PromotionRevealReceipt:
    if type(registry) is not PromotionAttemptLedger:
        raise ValueError("registry must be exact PromotionAttemptLedger")
    if type(plan) is not PromotionQualificationPlan:
        raise ValueError("plan must be exact PromotionQualificationPlan")
    if execution_binding != plan.execution_binding:
        raise ValueError("promotion reveal execution binding mismatch")
    execution_binding.assert_runtime_sources_match()
    registry._assert_exact_plan(
        plan=plan,
        status=BenchmarkAttemptStatus.SEALED,
    )
    if type(manifest) is not BenchmarkCorpusManifest:
        raise ValueError("manifest must be exact BenchmarkCorpusManifest")
    if manifest.digest != plan.qualification_manifest.digest:
        raise ValueError("promotion reveal manifest digest mismatch")
    if type(corpus) is not CalibrationCorpus:
        raise ValueError("corpus must be exact CalibrationCorpus")
    manifest.validate_corpus(corpus)
    expected_bytes = canonical_corpus_artifact_bytes(corpus)
    if artifact_bytes != expected_bytes:
        raise ValueError(
            "promotion holdout bytes do not canonically encode corpus"
        )
    artifact_digest = sha256(artifact_bytes).hexdigest()
    if artifact_digest != manifest.artifact_digest:
        raise ValueError("promotion holdout artifact digest mismatch")
    receipt = PromotionRevealReceipt(
        study_id=plan.study_id,
        attempt_id=plan.attempt_id,
        plan_digest=plan.digest,
        execution_binding_digest=execution_binding.digest,
        manifest_digest=manifest.digest,
        corpus_digest=corpus.digest,
        artifact_digest=artifact_digest,
        _reveal_token=_REVEAL_TOKEN,
    )
    registry.mark_revealed(plan=plan, reveal=receipt)
    return receipt


def qualify_promotion_candidate(
    *,
    registry: PromotionAttemptLedger,
    plan: PromotionQualificationPlan,
    execution_binding: PromotionExecutionBinding,
    reveal: PromotionRevealReceipt,
    corpus: CalibrationCorpus,
    cusum_spec: SequentialDetectorSpec,
) -> PromotionQualificationResult:
    if type(registry) is not PromotionAttemptLedger:
        raise ValueError("registry must be exact PromotionAttemptLedger")
    if type(plan) is not PromotionQualificationPlan:
        raise ValueError("plan must be exact PromotionQualificationPlan")
    if execution_binding != plan.execution_binding:
        raise ValueError("promotion execution binding mismatch")
    execution_binding.assert_runtime_sources_match()
    current = registry._assert_exact_plan(
        plan=plan,
        status=BenchmarkAttemptStatus.REVEALED,
    )
    if current.reveal_digest != reveal.digest:
        raise ValueError("promotion durable reveal digest mismatch")
    if reveal.plan_digest != plan.digest:
        raise ValueError("promotion reveal/plan digest mismatch")
    if reveal.corpus_digest != corpus.digest:
        raise ValueError("promotion reveal/corpus digest mismatch")
    plan.qualification_manifest.validate_corpus(corpus)
    if cusum_spec.digest != plan.reference_cusum_spec_digest:
        raise ValueError("promotion reference CUSUM spec digest mismatch")

    registry.begin_execution(plan=plan, reveal=reveal)
    try:
        result = qualify_detector_candidate(
            candidate=plan.candidate,
            calibration_plan=plan.calibration_plan,
            corpus=corpus,
            cusum_spec=cusum_spec,
        )
        result_digest = canonical_digest(result.payload())
        receipt = PromotionQualificationReceipt(
            study_id=plan.study_id,
            attempt_id=plan.attempt_id,
            plan_digest=plan.digest,
            nomination_digest=plan.nomination.digest,
            candidate_digest=plan.candidate.digest,
            reveal_digest=reveal.digest,
            candidate_result_digest=result_digest,
            qualification_passed=result.qualified,
            promotion_eligible=result.qualified,
            deployment_authorized=False,
            promotion_claim=PROMOTION_CLAIM,
            _qualification_token=_QUALIFICATION_TOKEN,
        )
        output = PromotionQualificationResult(
            receipt=receipt,
            candidate_result=result,
        )
    except Exception as exc:
        registry._invalidate_semantic_failure(
            plan=plan,
            reveal=reveal,
            reason=f"promotion_semantic_failure:{type(exc).__name__}",
            _failure_token=_SEMANTIC_FAILURE_TOKEN,
        )
        raise

    registry.mark_executed(
        plan=plan,
        reveal=reveal,
        result=receipt,
    )
    return output


__all__ = [
    "CandidateNominationReceipt",
    "PROMOTION_CLAIM",
    "PromotionAttemptLedger",
    "PromotionAttemptReceipt",
    "PromotionExecutionBinding",
    "PromotionQualificationPlan",
    "PromotionQualificationReceipt",
    "PromotionQualificationResult",
    "PromotionRevealReceipt",
    "SELECTION_CLAIM",
    "current_promotion_execution_binding",
    "nominate_candidate",
    "qualify_promotion_candidate",
    "reveal_promotion_holdout",
]
