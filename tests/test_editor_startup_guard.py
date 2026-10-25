"""Prevent concealed editor-on-open execution from returning to source.

Source validation does not establish whether a workstation executed a task.
"""

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUSPECT_NAMES = ("fa-solid.lkf", "fa-solid-500.woff2")


def read_jsonc(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    return json.loads(re.sub(r",\s*(?=[}\]])", "", text))


class EditorStartupGuardTests(unittest.TestCase):
    def test_disguised_executable_assets_absent(self):
        for name in SUSPECT_NAMES:
            with self.subTest(name=name):
                self.assertFalse((ROOT / "public" / "fonts" / name).exists())

    def test_no_automatic_workspace_task_or_loader_command(self):
        task_data = read_jsonc(ROOT / ".vscode" / "tasks.json")
        for task in task_data.get("tasks", ()):
            with self.subTest(task=task.get("label")):
                self.assertNotEqual(
                    task.get("runOptions", {}).get("runOn"), "folderOpen"
                )
                command = str(task.get("command", ""))
                for name in SUSPECT_NAMES:
                    self.assertNotIn(name, command)

    def test_workspace_settings_do_not_claim_task_consent(self):
        settings = read_jsonc(ROOT / ".vscode" / "settings.json")
        self.assertNotIn("task.allowAutomaticTasks", settings)
        self.assertNotIn("tasks", settings)


if __name__ == "__main__":
    unittest.main()
