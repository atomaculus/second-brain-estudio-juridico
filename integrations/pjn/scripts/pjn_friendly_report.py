#!/usr/bin/env python3
"""Generate a plain-language HTML view of the latest PJN run report."""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path


def vault_root() -> Path:
    return Path(__file__).resolve().parents[3]


def value(text: str, label: str, default: str = "No informado") -> str:
    match = re.search(rf"^-\s*{re.escape(label)}:\s*(.+?)\s*$", text, re.MULTILINE | re.IGNORECASE)
    return match.group(1).strip() if match else default


def created_at(text: str) -> datetime | None:
    match = re.search(r"^created:\s*(.+?)\s*$", text, re.MULTILINE)
    if not match:
        return None
    try:
        return datetime.fromisoformat(match.group(1).strip())
    except ValueError:
        return None


def number(text: str, label: str) -> int | None:
    raw = value(text, label, "")
    match = re.search(r"\d+", raw)
    return int(match.group()) if match else None


def parse_movement_date(raw: object) -> datetime | None:
    if not raw:
        return None
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(str(raw), fmt)
        except ValueError:
            continue
    return None


def matter_table(report_created: datetime | None) -> tuple[str, dict[str, int]]:
    scripts = Path(__file__).resolve().parent
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import pjn_expediente_sync as sync  # noqa: PLC0415

    registry = json.loads(sync.default_registry_path().read_text(encoding="utf-8"))
    rows: list[tuple[int, str]] = []
    counts = {"new": 0, "ok": 0, "error": 0, "pending": 0}

    for matter in registry.get("matters", []):
        matter_id = str(matter.get("matterId") or "Sin identificador")
        caratula = str(matter.get("caratula") or matter.get("matterName") or matter_id)
        state_path = sync.state_path_for(matter)
        state: dict = {}
        if state_path.exists():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                state = {}

        movements = state.get("despachos", {}) if isinstance(state.get("despachos", {}), dict) else {}
        movement_dates = [parse_movement_date(item.get("fechaFirma")) for item in movements.values()]
        movement_dates = [item for item in movement_dates if item]
        scw_last_known = parse_movement_date((matter.get("scw") or {}).get("ultimaActuacion"))
        latest = max(movement_dates) if movement_dates else scw_last_known
        latest_text = latest.strftime("%d/%m/%Y") if latest else "sin fecha disponible"

        run = (state.get("runs") or [])[-1] if state.get("runs") else None
        run_created = parse_movement_date(run.get("createdAt")) if run else None
        reviewed = bool(
            report_created
            and run_created
            and -120 <= (report_created - run_created).total_seconds() <= 30 * 60
        )
        downloaded = int(run.get("downloaded", 0)) if reviewed and run else 0
        errors = int(run.get("errors", 0)) if reviewed and run else 0
        published = 0
        staged = 0
        if reviewed and run:
            sync_report = Path(str(run.get("runDir") or "")) / "raw" / "sync-report.json"
            if sync_report.exists():
                try:
                    run_detail = json.loads(sync_report.read_text(encoding="utf-8"))
                    downloaded_items = run_detail.get("downloadedItems") or []
                    published = sum(1 for item in downloaded_items if item.get("publishedPath"))
                    staged = max(0, len(downloaded_items) - published)
                except (OSError, json.JSONDecodeError):
                    pass

        if reviewed and errors:
            kind, order = "error", 0
            if downloaded:
                movement_word = "movimiento nuevo" if downloaded == 1 else "movimientos nuevos"
                publication = ""
                if published:
                    publication = f"; {published} cargado" if published == 1 else f"; {published} cargados"
                    publication += " en la carpeta canónica"
                if staged:
                    publication += f" y {staged} pendiente de revisión" if staged == 1 else f" y {staged} pendientes de revisión"
                error_word = "error" if errors == 1 else "errores"
                status = f"Se detectaron {downloaded} {movement_word}{publication}. Hubo {errors} {error_word} que requiere atención."
            else:
                error_word = "error" if errors == 1 else "errores"
                status = f"Revisado con {errors} {error_word}. Último movimiento registrado: {latest_text}."
        elif reviewed and downloaded:
            kind, order = "new", 1
            movement_word = "movimiento nuevo" if downloaded == 1 else "movimientos nuevos"
            if published and staged:
                loaded_word = "cargado" if published == 1 else "cargados"
                pending_word = "pendiente" if staged == 1 else "pendientes"
                status = f"{downloaded} {movement_word}: {published} {loaded_word} en la carpeta canónica y {staged} {pending_word} de revisión."
            elif published:
                loaded_word = "cargado" if published == 1 else "cargados"
                status = f"{downloaded} {movement_word}, {loaded_word} en la carpeta canónica."
            else:
                pending_word = "pendiente" if downloaded == 1 else "pendientes"
                status = f"{downloaded} {movement_word}, {pending_word} de revisión antes de incorporarlos."
        elif reviewed:
            kind, order = "ok", 2
            status = f"No se registran nuevos movimientos. Último movimiento registrado: {latest_text}."
        else:
            kind, order = "pending", 3
            if not matter.get("pjnExpedienteId"):
                status = f"No pudo verificarse automáticamente. Requiere revisión en el portal PJN. Último dato registrado: {latest_text}."
            else:
                status = f"No fue alcanzado por la última corrida. Último dato registrado: {latest_text}."
        counts[kind] += 1

        searchable = html.escape(f"{caratula} {matter_id} {status}".casefold(), quote=True)
        row = f"""<article class="matter {kind}" data-search="{searchable}">
          <div class="matter-head"><span class="dot"></span><div><strong>{html.escape(caratula)}</strong><small>{html.escape(matter_id)}</small></div></div>
          <p>{html.escape(status)}</p>
        </article>"""
        rows.append((order, row))

    rows.sort(key=lambda item: item[0])
    return "".join(row for _, row in rows), counts


