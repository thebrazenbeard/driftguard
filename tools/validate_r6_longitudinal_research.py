from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DOC_PATH = "docs/research/DRIFTGUARD_R6_LONGITUDINAL_DRIFT_ARCHITECTURE_V0_1.md"
SPEC_PATH = "specs/research/DRIFTGUARD_R6_LONGITUDINAL_DRIFT_ARCHITECTURE_V0_1.json"
FIXTURE_PATH = "specs/research/fixtures/DRIFTGUARD_R6_LONGITUDINAL_HOSTILE_CASES_V0_1.json"

EXPECTED_PHASES = [
    "R6A_SUBJECT_IDENTITY",
    "R6B_EVALUATOR_CALIBRATION",
    "R6C_PROVENANCE_INDEPENDENCE",
    "R6D_SEQUENTIAL_DETECTION",
    "R6E_BASELINE_EVOLUTION",
    "R6F_SUSTAINED_RECOVERY",
    "R6G_PROVIDER_EFFECT_EVIDENCE",
    "R6H_TAMPER_EVIDENCE",
]

EXPECTED_CLAIM_CEILING = {
    "NO_RUNTIME_IMPLEMENTATION_CLAIM",
    "NO_PROVIDER_EFFECT_CLAIM",
    "NO_HIDDEN_STATE_RESTORATION_CLAIM",
    "NO_PERSON_IDENTITY_CONTINUITY_CLAIM",
    "NO_STATISTICAL_VALIDITY_CLAIM",
    "NO_SUSTAINED_RECOVERY_CLAIM",
    "NO_CANONICAL_PROMOTION",
}

EXPECTED_INVARIANTS = {
    "BEHAVIORAL_SIMILARITY_NE_HIDDEN_STATE_EQUIVALENCE",
    "RUNTIME_SUBJECT_BINDING_NE_PERSON_IDENTITY",
    "SESSION_CONTINUITY_NE_SUBJECT_CONTINUITY",
    "CALIBRATED_SCORE_NE_GROUND_TRUTH",
    "DIFFERENT_EVALUATORS_NE_INDEPENDENT_EVIDENCE",
    "SOURCE_COUNT_NE_INDEPENDENT_EVIDENCE_COUNT",
    "REPEATED_MEASUREMENT_NE_INDEPENDENT_REPLICATION",
    "PROBE_VERSION_CHANGE_NE_TARGET_DRIFT",
    "EVALUATOR_DRIFT_NE_TARGET_DRIFT",
    "MISSING_EVIDENCE_NE_STABLE",
    "THRESHOLD_BREACH_NE_PROVEN_CHANGE_POINT",
    "OBSERVED_DRIFT_NE_AUTHORITY_TO_CHANGE_BASELINE",
    "BASELINE_CHANGE_NE_RECOVERY",
    "FIRST_STABLE_REPLAY_NE_SUSTAINED_RECOVERY",
    "SUSTAINED_RECOVERY_NE_PERMANENT_RECOVERY",
    "ACKNOWLEDGEMENT_NE_PROVIDER_EFFECT_PROOF",
    "POLICY_SELECTED_AFTER_OUTCOME_NE_PRECOMMITTED_POLICY",
    "TAMPER_EVIDENT_NE_TAMPER_IMPOSSIBLE",
}

EXPECTED_FIELDS = {
    "R6A_SUBJECT_IDENTITY": {
        "required_fields": {
            "subject_id", "subject_epoch", "save_state_digest", "runtime_manifest_digest",
            "instruction_contract_digest", "capability_set_digest",
            "evaluation_harness_version", "detection_policy_version",
        }
    },
    "R6B_EVALUATOR_CALIBRATION": {
        "required_fields": {
            "source_ref", "source_version", "dimension_scope", "calibration_set_digest",
            "calibration_method", "calibration_epoch", "limitations",
            "recalibration_condition",
        }
    },
    "R6D_SEQUENTIAL_DETECTION": {
        "required_policy_fields": {
            "included_dimensions", "included_probes", "aggregation_method",
            "missing_evidence_rule", "decision_rule", "reset_or_stopping_rule",
            "subject_epoch", "calibration_epochs", "policy_digest",
        }
    },
    "R6E_BASELINE_EVOLUTION": {
        "required_transition_fields": {
            "predecessor_state_digest", "successor_state_digest", "behavioral_diff",
            "reason_and_evidence", "compatibility_class", "review_evidence",
            "effective_subject_epoch", "rollback_pointer",
        }
    },
    "R6F_SUSTAINED_RECOVERY": {
        "required_window_open_fields": {
            "session_id", "subject_epoch", "save_state_digest",
            "native_recovery_verification_digest", "start_turn", "start_generation",
            "policy_digest", "minimum_checkpoint_count", "minimum_turn_span",
            "checkpoint_admission_rule", "invalidation_rules",
        }
    },
}

