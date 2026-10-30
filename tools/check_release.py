#!/usr/bin/env python3
"""Check release metadata and local Markdown links without third-party modules."""
import json
from pathlib import Path
import re
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
VERSION_PATTERN = r"[0-9]+\.[0-9]+\.[0-9]+(?:-[a-z]+(?:\.[0-9]+)?)?"


def check(root=ROOT):
    errors = []
    version = (root / "VERSION").read_text().strip()
    if not re.fullmatch(VERSION_PATTERN, version):
        errors.append("VERSION is not a supported release version")
    manifest = json.loads((root / "adapters/claude/.claude-plugin/plugin.json").read_text())
    if manifest.get("version") != version:
        errors.append("Claude manifest version differs from VERSION")
    if manifest.get("license") != "MIT":
        errors.append("Claude manifest must declare the MIT license")
    if f"## {version}" not in (root / "CHANGELOG.md").read_text():
        errors.append("CHANGELOG.md has no entry for VERSION")
    if "MIT License" not in (root / "LICENSE").read_text():
        errors.append("Missing MIT license text")
    if not (root / "agent-status.tmux").stat().st_mode & 0o111:
        errors.append("agent-status.tmux must be executable")
    for path in root.rglob("*.md"):
        if any(part in {".git", ".venv", "dist", "node_modules", ".test-results"}
               for part in path.relative_to(root).parts):
            continue
        text = path.read_text()
        if re.search(r"OWNER/|/local/home/|/home/benremer/", text):
            errors.append(f"{path.relative_to(root)} contains a placeholder or local path")
        # Exclude code fences; validate normal Markdown links and images.
        text = re.sub(r"```.*?```", "", text, flags=re.S)
        for link in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", text):
            target = link.split()[0].strip("<>")
            if re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", target) or target.startswith("#"):
                continue
            target = unquote(target.split("#", 1)[0])
            if target and not (path.parent / target).exists():
                errors.append(f"{path.relative_to(root)} links to missing file: {target}")
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"Release metadata and local documentation links pass ({version}).")
    return version


if __name__ == "__main__":
    check()
