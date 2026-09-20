from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from tools.validate_r6_controlled_benchmark import (
    DOC_PATH,
    SCENARIO_PATH,
    SPEC_PATH,
    validate_controlled_benchmark,
)

ROOT = Path(__file__).resolve().parents[1]


def _load(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _mutated(mutator) -> list[str]:
    spec = copy.deepcopy(_load(SPEC_PATH))
    scenarios = copy.deepcopy(_load(SCENARIO_PATH))
    mutator(spec, scenarios)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for relative in (DOC_PATH, SPEC_PATH, SCENARIO_PATH):
            (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / DOC_PATH).write_text(
            (ROOT / DOC_PATH).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (root / SPEC_PATH).write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
        (root / SCENARIO_PATH).write_text(
            json.dumps(scenarios, indent=2) + "\n",
            encoding="utf-8",
        )
        return validate_controlled_benchmark(root)


class ControlledLongitudinalBenchmarkTests(unittest.TestCase):
    def test_repository_benchmark_validates(self) -> None:
        self.assertEqual(validate_controlled_benchmark(ROOT), [])

    def test_benchmark_cannot_select_algorithm(self) -> None:
        errors = _mutated(lambda spec, _: spec.update({"method_selection": "CUSUM"}))
        self.assertTrue(any("must not select" in error for error in errors))

    def test_confirmatory_stage_cannot_be_deleted(self) -> None:
        errors = _mutated(lambda spec, _: spec["stages"].remove("CONFIRMATORY"))
        self.assertTrue(any("stages" in error for error in errors))

    def test_candidate_freeze_cannot_drop_policy_digest(self) -> None:
        errors = _mutated(
            lambda spec, _: spec["candidate_freeze_required_fields"].remove(
                "decision_policy_digest"
            )
        )
        self.assertTrue(any("candidate freeze" in error for error in errors))

    def test_evaluator_only_drift_family_is_pinned(self) -> None:
        def mutate(spec, _):
            next(item for item in spec["scenario_families"] if item["id"] == "BM-05")[
                "expected_claim"
            ] = "TARGET_DRIFT_DETECTABLE"
        errors = _mutated(mutate)
        self.assertTrue(any("scenario family" in error for error in errors))

    def test_missing_evidence_cannot_become_stable(self) -> None:
        def mutate(_, scenarios):
            next(item for item in scenarios["instances"] if item["id"] == "DG-BM-008")[
                "expected_claim"
            ] = "CONTROL_NO_TARGET_DRIFT_CLAIM"
        errors = _mutated(mutate)
        self.assertTrue(any("DG-BM-008" in error or "expected claim" in error for error in errors))

    def test_shared_root_cannot_escalate_independence(self) -> None:
        def mutate(_, scenarios):
            next(item for item in scenarios["instances"] if item["id"] == "DG-BM-007")[
                "expected_claim"
            ] = "INDEPENDENT_CORROBORATION"
        errors = _mutated(mutate)
        self.assertTrue(any("DG-BM-007" in error or "expected claim" in error for error in errors))

    def test_periodic_reload_cannot_become_behavioral_drift(self) -> None:
        def mutate(_, scenarios):
            next(item for item in scenarios["instances"] if item["id"] == "DG-BM-009")[
                "expected_claim"
            ] = "TARGET_DRIFT_DETECTABLE"
        errors = _mutated(mutate)
        self.assertTrue(any("DG-BM-009" in error or "expected claim" in error for error in errors))

    def test_subject_epoch_change_cannot_continue_same_series(self) -> None:
        def mutate(_, scenarios):
            next(item for item in scenarios["instances"] if item["id"] == "DG-BM-011")[
                "expected_claim"
            ] = "CONTROL_NO_TARGET_DRIFT_CLAIM"
        errors = _mutated(mutate)
        self.assertTrue(any("DG-BM-011" in error or "expected claim" in error for error in errors))

    def test_post_hoc_policy_cannot_be_confirmatory_pass(self) -> None:
        def mutate(_, scenarios):
            next(item for item in scenarios["instances"] if item["id"] == "DG-BM-012")[
                "expected_claim"
            ] = "SUSTAINED_BOUNDED_RECOVERY"
        errors = _mutated(mutate)
        self.assertTrue(any("DG-BM-012" in error or "expected claim" in error for error in errors))

    def test_invalid_state_set_is_closed(self) -> None:
        errors = _mutated(
            lambda spec, _: spec["confirmatory_invalid_states"].remove(
                "CONFIRMATORY_LEAKAGE"
            )
        )
        self.assertTrue(any("invalid states" in error for error in errors))

    def test_default_numeric_thresholds_cannot_be_canonized(self) -> None:
        errors = _mutated(
            lambda spec, _: spec["quantitative_acceptance_policy"].update(
                {"canonized_default_thresholds": True}
            )
        )
        self.assertTrue(any("quantitative" in error for error in errors))

    def test_claim_ceiling_is_closed(self) -> None:
        errors = _mutated(lambda spec, _: spec["claim_ceiling"].append("PRODUCTION_READY"))
        self.assertTrue(any("claim ceiling" in error for error in errors))

    def test_scenario_fields_are_closed(self) -> None:
        def mutate(_, scenarios):
            scenarios["instances"][0]["merge_authority"] = True
        errors = _mutated(mutate)
        self.assertTrue(any("scenario fields" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