EXPECTED_INDEPENDENCE_STATES = {
    "INDEPENDENT_WITHIN_DECLARED_SCOPE",
    "PARTIALLY_SHARED_ANCESTRY",
    "SHARED_ROOT_ANCESTRY",
    "COMMON_GENERATION_CHANNEL",
    "ANCESTRY_UNKNOWN",
}

EXPECTED_RECOVERY_STATES = [
    "PENDING_MORE_OBSERVATION",
    "SUSTAINED_BOUNDED_RECOVERY",
    "DEGRADED_DRIFT_RETURNED",
    "RELAPSE_BEHAVIORAL_DRIFT",
    "INDETERMINATE_EVIDENCE",
    "INVALIDATED_SUBJECT_OR_POLICY_CHANGE",
]

PINNED_FIXTURES = {
    "DG-R6-001": ("R6A_SUBJECT_IDENTITY", "NEW_SUBJECT_EPOCH"),
    "DG-R6-005": ("R6B_EVALUATOR_CALIBRATION", "UNKNOWN"),
    "DG-R6-009": ("R6C_PROVENANCE_INDEPENDENCE", "SHARED_ROOT_ANCESTRY"),
    "DG-R6-013": ("R6D_SEQUENTIAL_DETECTION", "REJECT_POST_HOC_POLICY"),
    "DG-R6-016": ("R6E_BASELINE_EVOLUTION", "REJECT_BASELINE_LAUNDERING"),
    "DG-R6-019": ("R6F_SUSTAINED_RECOVERY", "PENDING_MORE_OBSERVATION"),
    "DG-R6-020": ("R6F_SUSTAINED_RECOVERY", "REJECT_NOT_PRECOMMITTED"),
    "DG-R6-022": ("R6G_PROVIDER_EFFECT_EVIDENCE", "READBACK_REQUIRED_NO_RETRY_AUTHORITY"),
    "DG-R6-023": ("R6H_TAMPER_EVIDENCE", "REJECT_TAMPER_PROOF_CLAIM"),
    "DG-R6-024": ("R6H_TAMPER_EVIDENCE", "REJECT_INDEPENDENCE_INFERENCE"),
}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} root must be object")
    return value


