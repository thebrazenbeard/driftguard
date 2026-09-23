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


if __name__ == "__main__":
    unittest.main()
