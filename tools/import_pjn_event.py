#!/usr/bin/env python3
"""Validate an externally obtained PJN event and write a neutral staging record."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


REQUIRED = (
    "externalEventId",
    "matterReference",
    "occurredAt",
    "eventType",
    "title",
    "sourceReference",
)


def normalize_event(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("sourceSystem") != "pjn":
        raise ValueError("sourceSystem must be pjn")
    missing = [field for field in REQUIRED if not str(data.get(field, "")).strip()]
    if missing:
        raise ValueError("missing required fields: " + ", ".join(missing))
    event = {field: data[field] for field in ("sourceSystem",) + REQUIRED}
    event["documentReferences"] = data.get("documentReferences", [])
    event["metadata"] = data.get("metadata", {})
    canonical = json.dumps(event, ensure_ascii=False, sort_keys=True).encode("utf-8")
    event["fingerprint"] = hashlib.sha256(canonical).hexdigest()
    event["reviewStatus"] = "pending"
    return event


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8-sig"))
    event = normalize_event(data)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(event, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"staged event {event['externalEventId']} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

