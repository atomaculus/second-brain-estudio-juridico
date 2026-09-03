#!/usr/bin/env python3
"""
Extract a short-lived PJN access token from a local browser session.

This helper does not store PJN credentials. It opens the stable Portal PJN app
with a persistent local browser profile and reads oidc-client sessionStorage.
Portal tokens include the API audiences used by the expediente sync.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from pjn_local_paths import browser_profile_dir, token_cache_file


DEFAULT_SESSION_KEY = "oidc.user:https://sso.pjn.gov.ar/auth/realms/pjn:pjn-portal"
DEFAULT_START_URL = "https://portalpjn.pjn.gov.ar/"
TOKEN_URL = "https://sso.pjn.gov.ar/auth/realms/pjn/protocol/openid-connect/token"


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def vault_root() -> Path:
    return Path(__file__).resolve().parents[3]


def lab_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_profile_dir() -> Path:
    return browser_profile_dir()


def default_cache_file() -> Path:
    return token_cache_file()


def node_helper_path() -> Path:
    return Path(__file__).with_suffix(".js")


def node_modules_bin() -> Path:
    return lab_root() / "node-tools" / "node_modules" / ".bin"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cache PJN Bearer token from an authenticated browser session.")
    parser.add_argument("--profile-dir", type=Path, default=default_profile_dir())
    parser.add_argument("--cache-file", type=Path, default=default_cache_file())
    parser.add_argument("--session-key", default=DEFAULT_SESSION_KEY)
    parser.add_argument("--start-url", default=DEFAULT_START_URL)
    parser.add_argument("--headed", action="store_true", help="Show browser window; use for first login.")
    parser.add_argument("--from-clipboard", action="store_true", help="Import oidc-client JSON copied from an existing PJN tab.")
    parser.add_argument("--timeout-sec", type=int, default=120)
    parser.add_argument("--min-ttl-sec", type=int, default=60)
    parser.add_argument("--print-token", action="store_true", help="Print the access token to stdout.")
    parser.add_argument("--refresh-only", action="store_true", help="Refresh from cached refresh_token only; do not open a browser.")
    parser.add_argument("--force-browser", action="store_true", help="Read sessionStorage from the browser even if the cache has a live token.")
    parser.add_argument("--watch", action="store_true", help="Keep refreshing the cached token until interrupted.")
    parser.add_argument("--watch-interval-sec", type=int, default=600, help="Refresh interval for --watch.")
    return parser.parse_args()


def read_clipboard() -> str:
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        fail(result.stderr.strip() or "could not read Windows clipboard")
    return result.stdout.strip()


def parse_oidc_user(raw: str) -> dict[str, Any]:
    if not raw:
        fail("clipboard is empty")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        fail(f"clipboard does not contain oidc-client JSON: {exc}")
    if not isinstance(data, dict):
        fail("clipboard JSON has unexpected shape")
    return data


def read_session_user(page: Any, session_key: str) -> dict[str, Any] | None:
    raw = page.evaluate(
        """
        (key) => {
          const raw = window.sessionStorage.getItem(key);
          return raw || null;
        }
        """,
        session_key,
    )
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        fail(f"sessionStorage key exists but is not JSON: {session_key}")
    if not isinstance(data, dict):
        fail(f"sessionStorage key has unexpected shape: {session_key}")
    return data


def token_ttl(user: dict[str, Any]) -> int:
    expires_at = user.get("expires_at")
    if expires_at is None:
        return -1
    try:
        return int(expires_at) - int(time.time())
    except (TypeError, ValueError):
        return -1


def client_id_from_session_key(session_key: str) -> str:
    return session_key.rsplit(":", 1)[-1] if ":" in session_key else "pjn-sne"


def write_cache(cache_file: Path, cache: dict[str, Any]) -> None:
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    temp_file = cache_file.with_name(f"{cache_file.name}.{os.getpid()}.tmp")
    temp_file.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp_file, cache_file)


def cache_token(user: dict[str, Any], cache_file: Path, source: str, session_key: str) -> dict[str, Any]:
    access_token = user.get("access_token")
    if not access_token:
        fail("OIDC session exists but access_token is missing")
    refresh_expires_at = user.get("refresh_expires_at")
    if not refresh_expires_at and user.get("refresh_expires_in"):
        try:
            refresh_expires_at = int(time.time()) + int(user["refresh_expires_in"])
        except (TypeError, ValueError):
            refresh_expires_at = None
    cache = {
        "createdAt": datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "session_key": session_key,
        "client_id": user.get("client_id") or client_id_from_session_key(session_key),
        "token_type": user.get("token_type", "bearer"),
        "scope": user.get("scope"),
        "expires_at": user.get("expires_at"),
        "refresh_expires_at": refresh_expires_at,
        "access_token": access_token,
    }
    for optional_key in ("refresh_token", "id_token", "session_state", "profile"):
        if user.get(optional_key):
            cache[optional_key] = user[optional_key]
    write_cache(cache_file, cache)
    return cache


def cache_has_live_access_token(cache: dict[str, Any], min_ttl_sec: int) -> bool:
    try:
        return int(cache.get("expires_at", 0)) > int(time.time()) + min_ttl_sec
    except (TypeError, ValueError):
        return False


def refresh_token_ttl(cache: dict[str, Any]) -> int:
    try:
        return int(cache.get("refresh_expires_at", 0)) - int(time.time())
    except (TypeError, ValueError):
        return -1


def refresh_from_cache(cache_file: Path, min_ttl_sec: int, session_key: str) -> dict[str, Any] | None:
    if not cache_file.exists():
        return None
    try:
        cache = json.loads(cache_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(cache, dict):
        return None
    if cache_has_live_access_token(cache, min_ttl_sec):
        return cache
    refresh_token = cache.get("refresh_token")
    if not refresh_token:
        return None
    if cache.get("refresh_expires_at") and refresh_token_ttl(cache) < min_ttl_sec:
        return None

    client_id = cache.get("client_id") or client_id_from_session_key(cache.get("session_key") or session_key)
    body = urlencode(
        {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": refresh_token,
        }
    ).encode("utf-8")
    req = Request(
        TOKEN_URL,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": "pjn-browser-token/0.2",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError:
        return None
    except (URLError, TimeoutError, json.JSONDecodeError):
        return None

    now = int(time.time())
    refreshed = dict(cache)
    refreshed.update(
        {
            "createdAt": datetime.now().isoformat(timespec="seconds"),
            "source": f"refresh_token grant {client_id}",
            "session_key": cache.get("session_key") or session_key,
            "client_id": client_id,
            "token_type": payload.get("token_type", cache.get("token_type", "bearer")),
            "scope": payload.get("scope", cache.get("scope")),
            "expires_at": now + int(payload.get("expires_in", 0)),
            "access_token": payload.get("access_token"),
        }
    )
    if payload.get("refresh_token"):
        refreshed["refresh_token"] = payload["refresh_token"]
    if payload.get("refresh_expires_in"):
        refreshed["refresh_expires_at"] = now + int(payload["refresh_expires_in"])
    for optional_key in ("id_token", "session_state"):
        if payload.get(optional_key):
            refreshed[optional_key] = payload[optional_key]
    if not refreshed.get("access_token"):
        return None
    write_cache(cache_file, refreshed)
    return refreshed


def main() -> None:
    args = parse_args()
    if args.watch:
        while True:
            refreshed = refresh_from_cache(args.cache_file, args.min_ttl_sec, args.session_key)
            if not refreshed:
                fail(f"no refreshable PJN token available in {args.cache_file}")
            print(
                json.dumps(
                    {
                        "status": "ok",
                        "cacheFile": str(args.cache_file),
                        "source": refreshed.get("source"),
                        "expires_at": refreshed.get("expires_at"),
                        "ttl_seconds": int(refreshed.get("expires_at", 0)) - int(time.time()),
                        "refresh_ttl_seconds": refresh_token_ttl(refreshed),
                        "next_refresh_seconds": args.watch_interval_sec,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            time.sleep(args.watch_interval_sec)

    refreshed = None if args.force_browser else refresh_from_cache(args.cache_file, args.min_ttl_sec, args.session_key)
    if refreshed:
        print(
            json.dumps(
                {
                    "status": "ok",
                    "cacheFile": str(args.cache_file),
                    "source": refreshed.get("source"),
                    "expires_at": refreshed.get("expires_at"),
                    "ttl_seconds": int(refreshed.get("expires_at", 0)) - int(time.time()),
                    "refresh_ttl_seconds": refresh_token_ttl(refreshed),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        if args.print_token:
            print(refreshed["access_token"])
        return
    if args.refresh_only:
        fail(f"no refreshable PJN token available in {args.cache_file}")

    if args.from_clipboard:
        user = parse_oidc_user(read_clipboard())
        ttl = token_ttl(user)
        if ttl < args.min_ttl_sec:
            fail(f"PJN token found but TTL is too short: {ttl}s")
        cache = cache_token(user, args.cache_file, f"clipboard {args.session_key}", args.session_key)
        print(
            json.dumps(
                {
                    "status": "ok",
                    "cacheFile": str(args.cache_file),
                    "expires_at": cache.get("expires_at"),
                    "ttl_seconds": ttl,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        if args.print_token:
            print(cache["access_token"])
        return

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        node_cmd = [
            "node",
            str(node_helper_path()),
            "--profile-dir",
            str(args.profile_dir),
            "--cache-file",
            str(args.cache_file),
            "--timeout-sec",
            str(args.timeout_sec),
            "--min-ttl-sec",
            str(args.min_ttl_sec),
            "--session-key",
            args.session_key,
            "--start-url",
            args.start_url,
        ]
        if args.headed:
            node_cmd.append("--headed")
        result = subprocess.run(
            node_cmd,
            text=True,
            env={**os.environ, "NODE_PATH": str(lab_root() / "node-tools" / "node_modules")},
        )
        if result.returncode != 0:
            fail(
                "Python Playwright failed and Node fallback did not complete. "
                f"Python error: {exc}"
            )
        return

    args.profile_dir.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + args.timeout_sec

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(args.profile_dir),
            headless=not args.headed,
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(args.start_url, wait_until="domcontentloaded")

        user = None
        while time.time() < deadline:
            user = read_session_user(page, args.session_key)
            if user and token_ttl(user) >= args.min_ttl_sec:
                break
            if user and token_ttl(user) < args.min_ttl_sec:
                page.reload(wait_until="domcontentloaded")
            page.wait_for_timeout(1000)

        if not user:
            context.close()
            fail(
                "No PJN OIDC session found. Run again with --headed, log in manually, "
                f"wait for {args.start_url} to load, then rerun."
            )
        ttl = token_ttl(user)
        if ttl < args.min_ttl_sec:
            context.close()
            fail(f"PJN token found but TTL is too short: {ttl}s")

        cache = cache_token(user, args.cache_file, f"{args.start_url} sessionStorage {args.session_key}", args.session_key)
        context.close()

    print(
        json.dumps(
            {
                "status": "ok",
                "cacheFile": str(args.cache_file),
                "expires_at": cache.get("expires_at"),
                "ttl_seconds": ttl,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if args.print_token:
        print(cache["access_token"])


if __name__ == "__main__":
    main()
