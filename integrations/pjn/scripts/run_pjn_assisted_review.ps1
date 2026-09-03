param(
  [int]$LoginTimeoutSec = 600,
  [switch]$NoPdf,
  [switch]$Apply,
  [string]$PythonCommand = "python"
)

$ErrorActionPreference = "Stop"
$mutex = New-Object System.Threading.Mutex($false, "Global\PJNAssistedReviewCEREBRO")
$hasLock = $false

try {
  $hasLock = $mutex.WaitOne(0)
  if (-not $hasLock) {
    Write-Host "Ya hay una revision PJN en curso. No se iniciara una segunda instancia."
    exit 0
  }

$BrainRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\..")).Path
$TokenScript = Join-Path $PSScriptRoot "pjn_browser_token.py"
$ReviewWrapper = Join-Path $PSScriptRoot "run_pjn_daily_review.ps1"

Set-Location -LiteralPath $BrainRoot
$env:PJN_BEARER_TOKEN = $null

Write-Host "============================================================"
Write-Host "PJN - Revision semiautomatica"
Write-Host "============================================================"
Write-Host "Se abrira el Portal PJN. Inicia sesion con tus credenciales."
Write-Host "Cuando el portal termine de cargar, la revision continuara sola."
Write-Host "No cierres esta ventana ni la ventana del navegador."
Write-Host ""

& $PythonCommand $TokenScript --headed --force-browser --timeout-sec $LoginTimeoutSec --min-ttl-sec 300
if ($LASTEXITCODE -ne 0) {
  Write-Error "No se obtuvo una sesion PJN valida. La revision no se ejecuto."
  exit $LASTEXITCODE
}

Write-Host "Sesion PJN valida. Iniciando revision automatica de expedientes..."
Write-Host "La consulta se realizara por la API del PJN."
Write-Host "Los expedientes que requieran SCW quedaran indicados para revision manual; no se abrira un segundo navegador."
& $ReviewWrapper -NoHeaded -NoPdf:$NoPdf -Apply:$Apply -PythonCommand $PythonCommand
if ($LASTEXITCODE -ne 0) {
  Write-Error "La revision PJN fallo con codigo $LASTEXITCODE."
  exit $LASTEXITCODE
}

Write-Host "Revision PJN completada. Ya podes cerrar esta ventana."
exit 0
}
finally {
  if ($hasLock) {
    $mutex.ReleaseMutex()
  }
  $mutex.Dispose()
}
