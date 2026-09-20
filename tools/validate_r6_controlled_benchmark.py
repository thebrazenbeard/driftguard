from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DOC_PATH = "docs/research/DRIFTGUARD_R6_CONTROLLED_LONGITUDINAL_BENCHMARK_V0_1.md"
SPEC_PATH = "specs/research/DRIFTGUARD_R6_CONTROLLED_LONGITUDINAL_BENCHMARK_V0_1.json"
SCENARIO_PATH = "specs/research/fixtures/DRIFTGUARD_R6_CONTROLLED_BENCHMARK_SCENARIOS_V0_1.json"

EXPECTED_STAGES = ["DESIGN", "CALIBRATION", "CONFIRMATORY"]

EXPECTED_INVARIANTS = {
    "BENCHMARK_PASS_NE_ALGORITHM_ADMISSION",
    "ALGORITHM_ADMISSION_NE_PRODUCTION_READINESS",
    "SYNTHETIC_DETECTION_SUCCESS_NE_REAL_WORLD_VALIDATION",
    "CONFIRMATORY_DATA_NE_CALIBRATION_DATA",
    "POST_OUTCOME_TUNING_NE_CONFIRMATORY_EVIDENCE",
    "EVALUATOR_CHANGE_NE_TARGET_CHANGE",
    "MISSING_EVIDENCE_NE_STABLE",
    "SOURCE_COUNT_NE_INDEPENDENT_EVIDENCE_COUNT",
    "PERIODIC_RELOAD_NE_BEHAVIORAL_DRIFT",
    "SESSION_CONTINUITY_NE_SUBJECT_CONTINUITY",
}

EXPECTED_FREEZE_FIELDS = {
    "detector_id",
    "detector_version",
    "implementation_digest",
    "parameter_digest",
    "decision_policy_digest",
    "reset_stopping_rule_digest",
    "missing_evidence_rule_digest",
    "subject_manifest_version",
    "evaluator_calibration_version",
    "provenance_policy_version",
    "benchmark_suite_version",
    "seed_set_digest",
    "acceptance_criteria_digest",
    "frozen_at",
}

EXPECTED_FAMILIES = [
    ("BM-01", "NO_DRIFT_CONTROL", "CONTROL_NO_TARGET_DRIFT_CLAIM"),
    ("BM-02", "ABRUPT_TARGET_DRIFT", "TARGET_DRIFT_DETECTABLE"),
    ("BM-03", "GRADUAL_TARGET_DRIFT", "GRADUAL_CHANGE_EVIDENCE_PRESERVED"),
    ("BM-04", "RECURRING_TARGET_DRIFT", "RECURRING_DRIFT_PATTERN_PRESERVED"),
    ("BM-05", "EVALUATOR_ONLY_DRIFT", "EVALUATOR_DRIFT_OR_MEASUREMENT_INVALID"),
    ("BM-06", "TARGET_DRIFT_STABLE_EVALUATOR", "TARGET_DRIFT_NOT_ERASED_BY_EVALUATOR_STABILITY"),
    ("BM-07", "SHARED_ROOT_CORRELATED_PROBES", "NO_INDEPENDENCE_ESCALATION"),
    ("BM-08", "MISSING_EVIDENCE", "INDETERMINATE_NOT_STABLE"),
    ("BM-09", "PERIODIC_RELOAD_NO_BEHAVIORAL_DRIFT", "OPERATIONAL_RELOAD_NOT_BEHAVIORAL_DRIFT"),
    ("BM-10", "BASELINE_SUCCESSOR_EPOCH", "NEW_BASELINE_EPOCH"),
    ("BM-11", "SUBJECT_EPOCH_CHANGE", "INVALIDATED_SUBJECT_OR_POLICY_CHANGE"),
    ("BM-12", "POST_HOC_POLICY_MUTATION", "INVALID_EXPERIMENT_POST_HOC_POLICY"),
]

EXPECTED_MEASUREMENTS = {
    "false_alert_count",
    "detection_delay_turns",
    "missed_target_drift_events",
    "evaluator_target_confusion_count",
    "missing_evidence_outcomes",
    "independence_escalation_count",
    "reload_behavior_conflation_count",
    "epoch_invalidation_count",
    "failed_or_aborted_runs",
    "candidate_freeze_id",
    "scenario_instance_id",
}

