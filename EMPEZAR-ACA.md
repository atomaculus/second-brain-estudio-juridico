# Empezar Aca

## Configuracion Inicial

1. Definir responsables y alcance en `08-context/business-profile.md`.
2. Declarar las fuentes de verdad en `08-context/source-of-truth.md`.
3. Copiar y completar `config/workspace.example.json` como `config/workspace.local.json`.
4. Elegir una estrategia de adopcion en `docs/adapting-an-office.md`.
5. Validar la instalacion con `python tools/validate_workspace.py --root .`.

## Rutina Operativa

1. Procesar `00-inbox/`.
2. Revisar asuntos activos en `02-matters/`.
3. Verificar vencimientos contra su fuente oficial.
4. Actualizar proxima accion, responsable y bloqueos.
5. Preparar la agenda o revision en `09-reviews/`.
6. Mantener los borradores en `10-outputs/` hasta su aprobacion.

## Regla De Migracion

Durante la adopcion, registrar primero la estructura existente. No mover ni renombrar carpetas masivamente hasta que los responsables validen el mapa de carpetas canonicas.

