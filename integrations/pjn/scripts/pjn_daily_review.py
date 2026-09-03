#!/usr/bin/env python3
"""
One-command PJN daily review.

For normal use through Codex/Claude: run this script. It refreshes/caches a PJN
token from the local browser profile and then runs the recurrent sync.
"""

from __future__ import annotations

import argparse
import os
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from pjn_local_paths import token_cache_file


def script_dir() -> Path:
    return Path(__file__).resolve().parent


def lab_root() -> Path:
    return script_dir().parent


def token_cache_path() -> Path:
    return token_cache_file()


def cache_has_live_token(min_ttl: int = 90) -> bool:
    path = token_cache_path()
    if not path.exists():
        return False
    try:
        cache = json.loads(path.read_text(encoding="utf-8"))
        return int(cache.get("expires_at", 0)) > int(time.time()) + min_ttl
    except Exception:
        return False


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def default_registry_path() -> Path:
    return script_dir().parents[2] / "08-context" / "registries" / "matter-registry.json"


def registry_matters(path: Path) -> list[dict[str, Any]]:
    registry = read_json(path, {"matters": []})
    matters = registry if isinstance(registry, list) else registry.get("matters", [])
    if not isinstance(matters, list):
        raise SystemExit(f"invalid registry shape: {path}")
    return matters


def scw_fallback_matters(registry_path: Path, matter_id: str | None) -> list[dict[str, Any]]:
    result = []
    for matter in registry_matters(registry_path):
        if matter_id and matter.get("matterId") != matter_id:
            continue
        if matter.get("status") == "cerrado":
            continue
        if matter.get("pjnSync", {}).get("enabled") is not True:
            continue
        if matter.get("pjnExpedienteId"):
            continue
        if not (matter.get("fuero") and matter.get("numero") and matter.get("anio")):
            continue
        route = matter.get("syncRoute") or {}
        if route and route.get("active") not in (None, "scw"):
            continue
        result.append(matter)
    return result


def run_step(command: list[str], env: dict[str, str] | None = None) -> None:
    result = subprocess.run(command, text=True, env=env)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run PJN daily review end to end.")
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Open the PJN browser window. Use when login is needed.",
    )
    parser.add_argument(
        "--matter-id",
        help="Review a single matter instead of all registry matters.",
    )
    parser.add_argument(
        "--no-pdf",
        action="store_true",
        help="Fetch metadata only; do not download PDFs.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Allow registry, state, PDF and canonical-folder writes. Default is dry-run.",
    )
    parser.add_argument(
        "--skip-resolve-ids",
        action="store_true",
        help="Do not enrich missing pjnExpedienteId values before review.",
    )
    parser.add_argument(
        "--skip-api",
        action="store_true",
        help="Do not run the API sync step; useful when retrying SCW fallback only.",
    )
    parser.add_argument(
        "--scw-fallback",
        action="store_true",
        help="Run SCW/browser fallback for enabled matters without pjnExpedienteId.",
    )
    parser.add_argument(
        "--scw-assisted-login",
        action="store_true",
        help="Open the first SCW fallback visibly for human login, then reuse its profile.",
    )
    parser.add_argument(
        "--scw-timeout-sec",
        type=int,
        default=180,
        help="Timeout passed to the SCW/browser fallback.",
    )
    parser.add_argument(
        "--scw-keep-open-on-error",
        action="store_true",
        help="Keep the headed SCW browser open briefly when a fallback matter fails.",
    )
    parser.add_argument(
        "--scw-error-pause-sec",
        type=int,
        default=180,
        help="How long to keep the SCW browser open on error.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    registry_path = default_registry_path()
    token_cmd = [sys.executable, str(script_dir() / "pjn_browser_token.py")]
    if args.headed:
        token_cmd.append("--headed")

    initial_matters = registry_matters(registry_path)
    initial_selected = [m for m in initial_matters if (not args.matter_id or m.get("matterId") == args.matter_id)]
    initial_api_selected = [m for m in initial_selected if m.get("pjnExpedienteId")]
    needs_token = not args.skip_resolve_ids or (bool(initial_api_selected) and not args.skip_api)
    if needs_token and not cache_has_live_token():
        run_step(token_cmd)
    sync_env = os.environ.copy()
    sync_env.pop("PJN_BEARER_TOKEN", None)
    if not args.skip_resolve_ids:
        resolve_cmd = [sys.executable, str(script_dir() / "pjn_resolve_expediente_ids.py")]
        if args.apply:
            resolve_cmd.append("--apply")
        run_step(resolve_cmd, env=sync_env)

    matters = registry_matters(registry_path)
    selected = [m for m in matters if (not args.matter_id or m.get("matterId") == args.matter_id)]
    api_selected = [m for m in selected if m.get("pjnExpedienteId")]
    if args.skip_api:
        print("Skipping API sync by request.")
    elif args.matter_id and selected and not api_selected:
        print(f"Skipping API sync for {args.matter_id}: no pjnExpedienteId; eligible for SCW fallback.")
    else:
        sync_cmd = [sys.executable, str(script_dir() / "pjn_expediente_sync.py")]
        if args.matter_id:
            sync_cmd.extend(["--matter-id", args.matter_id])
        else:
            sync_cmd.append("--all")
        if args.no_pdf:
            sync_cmd.append("--no-pdf")
        if args.apply:
            sync_cmd.append("--apply")
        run_step(sync_cmd, env=sync_env)

    if args.scw_fallback:
        scw_reports = []
        for matter in scw_fallback_matters(registry_path, args.matter_id):
            scw_cmd = [
                "node",
                str(script_dir() / "pjn_scw_actuaciones.js"),
                "--matter-id",
                str(matter["matterId"]),
                "--timeout-sec",
                str(args.scw_timeout_sec),
            ]
            if args.headed or (args.scw_assisted_login and not scw_reports):
                scw_cmd.append("--headed")
            if args.scw_keep_open_on_error:
                scw_cmd.append("--keep-open-on-error")
                scw_cmd.extend(["--error-pause-sec", str(args.scw_error_pause_sec)])
            result = subprocess.run(scw_cmd, text=True)
            scw_reports.append(
                {
                    "matterId": matter.get("matterId"),
                    "returncode": result.returncode,
                    "status": "ok" if result.returncode == 0 else "error",
                }
            )
        print(json.dumps({"scwFallback": scw_reports}, ensure_ascii=False, indent=2))
        failed = [item for item in scw_reports if item["returncode"] != 0]
        if failed:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
