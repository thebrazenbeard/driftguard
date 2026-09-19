import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout

from driftguard.cli import _load_json, main


ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def test_duplicate_json_keys_are_rejected(self):
        handle = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", delete=False, suffix=".json"
        )
        try:
            handle.write('{"x": 1, "x": 2}')
            handle.close()
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                _load_json(handle.name)
        finally:
            if not handle.closed:
                handle.close()
            os.unlink(handle.name)

    def test_example_evaluation_executes_end_to_end(self):
        db = tempfile.NamedTemporaryFile(delete=False)
        db.close()
        try:
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = main(
                    [
                        "evaluate",
                        "--state",
                        str(ROOT / "examples" / "save_state.json"),
                        "--evidence",
                        str(ROOT / "examples" / "evidence.json"),
                        "--observation",
                        str(ROOT / "examples" / "observation.txt"),
                        "--db",
                        db.name,
                        "--session",
                        "cli-example",
                        "--turn",
                        "0",
                        "--expected-generation",
                        "0",
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["decision"], "STABLE")
            self.assertFalse(payload["reload_required"])
            self.assertEqual(payload["generation_after"], 1)
        finally:
            os.unlink(db.name)

    def test_file_digest_is_deterministic(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = main(
                [
                    "file-digest",
                    "--file",
                    str(ROOT / "examples" / "observation.txt"),
                ]
            )
        self.assertEqual(code, 0)
        self.assertEqual(
            stdout.getvalue().strip(),
            "37f991657e3eb8442fe7eb044db9f7f44d4efa600209d36bacf3fd3f7436f6c2",
        )


if __name__ == "__main__":
    unittest.main()
