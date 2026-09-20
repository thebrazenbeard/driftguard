from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from tools.validate_r6_longitudinal_research import (
    DOC_PATH,
    FIXTURE_PATH,
    SPEC_PATH,
    validate_r6_longitudinal_research,
)

ROOT = Path(__file__).resolve().parents[1]


def _load(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _phase(spec: dict, phase_id: str) -> dict:
    return next(item for item in spec["phases"] if item["id"] == phase_id)


def _mutated(mutator) -> list[str]:
    spec = copy.deepcopy(_load(SPEC_PATH))
    fixtures = copy.deepcopy(_load(FIXTURE_PATH))
    mutator(spec, fixtures)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for relative in (DOC_PATH, SPEC_PATH, FIXTURE_PATH):
            (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / DOC_PATH).write_text(
            (ROOT / DOC_PATH).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (root / SPEC_PATH).write_text(
            json.dumps(spec, indent=2) + "\n",
            encoding="utf-8",
        )
        (root / FIXTURE_PATH).write_text(
            json.dumps(fixtures, indent=2) + "\n",
            encoding="utf-8",
        )
        return validate_r6_longitudinal_research(root)


class DriftGuardR6LongitudinalResearchTests(unittest.TestCase):
    def test_repository_research_package_validates(self) -> None:
        self.assertEqual(validate_r6_longitudinal_research(ROOT), [])

    def test_claim_ceiling_is_closed_set(self) -> None:
        errors = _mutated(
            lambda spec, _: spec["claim_ceiling"].append("PRODUCTION_READY")
        )
        self.assertTrue(any("claim_ceiling" in error for error in errors))

    def test_session_continuity_cannot_become_subject_identity(self) -> None:
        errors = _mutated(
            lambda spec, _: _phase(spec, "R6A_SUBJECT_IDENTITY")["rules"].update(
                {"session_continuity_proves_subject_continuity": True}
            )
        )
        self.assertTrue(any("session continuity" in error for error in errors))

    def test_subject_fields_are_closed_set(self) -> None:
        errors = _mutated(
            lambda spec, _: _phase(spec, "R6A_SUBJECT_IDENTITY")["required_fields"].append(
                "person_identity"
            )
        )
        self.assertTrue(any("required_fields" in error for error in errors))

    def test_missing_calibration_cannot_become_stable_measurement(self) -> None:
        errors = _mutated(
            lambda spec, _: _phase(spec, "R6B_EVALUATOR_CALIBRATION")["rules"].update(
                {"missing_or_expired_calibration": "STABLE"}
            )
        )
        self.assertTrue(any("calibration" in error for error in errors))

    def test_calibration_cannot_claim_ground_truth(self) -> None:
        errors = _mutated(
            lambda spec, _: _phase(spec, "R6B_EVALUATOR_CALIBRATION")["rules"].update(
                {"calibration_proves_ground_truth": True}
            )
        )
        self.assertTrue(any("ground truth" in error for error in errors))

    def test_unknown_ancestry_cannot_be_promoted_to_independent(self) -> None:
        errors = _mutated(
            lambda spec, _: _phase(spec, "R6C_PROVENANCE_INDEPENDENCE")["rules"].update(
                {"unknown_ancestry_implies_independence": True}
            )
        )
        self.assertTrue(any("unknown ancestry" in error for error in errors))

    def test_independence_states_are_closed_set(self) -> None:
        errors = _mutated(
            lambda spec, _: _phase(spec, "R6C_PROVENANCE_INDEPENDENCE")[
                "independence_states"
            ].append("FULLY_INDEPENDENT")
        )
        self.assertTrue(any("independence_states" in error for error in errors))

    def test_post_outcome_threshold_selection_is_rejected(self) -> None:
        errors = _mutated(
            lambda spec, _: _phase(spec, "R6D_SEQUENTIAL_DETECTION")["rules"].update(
                {"post_outcome_threshold_selection_forbidden": False}
            )
        )
        self.assertTrue(any("post-outcome" in error for error in errors))

    def test_missing_evidence_cannot_be_silently_dropped(self) -> None:
        errors = _mutated(
            lambda spec, _: _phase(spec, "R6D_SEQUENTIAL_DETECTION")["rules"].update(
                {"missing_evidence_cannot_be_silently_dropped": False}
            )
        )
        self.assertTrue(any("missing evidence" in error for error in errors))

    def test_drift_cannot_rewrite_baseline(self) -> None:
        errors = _mutated(
            lambda spec, _: _phase(spec, "R6E_BASELINE_EVOLUTION")["rules"].update(
                {"drift_cannot_rewrite_baseline": False}
            )
        )
        self.assertTrue(any("rewrite baseline" in error for error in errors))

    def test_recovery_window_must_preexist_later_observations(self) -> None:
        errors = _mutated(
            lambda spec, _: _phase(spec, "R6F_SUSTAINED_RECOVERY")["rules"].update(
                {"window_must_open_before_later_observations": False}
            )
        )
        self.assertTrue(any("open before" in error for error in errors))

    def test_past_window_cannot_become_current_stability(self) -> None:
        errors = _mutated(
            lambda spec, _: _phase(spec, "R6F_SUSTAINED_RECOVERY")["rules"].update(
                {"past_window_proves_current_stability": True}
            )
        )
        self.assertTrue(any("current stability" in error for error in errors))

    def test_generic_not_applied_cannot_grant_retry(self) -> None:
        errors = _mutated(
            lambda spec, _: _phase(spec, "R6G_PROVIDER_EFFECT_EVIDENCE")["rules"].update(
                {"generic_not_applied_grants_retry": True}
            )
        )
        self.assertTrue(any("NOT_APPLIED" in error for error in errors))

    def test_local_hash_chain_cannot_claim_tamper_proof(self) -> None:
        errors = _mutated(
            lambda spec, _: _phase(spec, "R6H_TAMPER_EVIDENCE")["rules"].update(
                {"local_hash_chain_is_tamper_proof": True}
            )
        )
        self.assertTrue(any("tamper proof" in error for error in errors))

    def test_dependency_order_is_closed(self) -> None:
        errors = _mutated(
            lambda spec, _: spec["dependency_order"].reverse()
        )
        self.assertTrue(any("dependency order" in error for error in errors))

    def test_r5_gate_cannot_make_discovery_mandatory(self) -> None:
        errors = _mutated(
            lambda spec, _: spec["r5_gate"].update(
                {"discovery_adapter_is_optional_not_core_dependency": False}
            )
        )
        self.assertTrue(any("R5 integration gate" in error for error in errors))

    def test_fixture_ids_are_contiguous(self) -> None:
        def mutate(_, fixtures):
            fixtures["cases"].pop(3)
        errors = _mutated(mutate)
        self.assertTrue(any("contiguous" in error for error in errors))

    def test_post_hoc_policy_fixture_is_pinned(self) -> None:
        def mutate(_, fixtures):
            next(
                case for case in fixtures["cases"] if case["id"] == "DG-R6-020"
            )["expected"] = "SUSTAINED_BOUNDED_RECOVERY"
        errors = _mutated(mutate)
        self.assertTrue(any("DG-R6-020" in error for error in errors))

    def test_fixture_fields_are_closed(self) -> None:
        def mutate(_, fixtures):
            fixtures["cases"][0]["authority"] = "merge"
        errors = _mutated(mutate)
        self.assertTrue(any("fixture fields" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
