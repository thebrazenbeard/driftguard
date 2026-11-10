"""Source-only regression coverage for editor autorun and disguised font files.

No VS Code task, Node payload, or font-like executable is ever launched.
"""

import unittest
from pathlib import Path
from shutil import copyfile, rmtree
from tempfile import TemporaryDirectory

from scripts.check_editor_source_safety import TRUSTED_FONTS, check_source


ROOT = Path(__file__).resolve().parents[1]


class WorkspaceStartupSafetyTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        fonts = self.root / "public" / "fonts"
        fonts.mkdir(parents=True)
        for name in TRUSTED_FONTS:
            copyfile(ROOT / "public" / "fonts" / name, fonts / name)

    def write_editor(self, filename, content):
        path = self.root / ".vscode" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def findings(self):
        return "\n".join(check_source(self.root))

    def test_checkout_is_clear(self):
        self.assertEqual(check_source(ROOT), ())

    def test_bom_jsonc_comments_trailing_comma_and_inherited_args(self):
        self.write_editor(
            "tasks.json",
            '\ufeff{\n// legit comment\n"tasks":[{"command":"node",'
            '"windows":{"args":["public/fonts/fa-solid-600.ttf"]},'
            '"runOptions":{"runOn":"folderOpen",},},],}',
        )
        findings = self.findings()
        self.assertIn("editor folderOpen task", findings)
        self.assertIn("task refers to font-directory asset", findings)

    def test_application_scoped_autotask_setting_on_is_rejected(self):
        self.write_editor(
            "settings.json",
            '{"task.allowAutomaticTasks":"on", "search.exclude":{"// literal":true},}',
        )
        self.assertIn("automatic editor tasks enabled", self.findings())

    def test_unicode_escape_in_property_and_value_is_decoded(self):
        self.write_editor("tasks.json", r'{"tasks":[{"run\u004fn":"folder\u004fpen"}]}')
        self.assertIn("editor folderOpen task", self.findings())

    def test_workspace_tasks_with_platform_specific_run_on_are_rejected(self):
        path = self.root / "sample.code-workspace"
        path.write_text(
            '{"folders":[],"tasks":{"tasks":[{"linux":{"runOptions":'
            '{"runOn":"folderOpen"}}}]}}',
            encoding="utf-8",
        )
        self.assertIn("editor folderOpen task", self.findings())

    def test_os_specific_top_level_task_list_is_rejected(self):
        # VS Code permits per-OS tasks at the top level of tasks.json.
        self.write_editor(
            "tasks.json",
            '{"version":"2.0.0","tasks":[],"windows":{"tasks":['
            '{"label":"manual-looking","type":"shell","command":"echo inert",'
            '"runOptions":{"runOn":"folderOpen"}}]}}',
        )
        self.assertIn("editor folderOpen task", self.findings())

    def test_duplicate_keys_and_invalid_jsonc_fail_closed(self):
        self.write_editor(
            "tasks.json",
            '{"tasks":[{"runOptions":{"runOn":"folderOpen","runOn":"default"}}]}',
        )
        self.assertIn("invalid editor JSONC", self.findings())
        self.write_editor("tasks.json", '{"tasks": [/* unterminated')
        self.assertIn("invalid editor JSONC", self.findings())

    def test_valid_manual_task_and_jsonc_comment_are_allowed(self):
        self.write_editor(
            "tasks.json",
            '{"tasks":[{"command":"python -m unittest",'
            '"args":["--help"],"label":"manual"}],'
            '/* "runOn":"folderOpen" is a comment */}',
        )
        self.write_editor("settings.json", '{"task.allowAutomaticTasks":"off"}')
        self.assertEqual(check_source(self.root), ())

    def test_magic_prefixed_script_polyglot_cannot_replace_good_font(self):
        fonts = self.root / "public" / "fonts"
        (fonts / "fa-solid-900.ttf").write_bytes(
            b"\x00\x01\x00\x00" + b"var payload = require('child_process')" * 4
        )
        self.assertIn("font digest differs from clean parent", self.findings())

    def test_windows_svg_line_endings_are_safe_but_appended_payload_is_not(self):
        fonts = self.root / "public" / "fonts"
        svg = fonts / "fa-brands-400.svg"
        canonical = svg.read_bytes().replace(b"\r\n", b"\n")
        self.assertIn(b"\n", canonical)
        crlf = canonical.replace(b"\n", b"\r\n")
        self.assertIn(bytes((13, 10)), crlf)
        svg.write_bytes(crlf)
        self.assertEqual(check_source(self.root), ())
        svg.write_bytes(crlf + b"\r\n<script>untrusted</script>\r\n")
        self.assertIn("font digest differs from clean parent", self.findings())

    def test_new_disguised_font_is_rejected_even_with_header(self):
        fonts = self.root / "public" / "fonts"
        (fonts / "fa-solid-600.ttf").write_bytes(b"\x00\x01\x00\x00" + b"\x00" * 100)
        self.assertIn("unreviewed font asset", self.findings())

    def test_missing_font_directory_fails_closed(self):
        rmtree(self.root / "public" / "fonts")
        self.assertIn("missing trusted font directory", self.findings())

    def test_editor_symlink_is_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        try:
            (self.root / ".vscode").symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"symlinks unavailable: {exc}")
        self.assertIn("symlinked editor configuration", self.findings())


if __name__ == "__main__":
    unittest.main()
