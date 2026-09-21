from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
import inspect
import json
from pathlib import Path
import sqlite3
from typing import Any

from .calibration import (
    CalibrationCorpus,
    CalibrationCorpusRole,
    CalibrationFamilyPolicy,
    CalibrationPlan,
)
from .comparison import (
    DetectorAlgorithm,
    DetectorCandidate,
    DetectorComparisonPlan,
    DetectorComparisonReceipt,
    compare_detectors,
)
from .model import SourceBinding, canonical_digest, require_sha256_digest
from .sequential import SequentialDetectorSpec


_REVEAL_RECEIPT_TOKEN = object()
_RUN_RECEIPT_TOKEN = object()
_ATTEMPT_RECEIPT_TOKEN = object()


def _nonempty(value: Any, label: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{label} must be a non-empty exact string")
    return value


def trajectory_content_digest(corpus: CalibrationCorpus) -> str:
    if type(corpus) is not CalibrationCorpus:
        raise ValueError("corpus must be exact CalibrationCorpus")
    return canonical_digest(
        {
            "schema": "DRIFTGUARD_BENCHMARK_TRAJECTORY_CONTENT_V1",
            "trajectories": [
                item.payload()
                for item in sorted(
                    corpus.trajectories,
                    key=lambda row: row.trajectory_id,
                )
            ],
        }
    )


def canonical_corpus_artifact_bytes(corpus: CalibrationCorpus) -> bytes:
    if type(corpus) is not CalibrationCorpus:
        raise ValueError("corpus must be exact CalibrationCorpus")
    return json.dumps(
        corpus.payload(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


class BenchmarkPhenomenon(StrEnum):
    STABLE_LOW_NOISE = "STABLE_LOW_NOISE"
    STABLE_AUTOCORRELATED = "STABLE_AUTOCORRELATED"
    STABLE_HEAVY_TAIL = "STABLE_HEAVY_TAIL"
    CONTEXT_STRESS = "CONTEXT_STRESS"
    EVALUATOR_SHIFT = "EVALUATOR_SHIFT"
    SUBJECT_BEHAVIOR_SHIFT = "SUBJECT_BEHAVIOR_SHIFT"
    NON_TARGET_DISTRIBUTION_SHIFT = "NON_TARGET_DISTRIBUTION_SHIFT"
    MIXED_TARGET_COLLATERAL_SHIFT = "MIXED_TARGET_COLLATERAL_SHIFT"


CORE_R11_PHENOMENA = frozenset(BenchmarkPhenomenon)
CORE_R11_COVERAGE_PROFILE = "DRIFTGUARD_R11_CORE_V1"
PRECOMMIT_CLAIM = "DIGEST_PRECOMMIT_NOT_PROOF_OF_NONACCESS_OR_TRUSTED_TIME"
REVEAL_CLAIM = "EXACT_DIGEST_REVEAL_MATCH_NOT_NONACCESS_PROOF"
RUN_CLAIM = "PRECOMMITTED_COMPARISON_EXECUTED_NO_SELECTION_OR_PROMOTION_AUTHORITY"
SELECTION_RULE = "COMPARE_ONLY_NO_PROMOTION"


@dataclass(frozen=True)
class BenchmarkExecutionBinding:
    repository: str
    commit_sha: str
    schema_version: str
    benchmark_source_digest: str
    calibration_source_digest: str
    comparison_source_digest: str
    sequential_source_digest: str

    def __post_init__(self) -> None:
        _nonempty(self.repository, "benchmark execution repository")
        _nonempty(self.schema_version, "benchmark execution schema version")
        if (
            type(self.commit_sha) is not str
            or len(self.commit_sha) != 40
            or any(ch not in "0123456789abcdef" for ch in self.commit_sha.lower())
        ):
            raise ValueError(
                "benchmark execution commit_sha must be an exact 40-hex Git SHA"
            )
        for value, label in (
            (self.benchmark_source_digest, "benchmark.py source digest"),
            (self.calibration_source_digest, "calibration.py source digest"),
            (self.comparison_source_digest, "comparison.py source digest"),
            (self.sequential_source_digest, "sequential.py source digest"),
        ):
            require_sha256_digest(value, label)

    def payload(self) -> dict[str, Any]:
        return {
            "schema": "DRIFTGUARD_BENCHMARK_EXECUTION_BINDING_V1",
            "repository": self.repository,
            "commit_sha": self.commit_sha,
            "schema_version": self.schema_version,
            "benchmark_source_digest": self.benchmark_source_digest,
            "calibration_source_digest": self.calibration_source_digest,
            "comparison_source_digest": self.comparison_source_digest,
            "sequential_source_digest": self.sequential_source_digest,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.payload())

    def assert_runtime_sources_match(self) -> None:
        observed = runtime_source_digests()
        expected = (
            self.benchmark_source_digest,
            self.calibration_source_digest,
            self.comparison_source_digest,
            self.sequential_source_digest,
        )
        if observed != expected:
            raise ValueError(
                "benchmark runtime source digests do not match precommitted execution binding"
            )


def _source_digest_for_object(value: object) -> str:
    path = inspect.getsourcefile(value)
    if path is None:
        raise ValueError("cannot resolve source file for execution binding")
    return sha256(Path(path).read_bytes()).hexdigest()


def runtime_source_digests() -> tuple[str, str, str, str]:
    return (
        sha256(Path(__file__).read_bytes()).hexdigest(),
        _source_digest_for_object(CalibrationCorpus),
        _source_digest_for_object(DetectorCandidate),
        _source_digest_for_object(SequentialDetectorSpec),
    )


def current_execution_binding(
    *,
    repository: str,
    commit_sha: str,
    schema_version: str = "DRIFTGUARD_R11_ATTEMPT_GOVERNANCE_V2",
) -> BenchmarkExecutionBinding:
    (
        benchmark_digest,
        calibration_digest,
        comparison_digest,
        sequential_digest,
    ) = runtime_source_digests()
    return BenchmarkExecutionBinding(
        repository=repository,
        commit_sha=commit_sha,
        schema_version=schema_version,
        benchmark_source_digest=benchmark_digest,
        calibration_source_digest=calibration_digest,
        comparison_source_digest=comparison_digest,
        sequential_source_digest=sequential_digest,
    )


@dataclass(frozen=True, order=True)
class BenchmarkFamilyManifest:
    family_id: str
    phenomenon: BenchmarkPhenomenon
    provenance: SourceBinding
    provenance_digest: str
    dimension_ids: tuple[str, ...]
    expected_shift_dimensions: tuple[str, ...]

    def __post_init__(self) -> None:
        _nonempty(self.family_id, "benchmark family id")
        if type(self.phenomenon) is not BenchmarkPhenomenon:
            raise ValueError(
                "benchmark phenomenon must be exact BenchmarkPhenomenon"
            )
        if type(self.provenance) is not SourceBinding:
            raise ValueError(
                "benchmark family provenance must be exact SourceBinding"
            )
        require_sha256_digest(
            self.provenance_digest,
            "benchmark family provenance digest",
        )
        if (
            type(self.dimension_ids) is not tuple
            or not self.dimension_ids
            or any(type(item) is not str or not item for item in self.dimension_ids)
            or len(self.dimension_ids) != len(set(self.dimension_ids))
        ):
            raise ValueError(
                "benchmark dimension_ids must be a non-empty unique string tuple"
            )
        if tuple(sorted(self.dimension_ids)) != self.dimension_ids:
            raise ValueError("benchmark dimension_ids must be canonical/sorted")
        if (
            type(self.expected_shift_dimensions) is not tuple
            or not self.expected_shift_dimensions
            or any(
                type(item) is not str or not item
                for item in self.expected_shift_dimensions
            )
            or len(self.expected_shift_dimensions)
            != len(set(self.expected_shift_dimensions))
        ):
            raise ValueError(
                "expected_shift_dimensions must be a non-empty unique string tuple"
            )
        if tuple(sorted(self.expected_shift_dimensions)) != (
            self.expected_shift_dimensions
        ):
            raise ValueError(
                "expected_shift_dimensions must be canonical/sorted"
            )
        if not set(self.expected_shift_dimensions).issubset(
            set(self.dimension_ids)
        ):
            raise ValueError(
                "expected shift dimensions must exist in benchmark dimensions"
            )

    def contract_payload(self) -> dict[str, Any]:
        return {
            "family_id": self.family_id,
            "phenomenon": self.phenomenon.value,
            "dimension_ids": list(self.dimension_ids),
            "expected_shift_dimensions": list(
                self.expected_shift_dimensions
            ),
        }

    def payload(self) -> dict[str, Any]:
        return {
            **self.contract_payload(),
            "provenance": {
                "ref": self.provenance.ref,
                "version": self.provenance.version,
            },
            "provenance_digest": self.provenance_digest,
        }


@dataclass(frozen=True)
class BenchmarkCorpusManifest:
    manifest_id: str
    corpus_id: str
    corpus_version: str
    corpus_role: CalibrationCorpusRole
    corpus_digest: str
    trajectory_content_digest: str
    artifact: SourceBinding
    artifact_digest: str
    families: tuple[BenchmarkFamilyManifest, ...]
    coverage_profile: str = CORE_R11_COVERAGE_PROFILE

    def __post_init__(self) -> None:
        _nonempty(self.manifest_id, "benchmark manifest id")
        _nonempty(self.corpus_id, "benchmark corpus id")
        _nonempty(self.corpus_version, "benchmark corpus version")
        if type(self.corpus_role) is not CalibrationCorpusRole:
            raise ValueError(
                "benchmark corpus role must be exact CalibrationCorpusRole"
            )
        require_sha256_digest(
            self.corpus_digest,
            "benchmark corpus digest",
        )
        require_sha256_digest(
            self.trajectory_content_digest,
            "benchmark trajectory content digest",
        )
        if type(self.artifact) is not SourceBinding:
            raise ValueError("benchmark artifact must be exact SourceBinding")
        require_sha256_digest(
            self.artifact_digest,
            "benchmark artifact digest",
        )
        if type(self.families) is not tuple or not self.families:
            raise ValueError(
                "benchmark families must be a non-empty tuple"
            )
        if any(type(item) is not BenchmarkFamilyManifest for item in self.families):
            raise ValueError(
                "benchmark families must contain exact BenchmarkFamilyManifest"
            )
        ids = [item.family_id for item in self.families]
        if ids != sorted(ids) or len(ids) != len(set(ids)):
            raise ValueError(
                "benchmark family ids must be unique and canonical/sorted"
            )
        phenomena = [item.phenomenon for item in self.families]
        if len(phenomena) != len(set(phenomena)):
            raise ValueError(
                "benchmark core profile permits one family per phenomenon"
            )
        if self.coverage_profile != CORE_R11_COVERAGE_PROFILE:
            raise ValueError("unsupported benchmark coverage profile")
        if set(phenomena) != set(CORE_R11_PHENOMENA):
            raise ValueError(
                "R11 core benchmark must cover every required phenomenon exactly once"
            )
        dimension_sets = {item.dimension_ids for item in self.families}
        if len(dimension_sets) != 1:
            raise ValueError(
                "all benchmark families must use one exact detector dimension set"
            )

    @property
    def dimension_ids(self) -> tuple[str, ...]:
        return self.families[0].dimension_ids

    @property
    def portfolio_digest(self) -> str:
        return canonical_digest(
            {
                "schema": "DRIFTGUARD_BENCHMARK_PORTFOLIO_V1",
                "coverage_profile": self.coverage_profile,
                "families": [
                    item.contract_payload() for item in self.families
                ],
            }
        )

    def payload(self) -> dict[str, Any]:
        return {
            "schema": "DRIFTGUARD_BENCHMARK_CORPUS_MANIFEST_V1",
            "manifest_id": self.manifest_id,
            "corpus_id": self.corpus_id,
            "corpus_version": self.corpus_version,
            "corpus_role": self.corpus_role.value,
            "corpus_digest": self.corpus_digest,
            "trajectory_content_digest": self.trajectory_content_digest,
            "artifact": {
                "ref": self.artifact.ref,
                "version": self.artifact.version,
            },
            "artifact_digest": self.artifact_digest,
            "coverage_profile": self.coverage_profile,
            "families": [item.payload() for item in self.families],
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.payload())

    def validate_corpus(self, corpus: CalibrationCorpus) -> None:
        if type(corpus) is not CalibrationCorpus:
            raise ValueError("benchmark corpus must be exact CalibrationCorpus")
        if corpus.corpus_id != self.corpus_id:
            raise ValueError("benchmark corpus id mismatch")
        if corpus.version != self.corpus_version:
            raise ValueError("benchmark corpus version mismatch")
        if corpus.role is not self.corpus_role:
            raise ValueError("benchmark corpus role mismatch")
        if corpus.digest != self.corpus_digest:
            raise ValueError("benchmark corpus digest mismatch")
        if trajectory_content_digest(corpus) != self.trajectory_content_digest:
            raise ValueError(
                "benchmark trajectory content digest mismatch"
            )

        by_family = {item.family_id: item for item in self.families}
        observed_families = {item.family_id for item in corpus.trajectories}
        if observed_families != set(by_family):
            raise ValueError(
                "benchmark corpus family set must exactly match manifest"
            )
        for trajectory in corpus.trajectories:
            family = by_family[trajectory.family_id]
            for sample in trajectory.samples:
                dimensions = tuple(sorted(item[0] for item in sample))
                if dimensions != family.dimension_ids:
                    raise ValueError(
                        "benchmark trajectory dimension set does not match manifest"
                    )
            if trajectory.shift_index is not None:
                if tuple(sorted(trajectory.shift_dimensions)) != (
                    family.expected_shift_dimensions
                ):
                    raise ValueError(
                        "benchmark trajectory shift dimensions do not match manifest"
                    )


@dataclass(frozen=True)
class HoldoutCorpusSeal:
    seal_id: str
    manifest: BenchmarkCorpusManifest
    seal_claim: str = PRECOMMIT_CLAIM

    def __post_init__(self) -> None:
        _nonempty(self.seal_id, "holdout seal id")
        if type(self.manifest) is not BenchmarkCorpusManifest:
            raise ValueError(
                "holdout seal manifest must be exact BenchmarkCorpusManifest"
            )
        if self.manifest.corpus_role is not CalibrationCorpusRole.HOLDOUT_QUALIFICATION:
            raise ValueError(
                "holdout seal requires HOLDOUT_QUALIFICATION manifest"
            )
        if self.seal_claim != PRECOMMIT_CLAIM:
            raise ValueError("unsupported holdout seal claim")

    def payload(self) -> dict[str, Any]:
        return {
            "schema": "DRIFTGUARD_HOLDOUT_CORPUS_SEAL_V1",
            "seal_id": self.seal_id,
            "manifest_digest": self.manifest.digest,
            "portfolio_digest": self.manifest.portfolio_digest,
            "corpus_digest": self.manifest.corpus_digest,
            "trajectory_content_digest": (
                self.manifest.trajectory_content_digest
            ),
            "artifact": {
                "ref": self.manifest.artifact.ref,
                "version": self.manifest.artifact.version,
            },
            "artifact_digest": self.manifest.artifact_digest,
            "seal_claim": self.seal_claim,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.payload())


@dataclass(frozen=True)
class BenchmarkPrecommitPlan:
    study_id: str
    attempt_id: str
    precommit_id: str
    predecessor_attempt_digests: tuple[str, ...]
    predecessor_holdout_digests: tuple[str, ...]
    execution_binding: BenchmarkExecutionBinding
    design_manifest: BenchmarkCorpusManifest
    holdout_seal: HoldoutCorpusSeal
    cusum_spec_digest: str
    family_policies: tuple[CalibrationFamilyPolicy, ...]
    candidates: tuple[DetectorCandidate, ...]
    calibration_plan_id: str
    comparison_id: str
    precommit_artifact: SourceBinding
    precommit_artifact_digest: str
    selection_rule: str = SELECTION_RULE
    precommit_claim: str = PRECOMMIT_CLAIM

    def __post_init__(self) -> None:
        _nonempty(self.study_id, "benchmark study id")
        _nonempty(self.attempt_id, "benchmark attempt id")
        _nonempty(self.precommit_id, "benchmark precommit id")
        if (
            type(self.predecessor_attempt_digests) is not tuple
            or any(
                type(item) is not str
                for item in self.predecessor_attempt_digests
            )
            or self.predecessor_attempt_digests
            != tuple(sorted(set(self.predecessor_attempt_digests)))
        ):
            raise ValueError(
                "predecessor attempt digests must be a canonical unique tuple"
            )
        for item in self.predecessor_attempt_digests:
            require_sha256_digest(item, "predecessor attempt digest")
        if (
            type(self.predecessor_holdout_digests) is not tuple
            or not self.predecessor_holdout_digests
            or any(
                type(item) is not str
                for item in self.predecessor_holdout_digests
            )
            or self.predecessor_holdout_digests
            != tuple(sorted(set(self.predecessor_holdout_digests)))
        ):
            raise ValueError(
                "predecessor holdout digests must be a non-empty canonical unique tuple"
            )
        for item in self.predecessor_holdout_digests:
            require_sha256_digest(item, "predecessor holdout digest")
        if type(self.execution_binding) is not BenchmarkExecutionBinding:
            raise ValueError(
                "execution_binding must be exact BenchmarkExecutionBinding"
            )
        if type(self.design_manifest) is not BenchmarkCorpusManifest:
            raise ValueError(
                "design manifest must be exact BenchmarkCorpusManifest"
            )
        if self.design_manifest.corpus_role is not CalibrationCorpusRole.DESIGN:
            raise ValueError("benchmark precommit requires DESIGN manifest")
        if type(self.holdout_seal) is not HoldoutCorpusSeal:
            raise ValueError("holdout_seal must be exact HoldoutCorpusSeal")
        if (
            self.holdout_seal.manifest.corpus_digest
            in self.predecessor_holdout_digests
        ):
            raise ValueError(
                "R11 holdout cannot reuse a predecessor R9/R10 or prior-attempt holdout"
            )
        if (
            self.design_manifest.portfolio_digest
            != self.holdout_seal.manifest.portfolio_digest
        ):
            raise ValueError(
                "design and holdout benchmark portfolio contracts must match"
            )
        if (
            self.design_manifest.trajectory_content_digest
            == self.holdout_seal.manifest.trajectory_content_digest
        ):
            raise ValueError(
                "design and holdout cannot reuse identical trajectory content"
            )
        if (
            self.design_manifest.artifact_digest
            == self.holdout_seal.manifest.artifact_digest
            or self.design_manifest.artifact
            == self.holdout_seal.manifest.artifact
        ):
            raise ValueError(
                "design and holdout must bind distinct corpus artifacts"
            )
        require_sha256_digest(
            self.cusum_spec_digest,
            "benchmark CUSUM spec digest",
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
                "benchmark family policies must contain exact CalibrationFamilyPolicy"
            )
        policy_ids = [item.family_id for item in self.family_policies]
        expected_ids = [item.family_id for item in self.holdout_seal.manifest.families]
        if policy_ids != sorted(policy_ids) or len(policy_ids) != len(set(policy_ids)):
            raise ValueError(
                "benchmark family policy ids must be unique and canonical"
            )
        if policy_ids != expected_ids:
            raise ValueError(
                "benchmark family policies must exactly match holdout families"
            )
        if (
            type(self.candidates) is not tuple
            or len(self.candidates) != len(DetectorAlgorithm)
            or any(type(item) is not DetectorCandidate for item in self.candidates)
        ):
            raise ValueError(
                "benchmark candidates must contain exact R10 candidate set"
            )
        candidate_ids = [item.candidate_id for item in self.candidates]
        if candidate_ids != sorted(candidate_ids):
            raise ValueError(
                "benchmark candidates must be canonical/sorted by candidate id"
            )
        cusum_candidates = tuple(
            item
            for item in self.candidates
            if item.algorithm is DetectorAlgorithm.CUSUM
        )
        if len(cusum_candidates) != 1:
            raise ValueError("benchmark requires one exact CUSUM candidate")
        if cusum_candidates[0].cusum_spec_digest != self.cusum_spec_digest:
            raise ValueError(
                "benchmark CUSUM candidate/spec digest mismatch"
            )
        _nonempty(self.calibration_plan_id, "benchmark calibration plan id")
        _nonempty(self.comparison_id, "benchmark comparison id")
        if type(self.precommit_artifact) is not SourceBinding:
            raise ValueError(
                "benchmark precommit artifact must be exact SourceBinding"
            )
        require_sha256_digest(
            self.precommit_artifact_digest,
            "benchmark precommit artifact digest",
        )
        if self.selection_rule != SELECTION_RULE:
            raise ValueError("unsupported benchmark selection rule")
        if self.precommit_claim != PRECOMMIT_CLAIM:
            raise ValueError("unsupported benchmark precommit claim")

        # Constructor validation of the exact future R9/R10 plans is itself
        # part of the precommit subject.
        _ = self.holdout_calibration_plan
        _ = self.holdout_comparison_plan

    @property
    def holdout_calibration_plan(self) -> CalibrationPlan:
        return CalibrationPlan(
            plan_id=self.calibration_plan_id,
            detector_spec_digest=self.cusum_spec_digest,
            corpus_digest=self.holdout_seal.manifest.corpus_digest,
            corpus_role=CalibrationCorpusRole.HOLDOUT_QUALIFICATION,
            family_policies=self.family_policies,
        )

    @property
    def holdout_comparison_plan(self) -> DetectorComparisonPlan:
        calibration = self.holdout_calibration_plan
        return DetectorComparisonPlan(
            comparison_id=self.comparison_id,
            calibration_plan_digest=calibration.digest,
            corpus_digest=self.holdout_seal.manifest.corpus_digest,
            candidates=self.candidates,
        )

    def payload(self) -> dict[str, Any]:
        return {
            "schema": "DRIFTGUARD_BENCHMARK_PRECOMMIT_PLAN_V2",
            "study_id": self.study_id,
            "attempt_id": self.attempt_id,
            "precommit_id": self.precommit_id,
            "predecessor_attempt_digests": list(
                self.predecessor_attempt_digests
            ),
            "predecessor_holdout_digests": list(
                self.predecessor_holdout_digests
            ),
            "execution_binding": self.execution_binding.payload(),
            "design_manifest_digest": self.design_manifest.digest,
            "design_portfolio_digest": self.design_manifest.portfolio_digest,
            "holdout_seal": self.holdout_seal.payload(),
            "cusum_spec_digest": self.cusum_spec_digest,
            "family_policies": [
                item.payload() for item in self.family_policies
            ],
            "candidates": [item.payload() for item in self.candidates],
            "calibration_plan_id": self.calibration_plan_id,
            "holdout_calibration_plan_digest": (
                self.holdout_calibration_plan.digest
            ),
            "comparison_id": self.comparison_id,
            "holdout_comparison_plan_digest": (
                self.holdout_comparison_plan.digest
            ),
            "precommit_artifact": {
                "ref": self.precommit_artifact.ref,
                "version": self.precommit_artifact.version,
            },
            "precommit_artifact_digest": self.precommit_artifact_digest,
            "selection_rule": self.selection_rule,
            "precommit_claim": self.precommit_claim,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.payload())


@dataclass(frozen=True, init=False)
class HoldoutRevealReceipt:
    study_id: str
    attempt_id: str
    precommit_digest: str
    execution_binding_digest: str
    seal_digest: str
    manifest_digest: str
    corpus_digest: str
    artifact_digest: str
    reveal_claim: str

    def __init__(
        self,
        *,
        study_id: str,
        attempt_id: str,
        precommit_digest: str,
        execution_binding_digest: str,
        seal_digest: str,
        manifest_digest: str,
        corpus_digest: str,
        artifact_digest: str,
        reveal_claim: str,
        _reveal_token: object | None = None,
    ) -> None:
        if _reveal_token is not _REVEAL_RECEIPT_TOKEN:
            raise ValueError(
                "HoldoutRevealReceipt must come from reveal_holdout"
            )
        object.__setattr__(self, "study_id", study_id)
        object.__setattr__(self, "attempt_id", attempt_id)
        object.__setattr__(self, "precommit_digest", precommit_digest)
        object.__setattr__(
            self,
            "execution_binding_digest",
            execution_binding_digest,
        )
        object.__setattr__(self, "seal_digest", seal_digest)
        object.__setattr__(self, "manifest_digest", manifest_digest)
        object.__setattr__(self, "corpus_digest", corpus_digest)
        object.__setattr__(self, "artifact_digest", artifact_digest)
        object.__setattr__(self, "reveal_claim", reveal_claim)
        self.__post_init__()

    def __post_init__(self) -> None:
        _nonempty(self.study_id, "reveal study id")
        _nonempty(self.attempt_id, "reveal attempt id")
        for value, label in (
            (self.precommit_digest, "reveal precommit digest"),
            (
                self.execution_binding_digest,
                "reveal execution binding digest",
            ),
            (self.seal_digest, "reveal seal digest"),
            (self.manifest_digest, "reveal manifest digest"),
            (self.corpus_digest, "reveal corpus digest"),
            (self.artifact_digest, "reveal artifact digest"),
        ):
            require_sha256_digest(value, label)
        if self.reveal_claim != REVEAL_CLAIM:
            raise ValueError("unsupported holdout reveal claim")

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "schema": "DRIFTGUARD_HOLDOUT_REVEAL_RECEIPT_V2",
                "study_id": self.study_id,
                "attempt_id": self.attempt_id,
                "precommit_digest": self.precommit_digest,
                "execution_binding_digest": self.execution_binding_digest,
                "seal_digest": self.seal_digest,
                "manifest_digest": self.manifest_digest,
                "corpus_digest": self.corpus_digest,
                "artifact_digest": self.artifact_digest,
                "reveal_claim": self.reveal_claim,
            }
        )


@dataclass(frozen=True, init=False)
class BenchmarkRunReceipt:
    study_id: str
    attempt_id: str
    precommit_digest: str
    execution_binding_digest: str
    reveal_digest: str
    calibration_plan_digest: str
    comparison_plan_digest: str
    comparison_receipt_digest: str
    promotion_authorized: bool
    run_claim: str

    def __init__(
        self,
        *,
        study_id: str,
        attempt_id: str,
        precommit_digest: str,
        execution_binding_digest: str,
        reveal_digest: str,
        calibration_plan_digest: str,
        comparison_plan_digest: str,
        comparison_receipt_digest: str,
        promotion_authorized: bool,
        run_claim: str,
        _run_token: object | None = None,
    ) -> None:
        if _run_token is not _RUN_RECEIPT_TOKEN:
            raise ValueError(
                "BenchmarkRunReceipt must come from run_precommitted_holdout"
            )
        object.__setattr__(self, "study_id", study_id)
        object.__setattr__(self, "attempt_id", attempt_id)
        object.__setattr__(self, "precommit_digest", precommit_digest)
        object.__setattr__(
            self,
            "execution_binding_digest",
            execution_binding_digest,
        )
        object.__setattr__(self, "reveal_digest", reveal_digest)
        object.__setattr__(
            self,
            "calibration_plan_digest",
            calibration_plan_digest,
        )
        object.__setattr__(
            self,
            "comparison_plan_digest",
            comparison_plan_digest,
        )
        object.__setattr__(
            self,
            "comparison_receipt_digest",
            comparison_receipt_digest,
        )
        object.__setattr__(
            self,
            "promotion_authorized",
            promotion_authorized,
        )
        object.__setattr__(self, "run_claim", run_claim)
        self.__post_init__()

    def __post_init__(self) -> None:
        _nonempty(self.study_id, "benchmark run study id")
        _nonempty(self.attempt_id, "benchmark run attempt id")
        for value, label in (
            (self.precommit_digest, "benchmark run precommit digest"),
            (
                self.execution_binding_digest,
                "benchmark run execution binding digest",
            ),
            (self.reveal_digest, "benchmark run reveal digest"),
            (
                self.calibration_plan_digest,
                "benchmark run calibration plan digest",
            ),
            (
                self.comparison_plan_digest,
                "benchmark run comparison plan digest",
            ),
            (
                self.comparison_receipt_digest,
                "benchmark run comparison receipt digest",
            ),
        ):
            require_sha256_digest(value, label)
        if type(self.promotion_authorized) is not bool:
            raise ValueError(
                "benchmark run promotion_authorized must be exact bool"
            )
        if self.promotion_authorized:
            raise ValueError(
                "R11 benchmark run cannot authorize detector promotion"
            )
        if self.run_claim != RUN_CLAIM:
            raise ValueError("unsupported benchmark run claim")

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "schema": "DRIFTGUARD_BENCHMARK_RUN_RECEIPT_V2",
                "study_id": self.study_id,
                "attempt_id": self.attempt_id,
                "precommit_digest": self.precommit_digest,
                "execution_binding_digest": self.execution_binding_digest,
                "reveal_digest": self.reveal_digest,
                "calibration_plan_digest": self.calibration_plan_digest,
                "comparison_plan_digest": self.comparison_plan_digest,
                "comparison_receipt_digest": self.comparison_receipt_digest,
                "promotion_authorized": self.promotion_authorized,
                "run_claim": self.run_claim,
            }
        )


