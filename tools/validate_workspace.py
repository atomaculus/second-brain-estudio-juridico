#!/usr/bin/env python3
"""Validate the portable workspace structure and example configuration."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from canonical_folders import validate_registry


REQUIRED = (
    "AGENTS.md",
    "CLAUDE.md",
    "SECURITY.md",
    "08-context/system-policy.md",
    "08-context/source-of-truth.md",
    "config/workspace.example.json",
    "08-context/registries/matter-registry.example.json",
)
SENSITIVE_DIRS = ("00-inbox", "01-clients", "02-matters", "04-sales", "06-finance", "09-reviews", "10-outputs")


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def git_ignored(root: Path, relative: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "-q", relative],
        cwd=root,
        check=False,
        capture_output=True,
    )
    return result.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.root.resolve()
    errors: list[str] = []
    for relative in REQUIRED:
        if not (root / relative).is_file():
            errors.append(f"missing required file: {relative}")
    try:
        config = load(root / "config/workspace.example.json")
        registry = load(root / "08-context/registries/matter-registry.example.json")
        errors.extend(validate_registry(registry, config.get("canonicalRoots", [])))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"invalid configuration: {exc}")
    if (root / ".git").exists():
        for directory in SENSITIVE_DIRS:
            probe = f"{directory}/private-data.example"
            if not git_ignored(root, probe):
                errors.append(f"sensitive path is not ignored: {probe}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("OK: workspace structure and safety defaults validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

