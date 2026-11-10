"""Read-only, dependency-free guard for tracked editor startup and font assets.

This is source review, not a VS Code runtime policy. In particular,
task.allowAutomaticTasks is APPLICATION-scoped; a workspace value of "off"
does not disable tasks on a user's workstation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

# SHA-256 of the 15 pre-incident fonts, unchanged from the clean parent.
# Pinning whole files catches font-header/JavaScript polyglots that magic-byte
# checks miss. Intentional font upgrades must explicitly review new digests.
TRUSTED_FONTS = {
    "fa-brands-400.eot": "811e1577184066108ceca86d5a624a9012303df5206c5cb0b27d5e3fedcba5a3",
    "fa-brands-400.svg": "02340ba1789d09bcc507563c89c4a847ba537bb8132082777a50519cf74bcb5b",
    "fa-brands-400.ttf": "a0c145382acfe59767d1487d6505f349665b685c2885cd91b621d141a292b0f8",
    "fa-brands-400.woff": "e836c5d5dfc13e18170c5bddefb4fdac7c65ac0ad43a4b431acdc4a98865a260",
    "fa-brands-400.woff2": "5d9190292acdd48ba0fc35080f7e7448f3cdf0d79199a4d23f0f49b5341fdf29",
    "fa-regular-400.eot": "01f4416f5db59e2dd6b6fbd9dc32336d99db18f7eb623a49f584d04afd279473",
    "fa-regular-400.svg": "865fd23de13b1920280e182359579e09eff7a09eb24676eceec7552838559f55",
    "fa-regular-400.ttf": "f32b94a29060dfec0c797a1dfe111357eb1d682f1aca4ac4b95cf0f4c3e2bfa9",
    "fa-regular-400.woff": "8e2d96198711b63752e5f2f5987b8ffc536df6156a065bdbe28cb7231cad793d",
    "fa-regular-400.woff2": "6a8c8e9e1e7f692c21af1956de163f3d026778e6449fe93a09a671847ca1ae65",
    "fa-solid-900.eot": "32501727bb23fc77615b1ec76b5f298ec22198c0f3d6a3e7d6fe4ac3cf315db9",
    "fa-solid-900.svg": "e768539808757f7eec20f09c9ee9b36b0e6c5636e90c9ee697995cbbc6ee0555",
    "fa-solid-900.ttf": "231d68cefbc6846fb78cafca8467401a4f371e226418662e8900e3d52adc00ab",
    "fa-solid-900.woff": "352f8ead280419dd953d2bc7843386bb9430e8152c2dbd2c2d2494f6b9567ee7",
    "fa-solid-900.woff2": "7f4d3fd0a705dbf8403298aad91d5de6972e6b5d536068eba8b24954a5a0a8c7",
}

SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", "dist", "build"}


def _jsonc(text: str):
    """Parse JSONC/BOM safely, preserving quoted // and commas in strings."""
    if text.startswith("\ufeff"):
        text = text[1:]
    chars = list(text)
    in_string = False
    escaped = False
    i = 0
    while i < len(chars):
        c = chars[i]
        if in_string:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                in_string = False
        elif c == '"':
            in_string = True
        elif c == "/" and i + 1 < len(chars) and chars[i + 1] in ("/", "*"):
            block = chars[i + 1] == "*"
            start = i
            if block:
                i += 2
                while i + 1 < len(chars) and chars[i:i + 2] != ["*", "/"]:
                    i += 1
                if i + 1 == len(chars):
                    raise ValueError("unterminated JSONC block comment")
                i += 2
            else:
                i += 2
                while i < len(chars) and chars[i] not in ("\r", "\n"):
                    i += 1
            for j in range(start, i):
                if chars[j] not in ("\r", "\n"):
                    chars[j] = " "
            continue
        i += 1

    in_string = False
    escaped = False
    for i, c in enumerate(chars):
        if in_string:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                in_string = False
        elif c == '"':
            in_string = True
        elif c == ",":
            j = i + 1
            while j < len(chars) and chars[j].isspace():
                j += 1
            if j < len(chars) and chars[j] in ("]", "}"):
                chars[i] = " "

    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSONC key: {key}")
            result[key] = value
        return result

    return json.loads("".join(chars), object_pairs_hook=unique_pairs)