def render(source: Path) -> str:
    report = source.read_text(encoding="utf-8")
    created = created_at(report)
    reviewed = number(report, "Expedientes consultados por API")
    new_docs = number(report, "Documentos nuevos para el sistema")
    published = number(report, "Documentos nuevos publicados en carpeta canónica")
    errors = number(report, "Errores")
    known = number(report, "No disponibles conocidos (no cuentan como error)")
    matters_html, matter_counts = matter_table(created)

    completed = errors == 0 and reviewed is not None
    status_class = "ok" if completed else "attention"
    status_title = "REVISIÓN COMPLETADA" if completed else "REVISAR EL RESULTADO"
    status_text = (
        "La consulta terminó sin errores técnicos informados."
        if completed
        else "La corrida informó errores o no contiene un resumen completo."
    )
    date_text = created.strftime("%d/%m/%Y a las %H:%M") if created else "Fecha no disponible"

    def card(label: str, amount: int | None, explanation: str) -> str:
        shown = "—" if amount is None else str(amount)
        return f"""<article class="card"><div class="amount">{shown}</div>
        <div class="label">{html.escape(label)}</div><div class="hint">{html.escape(explanation)}</div></article>"""

    cards = "".join(
        [
            card("Expedientes revisados", reviewed, "Consultados automáticamente en PJN"),
            card("Novedades detectadas", new_docs, "Documentos que el sistema no conocía"),
            card("Documentos incorporados", published, "Copiados a carpetas habilitadas"),
            card("Errores", errors, "Problemas que requieren atención"),
        ]
    )
    known_note = "" if not known else f"<p class='note'>{known} elemento(s) conocido(s) no disponible(s) en PJN; no se cuentan como error.</p>"
    technical = html.escape(report)
    generated = datetime.now().strftime("%d/%m/%Y %H:%M")

    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PJN - Último resultado</title>
