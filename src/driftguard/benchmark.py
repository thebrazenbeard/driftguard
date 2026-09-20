from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
import json
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


def _nonempty(value: Any, label: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{label} must be a non-empty exact string")
    return value


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
    precommit_id: str
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
        _nonempty(self.precommit_id, "benchmark precommit id")
        if type(self.design_manifest) is not BenchmarkCorpusManifest:
            raise ValueError(
                "design manifest must be exact BenchmarkCorpusManifest"
            )
        if self.design_manifest.corpus_role is not CalibrationCorpusRole.DESIGN:
            raise ValueError("benchmark precommit requires DESIGN manifest")
        if type(self.holdout_seal) is not HoldoutCorpusSeal:
            raise ValueError("holdout_seal must be exact HoldoutCorpusSeal")
        if (
            self.design_manifest.portfolio_digest
            != self.holdout_seal.manifest.portfolio_digest
        ):
            raise ValueError(
                "design and holdout benchmark portfolio contracts must match"
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
            "schema": "DRIFTGUARD_BENCHMARK_PRECOMMIT_PLAN_V1",
            "precommit_id": self.precommit_id,
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
    precommit_digest: str
    seal_digest: str
    manifest_digest: str
    corpus_digest: str
    artifact_digest: str
    reveal_claim: str

    def __init__(
        self,
        *,
        precommit_digest: str,
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
        object.__setattr__(self, "precommit_digest", precommit_digest)
        object.__setattr__(self, "seal_digest", seal_digest)
        object.__setattr__(self, "manifest_digest", manifest_digest)
        object.__setattr__(self, "corpus_digest", corpus_digest)
        object.__setattr__(self, "artifact_digest", artifact_digest)
        object.__setattr__(self, "reveal_claim", reveal_claim)
        self.__post_init__()

    def __post_init__(self) -> None:
        for value, label in (
            (self.precommit_digest, "reveal precommit digest"),
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
                "schema": "DRIFTGUARD_HOLDOUT_REVEAL_RECEIPT_V1",
                "precommit_digest": self.precommit_digest,
                "seal_digest": self.seal_digest,
                "manifest_digest": self.manifest_digest,
                "corpus_digest": self.corpus_digest,
                "artifact_digest": self.artifact_digest,
                "reveal_claim": self.reveal_claim,
            }
        )


@dataclass(frozen=True, init=False)
class BenchmarkRunReceipt:
    precommit_digest: str
    reveal_digest: str
    calibration_plan_digest: str
    comparison_plan_digest: str
    comparison_receipt_digest: str
    promotion_authorized: bool
    run_claim: str

    def __init__(
        self,
        *,
        precommit_digest: str,
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
        object.__setattr__(self, "precommit_digest", precommit_digest)
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
        for value, label in (
            (self.precommit_digest, "benchmark run precommit digest"),
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
                "schema": "DRIFTGUARD_BENCHMARK_RUN_RECEIPT_V1",
                "precommit_digest": self.precommit_digest,
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


def reveal_holdout(
    *,
    precommit: BenchmarkPrecommitPlan,
    manifest: BenchmarkCorpusManifest,
    corpus: CalibrationCorpus,
    artifact_bytes: bytes,
) -> HoldoutRevealReceipt:
    if type(precommit) is not BenchmarkPrecommitPlan:
        raise ValueError("precommit must be exact BenchmarkPrecommitPlan")
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
    return HoldoutRevealReceipt(
        precommit_digest=precommit.digest,
        seal_digest=seal.digest,
        manifest_digest=manifest.digest,
        corpus_digest=corpus.digest,
        artifact_digest=observed_artifact_digest,
        reveal_claim=REVEAL_CLAIM,
        _reveal_token=_REVEAL_RECEIPT_TOKEN,
    )


def run_precommitted_holdout(
    *,
    precommit: BenchmarkPrecommitPlan,
    reveal: HoldoutRevealReceipt,
    manifest: BenchmarkCorpusManifest,
    corpus: CalibrationCorpus,
    cusum_spec: SequentialDetectorSpec,
) -> BenchmarkRunResult:
    if type(precommit) is not BenchmarkPrecommitPlan:
        raise ValueError("precommit must be exact BenchmarkPrecommitPlan")
    if type(reveal) is not HoldoutRevealReceipt:
        raise ValueError("reveal must be exact HoldoutRevealReceipt")
    if type(manifest) is not BenchmarkCorpusManifest:
        raise ValueError("manifest must be exact BenchmarkCorpusManifest")
    if type(corpus) is not CalibrationCorpus:
        raise ValueError("corpus must be exact CalibrationCorpus")
    if type(cusum_spec) is not SequentialDetectorSpec:
        raise ValueError("cusum_spec must be exact SequentialDetectorSpec")
    if reveal.precommit_digest != precommit.digest:
        raise ValueError("benchmark reveal/precommit digest mismatch")
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
        precommit_digest=precommit.digest,
        reveal_digest=reveal.digest,
        calibration_plan_digest=calibration_plan.digest,
        comparison_plan_digest=comparison_plan.digest,
        comparison_receipt_digest=comparison.digest,
        promotion_authorized=False,
        run_claim=RUN_CLAIM,
        _run_token=_RUN_RECEIPT_TOKEN,
    )
    return BenchmarkRunResult(
        receipt=receipt,
        comparison=comparison,
    )


__all__ = [
    "BenchmarkCorpusManifest",
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
    "reveal_holdout",
    "canonical_corpus_artifact_bytes",
    "run_precommitted_holdout",
]