def _find_editor_risks(value, relative: Path, violations: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = key.casefold()
            if lowered == "runon" and isinstance(child, str) and child.casefold() == "folderopen":
                violations.append(f"{relative}: editor folderOpen task")
            if lowered == "task.allowautomatictasks" and child not in (False, "off", "false"):
                violations.append(f"{relative}: automatic editor tasks enabled")
            if lowered in {"command", "args"}:
                # Includes inherited commands, platform-specific command/args,
                # and command-line strings split across the task's fields.
                for item in _all_strings(child):
                    if re.search(r"(?i)(?:public[/\\]+fonts[/\\]+|fonts[/\\]+[^\s]*\.(?:ttf|woff2?|otf|eot|svg))", item):
                        violations.append(f"{relative}: task refers to font-directory asset")
                        break
            _find_editor_risks(child, relative, violations)
    elif isinstance(value, list):
        for item in value:
            _find_editor_risks(item, relative, violations)


def _all_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _all_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _all_strings(item)


def check_source(root: Path) -> tuple[str, ...]:
    root = root.resolve()
    violations: list[str] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if any(part.casefold() in SKIP_DIRS for part in relative.parts):
            continue
        in_editor = any(part.casefold() == ".vscode" for part in relative.parts)
        if path.name.casefold() == ".vscode" and path.is_symlink():
            violations.append(f"{relative}: symlinked editor configuration")
            continue
        if not (path.name.casefold().endswith(".code-workspace") or
                (in_editor and path.name.casefold().endswith(".json"))):
            continue
        if path.is_symlink() or not path.is_file():
            violations.append(f"{relative}: invalid editor configuration path")
            continue
        try:
            if path.stat().st_size > 262144:
                raise ValueError("oversized editor configuration")
            parsed = _jsonc(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError) as exc:
            violations.append(f"{relative}: unreadable/invalid editor JSONC: {exc}")
            continue
        _find_editor_risks(parsed, relative, violations)

    fonts = root / "public" / "fonts"
    if fonts.is_symlink():
        violations.append("public/fonts: symlinked font directory")
    elif fonts.exists() and not fonts.is_dir():
        violations.append("public/fonts: invalid font directory")
    elif fonts.is_dir():
        seen = set()
        for file in sorted(fonts.rglob("*")):
            relative = file.relative_to(root)
            if file.is_symlink() or not file.is_file():
                violations.append(f"{relative}: invalid font asset")
                continue
            if file.name == "README.md" and file.parent == fonts:
                continue
            if file.parent != fonts or file.name not in TRUSTED_FONTS:
                violations.append(f"{relative}: unreviewed font asset")
                continue
            seen.add(file.name)
            data = file.read_bytes()
            if file.suffix.casefold() == ".svg":
                # Git's Windows checkout may turn LF into CRLF for text SVGs.
                # Normalize ONLY line endings, then hash the full asset.
                data = data.replace(b"\r\n", b"\n")
            digest = hashlib.sha256(data).hexdigest()
            if digest != TRUSTED_FONTS[file.name]:
                violations.append(f"{relative}: font digest differs from clean parent")
        for name in TRUSTED_FONTS.keys() - seen:
            violations.append(f"public/fonts/{name}: missing trusted font asset")
    else:
        violations.append("public/fonts: missing trusted font directory")
    return tuple(violations)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    findings = check_source(args.root)
    for finding in findings:
        print(f"SOURCE-SAFETY BLOCK: {finding}")
    print("SOURCE-SAFETY PASS" if not findings else f"{len(findings)} source-safety violation(s)")
    return bool(findings)


if __name__ == "__main__":
    raise SystemExit(main())
