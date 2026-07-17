#!/usr/bin/env python3
"""Create a read-only folder inventory for migration planning."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def inventory(root: Path, max_depth: int) -> list[dict[str, Any]]:
    root = root.resolve(strict=True)
    records: list[dict[str, Any]] = []
    for current, directories, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        depth = len(current_path.relative_to(root).parts)
        directories[:] = sorted(
            name for name in directories if not name.startswith(".") and depth < max_depth
        )
        if depth == 0:
            continue
        records.append(
            {
                "relativePath": current_path.relative_to(root).as_posix(),
                "depth": depth,
                "immediateFileCount": len(files),
                "immediateDirectoryCount": len(directories),
            }
        )
    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--max-depth", type=int, default=2)
    parser.add_argument("--out", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.max_depth < 1:
        raise SystemExit("--max-depth must be at least 1")
    result = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sourceRoot": str(args.root.resolve(strict=True)),
        "readOnly": True,
        "folders": inventory(args.root, args.max_depth),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"inventoried {len(result['folders'])} folders -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

