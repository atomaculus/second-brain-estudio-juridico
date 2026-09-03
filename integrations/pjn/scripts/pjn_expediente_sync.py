#!/usr/bin/env python3
"""
PJN expediente sync.

Safe, recurrent sync for PJN actuaciones. It only calls expediente/despacho
endpoints, never notification PDFs or read-marking endpoints.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pjn_local_paths import token_cache_file


BASE_URL = "https://notif.pjn.gov.ar/api"
ALLOWED_TIPO_DOCUMENTO = {0, 1}
FORBIDDEN_PATTERNS = (
    re.compile(r"/api/notificaciones/(?:[^/]+/)?[^/]+/pdf", re.I),
    re.compile(r"/api/notificaciones/[^/]+/leida", re.I),
)

VISIBLE_FOLDERS = {
    "despacho": "01 Despachos",
    "escrito_nuestro": "02 Escritos nuestros",
    "escrito_parte_contraria": "03 Escritos parte contraria",
    "organismo_tercero": "04 Organismos y terceros",
    "fiscalia": "04 Organismos y terceros",
    "cedula_diligenciamiento": "07 Notificaciones",
}

ORIGIN_LABELS = {
    "despacho": "Despacho",
    "escrito_nuestro": "Escrito nuestro",
    "escrito_parte_contraria": "Escrito parte contraria",
    "organismo_tercero": "Organismo tercero",
    "fiscalia": "Fiscalia",
    "cedula_diligenciamiento": "Cedula diligenciamiento",
    "desconocido": "Desconocido",
}

COURT_PATTERNS = (
    "AGREGUESE",
    "CAMARA",
    "CERTIFICACION",
    "DECLARATORIA",
    "HAGASE",
    "JUZGADO",
    "PREVIO",
    "PROVEER",
    "PROVIDENCIA",
    "RESUELVO",
    "SECRETARIA",
    "SENTENCIA",
    "TENGASE",
    "VISTA",
)
FILING_PATTERNS = (
    "ACOMPA",
    "ACREDITA",
    "ADJUNTA",
    "CONTESTA",
    "DA CUMPLIMIENTO",
    "INTERPONE",
    "MANIFIESTA",
    "PROMUEVE",
    "SOLICITA",
)
THIRD_PARTY_PATTERNS = (
    "BANCO",
    "BOLETIN",
    "BORA",
    "COLEGIO",
    "EDICTO",
    "OFICIO",
)


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(message)


def vault_root() -> Path:
    return Path(__file__).resolve().parents[3]


def lab_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_known_unavailable() -> dict[str, set[str]]:
    """Documentos conocidos como no disponibles en PJN (404 confirmado, etc.).
    No cuentan como error del lote. Fuente: 08-context/registries/pjn-known-issues.json"""
    path = vault_root() / "08-context" / "registries" / "pjn-known-issues.json"
    data = read_json(path, {})
    result: dict[str, set[str]] = {}
    for item in (data.get("unavailableDocs") or []):
        mid = str(item.get("matterId") or "")
        did = str(item.get("despachoId") or "")
        if mid and did:
            result.setdefault(mid, set()).add(did)
    return result


def default_registry_path() -> Path:
    return vault_root() / "08-context" / "registries" / "matter-registry.json"


def default_token_file() -> Path:
    return token_cache_file()


def normalize(value: Any) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return text.upper()


def slug(value: Any, max_len: int = 90) -> str:
    text = unicodedata.normalize("NFKD", "" if value is None else str(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^A-Za-z0-9 ._-]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" ._-")
    return (text[:max_len].strip(" ._-") or "sin-descripcion")


def ensure_safe_url(url: str) -> None:
    for pattern in FORBIDDEN_PATTERNS:
        if pattern.search(url):
            fail(f"refusing to call endpoint with read side effect: {url}")


def ensure_inside(path: Path, root: Path, label: str) -> None:
    resolved = path.resolve()
    resolved_root = root.resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        fail(f"refusing to write outside {label}: {resolved}")


def request(auth: "TokenSession", url: str, accept: str = "application/json") -> tuple[bytes, str]:
    ensure_safe_url(url)
    for attempt in range(2):
        req = Request(
            url,
            headers={
                "Authorization": f"Bearer {auth.current()}",
                "Accept": accept,
                "User-Agent": "pjn-expediente-sync/0.3",
            },
            method="GET",
        )
        try:
            with urlopen(req, timeout=60) as response:
                return response.read(), response.headers.get("Content-Type", "")
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if exc.code == 401 and attempt == 0 and auth.can_refresh:
                auth.refresh()
                continue
            fail(f"HTTP {exc.code} for {url}\n{body[:1000]}")
        except URLError as exc:
            fail(f"request failed for {url}: {exc}")
    fail(f"authentication retry exhausted for {url}")


def get_json(auth: "TokenSession", url: str) -> Any:
    body, content_type = request(auth, url)
    if "json" not in content_type.lower():
        fail(f"expected JSON from {url}, got {content_type}")
    return json.loads(body.decode("utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync PJN actuaciones safely.")
    parser.add_argument("--matter-id", help="Matter ID from matter-registry.json.")
    parser.add_argument("--all", action="store_true", help="Sync all publish-enabled/indexed matters.")
    parser.add_argument("--registry", type=Path, default=default_registry_path())
    parser.add_argument("--fuero", help="Legacy single-expediente fuero, e.g. CIV.")
    parser.add_argument("--numero", type=int, help="Legacy single-expediente number.")
    parser.add_argument("--anio", type=int, help="Legacy single-expediente year.")
    parser.add_argument("--pjn-expediente-id", type=int, help="Optional legacy PJN expediente id.")
    parser.add_argument("--token-env", default="PJN_BEARER_TOKEN")
    parser.add_argument("--token-file", type=Path, default=default_token_file())
    configured_names = [name.strip() for name in os.environ.get("PJN_OWN_NAMES", "").split(";") if name.strip()]
    parser.add_argument("--own-name", action="append", default=configured_names)
    parser.add_argument("--no-pdf", action="store_true", help="Fetch metadata only.")
    parser.add_argument("--apply", action="store_true", help="Allow downloads, publication and state updates.")
    parser.add_argument("--dry-run", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--offline-raw-dir",
        type=Path,
        help="Use existing raw/expedientes.json, raw/despachos.json and raw/destinatarios.json.",
    )
    args = parser.parse_args()
    args.dry_run = args.dry_run or not args.apply
    return args


def load_token(args: argparse.Namespace) -> str | None:
    env_token = os.environ.get(args.token_env)
    if env_token:
        return env_token
    cache = read_json(args.token_file, None)
    if not isinstance(cache, dict):
        return None
    token = cache.get("access_token")
    expires_at = cache.get("expires_at")
    if not token:
        return None
    if expires_at:
        try:
            if int(expires_at) <= int(datetime.now().timestamp()) + 30:
                return None
        except (TypeError, ValueError):
            fail(f"invalid expires_at in token cache: {args.token_file}")
    return str(token)


class TokenSession:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.env_token = os.environ.get(args.token_env)
        self.token = load_token(args)
        if not self.token:
            self.refresh()

    @property
    def can_refresh(self) -> bool:
        return not bool(self.env_token)

    def cache_ttl(self) -> int:
        cache = read_json(self.args.token_file, None)
        if not isinstance(cache, dict):
            return -1
        try:
            return int(cache.get("expires_at", 0)) - int(datetime.now().timestamp())
        except (TypeError, ValueError):
            return -1

    def current(self) -> str:
        if self.env_token:
            return self.env_token
        if self.cache_ttl() <= 90:
            return self.refresh()
        cached = load_token(self.args)
        if cached:
            self.token = cached
        if not self.token:
            return self.refresh()
        return self.token

    def refresh(self) -> str:
        if not self.can_refresh:
            fail("PJN token from environment cannot be refreshed automatically")
        helper = Path(__file__).with_name("pjn_browser_token.py")
        result = subprocess.run(
            [
                sys.executable,
                str(helper),
                "--refresh-only",
                "--cache-file",
                str(self.args.token_file),
                "--min-ttl-sec",
                "120",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip().splitlines()
            suffix = f": {detail[-1]}" if detail else ""
            fail(f"could not refresh PJN token{suffix}")
        refreshed = load_token(self.args)
        if not refreshed:
            fail("PJN token refresh completed without a live access token")
        self.token = refreshed
        return refreshed


def load_registry(path: Path) -> list[dict[str, Any]]:
    registry = read_json(path, {"matters": []})
    if isinstance(registry, list):
        return registry
    matters = registry.get("matters", [])
    if not isinstance(matters, list):
        fail(f"invalid registry shape: {path}")
    return matters


def legacy_matter(args: argparse.Namespace) -> dict[str, Any]:
    if not (args.fuero and args.numero and args.anio):
        fail("use --matter-id/--all or provide --fuero --numero --anio")
    matter_id = f"{normalize(args.fuero)}-{args.numero}-{args.anio}"
    return {
        "matterId": matter_id,
        "status": "ad-hoc",
        "clientName": "",
        "matterName": "",
        "fuero": normalize(args.fuero),
        "numero": args.numero,
        "anio": args.anio,
        "pjnExpedienteId": args.pjn_expediente_id,
        "canonicalFolder": None,
        "publishPjnDownloads": False,
    }


def select_matters(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.matter_id or args.all:
        matters = load_registry(args.registry)
        if args.all:
            return [
                m
                for m in matters
                if m.get("status") != "cerrado"
                and m.get("pjnSync", {}).get("enabled") is True
                and m.get("fuero")
                and m.get("numero")
                and m.get("anio")
                and m.get("pjnExpedienteId")
            ]
        selected = [m for m in matters if m.get("matterId") == args.matter_id]
        if not selected:
            fail(f"matterId not found in registry: {args.matter_id}")
        if selected[0].get("pjnSync", {}).get("enabled") is True and not selected[0].get("pjnExpedienteId"):
            fail(f"matterId has no pjnExpedienteId yet; resolve it before syncing: {args.matter_id}")
        return selected
    return [legacy_matter(args)]


def run_dir_for(matter: dict[str, Any]) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = lab_root() / "runs" / str(matter["matterId"]) / timestamp
    ensure_inside(run_dir, lab_root(), "PJN lab")
    (run_dir / "raw").mkdir(parents=True, exist_ok=False)
    (run_dir / "pdf").mkdir(parents=True, exist_ok=True)
    (run_dir / "text").mkdir(parents=True, exist_ok=True)
    return run_dir


def canonical_folder_path(matter: dict[str, Any]) -> Path | None:
    raw = matter.get("canonicalFolder")
    if not raw:
        return None
    configured = Path(str(raw))
    if configured.exists():
        return configured
    if not configured.is_absolute():
        return vault_root() / configured
    return configured


def local_server_path(raw_path: str | Path | None) -> Path | None:
    """Rebase a Dropbox path created on another workstation onto this PC."""
    if not raw_path:
        return None
    configured = Path(str(raw_path))
    if configured.exists():
        return configured
    return configured


def state_path_for(matter: dict[str, Any]) -> Path:
    canonical = canonical_folder_path(matter)
    if canonical and matter.get("publishPjnDownloads") is True:
        return canonical / "_sistema" / "pjn-state.json"
    return lab_root() / "state" / str(matter["matterId"]) / "pjn-state.json"


def load_state(matter: dict[str, Any]) -> dict[str, Any]:
    state_path = state_path_for(matter)
    legacy_lab_state = lab_root() / "state" / str(matter["matterId"]) / "pjn-state.json"
    read_path = state_path
    if (
        matter.get("publishPjnDownloads") is True
        and not state_path.exists()
        and legacy_lab_state.exists()
    ):
        read_path = legacy_lab_state
    state = read_json(
        read_path,
        {
            "matterId": matter.get("matterId"),
            "createdAt": datetime.now().isoformat(timespec="seconds"),
            "despachos": {},
            "runs": [],
        },
    )
    state.setdefault("despachos", {})
    state.setdefault("runs", [])
    return state


def save_state(matter: dict[str, Any], state: dict[str, Any]) -> None:
    path = state_path_for(matter)
    canonical = canonical_folder_path(matter)
    if canonical and matter.get("publishPjnDownloads") is True:
        canonical_path = canonical
        if not canonical_path.exists():
            fail(f"canonicalFolder does not exist: {canonical_path}")
        ensure_inside(path, canonical_path, "canonical matter folder")
    else:
        ensure_inside(path, lab_root(), "PJN lab")
    state["updatedAt"] = datetime.now().isoformat(timespec="seconds")
    write_json(path, state)


def select_expediente(expedientes: list[dict[str, Any]], matter: dict[str, Any]) -> tuple[dict[str, Any], str]:
    pjn_id = matter.get("pjnExpedienteId")
    if pjn_id:
        exact_id = [item for item in expedientes if item.get("id") == pjn_id]
        if exact_id:
            return exact_id[0], "exact pjnExpedienteId match"
    wanted = normalize(matter.get("fuero"))
    exact_fuero = [item for item in expedientes if normalize(item.get("camara")) == wanted]
    if exact_fuero:
        return exact_fuero[0], "exact fuero match"
    return expedientes[0], "first result; no exact registry match"


def fetch_context(
    auth: TokenSession | None,
    matter: dict[str, Any],
    raw_dir: Path,
    offline_raw_dir: Path | None,
) -> tuple[dict[str, Any], str, list[dict[str, Any]], Any, list[dict[str, str]]]:
    requests_used: list[dict[str, str]] = []
    if offline_raw_dir:
        source = offline_raw_dir
        expedientes = read_json(source / "expedientes.json", [])
        despachos = read_json(source / "despachos.json", [])
        destinatarios = read_json(source / "destinatarios.json", [])
        write_json(raw_dir / "expedientes.json", expedientes)
        write_json(raw_dir / "despachos.json", despachos)
        write_json(raw_dir / "destinatarios.json", destinatarios)
        requests_used.append({"name": "offline-raw-dir", "url": str(source)})
    else:
        if not auth:
            fail("set $PJN_BEARER_TOKEN or use --offline-raw-dir")
        exp_query = urlencode({"numero": matter["numero"], "anio": matter["anio"]})
        exp_url = f"{BASE_URL}/expedientes?{exp_query}"
        expedientes = get_json(auth, exp_url)
        requests_used.append({"name": "expedientes", "url": exp_url})
        write_json(raw_dir / "expedientes.json", expedientes)
        if not isinstance(expedientes, list) or not expedientes:
            fail(f"no expediente found for {matter.get('matterId')}")
        selected_exp, _ = select_expediente(expedientes, matter)
        exp_id = selected_exp["id"]
        despachos_url = f"{BASE_URL}/despachos/{exp_id}"
        despachos = get_json(auth, despachos_url)
        requests_used.append({"name": "despachos", "url": despachos_url})
        write_json(raw_dir / "despachos.json", despachos)
        destinatarios_url = f"{BASE_URL}/destinatarios/{exp_id}"
        destinatarios = get_json(auth, destinatarios_url)
        requests_used.append({"name": "destinatarios", "url": destinatarios_url})
        write_json(raw_dir / "destinatarios.json", destinatarios)

    if not isinstance(expedientes, list) or not expedientes:
        fail("offline/remote expedientes response is empty")
    if not isinstance(despachos, list):
        fail("expected list from despachos endpoint")
    selected_exp, selection_reason = select_expediente(expedientes, matter)
    return selected_exp, selection_reason, despachos, destinatarios, requests_used


def despacho_date(despacho: dict[str, Any]) -> datetime | None:
    raw = str(despacho.get("fechaFirma") or despacho.get("fecha") or "")
    formats = ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d")
    for fmt in formats:
        try:
            return datetime.strptime(raw[: len(datetime.now().strftime(fmt))], fmt)
        except ValueError:
            continue
    return None


def date_label(despacho: dict[str, Any]) -> str:
    parsed = despacho_date(despacho)
    return parsed.strftime("%Y-%m-%d") if parsed else "sin-fecha"


def classify_despacho(despacho: dict[str, Any], own_names: list[str]) -> dict[str, str]:
    blob = normalize(json.dumps(despacho, ensure_ascii=False, sort_keys=True))
    descripcion = normalize(despacho.get("descripcion", ""))
    own_hits = [name for name in own_names if normalize(name) and normalize(name) in blob]

    if "FISCAL" in blob or "DICTAMEN" in descripcion:
        return {"classification": "fiscalia", "confidence": "alta", "reason": "menciona fiscalia o dictamen"}
    if "CEDULA" in descripcion or "DILIGENCIAMIENTO" in descripcion:
        return {"classification": "cedula_diligenciamiento", "confidence": "alta", "reason": "menciona cedula/diligenciamiento"}
    if any(pattern in descripcion for pattern in THIRD_PARTY_PATTERNS):
        return {"classification": "organismo_tercero", "confidence": "alta", "reason": "menciona organismo o tercero"}
    if despacho.get("tipoDocumento") == 1 or any(pattern in descripcion for pattern in COURT_PATTERNS):
        return {"classification": "despacho", "confidence": "alta", "reason": "tipoDocumento=1 o marcas judiciales"}
    if own_hits:
        return {"classification": "escrito_nuestro", "confidence": "alta", "reason": f"contiene nombre propio: {', '.join(own_hits[:3])}"}
    if any(pattern in descripcion for pattern in FILING_PATTERNS):
        return {"classification": "escrito_nuestro", "confidence": "media", "reason": "parece presentacion del estudio por descripcion"}
    return {"classification": "desconocido", "confidence": "baja", "reason": "metadatos insuficientes"}


def target_filename(despacho: dict[str, Any], item_class: dict[str, str]) -> str:
    origin = ORIGIN_LABELS.get(item_class["classification"], "Desconocido")
    desc = slug(despacho.get("descripcion"), 50)
    return f"{date_label(despacho)} - {origin} - {desc} - despacho-{despacho.get('id')}.pdf"


def download_pdf(auth: TokenSession, expediente_id: int, despacho_id: int) -> tuple[bytes, str, str]:
    url = f"{BASE_URL}/despachos/{expediente_id}/{despacho_id}/pdf"
    body, content_type = request(auth, url, accept="application/pdf")
    if not body.startswith(b"%PDF-"):
        fail(f"downloaded body is not a PDF for despacho {despacho_id}")
    return body, content_type, url


def sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def adopt_legacy_pdf_indexes(matter: dict[str, Any], state: dict[str, Any]) -> int:
    if state.get("despachos"):
        return 0
    adopted = 0
    matter_runs = lab_root() / "runs" / str(matter["matterId"])
    if not matter_runs.exists():
        return 0
    for index_path in matter_runs.glob("*/raw/pdf-index.json"):
        for item in read_json(index_path, []):
            despacho_id = str(item.get("id") or "")
            pdf_path_raw = item.get("pdfPath")
            if not despacho_id or not pdf_path_raw:
                continue
            pdf_path = Path(pdf_path_raw)
            if not pdf_path.exists():
                continue
            state["despachos"][despacho_id] = {
                "id": item.get("id"),
                "descripcion": item.get("descripcion"),
                "tipoDocumento": item.get("tipoDocumento"),
                "fechaFirma": item.get("fechaFirma"),
                "classification": {"classification": "desconocido", "confidence": "baja", "reason": "adopted from legacy pdf-index"},
                "sha256": sha256_file(pdf_path),
                "bytes": pdf_path.stat().st_size,
                "stagingPath": str(pdf_path),
                "textPath": None,
                "publishedPath": None,
                "publishStatus": "legacy-staging",
                "contentType": item.get("contentType"),
                "downloadedAt": item.get("createdAt") or datetime.now().isoformat(timespec="seconds"),
                "url": item.get("url"),
                "adoptedFrom": str(index_path),
            }
            adopted += 1
    return adopted


def extract_text(pdf_path: Path, txt_path: Path) -> dict[str, Any]:
    txt_path.parent.mkdir(parents=True, exist_ok=True)
    # 1) pdftotext si esta disponible (mejor layout).
    pdftotext = shutil.which("pdftotext")
    if pdftotext:
        result = subprocess.run(
            [pdftotext, "-layout", str(pdf_path), str(txt_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            return {"status": "ok", "path": str(txt_path), "engine": "pdftotext"}
        # si falla, sigue al fallback en Python
    # 2) Fallback en Python (pypdf): no depende de binarios externos.
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
        txt_path.write_text(text, encoding="utf-8")
        return {"status": "ok", "path": str(txt_path), "engine": "pypdf"}
    except Exception as exc:  # noqa: BLE001
        txt_path.write_text("", encoding="utf-8")
        return {
            "status": "skipped",
            "reason": f"sin extractor de texto disponible (pdftotext ausente; pypdf fallo: {exc})",
        }


def canonical_publish_target(matter: dict[str, Any], item_class: dict[str, str], filename: str) -> Path | None:
    canonical = canonical_folder_path(matter)
    if matter.get("publishPjnDownloads") is not True or not canonical:
        return None
    # Publicacion automatica: confianza alta y media (decision operativa 2026-07-24).
    # Baja/desconocido siguen quedando en staging para revision del indexador.
    if item_class["confidence"] not in ("alta", "media"):
        return None
    folder = VISIBLE_FOLDERS.get(item_class["classification"])
    if not folder:
        return None
    canonical_path = canonical
    if not canonical_path.exists():
        return None
    return canonical_path / folder / filename


def publish_pdf(source: Path, target: Path, canonical_root: Path) -> str:
    ensure_inside(target, canonical_root, "canonical matter folder")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return "already-exists"
    source_for_copy: str | Path = source
    target_for_copy: str | Path = target
    if os.name == "nt":
        # CopyFile2 can fail with WinError 3 for otherwise valid paths over MAX_PATH.
        source_for_copy = "\\\\?\\" + str(source.resolve())
        target_for_copy = "\\\\?\\" + str(target.resolve())
    shutil.copy2(source_for_copy, target_for_copy)
    return "copied"


def publish_existing_state_items(
    matter: dict[str, Any], state: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Publish previously staged PDFs after a canonical folder is enabled."""
    canonical_root = canonical_folder_path(matter)
    if matter.get("publishPjnDownloads") is not True or not canonical_root or not canonical_root.exists():
        return [], []
    published: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for despacho_id, record in state.get("despachos", {}).items():
        current_published = local_server_path(record.get("publishedPath"))
        if current_published and current_published.exists():
            continue
        item_class = record.get("classification") or {}
        source = local_server_path(record.get("stagingPath"))
        filename = source.name if source else target_filename(record, item_class)
        target = canonical_publish_target(matter, item_class, filename)
        if not source or not source.exists() or not target:
            blocked.append(
                {
                    "id": despacho_id,
                    "reason": "missing-staging-or-low-confidence",
                    "stagingExists": bool(source and source.exists()),
                }
            )
            continue
        status = publish_pdf(source, target, canonical_root)
        record["publishedPath"] = str(target)
        record["publishStatus"] = status
        published.append(
            {
                "id": despacho_id,
                "fechaFirma": record.get("fechaFirma"),
                "descripcion": record.get("descripcion"),
                "classification": item_class,
                "publishedPath": str(target),
                "publishStatus": status,
            }
        )
    return published, blocked


