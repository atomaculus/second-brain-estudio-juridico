# Adaptar Un Estudio Existente

## Fase 1: Descubrimiento

- Identificar sistemas y responsables.
- Declarar fuentes de verdad.
- Inventariar carpetas y formatos de nombres.
- Separar datos vivos, modelos, archivos historicos y temporales.
- No mover ni duplicar documentos durante esta fase.

Generar un inventario de solo lectura:

```powershell
python tools/inventory_folders.py `
  --root D:\Estudio\Asuntos `
  --max-depth 2 `
  --out 00-inbox\integrations\folder-inventory.json
```

## Fase 2: Piloto

Elegir entre tres y cinco asuntos no urgentes. Crear sus registros, mapear carpetas canonicas y comprobar que las personas pueden encontrarlos por cliente, expediente y sistema externo.

## Fase 3: Integraciones

Configurar importaciones en `dry-run`. Comparar resultados con la fuente. Los conflictos se resuelven manualmente; nunca se elige una fuente por silencio.

## Fase 4: Operacion

Incorporar agenda diaria, revision semanal y control de vencimientos. Definir expresamente qué sistema confirma cada fecha.

## Variantes De Estructura

- **Una carpeta por cliente:** cada asunto apunta a una subcarpeta o comparte carpeta canonica con una referencia documental explicita.
- **Una carpeta por expediente:** mapeo directo entre asunto y carpeta.
- **Carpetas por año/fuero:** el registro abstrae la ubicacion fisica.
- **LexDoctor como sistema central:** LexDoctor conserva los datos canonicos y el vault almacena contexto operativo y enlaces.

## Criterio De Exito

Una persona nueva debe poder identificar fuente, responsable, carpeta canonica, proxima accion y vencimiento verificado sin depender del nombre informal de una carpeta.

