#!/usr/bin/env python3
"""Normalize an authorized LexDoctor CSV export into a staging JSON file."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


NORMAL_FIELDS = (
    "externalId",
    "caseNumber",
    "caption",
    "client",
    "jurisdiction",
    "court",
    "status",
    "nextDeadline",
)


def load_mapping(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        mapping = json.load(handle)
    if mapping.get("schemaVersion") != 1 or not isinstance(mapping.get("fields"), dict):
        raise ValueError("mapping must use schemaVersion 1 and contain fields")
    return mapping


def normalize_row(row: dict[str, str], fields: dict[str, str]) -> dict[str, str]:
    return {
        field: (row.get(fields.get(field, ""), "") or "").strip()
        for field in NORMAL_FIELDS
    }


def build_preview(csv_path: Path, mapping: dict[str, Any]) -> dict[str, Any]:
    delimiter = mapping.get("delimiter", ";")
    encoding = mapping.get("encoding", "utf-8-sig")
    records: list[dict[str, str]] = []
    issues: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    with csv_path.open("r", encoding=encoding, newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        for line, row in enumerate(reader, start=2):
            item = normalize_row(row, mapping["fields"])
            key = (item["externalId"], item["caseNumber"])
            if not any(key):
                issues.append({"line": line, "type": "missing-identity"})
                continue
            if key in seen:
                issues.append({"line": line, "type": "duplicate", "key": list(key)})
                continue
            seen.add(key)
            records.append(item)
    return {
        "schemaVersion": 1,
        "sourceSystem": "lexdoctor-csv",
        "sourceFile": csv_path.name,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "dryRun": True,
        "records": records,
        "issues": issues,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--map", required=True, dest="mapping", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    preview = build_preview(args.csv, load_mapping(args.mapping))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(preview, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"dry-run: {len(preview['records'])} records, "
        f"{len(preview['issues'])} issues -> {args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