@dataclass(frozen=True)
class BenchmarkRunResult:
    receipt: BenchmarkRunReceipt
    comparison: DetectorComparisonReceipt

    def __post_init__(self) -> None:
        if type(self.receipt) is not BenchmarkRunReceipt:
            raise ValueError("benchmark result receipt must be BenchmarkRunReceipt")
        if type(self.comparison) is not DetectorComparisonReceipt:
            raise ValueError(
                "benchmark result comparison must be DetectorComparisonReceipt"
            )
        if self.receipt.comparison_receipt_digest != self.comparison.digest:
            raise ValueError(
                "benchmark run receipt/comparison digest mismatch"
            )
        if self.receipt.promotion_authorized:
            raise ValueError(
                "benchmark result cannot authorize promotion"
            )


class BenchmarkAttemptStatus(StrEnum):
    SEALED = "SEALED"
    REVEALED = "REVEALED"
    EXECUTING = "EXECUTING"
    EXECUTED = "EXECUTED"
    INVALIDATED = "INVALIDATED"
    ABORTED = "ABORTED"


_TERMINAL_ATTEMPT_STATUSES = frozenset(
    {
        BenchmarkAttemptStatus.EXECUTED,
        BenchmarkAttemptStatus.INVALIDATED,
        BenchmarkAttemptStatus.ABORTED,
    }
)


