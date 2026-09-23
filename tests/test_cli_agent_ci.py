from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
import tempfile
import unittest
from pathlib import Path

from driftguard.cli import main
from driftguard.ci_gate import CiReport


class AgentCiCliTests(unittest.TestCase):
    def test_report_command_writes_loadable_report(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "candidate.json"
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = main(
                    [
                        "report",
                        "--run-id",
                        "candidate-1",
                        "--subject",
                        "agent",
                        "--metric",
                        "quality=0.95",
                        "--metric",
                        "latency_ms=1200",
                        "--output",
                        str(output),
                    ]
                )
            self.assertEqual(code, 0)
            report = CiReport.load(output)
            self.assertEqual(report.run_id, "candidate-1")
            self.assertEqual(report.subject, "agent")
            self.assertEqual(
                dict(report.metrics),
                {"latency_ms": 1200.0, "quality": 0.95},
            )
            emitted = json.loads(stdout.getvalue())
            self.assertEqual(emitted["report_digest"], report.digest)

    def test_prepare_baseline_writes_proposal_not_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            policy = root / "driftguard.toml"
            baseline = root / "baseline.json"
            candidate = root / "candidate.json"
            proposed = root / "baseline.next.json"
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
                        "run_id": "accepted",
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

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = main(
                    [
                        "prepare-baseline",
                        "--policy",
                        str(policy),
                        "--baseline",
                        str(baseline),
                        "--candidate",
                        str(candidate),
                        "--output",
                        str(proposed),
                        "--receipt",
                        str(receipt),
                    ]
                )

            self.assertEqual(code, 0)
            self.assertEqual(CiReport.load(baseline).run_id, "accepted")
            self.assertEqual(CiReport.load(proposed).run_id, "candidate")
            receipt_payload = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(
                receipt_payload["effect_state"],
                "PREPARED_FOR_REVIEW",
            )
            emitted = json.loads(stdout.getvalue())
            self.assertEqual(
                emitted["promotion_digest"],
                receipt_payload["promotion_digest"],
            )

    def test_prepare_baseline_rejects_nonpass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            policy = root / "driftguard.toml"
            baseline = root / "baseline.json"
            candidate = root / "candidate.json"
            proposed = root / "baseline.next.json"

            policy.write_text(
                """schema = "DRIFTGUARD_CI_POLICY_V1"
policy_id = "quality-v1"
unknown = "block"

[[metric]]
name = "quality"
direction = "higher"
max_regression = 0.02
severity = "block"
""",
                encoding="utf-8",
            )
            baseline.write_text(
                json.dumps(
                    {
                        "schema": "DRIFTGUARD_CI_REPORT_V1",
                        "run_id": "accepted",
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
                        "metrics": {"quality": 0.80},
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(RuntimeError, "requires an exact PASS"):
                main(
                    [
                        "prepare-baseline",
                        "--policy",
                        str(policy),
                        "--baseline",
                        str(baseline),
                        "--candidate",
                        str(candidate),
                        "--output",
                        str(proposed),
                    ]
                )
            self.assertFalse(proposed.exists())


if __name__ == "__main__":
    unittest.main()
