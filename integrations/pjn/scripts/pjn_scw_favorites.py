#!/usr/bin/env python3
"""Run the Node-based SCW favorites extractor."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def lab_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> None:
    script = Path(__file__).with_suffix(".js")
    env = os.environ.copy()
    env["NODE_PATH"] = str(lab_root() / "node-tools" / "node_modules")
    result = subprocess.run(["node", str(script), *sys.argv[1:]], env=env, text=True)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
