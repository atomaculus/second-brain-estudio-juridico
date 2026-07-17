#!/usr/bin/env python3
"""Conservative scan for secrets and likely real-world identifiers."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules"}
TEXT_SUFFIXES = {".md", ".txt", ".json", ".yml", ".yaml", ".toml", ".py", ".ps1", ".js", ".csv", ".env"}
PATTERNS = {
    "github-token": re.compile(r"\bgh[opusr]_[A-Za-z0-9]{20,}\b"),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
    "private-key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "user-path": re.compile(r"(?i)\b[A-Z]:[\\/](?:Users|Usuarios)[\\/][^\\/\s]+"),
    "labelled-id": re.compile(r"(?i)\b(?:DNI|CUIT|CUIL)\s*[:#-]?\s*\d{7,11}\b"),
    "likely-case-number": re.compile(r"\b(?:CIV|CNT|COM|CAF|CFP|CSS|FCR)\s*[- ]?\d{3,}/\d{4}\b", re.I),
}


def iter_text_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file() or any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.resolve() == Path(__file__).resolve():
            continue
        if path.suffix.lower() in TEXT_SUFFIXES or path.name.startswith(".env"):
            yield path


def scan(root: Path) -> list[tuple[Path, int, str]]:
    findings: list[tuple[Path, int, str]] = []
    for path in iter_text_files(root):
        try:
            lines = path.read_text(encoding="utf-8-sig").splitlines()
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(lines, start=1):
            for label, pattern in PATTERNS.items():
                if pattern.search(line):
                    findings.append((path.relative_to(root), number, label))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    findings = scan(args.root.resolve())
    if findings:
        for path, line, label in findings:
            print(f"RISK {label}: {path}:{line}")
        return 1
    print("OK: no configured risk patterns found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
