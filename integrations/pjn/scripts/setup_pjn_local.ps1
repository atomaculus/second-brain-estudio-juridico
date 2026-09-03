param(
  [switch]$SkipBrowserInstall
)

$ErrorActionPreference = "Stop"

$LabRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$SourceNodeTools = Join-Path $LabRoot "node-tools"
$SourcePackageJson = Join-Path $SourceNodeTools "package.json"
$SourcePackageLock = Join-Path $SourceNodeTools "package-lock.json"
$LocalBase = if ($env:PJN_LOCAL_STATE_DIR) {
  [Environment]::ExpandEnvironmentVariables($env:PJN_LOCAL_STATE_DIR)
} else {
  Join-Path $env:LOCALAPPDATA "SegundoCerebroJuridico\PJN"
}
$NodeTools = Join-Path $LocalBase "node-tools"

function Require-Command {
  param([string]$Name)
  $command = Get-Command $Name -ErrorAction SilentlyContinue
  if (-not $command) {
    throw "No se encontro '$Name' en PATH. Instalalo antes de continuar."
  }
  return $command.Source
}

$python = Require-Command "python"
$node = Require-Command "node"
$npm = Require-Command "npm.cmd"

Write-Host "Python: $python"
& $python --version
Write-Host "Node: $node"
& $node --version

# Extractor de texto de PDFs en Python (fallback si no esta pdftotext).
Write-Host "Instalando pypdf (extractor de texto de respaldo)..."
& $python -m pip install --user --upgrade pypdf
if ($LASTEXITCODE -ne 0) {
  Write-Host "Aviso: no se pudo instalar pypdf automaticamente. El sistema intentara usar pdftotext si esta disponible."
}
$hasPdftotext = Get-Command pdftotext -ErrorAction SilentlyContinue
if ($hasPdftotext) {
  Write-Host "pdftotext encontrado en: $($hasPdftotext.Source)"
} else {
  Write-Host "pdftotext no esta instalado. Se usara el extractor Python (pypdf). Opcional: instalar Poppler para mejor calidad."
}

if (-not (Test-Path -LiteralPath $SourcePackageJson) -or -not (Test-Path -LiteralPath $SourcePackageLock)) {
  throw "Faltan los manifiestos Node; no se puede hacer una instalacion reproducible."
}

New-Item -ItemType Directory -Force -Path $NodeTools | Out-Null
Copy-Item -LiteralPath $SourcePackageJson -Destination (Join-Path $NodeTools "package.json") -Force
Copy-Item -LiteralPath $SourcePackageLock -Destination (Join-Path $NodeTools "package-lock.json") -Force

Push-Location -LiteralPath $NodeTools
try {
  Write-Host "Instalando dependencias Node declaradas en package-lock.json..."
  & $npm ci
  if ($LASTEXITCODE -ne 0) {
    throw "npm ci fallo con codigo $LASTEXITCODE"
  }

  if (-not $SkipBrowserInstall) {
    $npx = Require-Command "npx.cmd"
    Write-Host "Instalando Chromium para Playwright..."
    & $npx playwright install chromium
    if ($LASTEXITCODE -ne 0) {
      throw "playwright install chromium fallo con codigo $LASTEXITCODE"
    }
  }
}
finally {
  Pop-Location
}

Write-Host "Instalacion local PJN completada."
Write-Host "Dependencias Node locales: $NodeTools"
Write-Host "Playwright de Python es opcional: el capturador usa el fallback Node instalado."
