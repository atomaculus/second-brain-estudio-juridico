#!/usr/bin/env python3
"""
Resolve PJN expediente ids for registry matters.

This only calls GET /api/expedientes?numero=&anio=. It does not open
notifications, download PDFs, or mark anything as read.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pjn_local_paths import token_cache_file


BASE_URL = "https://notif.pjn.gov.ar/api"


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def vault_root() -> Path:
    return Path(__file__).resolve().parents[3]


def lab_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_registry_path() -> Path:
    return vault_root() / "08-context" / "registries" / "matter-registry.json"


def default_token_file() -> Path:
    return token_cache_file()


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize(value: Any) -> str:
    text = "" if value is None else str(value)
    replacements = {
        "Ã‘": "Ñ",
        "Ã±": "ñ",
        "Âº": "º",
        "NÂº": "Nº",
        "DAÃ‘OS": "DAÑOS",
        "daÃ±os": "daños",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.upper()
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def token_words(value: Any) -> set[str]:
    stop = {
        "C",
        "S",
        "Y",
        "DE",
        "DEL",
        "LA",
        "LAS",
        "LOS",
        "EL",
        "EN",
        "POR",
        "ART",
        "ARTS",
        "INC",
        "N",
        "NO",
    }
    return {word for word in normalize(value).split() if len(word) > 2 and word not in stop}


def word_overlap(left: Any, right: Any) -> float:
    left_words = token_words(left)
    right_words = token_words(right)
    if not left_words or not right_words:
        return 0.0
    return len(left_words & right_words) / max(len(left_words), len(right_words))


def incident_number(value: Any) -> int | None:
    text = normalize(value)
    match = re.search(r"\bINCIDENTE\s+(?:N|NO|NUMERO)?\s*(\d+)\b", text)
    if not match:
        return None
    return int(match.group(1))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve missing pjnExpedienteId values in matter registry.")
    parser.add_argument("--registry", type=Path, default=default_registry_path())
    parser.add_argument("--token-env", default="PJN_BEARER_TOKEN")
    parser.add_argument("--token-file", type=Path, default=default_token_file())
    parser.add_argument("--matter-id", action="append", help="Resolve only this matterId; repeatable.")
    parser.add_argument("--apply", action="store_true", help="Allow updating the local matter registry.")
    parser.add_argument("--dry-run", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--force", action="store_true", help="Re-check matters that already have pjnExpedienteId.")
    parser.add_argument("--limit", type=int, help="Maximum matters to query.")
    args = parser.parse_args()
    args.dry_run = args.dry_run or not args.apply
    return args


def load_token(args: argparse.Namespace) -> str:
    cache = read_json(args.token_file, None)
    if isinstance(cache, dict) and cache.get("access_token"):
        try:
            if int(cache.get("expires_at")) > int(time.time()) + 30:
                return str(cache["access_token"])
        except (TypeError, ValueError):
            pass
    env_token = os.environ.get(args.token_env)
    if env_token:
        return env_token
    fail(f"no live PJN token available; refresh cache with pjn_browser_token.py")


def get_json(token: str, url: str) -> Any:
    req = Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "pjn-expediente-id-resolver/0.1",
        },
        method="GET",
    )
    try:
        with urlopen(req, timeout=60) as response:
            body = response.read()
            content_type = response.headers.get("Content-Type", "")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        fail(f"HTTP {exc.code} for {url}\n{body[:1000]}")
    except URLError as exc:
        fail(f"request failed for {url}: {exc}")
    if "json" not in content_type.lower():
        fail(f"expected JSON from {url}, got {content_type}")
    return json.loads(body.decode("utf-8"))


def expediente_url(matter: dict[str, Any]) -> str:
    return f"{BASE_URL}/expedientes?{urlencode({'numero': matter['numero'], 'anio': matter['anio']})}"


def select_match(matter: dict[str, Any], expedientes: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str, list[dict[str, Any]]]:
    fuero = normalize(matter.get("fuero"))
    sub = matter.get("subexpediente")
    wanted_sub = incident_number(matter.get("caratula")) or (int(sub) if str(sub or "").isdigit() else 0)

    candidates = [
        item
        for item in expedientes
        if normalize(item.get("camara")) == fuero
        and int(item.get("numero") or 0) == int(matter.get("numero") or 0)
        and int(item.get("anio") or 0) == int(matter.get("anio") or 0)
    ]
    if not candidates:
        return None, "no candidate with same fuero/numero/anio", []

    sub_candidates = [item for item in candidates if int(item.get("numeroSubexpediente") or 0) == wanted_sub]
    if wanted_sub and not sub_candidates:
        return None, f"no candidate with expected subexpediente/incidente {wanted_sub}", candidates
    if sub_candidates:
        candidates = sub_candidates

    if len(candidates) == 1:
        expected_incident = incident_number(matter.get("caratula"))
        candidate_incident = incident_number(candidates[0].get("caratula"))
        if expected_incident and candidate_incident and expected_incident != candidate_incident:
            return None, f"incident number mismatch: expected {expected_incident}, got {candidate_incident}", candidates
        return candidates[0], "unique fuero/numero/anio/subexpediente match", candidates

    expected = matter.get("caratula") or matter.get("matterName") or ""
    exact = [item for item in candidates if normalize(item.get("caratula")) == normalize(expected)]
    if len(exact) == 1:
        return exact[0], "unique normalized caratula match", candidates

    scored = sorted(
        ((word_overlap(expected, item.get("caratula")), item) for item in candidates),
        key=lambda pair: pair[0],
        reverse=True,
    )
    if scored and scored[0][0] >= 0.75 and (len(scored) == 1 or scored[0][0] - scored[1][0] >= 0.20):
        return scored[0][1], f"high caratula overlap {scored[0][0]:.2f}", candidates

    return None, f"ambiguous candidates: {len(candidates)}", candidates


def sync_route_reason(reason: str, candidate_count: int) -> str:
    normalized = normalize(reason)
    if "EXPECTED SUBEXPEDIENTE" in normalized or "INCIDENT" in normalized:
        return "api_candidate_is_parent_or_wrong_subexpediente"
    if candidate_count == 0 or "NO CANDIDATE" in normalized:
        return "api_no_candidate"
    return "api_no_valid_candidate"


def matters_to_resolve(registry: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    selected_ids = set(args.matter_id or [])
    matters = registry.get("matters", [])
    if not isinstance(matters, list):
        fail(f"invalid registry shape: {args.registry}")
    result = []
    for matter in matters:
        if selected_ids and matter.get("matterId") not in selected_ids:
            continue
        if matter.get("status") == "cerrado":
            continue
        if matter.get("pjnSync", {}).get("enabled") is not True:
            continue
        if not (matter.get("fuero") and matter.get("numero") and matter.get("anio")):
            continue
        if matter.get("pjnExpedienteId") and not args.force:
            continue
        result.append(matter)
    return result[: args.limit] if args.limit else result


def compact_candidate(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "camara": item.get("camara"),
        "numero": item.get("numero"),
        "anio": item.get("anio"),
        "numeroSubexpediente": item.get("numeroSubexpediente"),
        "numeracion": item.get("numeracion"),
        "caratula": item.get("caratula"),
        "oficina": item.get("oficina"),
    }


def main() -> None:
    args = parse_args()
    registry = read_json(args.registry, {"matters": []})
    token = load_token(args)
    route_changed = False
    run_dir = lab_root() / "runs" / "resolve-expediente-ids" / datetime.now().strftime("%Y%m%d-%H%M%S")
    raw_dir = run_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=False)

    resolved: list[dict[str, Any]] = []
    unchanged: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    queried = 0

    for matter in matters_to_resolve(registry, args):
        url = expediente_url(matter)
        expedientes = get_json(token, url)
        queried += 1
        if not isinstance(expedientes, list):
            fail(f"unexpected expediente response for {matter.get('matterId')}")
        write_json(raw_dir / f"{matter['matterId']}.json", expedientes)
        match, reason, candidates = select_match(matter, expedientes)
        if not match:
            unresolved.append(
                {
                    "matterId": matter.get("matterId"),
                    "reason": reason,
                    "candidateCount": len(candidates),
                    "candidates": [compact_candidate(item) for item in candidates[:10]],
                }
            )
            continue

        old_id = matter.get("pjnExpedienteId")
        new_id = match.get("id")
        detail = {
            "matterId": matter.get("matterId"),
            "oldPjnExpedienteId": old_id,
            "newPjnExpedienteId": new_id,
            "reason": reason,
            "numeracion": match.get("numeracion"),
            "caratula": match.get("caratula"),
            "oficina": match.get("oficina"),
        }
        if old_id == new_id:
            route_changed = True
            matter["syncRoute"] = {
                "active": "api",
                "reason": "pjn_expediente_id_verified",
                "updatedAt": datetime.now().isoformat(timespec="seconds"),
            }
            unchanged.append(detail)
            continue
        matter["pjnExpedienteId"] = new_id
        route_changed = True
        matter["syncRoute"] = {
            "active": "api",
            "reason": "pjn_expediente_id_resolved",
            "updatedAt": datetime.now().isoformat(timespec="seconds"),
        }
        matter.setdefault("pjnResolution", {})
        matter["pjnResolution"] = {
            "resolvedAt": datetime.now().isoformat(timespec="seconds"),
            "method": reason,
            "source": "GET /api/expedientes",
            "numeracion": match.get("numeracion"),
            "caratula": match.get("caratula"),
            "oficina": match.get("oficina"),
            "numeroSubexpediente": match.get("numeroSubexpediente"),
        }
        resolved.append(detail)

    report_time = datetime.now().isoformat(timespec="seconds")
    for item in unresolved:
        matter = next((m for m in registry.get("matters", []) if m.get("matterId") == item.get("matterId")), None)
        if not matter:
            continue
        route_changed = True
        matter["syncRoute"] = {
            "active": "scw",
            "reason": sync_route_reason(item.get("reason", ""), int(item.get("candidateCount") or 0)),
            "updatedAt": report_time,
            "apiResolution": {
                "reason": item.get("reason"),
                "candidateCount": item.get("candidateCount"),
            },
        }

    report = {
        "createdAt": report_time,
        "dryRun": args.dry_run,
        "registry": str(args.registry),
        "queried": queried,
        "resolved": len(resolved),
        "unchanged": len(unchanged),
        "unresolved": len(unresolved),
        "endpointsAllowed": ["GET /api/expedientes"],
        "endpointsForbidden": [
            "GET /api/notificaciones/RECIBIDAS/{notifId}/pdf",
            "GET /api/notificaciones/{notifId}/pdf",
            "PATCH /api/notificaciones/{notifId}/leida",
        ],
        "resolvedItems": resolved,
        "unchangedItems": unchanged,
        "unresolvedItems": unresolved,
    }
    write_json(raw_dir / "resolve-report.json", report)

    if not args.dry_run and route_changed:
        registry["updatedAt"] = datetime.now().date().isoformat()
        registry["lastPjnExpedienteIdResolution"] = {
            "createdAt": report["createdAt"],
            "runDir": str(run_dir),
            "queried": queried,
            "resolved": len(resolved),
            "unchanged": len(unchanged),
            "unresolved": len(unresolved),
        }
        write_json(args.registry, registry)

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
