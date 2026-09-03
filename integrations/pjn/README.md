# Integracion PJN

Modulo portable para consultar actuaciones del Portal PJN, descargar documentos autorizados y dejar resultados en staging. Incluye una ruta API y un fallback asistido mediante navegador para SCW.

## Limites de seguridad

- Las consultas API admitidas son de lectura sobre expedientes y despachos.
- El codigo bloquea endpoints de notificaciones que puedan marcar una lectura.
- El modo predeterminado es simulacion: consulta y genera reportes locales, pero no publica documentos ni actualiza el registro.
- `--apply` o `-Apply` debe indicarse expresamente para escribir estado, actualizar el registro o publicar PDFs.
- Tokens, perfiles, corridas, estados y logs quedan fuera de Git.
- Los vencimientos y efectos procesales siempre requieren verificacion humana en la fuente oficial.

## Requisitos

- Windows y PowerShell para los wrappers asistidos.
- Python 3.11 o posterior.
- Node.js 20 o posterior para Playwright.

Desde la raiz del repositorio:

```powershell
integrations\pjn\scripts\setup_pjn_local.ps1
```

En Windows tambien puede ejecutarse con doble clic el instalador portable:

```text
integrations\pjn\INSTALAR PJN EN ESTA PC.bat
```

Comprueba o instala los requisitos, prepara Playwright fuera del repositorio,
ejecuta pruebas y crea accesos directos para iniciar la revision, ver el ultimo
resultado y reparar componentes. No registra tareas programadas.

La sesion, dependencias, corridas crudas y logs se guardan por defecto fuera del
repositorio en `%LOCALAPPDATA%\SegundoCerebroJuridico\PJN`. Puede cambiarse con
`PJN_LOCAL_STATE_DIR`.

## Configuracion

Crear `08-context/registries/matter-registry.json` a partir del archivo de ejemplo. Para cada asunto habilitado, completar los campos PJN y mantener inicialmente:

```json
{
  "matterId": "matter-local-001",
  "fuero": "CIV",
  "numero": 1,
  "anio": 2099,
  "pjnExpedienteId": 999999999,
  "pjnSync": {"enabled": true},
  "publishPjnDownloads": false
}
```

Configurar localmente los apellidos o identificadores del propio estudio:

```powershell
$env:PJN_OWN_NAMES = "APELLIDO1;APELLIDO2"
```

No guardar ese valor ni tokens en archivos rastreados por Git.

## Uso seguro

Primera autenticacion y revision en modo simulacion:

```powershell
integrations\pjn\scripts\run_pjn_assisted_review.ps1 -NoPdf
```

Revision de un solo asunto sin publicar cambios:

```powershell
integrations\pjn\scripts\run_pjn_daily_review.ps1 -MatterId matter-local-001 -NoPdf
```

Despues de revisar configuracion y resultados, habilitar escrituras expresamente:

```powershell
integrations\pjn\scripts\run_pjn_assisted_review.ps1 -Apply
```

Las corridas crudas quedan en el almacenamiento local de cada PC. El informe
legible continúa en `09-reviews/pjn/` y puede abrirse con el acceso directo
`PJN - Ver ultimo resultado`. No copiar `runs`, tokens o perfiles entre PCs.

## Pruebas

```powershell
python -m unittest discover -s integrations/pjn/tests -v
python tools/privacy_scan.py --root .
```

La integracion depende de interfaces y comportamiento de terceros que pueden cambiar. Debe probarse en modo simulacion antes de cada despliegue.

