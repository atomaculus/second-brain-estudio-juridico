#!/usr/bin/env python3
"""Validate and query a canonical-folder registry without moving files."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def normalized(path: str) -> str:
    return os.path.normcase(os.path.abspath(os.path.expandvars(os.path.expanduser(path))))


def is_under(path: str, roots: list[str]) -> bool:
    candidate = normalized(path)
    for root in roots:
        root_value = normalized(root)
        try:
            if os.path.commonpath([candidate, root_value]) == root_value:
                return True
        except ValueError:
            continue
    return False


def validate_registry(registry: dict[str, Any], roots: list[str]) -> list[str]:
    errors: list[str] = []
    matters = registry.get("matters")
    if registry.get("schemaVersion") != 1:
        errors.append("registry schemaVersion must be 1")
    if not isinstance(matters, list):
        return errors + ["registry matters must be an array"]

    ids: set[str] = set()
    folders: dict[str, str] = {}
    for index, matter in enumerate(matters):
        prefix = f"matters[{index}]"
        if not isinstance(matter, dict):
            errors.append(f"{prefix} must be an object")
            continue
        matter_id = str(matter.get("matterId", "")).strip()
        folder = str(matter.get("canonicalFolder", "")).strip()
        if not matter_id:
            errors.append(f"{prefix}.matterId is required")
        elif matter_id in ids:
            errors.append(f"duplicate matterId: {matter_id}")
        ids.add(matter_id)
        if not folder:
            errors.append(f"{prefix}.canonicalFolder is required")
            continue
        folder_key = normalized(folder)
        if folder_key in folders and folders[folder_key] != matter_id:
            errors.append(
                f"canonical folder collision: {folder} is used by "
                f"{folders[folder_key]} and {matter_id}"
            )
        folders[folder_key] = matter_id
        if roots and not is_under(folder, roots):
            errors.append(f"canonical folder outside configured roots: {folder}")
        aliases = matter.get("folderAliases", [])
        if not isinstance(aliases, list):
            errors.append(f"{prefix}.folderAliases must be an array")
    return errors


def find_matter(registry: dict[str, Any], matter_id: str) -> dict[str, Any] | None:
    return next(
        (item for item in registry.get("matters", []) if item.get("matterId") == matter_id),
        None,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--resolve", metavar="MATTER_ID")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    registry = load_json(args.registry)
    config = load_json(args.config)
    roots = config.get("canonicalRoots", [])
    if not isinstance(roots, list):
        print("ERROR: canonicalRoots must be an array")
        return 2
    errors = validate_registry(registry, [str(root) for root in roots])
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    if args.resolve:
        matter = find_matter(registry, args.resolve)
        if not matter:
            print(f"ERROR: matter not found: {args.resolve}")
            return 1
        print(json.dumps(matter, ensure_ascii=False, indent=2))
    else:
        print(f"OK: {len(registry.get('matters', []))} matters validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