@dataclass(frozen=True, init=False)
class BenchmarkAttemptReceipt:
    study_id: str
    attempt_id: str
    precommit_id: str
    precommit_digest: str
    seal_digest: str
    holdout_corpus_digest: str
    execution_binding_digest: str
    predecessor_attempt_digests: tuple[str, ...]
    status: BenchmarkAttemptStatus
    reveal_digest: str | None
    run_digest: str | None
    reason: str | None

    def __init__(
        self,
        *,
        study_id: str,
        attempt_id: str,
        precommit_id: str,
        precommit_digest: str,
        seal_digest: str,
        holdout_corpus_digest: str,
        execution_binding_digest: str,
        predecessor_attempt_digests: tuple[str, ...],
        status: BenchmarkAttemptStatus,
        reveal_digest: str | None,
        run_digest: str | None,
        reason: str | None,
        _attempt_token: object | None = None,
    ) -> None:
        if _attempt_token is not _ATTEMPT_RECEIPT_TOKEN:
            raise ValueError(
                "BenchmarkAttemptReceipt must come from BenchmarkAttemptLedger"
            )
        object.__setattr__(self, "study_id", study_id)
        object.__setattr__(self, "attempt_id", attempt_id)
        object.__setattr__(self, "precommit_id", precommit_id)
        object.__setattr__(self, "precommit_digest", precommit_digest)
        object.__setattr__(self, "seal_digest", seal_digest)
        object.__setattr__(
            self,
            "holdout_corpus_digest",
            holdout_corpus_digest,
        )
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
        object.__setattr__(self, "run_digest", run_digest)
        object.__setattr__(self, "reason", reason)
        self.__post_init__()

    def __post_init__(self) -> None:
        _nonempty(self.study_id, "attempt receipt study id")
        _nonempty(self.attempt_id, "attempt receipt attempt id")
        _nonempty(self.precommit_id, "attempt receipt precommit id")
        for value, label in (
            (self.precommit_digest, "attempt receipt precommit digest"),
            (self.seal_digest, "attempt receipt seal digest"),
            (
                self.holdout_corpus_digest,
                "attempt receipt holdout corpus digest",
            ),
            (
                self.execution_binding_digest,
                "attempt receipt execution binding digest",
            ),
        ):
            require_sha256_digest(value, label)
        if (
            type(self.predecessor_attempt_digests) is not tuple
            or self.predecessor_attempt_digests
            != tuple(sorted(set(self.predecessor_attempt_digests)))
        ):
            raise ValueError(
                "attempt receipt predecessor digests must be canonical/unique"
            )
        for item in self.predecessor_attempt_digests:
            require_sha256_digest(item, "attempt receipt predecessor digest")
        if type(self.status) is not BenchmarkAttemptStatus:
            raise ValueError(
                "attempt receipt status must be exact BenchmarkAttemptStatus"
            )
        if self.reveal_digest is not None:
            require_sha256_digest(
                self.reveal_digest,
                "attempt receipt reveal digest",
            )
        if self.run_digest is not None:
            require_sha256_digest(
                self.run_digest,
                "attempt receipt run digest",
            )
        if self.status is BenchmarkAttemptStatus.SEALED:
            if self.reveal_digest is not None or self.run_digest is not None:
                raise ValueError(
                    "SEALED attempt cannot already contain reveal/run digest"
                )
            if self.reason is not None:
                raise ValueError("SEALED attempt cannot contain terminal reason")
        elif self.status is BenchmarkAttemptStatus.REVEALED:
            if self.reveal_digest is None or self.run_digest is not None:
                raise ValueError(
                    "REVEALED attempt requires reveal digest and no run digest"
                )
            if self.reason is not None:
                raise ValueError("REVEALED attempt cannot contain terminal reason")
        elif self.status is BenchmarkAttemptStatus.EXECUTING:
            if self.reveal_digest is None or self.run_digest is not None:
                raise ValueError(
                    "EXECUTING attempt requires reveal digest and no run digest"
                )
            if self.reason is not None:
                raise ValueError("EXECUTING attempt cannot contain terminal reason")
        elif self.status is BenchmarkAttemptStatus.EXECUTED:
            if self.reveal_digest is None or self.run_digest is None:
                raise ValueError(
                    "EXECUTED attempt requires reveal and run digests"
                )
            if self.reason is not None:
                raise ValueError("EXECUTED attempt cannot contain terminal reason")
        else:
            if type(self.reason) is not str or not self.reason.strip():
                raise ValueError(
                    "ABORTED/INVALIDATED attempt requires non-empty reason"
                )

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "schema": "DRIFTGUARD_BENCHMARK_ATTEMPT_RECEIPT_V1",
                "study_id": self.study_id,
                "attempt_id": self.attempt_id,
                "precommit_id": self.precommit_id,
                "precommit_digest": self.precommit_digest,
                "seal_digest": self.seal_digest,
                "holdout_corpus_digest": self.holdout_corpus_digest,
                "execution_binding_digest": self.execution_binding_digest,
                "predecessor_attempt_digests": list(
                    self.predecessor_attempt_digests
                ),
                "status": self.status.value,
                "reveal_digest": self.reveal_digest,
                "run_digest": self.run_digest,
                "reason": self.reason,
            }
        )