<style>
:root{{--ink:#18324a;--muted:#5e6c78;--ok:#167447;--okbg:#e9f7ef;--warn:#9a4d00;--warnbg:#fff3df;--line:#dbe3e9;--bg:#f4f7f9}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font-family:Segoe UI,Arial,sans-serif;font-size:20px;line-height:1.45}}
main{{max-width:1050px;margin:0 auto;padding:36px 24px 60px}} h1{{font-size:38px;margin:0 0 8px}} .date{{color:var(--muted);margin:0 0 26px}}
.status{{border-radius:16px;padding:24px 28px;margin-bottom:28px;border:2px solid}} .status.ok{{background:var(--okbg);border-color:#65ad87}} .status.attention{{background:var(--warnbg);border-color:#d79b50}}
.status strong{{display:block;font-size:30px;color:var(--ok)}} .status.attention strong{{color:var(--warn)}}
.cards{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}} .card{{background:white;border:1px solid var(--line);border-radius:14px;padding:22px}}
.amount{{font-size:46px;font-weight:750;line-height:1}} .label{{font-size:22px;font-weight:700;margin-top:10px}} .hint{{color:var(--muted);font-size:17px;margin-top:4px}}
.notice{{margin-top:28px;background:white;border-left:6px solid #527da3;padding:18px 22px;border-radius:8px}} .note{{font-size:17px;color:var(--muted)}}
details{{margin-top:30px;background:white;border:1px solid var(--line);border-radius:12px;padding:18px}} summary{{cursor:pointer;font-weight:700}}
pre{{white-space:pre-wrap;word-break:break-word;font:15px/1.45 Consolas,monospace;color:#354b5c}} footer{{margin-top:24px;color:var(--muted);font-size:15px}}
.tabs{{display:flex;gap:10px;margin:22px 0}} .tab-button{{border:1px solid #9fb2c1;background:white;color:var(--ink);padding:13px 20px;border-radius:10px;font-size:18px;font-weight:700;cursor:pointer}}
.tab-button.active{{background:var(--ink);color:white}} .tab-panel{{display:none}} .tab-panel.active{{display:block}}
.matter-summary{{background:white;border:1px solid var(--line);padding:15px 18px;border-radius:12px;margin-bottom:16px;font-size:17px}}
#matter-search{{width:100%;padding:15px 18px;border:2px solid #aebdca;border-radius:10px;font-size:19px;margin-bottom:18px}}
.matter{{background:white;border:1px solid var(--line);border-left:7px solid #66849a;border-radius:12px;padding:18px 20px;margin:12px 0}} .matter.new{{border-left-color:#167447}} .matter.error{{border-left-color:#bd421e}} .matter.pending{{border-left-color:#d39332}}
.matter-head{{display:flex;gap:11px;align-items:flex-start}} .matter strong{{display:block;font-size:19px}} .matter small{{display:block;color:var(--muted);font-size:15px;margin-top:3px}} .matter p{{margin:11px 0 0 25px;font-size:17px}}
.dot{{width:14px;height:14px;background:#66849a;border-radius:50%;margin-top:7px;flex:0 0 auto}} .new .dot{{background:#167447}} .error .dot{{background:#bd421e}} .pending .dot{{background:#d39332}}
@media(max-width:700px){{.cards{{grid-template-columns:1fr}} h1{{font-size:31px}} body{{font-size:18px}}}}
</style></head><body><main>
<h1>Resultado de la revisión PJN</h1><p class="date">Última corrida: {html.escape(date_text)}</p>
<nav class="tabs"><button class="tab-button active" onclick="showTab('summary',this)">Resumen</button><button class="tab-button" onclick="showTab('matters',this)">Expediente por expediente</button></nav>
<section id="summary" class="tab-panel active">
<section class="status {status_class}"><strong>{status_title}</strong>{html.escape(status_text)}</section>
<section class="cards">{cards}</section>{known_note}
<section class="notice"><strong>Importante</strong><br>Este control es una ayuda operativa. Antes de calcular plazos o tomar una decisión procesal, verificar la actuación directamente en PJN.</section>
<details><summary>Ver detalle técnico completo</summary><pre>{technical}</pre></details>
</section>
<section id="matters" class="tab-panel"><div class="matter-summary"><strong>Lectura de la última corrida:</strong> {matter_counts['new']} con novedades · {matter_counts['ok']} sin novedades · {matter_counts['error']} con error · {matter_counts['pending']} pendientes/no revisados.</div>
<input id="matter-search" type="search" placeholder="Buscar por cliente, carátula o número de expediente..." oninput="filterMatters(this.value)">
<div id="matter-list">{matters_html}</div></section>
<footer>Vista generada automáticamente el {generated}. Fuente: {html.escape(source.name)}.</footer>
<script>
function showTab(id,button){{document.querySelectorAll('.tab-panel').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.tab-button').forEach(x=>x.classList.remove('active'));document.getElementById(id).classList.add('active');button.classList.add('active')}}
function filterMatters(query){{query=query.toLocaleLowerCase('es');document.querySelectorAll('.matter').forEach(x=>x.style.display=x.dataset.search.includes(query)?'block':'none')}}
if(location.hash==='#matters'){{showTab('matters',document.querySelectorAll('.tab-button')[1])}}
</script>
</main></body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser()
    reports = vault_root() / "09-reviews" / "pjn"
    parser.add_argument("--source", type=Path, default=reports / "ULTIMA-CORRIDA.md")
    parser.add_argument("--output", type=Path, default=reports / "ULTIMO-RESULTADO.html")
    args = parser.parse_args()
    if not args.source.exists():
        raise SystemExit(f"No existe el informe fuente: {args.source}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(render(args.source), encoding="utf-8")
    temporary.replace(args.output)
    print(args.output)


if __name__ == "__main__":
    main()
