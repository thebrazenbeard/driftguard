from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from driftguard.adoption import (
    AdoptionError,
    build_report,
    parse_metric_assignments,
    promote_baseline_file,
    qualify_baseline_promotion,
)
from driftguard.ci_gate import CiPolicy, CiReport


POLICY = {
    "schema": "DRIFTGUARD_CI_POLICY_V1",
    "policy_id": "quality-v1",
    "unknown": "block",
    "metric": [
        {
            "name": "quality",
            "direction": "higher",
            "max_regression": 0.02,
            "min_candidate": 0.90,
            "severity": "block",
        }
    ],
}


class AdoptionTests(unittest.TestCase):
    def test_metric_assignment_parser(self):
        parsed = parse_metric_assignments(
            ["quality=0.95", "latency_ms=123.5"]
        )
        self.assertEqual(
            parsed,
            {"quality": 0.95, "latency_ms": 123.5},
        )

    def test_metric_assignment_rejects_duplicates(self):
        with self.assertRaisesRegex(AdoptionError, "duplicate"):
            parse_metric_assignments(["quality=0.95", "quality=0.96"])

    def test_build_report_is_schema_valid_and_digestible(self):
        report = build_report(
            run_id="abc123",
            subject="agent",
            metrics={"quality": 0.95},
        )
        self.assertEqual(report.run_id, "abc123")
        self.assertEqual(report.subject, "agent")
        self.assertEqual(dict(report.metrics), {"quality": 0.95})
        self.assertEqual(len(report.digest), 64)

    def test_promotion_requires_pass(self):
        policy = CiPolicy.from_mapping(POLICY)
        baseline = CiReport.from_mapping(
            {
                "schema": "DRIFTGUARD_CI_REPORT_V1",
                "run_id": "base",
                "subject": "agent",
                "metrics": {"quality": 0.95},
            }
        )
        bad = CiReport.from_mapping(
            {
                "schema": "DRIFTGUARD_CI_REPORT_V1",
                "run_id": "candidate",
                "subject": "agent",
                "metrics": {"quality": 0.89},
            }
        )
        with self.assertRaisesRegex(AdoptionError, "requires an exact PASS"):
            qualify_baseline_promotion(
                policy=policy,
                baseline=baseline,
                candidate=bad,
            )

    def test_promote_writes_candidate_and_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            policy = root / "driftguard.toml"
            baseline = root / "baseline.json"
            candidate = root / "candidate.json"
            receipt = root / "receipt.json"

            policy.write_text(
                """schema = "DRIFTGUARD_CI_POLICY_V1"
policy_id = "quality-v1"
unknown = "block"

[[metric]]
name = "quality"
direction = "higher"
max_regression = 0.02
min_candidate = 0.90
severity = "block"
""",
                encoding="utf-8",
            )
            baseline.write_text(
                json.dumps(
                    {
                        "schema": "DRIFTGUARD_CI_REPORT_V1",
                        "run_id": "base",
                        "subject": "agent",
                        "metrics": {"quality": 0.95},
                    }
                ),
                encoding="utf-8",
            )
            candidate.write_text(
                json.dumps(
                    {
                        "schema": "DRIFTGUARD_CI_REPORT_V1",
                        "run_id": "candidate",
                        "subject": "agent",
                        "metrics": {"quality": 0.94},
                    }
                ),
                encoding="utf-8",
            )

            result = promote_baseline_file(
                policy_path=policy,
                baseline_path=baseline,
                candidate_path=candidate,
                output_path=baseline,
                receipt_path=receipt,
            )

            promoted = CiReport.load(baseline)
            self.assertEqual(promoted.run_id, "candidate")
            receipt_value = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(
                receipt_value["previous_baseline_digest"],
                result.previous_baseline_digest,
            )
            self.assertEqual(
                receipt_value["promoted_candidate_digest"],
                promoted.digest,
            )
            self.assertEqual(
                receipt_value["promotion_digest"],
                result.digest,
            )


if __name__ == "__main__":
    unittest.main()
