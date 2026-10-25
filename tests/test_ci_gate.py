from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from driftguard.ci_gate import (
    CiPolicy,
    CiReport,
    GateDecision,
    MetricSeverity,
    evaluate_ci,
    render_markdown,
)


POLICY = {
    "schema": "DRIFTGUARD_CI_POLICY_V1",
    "policy_id": "agent-quality",
    "unknown": "block",
    "metric": [
        {
            "name": "task_success",
            "direction": "higher",
            "max_regression": 0.03,
            "min_candidate": 0.90,
            "severity": "block",
        },
        {
            "name": "latency_ms",
            "direction": "lower",
            "max_regression": 250.0,
            "max_candidate": 2500.0,
            "severity": "warn",
        },
    ],
}


def report(run_id: str, **metrics) -> CiReport:
    return CiReport.from_mapping(
        {
            "schema": "DRIFTGUARD_CI_REPORT_V1",
            "run_id": run_id,
            "subject": "checkout-agent",
            "metrics": metrics,
        }
    )


class CiGateTests(unittest.TestCase):
    def setUp(self):
        self.policy = CiPolicy.from_mapping(POLICY)
        self.baseline = report(
            "baseline",
            task_success=0.95,
            latency_ms=1000,
        )

    def test_passes_within_regression_budget(self):
        result = evaluate_ci(
            policy=self.policy,
            baseline=self.baseline,
            candidate=report(
                "candidate",
                task_success=0.93,
                latency_ms=1100,
            ),
        )
        self.assertEqual(result.decision, GateDecision.PASS)
        self.assertEqual(result.exit_code, 0)

    def test_blocking_metric_blocks(self):
        result = evaluate_ci(
            policy=self.policy,
            baseline=self.baseline,
            candidate=report(
                "candidate",
                task_success=0.89,
                latency_ms=1000,
            ),
        )
        self.assertEqual(result.decision, GateDecision.BLOCK)
        self.assertEqual(result.exit_code, 1)

    def test_warning_metric_warns_without_failing_ci(self):
        result = evaluate_ci(
            policy=self.policy,
            baseline=self.baseline,
            candidate=report(
                "candidate",
                task_success=0.95,
                latency_ms=1400,
            ),
        )
        self.assertEqual(result.decision, GateDecision.WARN)
        self.assertEqual(result.exit_code, 0)

    def test_missing_required_metric_is_unknown(self):
        result = evaluate_ci(
            policy=self.policy,
            baseline=self.baseline,
            candidate=report("candidate", task_success=0.95),
        )
        self.assertEqual(result.decision, GateDecision.UNKNOWN)
        self.assertEqual(result.exit_code, 2)

    def test_unknown_can_be_warning(self):
        raw = dict(POLICY)
        raw["unknown"] = "warn"
        policy = CiPolicy.from_mapping(raw)
        result = evaluate_ci(
            policy=policy,
            baseline=self.baseline,
            candidate=report("candidate", task_success=0.95),
        )
        self.assertEqual(result.decision, GateDecision.WARN)
        self.assertEqual(result.exit_code, 0)

    def test_subject_mismatch_is_unknown(self):
        candidate = CiReport.from_mapping(
            {
                "schema": "DRIFTGUARD_CI_REPORT_V1",
                "run_id": "candidate",
                "subject": "different-agent",
                "metrics": {
                    "task_success": 0.95,
                    "latency_ms": 1000,
                },
            }
        )
        result = evaluate_ci(
            policy=self.policy,
            baseline=self.baseline,
            candidate=candidate,
        )
        self.assertEqual(result.decision, GateDecision.UNKNOWN)
        self.assertIn("baseline_candidate_subject_mismatch", result.reasons)

    def test_candidate_cannot_omit_trusted_baseline_subject(self):
        candidate = CiReport.from_mapping(
            {
                "schema": "DRIFTGUARD_CI_REPORT_V1",
                "run_id": "candidate",
                "metrics": {
                    "task_success": 0.95,
                    "latency_ms": 1000,
                },
            }
        )
        result = evaluate_ci(
            policy=self.policy,
            baseline=self.baseline,
            candidate=candidate,
        )
        self.assertEqual(result.decision, GateDecision.UNKNOWN)
        self.assertIn("baseline_candidate_subject_mismatch", result.reasons)

    def test_report_rejects_untrusted_preview_authority_fields(self):
        trusted_shape = {
            "schema": "DRIFTGUARD_CI_REPORT_V1",
            "run_id": "candidate",
            "subject": "checkout-agent",
            "metrics": {"task_success": 0.95},
        }
        for key, value in (
            ("admission_eligible", False),
            ("preview_only", True),
            ("authorization_effect", "NONE"),
            ("independent_custody_verified", False),
            ("driftguard_preview", {"admission_eligible": False}),
        ):
            with self.subTest(field=key):
                with self.assertRaisesRegex(ValueError, "unknown CI report field"):
                    CiReport.from_mapping({**trusted_shape, key: value})

    def test_json_report_rejects_relabelled_preview_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidate.json"
            path.write_text(
                '{"schema":"DRIFTGUARD_CI_REPORT_V1",'
                '"run_id":"candidate","metrics":{"task_success":0.95},'
                '"authorization_effect":"NONE","admission_eligible":false}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "unknown CI report field"):
                CiReport.load(path)

    def test_policy_digest_is_order_stable(self):
        first = self.policy.digest
        raw = {
            "unknown": "block",
            "metric": list(reversed(POLICY["metric"])),
            "policy_id": "agent-quality",
            "schema": "DRIFTGUARD_CI_POLICY_V1",
        }
        second = CiPolicy.from_mapping(raw).digest
        self.assertEqual(first, second)

    def test_report_rejects_duplicate_names_after_normalization(self):
        with self.assertRaisesRegex(ValueError, "duplicate report metric name"):
            CiReport.from_mapping(
                {
                    "schema": "DRIFTGUARD_CI_REPORT_V1",
                    "run_id": "candidate",
                    "subject": "checkout-agent",
                    "metrics": {
                        "task_success": 0.1,
                        " task_success ": 0.95,
                    },
                }
            )

    def test_json_report_rejects_duplicate_names_after_normalization(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidate.json"
            path.write_text(
                '{"schema":"DRIFTGUARD_CI_REPORT_V1",'
                '"run_id":"candidate","subject":"checkout-agent",'
                '"metrics":{"task_success":0.1," task_success ":0.95}}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "duplicate report metric name"):
                CiReport.load(path)

    def test_tiny_nonzero_regression_exceeds_zero_budget(self):
        policy = CiPolicy.from_mapping({
            "schema": "DRIFTGUARD_CI_POLICY_V1",
            "policy_id": "strict",
            "metric": [{
                "name": "quality", "direction": "higher",
                "max_regression": 0, "severity": "block",
            }],
        })
        result = evaluate_ci(
            policy=policy,
            baseline=report("baseline", quality=1.0),
            candidate=report("candidate", quality=0.9999999999996),
        )
        self.assertEqual(result.decision, GateDecision.BLOCK)
        self.assertGreater(result.metrics[0].regression, 0)
        self.assertEqual(len(result.digest), 64)

    def test_decimal_threshold_equality_is_not_a_regression(self):
        policy = CiPolicy.from_mapping({
            "schema": "DRIFTGUARD_CI_POLICY_V1",
            "policy_id": "bounded",
            "metric": [{
                "name": "quality", "direction": "higher",
                "max_regression": 0.02, "severity": "block",
            }],
        })
        result = evaluate_ci(
            policy=policy,
            baseline=report("baseline", quality=1.0),
            candidate=report("candidate", quality=0.98),
        )
        self.assertEqual(result.decision, GateDecision.PASS)
        self.assertEqual(result.metrics[0].regression, 0.02)

    def test_decimal_budget_cannot_hide_small_exponent_addend(self):
        policy = CiPolicy.from_mapping({
            "schema": "DRIFTGUARD_CI_POLICY_V1",
            "policy_id": "exact-decimal",
            "metric": [{
                "name": "quality", "direction": "higher",
                "max_regression": 1e100, "severity": "block",
            }],
        })
        result = evaluate_ci(
            policy=policy,
            baseline=report("baseline", quality=1e100),
            candidate=report("candidate", quality=-1e-100),
        )
        self.assertEqual(result.decision, GateDecision.BLOCK)
        self.assertEqual(result.exit_code, 1)
        self.assertIn(
            "regression_exceeds_limit_below_display_resolution",
            result.metrics[0].reasons,
        )
        self.assertEqual(len(result.digest), 64)

    def test_reason_does_not_render_distinct_regressions_as_equal(self):
        policy = CiPolicy.from_mapping({
            "schema": "DRIFTGUARD_CI_POLICY_V1",
            "policy_id": "display-precision",
            "metric": [{
                "name": "quality", "direction": "higher",
                "max_regression": 0.1234567890123, "severity": "block",
            }],
        })
        result = evaluate_ci(
            policy=policy,
            baseline=report("baseline", quality=1.0),
            candidate=report("candidate", quality=0.8765432109876),
        )
        self.assertEqual(result.decision, GateDecision.BLOCK)
        self.assertIn(
            "regression_exceeds_limit_below_display_resolution",
            result.metrics[0].reasons,
        )

    def test_finite_inputs_with_unrepresentable_regression_fail_closed(self):
        for unknown in ("block", "warn"):
            with self.subTest(unknown=unknown):
                policy = CiPolicy.from_mapping({
                    "schema": "DRIFTGUARD_CI_POLICY_V1",
                    "policy_id": "extreme",
                    "unknown": unknown,
                    "metric": [{
                        "name": "quality", "direction": "higher",
                        "max_regression": 0, "severity": "block",
                    }],
                })
                result = evaluate_ci(
                    policy=policy,
                    baseline=report("baseline", quality=1e308),
                    candidate=report("candidate", quality=-1e308),
                )
                self.assertEqual(result.decision, GateDecision.UNKNOWN)
                self.assertEqual(result.exit_code, 2)
                self.assertIsNone(result.metrics[0].regression)
                self.assertIn("regression_unrepresentable", result.metrics[0].reasons)
                self.assertIn("one_or_more_regressions_unrepresentable", result.reasons)
                self.assertEqual(len(result.digest), 64)

    def test_oversized_json_number_has_controlled_validation_error(self):
        with self.assertRaisesRegex(ValueError, "must be finite"):
            report("candidate", quality=10 ** 309)

    def test_integer_metric_cannot_silently_lose_precision(self):
        exact = report("candidate", quality=2 ** 53)
        self.assertEqual(dict(exact.metrics)["quality"], 2 ** 53)
        with self.assertRaisesRegex(ValueError, "cannot be represented exactly"):
            report("candidate", quality=2 ** 53 + 1)

    def test_markdown_contains_result_digest(self):
        result = evaluate_ci(
            policy=self.policy,
            baseline=self.baseline,
            candidate=report(
                "candidate",
                task_success=0.95,
                latency_ms=1000,
            ),
        )
        rendered = render_markdown(result)
        self.assertIn("## DriftGuard: PASS", rendered)
        self.assertIn(result.digest, rendered)

    def test_loads_toml_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "driftguard.toml"
            path.write_text(
                """schema = "DRIFTGUARD_CI_POLICY_V1"
policy_id = "demo"
unknown = "block"

[[metric]]
name = "quality"
direction = "higher"
max_regression = 0.01
severity = "block"
""",
                encoding="utf-8",
            )
            loaded = CiPolicy.load(path)
            self.assertEqual(loaded.policy_id, "demo")
            self.assertEqual(loaded.unknown, MetricSeverity.BLOCK)

    def test_rejects_unrecognized_root_policy_key(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "driftguard.toml"
            path.write_text(
                '''schema = "DRIFTGUARD_CI_POLICY_V1"
policy_id = "demo"
unknwon = "warn"

[[metric]]
name = "quality"
direction = "higher"
max_regression = 0
''',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "unknown CI policy field"):
                CiPolicy.load(path)

    def test_rejects_unrecognized_metric_policy_key(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "driftguard.toml"
            path.write_text(
                '''schema = "DRIFTGUARD_CI_POLICY_V1"
policy_id = "demo"

[[metric]]
name = "quality"
direction = "higher"
max_regression = 0
min_canidate = 0.90
''',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "unknown metric policy field"):
                CiPolicy.load(path)


if __name__ == "__main__":
    unittest.main()
