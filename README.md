# Segundo Cerebro Para Estudios Juridicos

Plantilla portable para organizar la operacion de un estudio juridico con archivos Markdown, Obsidian y agentes de IA. Se adapta a estudios que trabajan con carpetas, unidades compartidas, Dropbox, OneDrive o exportaciones de sistemas de gestion como LexDoctor.

El repositorio contiene solamente estructura, instrucciones, esquemas, herramientas y datos sinteticos. Los datos vivos de clientes y expedientes se mantienen fuera de Git mediante reglas de exclusion.

## Principios

- Una fuente de verdad declarada para cada tipo de dato.
- Una carpeta canonica por asunto, aunque existan alias o ubicaciones historicas.
- Borradores separados de documentos aprobados.
- Vencimientos confirmados solamente contra una fuente oficial.
- Acciones externas y juridicas bajo aprobacion humana.
- Integraciones en staging y `dry-run` antes de modificar registros canonicos.
- Compatibilidad con Claude mediante `CLAUDE.md` y con Codex/otros agentes mediante `AGENTS.md`.

## Estructura

| Ruta | Proposito |
|---|---|
| `00-inbox/` | Capturas pendientes de clasificar. |
| `01-clients/` | Registros vivos de clientes; ignorados por Git. |
| `02-matters/` | Registros vivos de asuntos; ignorados por Git. |
| `03-operations/` | Procedimientos, plantillas y herramientas. |
| `04-sales/` | Consultas y propuestas; ignoradas por Git. |
| `05-marketing/` | Contenido y aprendizajes no confidenciales. |
| `06-finance/` | Finanzas; ignoradas por Git. |
| `07-knowledge/` | Criterios internos autorizados y material reusable. |
| `08-context/` | Politicas, configuracion y registros estructurales. |
| `09-reviews/` | Agendas y revisiones; ignoradas por Git. |
| `10-outputs/` | Borradores generados; ignorados por Git. |
| `docs/` | Arquitectura, adaptacion e integraciones. |
| `tools/` | Utilidades locales sin dependencias externas. |

## Inicio Rapido

1. Clonar el repositorio en una ubicacion privada.
2. Leer `EMPEZAR-ACA.md`.
3. Copiar `config/workspace.example.json` a `config/workspace.local.json`.
4. Completar `08-context/source-of-truth.md` y `08-context/business-profile.md`.
5. Ejecutar la validacion:

```powershell
python tools/validate_workspace.py --root .
```

6. Importar o registrar asuntos primero en modo simulacion.

## Modos De Adopcion

- **Carpetas existentes:** registrar cada carpeta actual y resolver duplicados sin mover archivos inicialmente.
- **Estructura nueva:** crear carpetas canonicas desde el registro de asuntos.
- **LexDoctor:** importar un CSV exportado por el usuario mediante un mapa configurable de columnas.
- **PJN:** usar la integracion opcional en `integrations/pjn/`, con sesiones locales fuera de Git y modo simulacion predeterminado.
- **Otros portales:** implementar un adaptador autorizado que genere eventos normalizados en staging.

Consultar [arquitectura](docs/architecture.md), [carpeta canonica](docs/canonical-folder.md), [adaptacion](docs/adapting-an-office.md), [LexDoctor](docs/lexdoctor.md) y [PJN](docs/pjn.md).

## Seguridad

No ingresar datos reales en issues, PR, fixtures o ejemplos. Antes de publicar cambios, ejecutar:

```powershell
python tools/privacy_scan.py --root .
```

La herramienta detecta categorias de riesgo, pero no reemplaza una revision humana. Ver `SECURITY.md`.

## Alcance

Este proyecto organiza informacion y asiste la operacion. No sustituye la revision profesional, un sistema de gestion homologado, una agenda oficial ni las fuentes judiciales.