def short_description(despacho: dict[str, Any]) -> str:
    text = str(despacho.get("descripcion") or "").replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:180] + ("..." if len(text) > 180 else "")


def build_timeline(
    matter: dict[str, Any],
    selected_exp: dict[str, Any],
    selection_reason: str,
    despachos: list[dict[str, Any]],
    classifications: dict[str, dict[str, str]],
) -> str:
    rows = []
    for despacho in sorted(despachos, key=lambda d: despacho_date(d) or datetime.min, reverse=True):
        item_class = classifications[str(despacho.get("id"))]
        rows.append(
            "| {fecha} | {tipo} | {clasificacion} | {confianza} | {descripcion} | {id} |".format(
                fecha=despacho.get("fechaFirma") or despacho.get("fecha") or "",
                tipo=despacho.get("tipoDocumento", ""),
                clasificacion=item_class["classification"],
                confianza=item_class["confidence"],
                descripcion=short_description(despacho).replace("|", "\\|"),
                id=despacho.get("id"),
            )
        )
    return "\n".join(
        [
            "---",
            "type: pjn-sync-timeline",
            f"matterId: {matter.get('matterId')}",
            f"created: {datetime.now().isoformat(timespec='seconds')}",
            "---",
            "",
            f"# Timeline PJN - {selected_exp.get('numeracion', matter.get('matterId'))}",
            "",
            f"- Caratula: {selected_exp.get('caratula', '')}",
            f"- Expediente ID PJN: {selected_exp.get('id', '')}",
            f"- Seleccion: {selection_reason}",
            "",
            "| Fecha | TipoDoc | Clasificacion | Confianza | Descripcion | ID |",
            "|---|---:|---|---|---|---:|",
            *rows,
            "",
        ]
    )


