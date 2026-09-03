#!/usr/bin/env python3
"""Diagnostico: que extractor de texto de PDF hay disponible en esta PC."""
from __future__ import annotations
import shutil

print("== Diagnostico de extraccion de texto de PDFs ==\n")

pdftotext = shutil.which("pdftotext")
if pdftotext:
    print(f"[OK]  pdftotext instalado: {pdftotext}")
else:
    print("[--]  pdftotext NO instalado (opcional).")

try:
    import pypdf  # noqa: F401
    print(f"[OK]  pypdf instalado (version {pypdf.__version__}) - extractor de respaldo listo.")
    have_py = True
except Exception as exc:  # noqa: BLE001
    print(f"[!!]  pypdf NO disponible: {exc}")
    have_py = False

print()
if pdftotext or have_py:
    engine = "pdftotext" if pdftotext else "pypdf"
    print(f"RESULTADO: la extraccion de texto FUNCIONA (motor: {engine}).")
    print("El agente de alertas procesales va a poder leer los despachos.")
else:
    print("RESULTADO: NO hay extractor de texto disponible.")
    print("Corré el lanzador 'PJN - Reparar componentes tecnicos' para instalar pypdf.")