def _phase_map(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    phases = spec.get("phases")
    if not isinstance(phases, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for item in phases:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            result[item["id"]] = item
    return result


def _exact_set(
    errors: list[str],
    actual: Any,
    expected: set[str],
    label: str,
) -> None:
    if not isinstance(actual, list) or set(actual) != expected or len(actual) != len(expected):
        errors.append(f"{label} must be exact closed set")


def validate_r6_longitudinal_research(root: Path) -> list[str]:
    errors: list[str] = []

    for relative in (DOC_PATH, SPEC_PATH, FIXTURE_PATH):
        if not (root / relative).is_file():
            errors.append(f"missing {relative}")
    if errors:
        return errors

    try:
        spec = _load(root / SPEC_PATH)
        fixtures = _load(root / FIXTURE_PATH)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return [f"research package invalid JSON: {exc}"]

    if spec.get("schema_version") != "DRIFTGUARD_R6_LONGITUDINAL_DRIFT_ARCHITECTURE_V0_1":
        errors.append("spec schema_version drifted")
    if spec.get("status") != "RESEARCH_PROPOSAL_MACHINE_CONTRACT":
        errors.append("spec must remain research proposal")
    if spec.get("repository") != "thebrazenbeard/driftguard":
        errors.append("repository binding drifted")
    if spec.get("source_issue") != 13:
        errors.append("source issue binding drifted")
    if spec.get("reviewed_base_head") != "e815c75ffccf469d9d1c09d58c0050798c8e4f53":
        errors.append("reviewed R4 base binding drifted")

    _exact_set(errors, spec.get("claim_ceiling"), EXPECTED_CLAIM_CEILING, "claim_ceiling")
    _exact_set(errors, spec.get("invariants"), EXPECTED_INVARIANTS, "invariants")

    phases = spec.get("phases")
    if not isinstance(phases, list):
        errors.append("phases must be list")
        phases = []
    ids = [item.get("id") for item in phases if isinstance(item, dict)]
    if ids != EXPECTED_PHASES:
        errors.append("phase order/set must remain exactly R6A..R6H")
    phase = _phase_map(spec)
    if set(phase) != set(EXPECTED_PHASES):
        errors.append("phase identities must be unique and complete")

    for phase_id, field_map in EXPECTED_FIELDS.items():
        item = phase.get(phase_id, {})
        for field_name, expected in field_map.items():
            _exact_set(errors, item.get(field_name), expected, f"{phase_id}.{field_name}")

    subject = phase.get("R6A_SUBJECT_IDENTITY", {}).get("rules", {})
    if subject.get("material_change_opens_new_epoch") is not True:
        errors.append("material subject change must open new epoch")
    if subject.get("session_continuity_proves_subject_continuity") is not False:
        errors.append("session continuity must not prove subject continuity")
    if subject.get("subject_manifest_proves_hidden_identity") is not False:
        errors.append("subject manifest must not prove hidden identity")
    if subject.get("privacy_preserving_digests_allowed") is not True:
        errors.append("privacy-preserving subject digests must remain allowed")

    calibration = phase.get("R6B_EVALUATOR_CALIBRATION", {}).get("rules", {})
    if calibration.get("missing_or_expired_calibration") != "UNKNOWN":
        errors.append("missing/expired calibration must fail to UNKNOWN")
    if calibration.get("evaluator_version_change_requires_new_epoch") is not True:
        errors.append("evaluator version change must require new calibration epoch")
    if calibration.get("target_outcomes_must_not_tune_same_evaluation_epoch") is not True:
        errors.append("post-hoc calibration tuning guard missing")
    if calibration.get("disagreement_must_remain_observable") is not True:
        errors.append("evaluator disagreement must remain observable")
    if calibration.get("calibration_proves_ground_truth") is not False:
        errors.append("calibration must not prove ground truth")

    provenance = phase.get("R6C_PROVENANCE_INDEPENDENCE", {})
    _exact_set(
        errors,
        provenance.get("independence_states"),
        EXPECTED_INDEPENDENCE_STATES,
        "R6C_PROVENANCE_INDEPENDENCE.independence_states",
    )
    provenance_rules = provenance.get("rules", {})
    if provenance_rules.get("unknown_ancestry_implies_independence") is not False:
        errors.append("unknown ancestry must not imply independence")
    if provenance_rules.get("distinct_agent_instances_imply_independence") is not False:
        errors.append("distinct agent instances must not imply independence")
    if provenance_rules.get("copied_descendants_count_as_new_corroboration") is not False:
        errors.append("copied descendants must not count as new corroboration")

    detection = phase.get("R6D_SEQUENTIAL_DETECTION", {}).get("rules", {})
    if detection.get("policy_must_preexist_classified_observations") is not True:
        errors.append("detection policy must preexist classified observations")
    if detection.get("raw_admitted_observations_preserved") is not True:
        errors.append("raw admitted observations must be preserved")
    if detection.get("post_outcome_threshold_selection_forbidden") is not True:
        errors.append("post-outcome threshold selection must be forbidden")
    if detection.get("missing_evidence_cannot_be_silently_dropped") is not True:
        errors.append("missing evidence cannot be silently dropped")

    baseline = phase.get("R6E_BASELINE_EVOLUTION", {}).get("rules", {})
    if baseline.get("drift_cannot_rewrite_baseline") is not True:
        errors.append("drift must not rewrite baseline")
    if baseline.get("promotion_is_not_recovery") is not True:
        errors.append("baseline promotion must not imply recovery")
    if baseline.get("predecessor_history_must_be_preserved") is not True:
        errors.append("baseline predecessor history must be preserved")

    recovery = phase.get("R6F_SUSTAINED_RECOVERY", {})
    if recovery.get("result_states") != EXPECTED_RECOVERY_STATES:
        errors.append("recovery result states/order drifted")
    recovery_rules = recovery.get("rules", {})
    if recovery_rules.get("window_must_open_before_later_observations") is not True:
        errors.append("recovery window must open before later observations")
    if recovery_rules.get("native_recovery_verification_required") is not True:
        errors.append("native recovery verification must seed sustained recovery")
    if recovery_rules.get("later_checkpoints_must_be_durable") is not True:
        errors.append("recovery checkpoints must be durable")
    if recovery_rules.get("operational_reload_trace_separate_from_behavioral_trace") is not True:
        errors.append("reload and behavioral traces must remain separate")
    if recovery_rules.get("past_window_proves_current_stability") is not False:
        errors.append("past window must not prove current stability")

    provider = phase.get("R6G_PROVIDER_EFFECT_EVIDENCE", {}).get("rules", {})
    if provider.get("generic_not_applied_grants_retry") is not False:
        errors.append("generic NOT_APPLIED must not grant retry")
    if provider.get("verified_readback_required_for_retry_authority") is not True:
        errors.append("verified readback must gate retry authority")
    if provider.get("provider_receipt_alone_proves_effect") is not False:
        errors.append("provider receipt alone must not prove effect")
    if provider.get("attempt_identity_must_be_exactly_bound") is not True:
        errors.append("provider effect must bind exact attempt identity")

    tamper = phase.get("R6H_TAMPER_EVIDENCE", {}).get("rules", {})
    if tamper.get("local_hash_chain_is_tamper_proof") is not False:
        errors.append("local hash chain must not be called tamper proof")
    if tamper.get("tamper_evident_not_tamper_impossible") is not True:
        errors.append("tamper-evident claim ceiling missing")
    if tamper.get("authenticated_source_implies_independence") is not False:
        errors.append("authentication must not imply independence")

    if spec.get("dependency_order") != EXPECTED_PHASES:
        errors.append("dependency order must remain R6A..R6H")

    gate = spec.get("r5_gate")
    expected_gate = {
        "canonical_review_required_for_pr8": True,
        "exact_hostile_review_required_for_pr11": True,
        "obsolete_external_recovery_helper_must_not_be_integrated": True,
        "discovery_adapter_is_optional_not_core_dependency": True,
        "fresh_combined_head_requires_independent_review": True,
    }
    if gate != expected_gate:
        errors.append("R5 integration gate must remain exact")

    if fixtures.get("schema_version") != "DRIFTGUARD_R6_LONGITUDINAL_HOSTILE_CASES_V0_1":
        errors.append("fixture schema_version drifted")
    if fixtures.get("status") != "RESEARCH_FIXTURES":
        errors.append("fixtures must remain research-only")
    cases = fixtures.get("cases")
    if not isinstance(cases, list):
        errors.append("fixture cases must be list")
        cases = []

    expected_ids = [f"DG-R6-{index:03d}" for index in range(1, 25)]
    actual_ids = [case.get("id") for case in cases if isinstance(case, dict)]
    if actual_ids != expected_ids:
        errors.append("fixture IDs must be contiguous DG-R6-001..024")

    expected_case_keys = {"id", "phase", "title", "expected", "reason"}
    by_id: dict[str, dict[str, Any]] = {}
    for case in cases:
        if not isinstance(case, dict):
            errors.append("fixture case must be object")
            continue
        if set(case) != expected_case_keys:
            errors.append(f"{case.get('id')} fixture fields must be exact")
        case_id = case.get("id")
        if isinstance(case_id, str):
            by_id[case_id] = case
        if case.get("phase") not in EXPECTED_PHASES:
            errors.append(f"{case_id} invalid phase")
        for field in ("title", "expected", "reason"):
            if not isinstance(case.get(field), str) or not case.get(field):
                errors.append(f"{case_id} missing {field}")

    for case_id, (expected_phase, expected_result) in PINNED_FIXTURES.items():
        case = by_id.get(case_id, {})
        if case.get("phase") != expected_phase or case.get("expected") != expected_result:
            errors.append(f"{case_id} pinned hostile expectation drifted")

    doc = (root / DOC_PATH).read_text(encoding="utf-8")
    required_doc_markers = {
        "RUNTIME_SUBJECT_BINDING != PERSON_IDENTITY",
        "CALIBRATED_SCORE != GROUND_TRUTH",
        "SOURCE_COUNT != INDEPENDENT_EVIDENCE_COUNT",
        "POST_HOC_THRESHOLD != PRECOMMITTED_DETECTION_POLICY",
        "OBSERVED_DRIFT != AUTHORITY_TO_CHANGE_BASELINE",
        "FIRST_STABLE_REPLAY != SUSTAINED_RECOVERY",
        "PAST_STABLE_WINDOW != CURRENT_STABILITY",
        "PROVIDER_RECEIPT != EFFECT_TRUTH_WITHOUT_VERIFIED_READBACK",
        "TAMPER_EVIDENT != TAMPER_IMPOSSIBLE",
    }
    for marker in sorted(required_doc_markers):
        if marker not in doc:
            errors.append(f"architecture doc missing marker: {marker}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    errors = validate_r6_longitudinal_research(Path(args.root).resolve())
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print("DriftGuard R6 longitudinal research architecture: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