def build_review(pending: list[dict[str, Any]]) -> str:
    lines = [
        "---",
        "type: pjn-sync-review",
        f"created: {datetime.now().isoformat(timespec='seconds')}",
        "---",
        "",
        "# Revision Pendiente PJN",
        "",
    ]
    if not pending:
        lines.append("No hay actuaciones pendientes de revision en esta corrida.")
        return "\n".join(lines) + "\n"
    for item in pending:
        despacho = item["despacho"]
        item_class = item["classification"]
        lines.extend(
            [
                f"## Despacho {despacho.get('id')}",
                "",
                f"- Fecha: {despacho.get('fechaFirma') or despacho.get('fecha') or ''}",
                f"- TipoDocumento: {despacho.get('tipoDocumento')}",
                f"- Clasificacion sugerida: {item_class['classification']}",
                f"- Confianza: {item_class['confidence']}",
                f"- Motivo: {item_class['reason']}",
                f"- Descripcion: {short_description(despacho)}",
                "",
            ]
        )
    return "\n".join(lines)


def sync_one(args: argparse.Namespace, matter: dict[str, Any]) -> dict[str, Any]:
    run_dir = run_dir_for(matter)
    raw_dir = run_dir / "raw"
    auth = None if args.offline_raw_dir else TokenSession(args)
    state = load_state(matter)
    initial_state_items = len(state.get("despachos", {}))
    adopted_legacy = adopt_legacy_pdf_indexes(matter, state)
    backfilled, backfill_blocked = publish_existing_state_items(matter, state) if not args.dry_run else ([], [])
    selected_exp, selection_reason, despachos, destinatarios, requests_used = fetch_context(
        auth,
        matter,
        raw_dir,
        args.offline_raw_dir,
    )
    expediente_id = int(selected_exp["id"])

    classifications = {str(d.get("id")): classify_despacho(d, args.own_name) for d in despachos}
    targets = [d for d in despachos if d.get("tipoDocumento") in ALLOWED_TIPO_DOCUMENTO]
    downloaded: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    pending_review: list[dict[str, Any]] = []
    # Documentos conocidos como no disponibles en PJN (404 confirmado, etc.). No cuentan
    # como error del lote; se reportan aparte. Fuente: 08-context/registries/pjn-known-issues.json
    known_unavailable_ids = load_known_unavailable().get(str(matter.get("matterId")), set())
    known_unavailable_hits: list[dict[str, Any]] = []

    for despacho in sorted(targets, key=lambda d: despacho_date(d) or datetime.min):
        despacho_id = str(despacho.get("id"))
        item_class = classifications[despacho_id]
        filename = target_filename(despacho, item_class)
        pdf_path = run_dir / "pdf" / filename
        txt_path = run_dir / "text" / f"{pdf_path.stem}.txt"
        previous = state["despachos"].get(despacho_id)
        if previous:
            skipped.append({"id": despacho_id, "reason": "already-in-state", "publishedPath": previous.get("publishedPath")})
            continue
        if args.no_pdf or args.dry_run:
            skipped.append({"id": despacho_id, "reason": "dry-run-or-no-pdf", "filename": filename})
            if item_class["confidence"] != "alta" or item_class["classification"] == "desconocido":
                pending_review.append({"despacho": despacho, "classification": item_class})
            continue
        try:
            if not auth:
                fail("set $PJN_BEARER_TOKEN before downloading PDFs")
            body, content_type, url = download_pdf(auth, expediente_id, int(despacho_id))
            digest = sha256_bytes(body)
            pdf_path.write_bytes(body)
            text_result = extract_text(pdf_path, txt_path)
            published_path = None
            publish_status = "not-configured"
            target = canonical_publish_target(matter, item_class, filename)
            if target:
                canonical_root = canonical_folder_path(matter)
                if not canonical_root:
                    fail("canonicalFolder is required for publication")
                publish_status = publish_pdf(pdf_path, target, canonical_root)
                published_path = str(target)
            elif matter.get("publishPjnDownloads") is True:
                publish_status = "blocked-no-valid-canonical-or-low-confidence"
            record = {
                "id": int(despacho_id),
                "descripcion": despacho.get("descripcion"),
                "tipoDocumento": despacho.get("tipoDocumento"),
                "fechaFirma": despacho.get("fechaFirma"),
                "classification": item_class,
                "sha256": digest,
                "bytes": len(body),
                "stagingPath": str(pdf_path),
                "textPath": str(txt_path),
                "publishedPath": published_path,
                "publishStatus": publish_status,
                "contentType": content_type,
                "downloadedAt": datetime.now().isoformat(timespec="seconds"),
                "url": url,
                "textExtraction": text_result,
            }
            state["despachos"][despacho_id] = record
            downloaded.append(record)
            if not args.dry_run and len(downloaded) % 25 == 0:
                save_state(matter, state)
        except SystemExit as exc:
            if despacho_id in known_unavailable_ids:
                known_unavailable_hits.append({"id": despacho_id, "error": str(exc)})
            else:
                errors.append({"id": despacho_id, "error": str(exc)})
        except Exception as exc:  # noqa: BLE001 - keep run report instead of losing batch context
            if despacho_id in known_unavailable_ids:
                known_unavailable_hits.append({"id": despacho_id, "error": str(exc)})
            else:
                errors.append({"id": despacho_id, "error": str(exc)})
        if item_class["confidence"] != "alta" or item_class["classification"] == "desconocido":
            pending_review.append({"despacho": despacho, "classification": item_class})

    report = {
        "createdAt": datetime.now().isoformat(timespec="seconds"),
        "safeMode": True,
        "dryRun": args.dry_run,
        "matterId": matter.get("matterId"),
        "runDir": str(run_dir),
        "statePath": str(state_path_for(matter)),
        "expedienteId": expediente_id,
        "expediente": selected_exp.get("numeracion"),
        "selectionReason": selection_reason,
        "despachosFetched": len(despachos),
        "documentTargets": len(targets),
        "downloaded": len(downloaded),
        "skipped": len(skipped),
        "errors": len(errors),
        "knownUnavailable": len(known_unavailable_hits),
        "knownUnavailableItems": known_unavailable_hits,
        "adoptedLegacyPdfIndexItems": adopted_legacy,
        "initialStateItems": initial_state_items,
        "baselineMode": initial_state_items == 0,
        "backfilledPublished": len(backfilled),
        "backfillBlocked": len(backfill_blocked),
        "requests": requests_used,
        "endpointsAllowed": [
            "GET /api/expedientes",
            "GET /api/despachos/{expedienteId}",
            "GET /api/destinatarios/{expedienteId}",
            "GET /api/despachos/{expedienteId}/{despachoId}/pdf",
        ],
        "endpointsForbidden": [
            "GET /api/notificaciones/RECIBIDAS/{notifId}/pdf",
            "GET /api/notificaciones/{notifId}/pdf",
            "PATCH /api/notificaciones/{notifId}/leida",
        ],
        "downloadedItems": downloaded,
        "backfilledItems": backfilled,
        "backfillBlockedItems": backfill_blocked,
        "skippedItems": skipped,
        "errorsItems": errors,
    }

    write_json(raw_dir / "sync-report.json", report)
    (run_dir / "timeline.md").write_text(
        build_timeline(matter, selected_exp, selection_reason, despachos, classifications),
        encoding="utf-8",
    )
    (run_dir / "classification-review.md").write_text(build_review(pending_review), encoding="utf-8")

    if not args.dry_run:
        state["runs"].append(
            {
                "createdAt": report["createdAt"],
                "runDir": str(run_dir),
                "downloaded": len(downloaded),
                "skipped": len(skipped),
                "errors": len(errors),
            }
        )
        save_state(matter, state)
    return report