EXPECTED_INVALID_STATES = {
    "POST_HOC_POLICY_CHANGE",
    "CONFIRMATORY_LEAKAGE",
    "OUTCOME_DROPPED_FROM_REPORT",
    "EVALUATOR_DRIFT_MISLABELED_TARGET_DRIFT",
    "MISSING_EVIDENCE_CLASSIFIED_STABLE",
    "SHARED_ROOT_COUNTED_INDEPENDENT",
    "BASELINE_MUTATED_TO_ERASE_DRIFT",
    "SUBJECT_CHANGE_CONTINUED_AS_SAME_SERIES",
    "PERIODIC_RELOAD_LABELED_BEHAVIORAL_DRIFT",
}

EXPECTED_INSTANCE_FIELDS = {
    "scenario_id",
    "scenario_version",
    "subject_epoch",
    "save_state_digest",
    "evaluator_calibration_epoch",
    "provenance_topology_digest",
    "turn_sequence_digest",
    "hidden_injection_schedule_digest",
    "evidence_completeness_schedule_digest",
    "operational_reload_schedule_digest",
    "expected_claim",
}

EXPECTED_CLAIM_CEILING = {
    "NO_ALGORITHM_ADMISSION",
    "NO_RUNTIME_DETECTOR_IMPLEMENTATION",
    "NO_REAL_WORLD_GENERALIZATION_CLAIM",
    "NO_PROVIDER_OR_EVALUATOR_HONESTY_CLAIM",
    "NO_HIDDEN_STATE_OR_IDENTITY_CLAIM",
    "NO_PRODUCTION_READINESS",
    "NO_MERGE_OR_DEPLOY_AUTHORITY",
}

SCENARIO_FIELDS = {
    "id",
    "family",
    "target_schedule",
    "evaluator_schedule",
    "evidence_schedule",
    "provenance",
    "reload_schedule",
    "expected_claim",
}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} root must be object")
    return value


def _exact_set(errors: list[str], value: Any, expected: set[str], label: str) -> None:
    if not isinstance(value, list) or len(value) != len(expected) or set(value) != expected:
        errors.append(f"{label} must be exact closed set")