class BenchmarkAttemptLedger:
    def __init__(self, path: str) -> None:
        _nonempty(path, "benchmark attempt ledger path")
        self.path = path
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS benchmark_attempts (
                    attempt_id TEXT PRIMARY KEY,
                    study_id TEXT NOT NULL,
                    precommit_id TEXT NOT NULL UNIQUE,
                    precommit_digest TEXT NOT NULL,
                    seal_digest TEXT NOT NULL,
                    holdout_corpus_digest TEXT NOT NULL,
                    execution_binding_digest TEXT NOT NULL,
                    predecessor_attempt_digests_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reveal_digest TEXT NULL,
                    run_digest TEXT NULL,
                    reason TEXT NULL
                )
                """
            )
            db.execute(
                """
                CREATE INDEX IF NOT EXISTS benchmark_attempts_study_idx
                    ON benchmark_attempts(study_id)
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS benchmark_attempt_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    attempt_id TEXT NOT NULL,
                    study_id TEXT NOT NULL,
                    precommit_digest TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reveal_digest TEXT NULL,
                    run_digest TEXT NULL,
                    reason TEXT NULL,
                    FOREIGN KEY(attempt_id)
                        REFERENCES benchmark_attempts(attempt_id)
                )
                """
            )
            db.execute(
                """
                CREATE INDEX IF NOT EXISTS benchmark_attempt_events_attempt_idx
                    ON benchmark_attempt_events(attempt_id, event_id)
                """
            )

    @staticmethod
    def _row_to_receipt(row: sqlite3.Row) -> BenchmarkAttemptReceipt:
        raw = json.loads(str(row["predecessor_attempt_digests_json"]))
        if type(raw) is not list or any(type(item) is not str for item in raw):
            raise ValueError(
                "stored predecessor attempt digests are invalid"
            )
        return BenchmarkAttemptReceipt(
            study_id=str(row["study_id"]),
            attempt_id=str(row["attempt_id"]),
            precommit_id=str(row["precommit_id"]),
            precommit_digest=str(row["precommit_digest"]),
            seal_digest=str(row["seal_digest"]),
            holdout_corpus_digest=str(row["holdout_corpus_digest"]),
            execution_binding_digest=str(row["execution_binding_digest"]),
            predecessor_attempt_digests=tuple(raw),
            status=BenchmarkAttemptStatus(str(row["status"])),
            reveal_digest=(
                str(row["reveal_digest"])
                if row["reveal_digest"] is not None
                else None
            ),
            run_digest=(
                str(row["run_digest"])
                if row["run_digest"] is not None
                else None
            ),
            reason=(
                str(row["reason"])
                if row["reason"] is not None
                else None
            ),
            _attempt_token=_ATTEMPT_RECEIPT_TOKEN,
        )

    def attempt_receipt(
        self,
        *,
        attempt_id: str,
    ) -> BenchmarkAttemptReceipt | None:
        _nonempty(attempt_id, "benchmark attempt id")
        with closing(sqlite3.connect(self.path)) as db:
            db.row_factory = sqlite3.Row
            row = db.execute(
                "SELECT * FROM benchmark_attempts WHERE attempt_id=?",
                (attempt_id,),
            ).fetchone()
        return self._row_to_receipt(row) if row is not None else None

    def study_attempts(
        self,
        *,
        study_id: str,
    ) -> tuple[BenchmarkAttemptReceipt, ...]:
        _nonempty(study_id, "benchmark study id")
        with closing(sqlite3.connect(self.path)) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                """
                SELECT * FROM benchmark_attempts
                 WHERE study_id=?
                 ORDER BY rowid
                """,
                (study_id,),
            ).fetchall()
        return tuple(self._row_to_receipt(row) for row in rows)

    def attempt_history(
        self,
        *,
        attempt_id: str,
    ) -> tuple[dict[str, Any], ...]:
        _nonempty(attempt_id, "benchmark attempt id")
        with closing(sqlite3.connect(self.path)) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                """
                SELECT event_id,attempt_id,study_id,precommit_digest,
                       status,reveal_digest,run_digest,reason
                  FROM benchmark_attempt_events
                 WHERE attempt_id=?
                 ORDER BY event_id
                """,
                (attempt_id,),
            ).fetchall()
        return tuple(
            {
                "event_id": int(row["event_id"]),
                "attempt_id": str(row["attempt_id"]),
                "study_id": str(row["study_id"]),
                "precommit_digest": str(row["precommit_digest"]),
                "status": str(row["status"]),
                "reveal_digest": (
                    str(row["reveal_digest"])
                    if row["reveal_digest"] is not None
                    else None
                ),
                "run_digest": (
                    str(row["run_digest"])
                    if row["run_digest"] is not None
                    else None
                ),
                "reason": (
                    str(row["reason"])
                    if row["reason"] is not None
                    else None
                ),
            }
            for row in rows
        )

    @staticmethod
    def _append_event(
        db: sqlite3.Connection,
        *,
        attempt_id: str,
        study_id: str,
        precommit_digest: str,
        status: BenchmarkAttemptStatus,
        reveal_digest: str | None,
        run_digest: str | None,
        reason: str | None,
    ) -> None:
        db.execute(
            """
            INSERT INTO benchmark_attempt_events(
                attempt_id,study_id,precommit_digest,status,
                reveal_digest,run_digest,reason
            ) VALUES(?,?,?,?,?,?,?)
            """,
            (
                attempt_id,
                study_id,
                precommit_digest,
                status.value,
                reveal_digest,
                run_digest,
                reason,
            ),
        )

    def seal_precommit(
        self,
        *,
        precommit: BenchmarkPrecommitPlan,
    ) -> BenchmarkAttemptReceipt:
        if type(precommit) is not BenchmarkPrecommitPlan:
            raise ValueError(
                "precommit must be exact BenchmarkPrecommitPlan"
            )
        precommit.execution_binding.assert_runtime_sources_match()
        predecessor_json = json.dumps(
            list(precommit.predecessor_attempt_digests),
            separators=(",", ":"),
        )
        with closing(sqlite3.connect(self.path)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN IMMEDIATE")
            existing_attempt = db.execute(
                "SELECT * FROM benchmark_attempts WHERE attempt_id=?",
                (precommit.attempt_id,),
            ).fetchone()
            if existing_attempt is not None:
                receipt = self._row_to_receipt(existing_attempt)
                if receipt.precommit_digest != precommit.digest:
                    raise ValueError(
                        "same attempt_id cannot bind divergent precommit digest"
                    )
                return receipt

            existing_precommit_id = db.execute(
                "SELECT * FROM benchmark_attempts WHERE precommit_id=?",
                (precommit.precommit_id,),
            ).fetchone()
            if existing_precommit_id is not None:
                receipt = self._row_to_receipt(existing_precommit_id)
                if receipt.precommit_digest != precommit.digest:
                    raise ValueError(
                        "same precommit_id cannot bind divergent precommit digest"
                    )
                raise ValueError(
                    "precommit_id is already registered to another attempt"
                )

            rows = db.execute(
                """
                SELECT * FROM benchmark_attempts
                 WHERE study_id=?
                 ORDER BY rowid
                """,
                (precommit.study_id,),
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
                    "study already has an active benchmark attempt"
                )
            if any(
                item.status not in _TERMINAL_ATTEMPT_STATUSES
                for item in receipts
            ):
                raise ValueError(
                    "prior benchmark attempt is not terminal"
                )
            expected_predecessors = tuple(
                sorted(item.digest for item in receipts)
            )
            if (
                precommit.predecessor_attempt_digests
                != expected_predecessors
            ):
                raise ValueError(
                    "successor attempt must reference every prior terminal attempt digest"
                )
            prior_holdouts = {
                item.holdout_corpus_digest for item in receipts
            }
            if not prior_holdouts.issubset(
                set(precommit.predecessor_holdout_digests)
            ):
                raise ValueError(
                    "successor attempt must disclose every prior attempt holdout digest"
                )

            db.execute(
                """
                INSERT INTO benchmark_attempts(
                    attempt_id,study_id,precommit_id,precommit_digest,
                    seal_digest,holdout_corpus_digest,
                    execution_binding_digest,
                    predecessor_attempt_digests_json,status,
                    reveal_digest,run_digest,reason
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    precommit.attempt_id,
                    precommit.study_id,
                    precommit.precommit_id,
                    precommit.digest,
                    precommit.holdout_seal.digest,
                    precommit.holdout_seal.manifest.corpus_digest,
                    precommit.execution_binding.digest,
                    predecessor_json,
                    BenchmarkAttemptStatus.SEALED.value,
                    None,
                    None,
                    None,
                ),
            )
            self._append_event(
                db,
                attempt_id=precommit.attempt_id,
                study_id=precommit.study_id,
                precommit_digest=precommit.digest,
                status=BenchmarkAttemptStatus.SEALED,
                reveal_digest=None,
                run_digest=None,
                reason=None,
            )
            row = db.execute(
                "SELECT * FROM benchmark_attempts WHERE attempt_id=?",
                (precommit.attempt_id,),
            ).fetchone()
            if row is None:
                raise ValueError("sealed benchmark attempt readback missing")
            return self._row_to_receipt(row)

    def _assert_exact_precommit(
        self,
        *,
        precommit: BenchmarkPrecommitPlan,
        required_status: BenchmarkAttemptStatus,
    ) -> BenchmarkAttemptReceipt:
        receipt = self.attempt_receipt(attempt_id=precommit.attempt_id)
        if receipt is None:
            raise ValueError(
                "benchmark attempt must be durably sealed before use"
            )
        if receipt.study_id != precommit.study_id:
            raise ValueError("benchmark attempt study id mismatch")
        if receipt.precommit_id != precommit.precommit_id:
            raise ValueError("benchmark attempt precommit id mismatch")
        if receipt.precommit_digest != precommit.digest:
            raise ValueError("benchmark attempt precommit digest mismatch")
        if receipt.seal_digest != precommit.holdout_seal.digest:
            raise ValueError("benchmark attempt seal digest mismatch")
        if (
            receipt.execution_binding_digest
            != precommit.execution_binding.digest
        ):
            raise ValueError(
                "benchmark attempt execution binding mismatch"
            )
        if receipt.status is not required_status:
            raise ValueError(
                f"benchmark attempt must be {required_status.value}"
            )
        return receipt

    def mark_revealed(
        self,
        *,
        precommit: BenchmarkPrecommitPlan,
        reveal: HoldoutRevealReceipt,
    ) -> BenchmarkAttemptReceipt:
        self._assert_exact_precommit(
            precommit=precommit,
            required_status=BenchmarkAttemptStatus.SEALED,
        )
        with closing(sqlite3.connect(self.path)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN IMMEDIATE")
            updated = db.execute(
                """
                UPDATE benchmark_attempts
                   SET status=?, reveal_digest=?
                 WHERE attempt_id=?
                   AND precommit_digest=?
                   AND status=?
                   AND reveal_digest IS NULL
                   AND run_digest IS NULL
                """,
                (
                    BenchmarkAttemptStatus.REVEALED.value,
                    reveal.digest,
                    precommit.attempt_id,
                    precommit.digest,
                    BenchmarkAttemptStatus.SEALED.value,
                ),
            )
            if updated.rowcount != 1:
                raise ValueError(
                    "benchmark reveal is single-use or attempt is stale"
                )
            self._append_event(
                db,
                attempt_id=precommit.attempt_id,
                study_id=precommit.study_id,
                precommit_digest=precommit.digest,
                status=BenchmarkAttemptStatus.REVEALED,
                reveal_digest=reveal.digest,
                run_digest=None,
                reason=None,
            )
            row = db.execute(
                "SELECT * FROM benchmark_attempts WHERE attempt_id=?",
                (precommit.attempt_id,),
            ).fetchone()
            return self._row_to_receipt(row)

    def begin_execution(
        self,
        *,
        precommit: BenchmarkPrecommitPlan,
        reveal: HoldoutRevealReceipt,
    ) -> BenchmarkAttemptReceipt:
        current = self._assert_exact_precommit(
            precommit=precommit,
            required_status=BenchmarkAttemptStatus.REVEALED,
        )
        if current.reveal_digest != reveal.digest:
            raise ValueError(
                "benchmark attempt reveal digest mismatch"
            )
        with closing(sqlite3.connect(self.path)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN IMMEDIATE")
            updated = db.execute(
                """
                UPDATE benchmark_attempts
                   SET status=?
                 WHERE attempt_id=?
                   AND precommit_digest=?
                   AND status=?
                   AND reveal_digest=?
                   AND run_digest IS NULL
                """,
                (
                    BenchmarkAttemptStatus.EXECUTING.value,
                    precommit.attempt_id,
                    precommit.digest,
                    BenchmarkAttemptStatus.REVEALED.value,
                    reveal.digest,
                ),
            )
            if updated.rowcount != 1:
                raise ValueError(
                    "benchmark execution is single-use or attempt is stale"
                )
            self._append_event(
                db,
                attempt_id=precommit.attempt_id,
                study_id=precommit.study_id,
                precommit_digest=precommit.digest,
                status=BenchmarkAttemptStatus.EXECUTING,
                reveal_digest=reveal.digest,
                run_digest=None,
                reason=None,
            )
            row = db.execute(
                "SELECT * FROM benchmark_attempts WHERE attempt_id=?",
                (precommit.attempt_id,),
            ).fetchone()
            return self._row_to_receipt(row)

    def mark_executed(
        self,
        *,
        precommit: BenchmarkPrecommitPlan,
        reveal: HoldoutRevealReceipt,
        run: BenchmarkRunReceipt,
    ) -> BenchmarkAttemptReceipt:
        current = self._assert_exact_precommit(
            precommit=precommit,
            required_status=BenchmarkAttemptStatus.EXECUTING,
        )
        if current.reveal_digest != reveal.digest:
            raise ValueError(
                "benchmark attempt reveal digest mismatch"
            )
        with closing(sqlite3.connect(self.path)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN IMMEDIATE")
            updated = db.execute(
                """
                UPDATE benchmark_attempts
                   SET status=?, run_digest=?
                 WHERE attempt_id=?
                   AND precommit_digest=?
                   AND status=?
                   AND reveal_digest=?
                   AND run_digest IS NULL
                """,
                (
                    BenchmarkAttemptStatus.EXECUTED.value,
                    run.digest,
                    precommit.attempt_id,
                    precommit.digest,
                    BenchmarkAttemptStatus.EXECUTING.value,
                    reveal.digest,
                ),
            )
            if updated.rowcount != 1:
                raise ValueError(
                    "benchmark run is single-use or attempt is stale"
                )
            self._append_event(
                db,
                attempt_id=precommit.attempt_id,
                study_id=precommit.study_id,
                precommit_digest=precommit.digest,
                status=BenchmarkAttemptStatus.EXECUTED,
                reveal_digest=reveal.digest,
                run_digest=run.digest,
                reason=None,
            )
            row = db.execute(
                "SELECT * FROM benchmark_attempts WHERE attempt_id=?",
                (precommit.attempt_id,),
            ).fetchone()
            return self._row_to_receipt(row)

    def _terminalize(
        self,
        *,
        attempt_id: str,
        status: BenchmarkAttemptStatus,
        reason: str,
    ) -> BenchmarkAttemptReceipt:
        if status not in {
            BenchmarkAttemptStatus.ABORTED,
            BenchmarkAttemptStatus.INVALIDATED,
        }:
            raise ValueError("unsupported benchmark terminal status")
        _nonempty(reason, "benchmark terminal reason")
        with closing(sqlite3.connect(self.path)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM benchmark_attempts WHERE attempt_id=?",
                (attempt_id,),
            ).fetchone()
            if row is None:
                raise ValueError("benchmark attempt not found")
            current = self._row_to_receipt(row)
            if current.status not in {
                BenchmarkAttemptStatus.SEALED,
                BenchmarkAttemptStatus.REVEALED,
                BenchmarkAttemptStatus.EXECUTING,
            }:
                raise ValueError(
                    "only active benchmark attempt can be aborted/invalidated"
                )
            db.execute(
                """
                UPDATE benchmark_attempts
                   SET status=?, reason=?
                 WHERE attempt_id=?
                """,
                (status.value, reason, attempt_id),
            )
            self._append_event(
                db,
                attempt_id=attempt_id,
                study_id=current.study_id,
                precommit_digest=current.precommit_digest,
                status=status,
                reveal_digest=current.reveal_digest,
                run_digest=current.run_digest,
                reason=reason,
            )
            row = db.execute(
                "SELECT * FROM benchmark_attempts WHERE attempt_id=?",
                (attempt_id,),
            ).fetchone()
            return self._row_to_receipt(row)

    def abort_attempt(
        self,
        *,
        attempt_id: str,
        reason: str,
    ) -> BenchmarkAttemptReceipt:
        return self._terminalize(
            attempt_id=attempt_id,
            status=BenchmarkAttemptStatus.ABORTED,
            reason=reason,
        )

    def invalidate_attempt(
        self,
        *,
        attempt_id: str,
        reason: str,
    ) -> BenchmarkAttemptReceipt:
        return self._terminalize(
            attempt_id=attempt_id,
            status=BenchmarkAttemptStatus.INVALIDATED,
            reason=reason,
        )


def reveal_holdout(
    *,
    registry: BenchmarkAttemptLedger,
    precommit: BenchmarkPrecommitPlan,
    execution_binding: BenchmarkExecutionBinding,
    manifest: BenchmarkCorpusManifest,
    corpus: CalibrationCorpus,
    artifact_bytes: bytes,
) -> HoldoutRevealReceipt:
    if type(registry) is not BenchmarkAttemptLedger:
        raise ValueError("registry must be exact BenchmarkAttemptLedger")
    if type(precommit) is not BenchmarkPrecommitPlan:
        raise ValueError("precommit must be exact BenchmarkPrecommitPlan")
    if type(execution_binding) is not BenchmarkExecutionBinding:
        raise ValueError(
            "execution_binding must be exact BenchmarkExecutionBinding"
        )
    if execution_binding != precommit.execution_binding:
        raise ValueError(
            "reveal execution binding does not match precommit"
        )
    execution_binding.assert_runtime_sources_match()
    registry._assert_exact_precommit(
        precommit=precommit,
        required_status=BenchmarkAttemptStatus.SEALED,
    )
    if type(manifest) is not BenchmarkCorpusManifest:
        raise ValueError("manifest must be exact BenchmarkCorpusManifest")
    if type(corpus) is not CalibrationCorpus:
        raise ValueError("corpus must be exact CalibrationCorpus")
    if type(artifact_bytes) is not bytes:
        raise ValueError("artifact_bytes must be exact bytes")

    seal = precommit.holdout_seal
    if manifest.digest != seal.manifest.digest:
        raise ValueError("revealed holdout manifest digest mismatch")
    if manifest.corpus_role is not CalibrationCorpusRole.HOLDOUT_QUALIFICATION:
        raise ValueError("revealed corpus is not HOLDOUT_QUALIFICATION")
    manifest.validate_corpus(corpus)
    expected_artifact_bytes = canonical_corpus_artifact_bytes(corpus)
    if artifact_bytes != expected_artifact_bytes:
        raise ValueError(
            "revealed holdout artifact bytes do not canonically encode corpus"
        )
    observed_artifact_digest = sha256(artifact_bytes).hexdigest()
    if observed_artifact_digest != manifest.artifact_digest:
        raise ValueError("revealed holdout artifact digest mismatch")

    receipt = HoldoutRevealReceipt(
        study_id=precommit.study_id,
        attempt_id=precommit.attempt_id,
        precommit_digest=precommit.digest,
        execution_binding_digest=execution_binding.digest,
        seal_digest=seal.digest,
        manifest_digest=manifest.digest,
        corpus_digest=corpus.digest,
        artifact_digest=observed_artifact_digest,
        reveal_claim=REVEAL_CLAIM,
        _reveal_token=_REVEAL_RECEIPT_TOKEN,
    )
    registry.mark_revealed(
        precommit=precommit,
        reveal=receipt,
    )
    return receipt


def run_precommitted_holdout(
    *,
    registry: BenchmarkAttemptLedger,
    precommit: BenchmarkPrecommitPlan,
    execution_binding: BenchmarkExecutionBinding,
    reveal: HoldoutRevealReceipt,
    manifest: BenchmarkCorpusManifest,
    corpus: CalibrationCorpus,
    cusum_spec: SequentialDetectorSpec,
) -> BenchmarkRunResult:
    if type(registry) is not BenchmarkAttemptLedger:
        raise ValueError("registry must be exact BenchmarkAttemptLedger")
    if type(precommit) is not BenchmarkPrecommitPlan:
        raise ValueError("precommit must be exact BenchmarkPrecommitPlan")
    if type(execution_binding) is not BenchmarkExecutionBinding:
        raise ValueError(
            "execution_binding must be exact BenchmarkExecutionBinding"
        )
    if execution_binding != precommit.execution_binding:
        raise ValueError(
            "run execution binding does not match precommit"
        )
    execution_binding.assert_runtime_sources_match()
    current_attempt = registry._assert_exact_precommit(
        precommit=precommit,
        required_status=BenchmarkAttemptStatus.REVEALED,
    )
    if type(reveal) is not HoldoutRevealReceipt:
        raise ValueError("reveal must be exact HoldoutRevealReceipt")
    if type(manifest) is not BenchmarkCorpusManifest:
        raise ValueError("manifest must be exact BenchmarkCorpusManifest")
    if type(corpus) is not CalibrationCorpus:
        raise ValueError("corpus must be exact CalibrationCorpus")
    if type(cusum_spec) is not SequentialDetectorSpec:
        raise ValueError("cusum_spec must be exact SequentialDetectorSpec")

    if reveal.study_id != precommit.study_id:
        raise ValueError("benchmark reveal study id mismatch")
    if reveal.attempt_id != precommit.attempt_id:
        raise ValueError("benchmark reveal attempt id mismatch")
    if reveal.precommit_digest != precommit.digest:
        raise ValueError("benchmark reveal/precommit digest mismatch")
    if reveal.execution_binding_digest != execution_binding.digest:
        raise ValueError("benchmark reveal execution binding mismatch")
    if current_attempt.reveal_digest != reveal.digest:
        raise ValueError("benchmark durable reveal digest mismatch")
    if reveal.seal_digest != precommit.holdout_seal.digest:
        raise ValueError("benchmark reveal/seal digest mismatch")
    if reveal.manifest_digest != manifest.digest:
        raise ValueError("benchmark reveal/manifest digest mismatch")
    if reveal.corpus_digest != corpus.digest:
        raise ValueError("benchmark reveal/corpus digest mismatch")
    if manifest.digest != precommit.holdout_seal.manifest.digest:
        raise ValueError("benchmark manifest is not the precommitted holdout")

    manifest.validate_corpus(corpus)
    if cusum_spec.digest != precommit.cusum_spec_digest:
        raise ValueError("benchmark CUSUM spec digest mismatch")

    calibration_plan = precommit.holdout_calibration_plan
    comparison_plan = precommit.holdout_comparison_plan
    registry.begin_execution(
        precommit=precommit,
        reveal=reveal,
    )
    try:
        comparison = compare_detectors(
            plan=comparison_plan,
            calibration_plan=calibration_plan,
            corpus=corpus,
            cusum_spec=cusum_spec,
        )
        if comparison.promotion_authorized:
            raise ValueError(
                "R10 comparison unexpectedly authorized promotion"
            )

        receipt = BenchmarkRunReceipt(
            study_id=precommit.study_id,
            attempt_id=precommit.attempt_id,
            precommit_digest=precommit.digest,
            execution_binding_digest=execution_binding.digest,
            reveal_digest=reveal.digest,
            calibration_plan_digest=calibration_plan.digest,
            comparison_plan_digest=comparison_plan.digest,
            comparison_receipt_digest=comparison.digest,
            promotion_authorized=False,
            run_claim=RUN_CLAIM,
            _run_token=_RUN_RECEIPT_TOKEN,
        )
    except Exception as exc:
        registry.invalidate_attempt(
            attempt_id=precommit.attempt_id,
            reason=f"semantic_execution_failed:{type(exc).__name__}",
        )
        raise

    # Durable completion is deliberately outside the semantic-failure catch.
    # If finalization/storage itself fails ambiguously, the attempt remains
    # EXECUTING and therefore cannot be retried as a fresh governed run.
    registry.mark_executed(
        precommit=precommit,
        reveal=reveal,
        run=receipt,
    )
    return BenchmarkRunResult(
        receipt=receipt,
        comparison=comparison,
    )


__all__ = [
    "BenchmarkAttemptLedger",
    "BenchmarkAttemptReceipt",
    "BenchmarkAttemptStatus",
    "BenchmarkCorpusManifest",
    "BenchmarkExecutionBinding",
    "BenchmarkFamilyManifest",
    "BenchmarkPhenomenon",
    "BenchmarkPrecommitPlan",
    "BenchmarkRunReceipt",
    "BenchmarkRunResult",
    "CORE_R11_COVERAGE_PROFILE",
    "CORE_R11_PHENOMENA",
    "HoldoutCorpusSeal",
    "HoldoutRevealReceipt",
    "PRECOMMIT_CLAIM",
    "REVEAL_CLAIM",
    "RUN_CLAIM",
    "SELECTION_RULE",
    "canonical_corpus_artifact_bytes",
    "current_execution_binding",
    "reveal_holdout",
    "run_precommitted_holdout",
    "runtime_source_digests",
    "trajectory_content_digest",
]