def staff_report(reports: list[dict[str, Any]], created_at: datetime) -> str:
    total_downloaded = sum(item["downloaded"] for item in reports)
    total_published_new = sum(
        1 for report in reports for item in report["downloadedItems"] if item.get("publishedPath")
    )
    total_backfilled = sum(item.get("backfilledPublished", 0) for item in reports)
    total_errors = sum(item["errors"] for item in reports)
    total_known_unavailable = sum(item.get("knownUnavailable", 0) for item in reports)
    lines = [
        "---",
        "type: pjn-run-report",
        f"created: {created_at.isoformat(timespec='seconds')}",
        "status: requiere-revision-humana",
        "---",
        "",
        f"# Informe de corrida PJN - {created_at.strftime('%Y-%m-%d %H:%M')}",
        "",
        "> Informe interno automático. Verificar en PJN antes de calcular plazos o tomar decisiones procesales.",
        "",
        "## Resumen",
        "",
        f"- Expedientes consultados por API: {len(reports)}",
        f"- Documentos nuevos para el sistema: {total_downloaded}",
        f"- Documentos nuevos publicados en carpeta canónica: {total_published_new}",
        f"- Documentos históricos publicados en carga inicial: {total_backfilled}",
        f"- Errores: {total_errors}",
        f"- No disponibles conocidos (no cuentan como error): {total_known_unavailable}",
        "",
        "## Expedientes con actividad",
        "",
    ]
    active = [
        report for report in reports
        if report["downloaded"] or report.get("backfilledPublished") or report["errors"]
    ]
    if not active:
        lines.append("No se detectaron documentos nuevos ni errores en esta corrida.")
    for report in active:
        lines.extend(
            [
                f"### {report['matterId']} ({report.get('expediente') or 'sin numeración'})",
                "",
                f"- Nuevos para el sistema: {report['downloaded']}",
                f"- Publicados ahora: {sum(1 for item in report['downloadedItems'] if item.get('publishedPath'))}",
                f"- Históricos publicados en carga inicial: {report.get('backfilledPublished', 0)}",
                f"- Errores: {report['errors']}",
                "",
            ]
        )
        for item in report["downloadedItems"]:
            classification = (item.get("classification") or {}).get("classification", "sin-clasificar")
            destination = "publicado" if item.get("publishedPath") else "staging/revisión"
            lines.append(
                f"- {item.get('fechaFirma') or 'sin fecha'} — {classification} — "
                f"{short_description(item)} — {destination}"
            )
        if report["downloadedItems"]:
            lines.append("")
        for error in report.get("errorsItems", []):
            lines.append(f"- Error en documento {error.get('id')}: {error.get('error')}")
        if report.get("errorsItems"):
            lines.append("")
    lines.extend(
        [
            "## Lectura del informe",
            "",
            "- `Nuevo para el sistema` significa que el identificador no estaba en el estado local; debe validarse antes de tratarlo como novedad procesal.",
            "- `Histórico publicado en carga inicial` es un PDF ya descargado anteriormente que se incorporó ahora a la carpeta canónica.",
            "- Los documentos de confianza baja o sin carpeta canónica quedan en staging y no se publican automáticamente.",
            "",
        ]
    )
    return "\n".join(lines)


def write_staff_report(reports: list[dict[str, Any]]) -> Path:
    created_at = datetime.now()
    reports_root = vault_root() / "09-reviews" / "pjn"
    history_root = reports_root / "historial"
    history_root.mkdir(parents=True, exist_ok=True)
    content = staff_report(reports, created_at)
    history_path = history_root / f"{created_at.strftime('%Y-%m-%d_%H%M%S')}.md"
    history_path.write_text(content, encoding="utf-8")
    latest_path = reports_root / "ULTIMA-CORRIDA.md"
    latest_path.write_text(content, encoding="utf-8")
    return history_path


def main() -> None:
    args = parse_args()
    matters = select_matters(args)
    reports = [sync_one(args, matter) for matter in matters]
    staff_report_path = write_staff_report(reports)
    output = {
        "createdAt": datetime.now().isoformat(timespec="seconds"),
        "staffReport": str(staff_report_path),
        "matters": reports,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