def validate_controlled_benchmark(root: Path) -> list[str]:
    errors: list[str] = []
    for relative in (DOC_PATH, SPEC_PATH, SCENARIO_PATH):
        if not (root / relative).is_file():
            errors.append(f"missing {relative}")
    if errors:
        return errors

    try:
        spec = _load(root / SPEC_PATH)
        scenarios = _load(root / SCENARIO_PATH)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return [f"benchmark package invalid JSON: {exc}"]

    if spec.get("schema_version") != "DRIFTGUARD_R6_CONTROLLED_LONGITUDINAL_BENCHMARK_V0_1":
        errors.append("benchmark schema_version drifted")
    if spec.get("status") != "RESEARCH_BENCHMARK_CONTRACT":
        errors.append("benchmark must remain research contract")
    if spec.get("parent_architecture") != "DRIFTGUARD_R6_LONGITUDINAL_DRIFT_ARCHITECTURE_V0_1":
        errors.append("parent architecture binding drifted")
    if spec.get("method_selection") != "NONE":
        errors.append("benchmark must not select a detector method")
    if spec.get("stages") != EXPECTED_STAGES:
        errors.append("experimental stages/order drifted")

    _exact_set(errors, spec.get("invariants"), EXPECTED_INVARIANTS, "invariants")
    _exact_set(
        errors,
        spec.get("candidate_freeze_required_fields"),
        EXPECTED_FREEZE_FIELDS,
        "candidate freeze fields",
    )
    _exact_set(
        errors,
        spec.get("required_measurements"),
        EXPECTED_MEASUREMENTS,
        "required measurements",
    )
    _exact_set(
        errors,
        spec.get("confirmatory_invalid_states"),
        EXPECTED_INVALID_STATES,
        "confirmatory invalid states",
    )
    _exact_set(
        errors,
        spec.get("scenario_instance_required_fields"),
        EXPECTED_INSTANCE_FIELDS,
        "scenario instance required fields",
    )
    _exact_set(errors, spec.get("claim_ceiling"), EXPECTED_CLAIM_CEILING, "claim ceiling")

    families = spec.get("scenario_families")
    if not isinstance(families, list):
        errors.append("scenario_families must be list")
        families = []
    actual_families = []
    for item in families:
        if not isinstance(item, dict) or set(item) != {"id", "class", "expected_claim"}:
            errors.append("scenario family fields must be exact")
            continue
        actual_families.append((item["id"], item["class"], item["expected_claim"]))
    if actual_families != EXPECTED_FAMILIES:
        errors.append("scenario family identities/order/expectations drifted")

    quantitative = spec.get("quantitative_acceptance_policy")
    expected_quantitative = {
        "canonized_default_thresholds": False,
        "criteria_must_be_method_specific": True,
        "criteria_must_be_precommitted": True,
        "criteria_must_be_versioned": True,
    }
    if quantitative != expected_quantitative:
        errors.append("quantitative acceptance policy drifted")

    if scenarios.get("schema_version") != "DRIFTGUARD_R6_CONTROLLED_BENCHMARK_SCENARIOS_V0_1":
        errors.append("scenario schema_version drifted")
    if scenarios.get("status") != "RESEARCH_FIXTURES":
        errors.append("scenarios must remain research fixtures")

    instances = scenarios.get("instances")
    if not isinstance(instances, list):
        errors.append("instances must be list")
        instances = []

    expected_ids = [f"DG-BM-{index:03d}" for index in range(1, 13)]
    actual_ids = [item.get("id") for item in instances if isinstance(item, dict)]
    if actual_ids != expected_ids:
        errors.append("scenario IDs must be contiguous DG-BM-001..012")

    family_map = {item[0]: item[2] for item in EXPECTED_FAMILIES}
    seen_families: list[str] = []
    for item in instances:
        if not isinstance(item, dict):
            errors.append("scenario instance must be object")
            continue
        if set(item) != SCENARIO_FIELDS:
            errors.append(f"{item.get('id')} scenario fields must be exact")
        family = item.get("family")
        seen_families.append(family)
        if family not in family_map:
            errors.append(f"{item.get('id')} references unknown family")
        elif item.get("expected_claim") != family_map[family]:
            errors.append(f"{item.get('id')} expected claim drifted")
        for field in SCENARIO_FIELDS:
            if not isinstance(item.get(field), str) or not item.get(field):
                errors.append(f"{item.get('id')} missing {field}")

    if seen_families != [item[0] for item in EXPECTED_FAMILIES]:
        errors.append("each scenario family must have one ordered fixture instance")

    by_id = {
        item.get("id"): item
        for item in instances
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    pinned = {
        "DG-BM-005": ("EVALUATOR_ONLY_DRIFT", "EVALUATOR_DRIFT_OR_MEASUREMENT_INVALID"),
        "DG-BM-007": ("SHARED_ROOT_CORRELATED_PROBES", "NO_INDEPENDENCE_ESCALATION"),
        "DG-BM-008": ("MISSING_EVIDENCE", "INDETERMINATE_NOT_STABLE"),
        "DG-BM-009": ("PERIODIC_RELOAD_NO_BEHAVIORAL_DRIFT", "OPERATIONAL_RELOAD_NOT_BEHAVIORAL_DRIFT"),
        "DG-BM-010": ("BASELINE_SUCCESSOR_EPOCH", "NEW_BASELINE_EPOCH"),
        "DG-BM-011": ("SUBJECT_EPOCH_CHANGE", "INVALIDATED_SUBJECT_OR_POLICY_CHANGE"),
        "DG-BM-012": ("POST_HOC_POLICY_MUTATION", "INVALID_EXPERIMENT_POST_HOC_POLICY"),
    }
    family_class = {item[0]: item[1] for item in EXPECTED_FAMILIES}
    for fixture_id, (expected_class, expected_claim) in pinned.items():
        item = by_id.get(fixture_id, {})
        family = item.get("family")
        if family_class.get(family) != expected_class or item.get("expected_claim") != expected_claim:
            errors.append(f"{fixture_id} pinned benchmark expectation drifted")

    doc = (root / DOC_PATH).read_text(encoding="utf-8")
    for marker in (
        "BENCHMARK_PASS != ALGORITHM_ADMISSION",
        "CONFIRMATORY_DATA != CALIBRATION_DATA",
        "POST_OUTCOME_TUNING != CONFIRMATORY_EVIDENCE",
        "EVALUATOR_CHANGE != TARGET_CHANGE",
        "SOURCE_COUNT != INDEPENDENT_EVIDENCE_COUNT",
        "A single aggregate score must never replace per-scenario evidence.",
    ):
        if marker not in doc:
            errors.append(f"benchmark doc missing marker: {marker}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    errors = validate_controlled_benchmark(Path(args.root).resolve())
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print("DriftGuard R6 controlled longitudinal benchmark: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
