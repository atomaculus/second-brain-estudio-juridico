# Carpeta Canonica

## Concepto

La carpeta canonica es la ubicacion declarada como destino principal de los documentos de un asunto. Puede haber accesos historicos, aliases o carpetas duplicadas, pero solo una ubicacion se considera canonica.

El registro no obliga a reorganizar el servidor. Primero describe la realidad; los movimientos se realizan despues, en lotes pequenos y con aprobacion.

## Registro Minimo

```json
{
  "matterId": "matter-demo-001",
  "displayName": "Persona Ejemplo c/ Empresa Demo",
  "canonicalFolder": "D:/Estudio/Asuntos/DEMO-001",
  "folderAliases": ["D:/Estudio/Historico/DEMO-001"],
  "sourceSystem": "filesystem",
  "externalIds": {"filesystem": "DEMO-001"},
  "status": "active",
  "confirmed": false
}
```

## Reglas

- Una carpeta canonica por `matterId`.
- Una carpeta no puede ser canonica para dos asuntos distintos.
- Las rutas deben estar debajo de una raiz autorizada.
- `confirmed=false` hasta que una persona valide el mapeo.
- Los aliases nunca se eliminan automaticamente.
- Crear o mover carpetas requiere una operacion separada del descubrimiento.

## Flujo De Adopcion

1. Inventariar carpetas sin modificarlas.
2. Proponer coincidencias por numero, cliente o referencia externa.
3. Revisar colisiones y casos ambiguos.
4. Confirmar la carpeta canonica.
5. Recién entonces planificar movimientos o accesos directos.

La utilidad `tools/canonical_folders.py` valida y resuelve el registro; no mueve documentos.

