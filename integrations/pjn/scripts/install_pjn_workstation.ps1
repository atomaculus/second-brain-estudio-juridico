param(
  [switch]$SkipPrerequisiteInstall,
  [switch]$SkipBrowserInstall
)

$ErrorActionPreference = "Stop"

$PjnRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$VaultRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\..")).Path
$LauncherDir = Join-Path $PjnRoot "launchers"
$SetupScript = Join-Path $PSScriptRoot "setup_pjn_local.ps1"
$StartLauncher = Join-Path $LauncherDir "PJN - Iniciar sesion y revision.bat"
$ResultLauncher = Join-Path $LauncherDir "PJN - Ver ultimo resultado.bat"
$RepairLauncher = Join-Path $LauncherDir "PJN - Reparar componentes tecnicos.bat"
$TestDir = Join-Path $PjnRoot "tests"

$LocalBase = if ($env:PJN_LOCAL_STATE_DIR) {
  [Environment]::ExpandEnvironmentVariables($env:PJN_LOCAL_STATE_DIR)
} else {
  Join-Path $env:LOCALAPPDATA "SegundoCerebroJuridico\PJN"
}
$InstallerLogDir = Join-Path $LocalBase "installer-logs"
New-Item -ItemType Directory -Force -Path $InstallerLogDir | Out-Null
$InstallerLog = Join-Path $InstallerLogDir ("install-{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss"))

function Refresh-ProcessPath {
  $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
  $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
  $env:Path = "$machinePath;$userPath"
}

function Test-CommandWorks {
  param(
    [Parameter(Mandatory)][string]$Name,
    [string[]]$Arguments = @("--version")
  )
  $command = Get-Command $Name -ErrorAction SilentlyContinue
  if (-not $command) {
    return $false
  }
  try {
    & $command.Source @Arguments *> $null
    return $LASTEXITCODE -eq 0
  }
  catch {
    return $false
  }
}

function Install-Prerequisite {
  param(
    [Parameter(Mandatory)][string]$PackageId,
    [Parameter(Mandatory)][string]$DisplayName
  )
  if ($SkipPrerequisiteInstall) {
    throw "Falta $DisplayName. Instalalo y volve a ejecutar el instalador."
  }
  $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
  if (-not $winget) {
    throw "Falta $DisplayName y Windows Package Manager (winget) no esta disponible. Instalalo manualmente y volve a intentar."
  }
  Write-Host "Instalando $DisplayName..."
  & $winget.Source install --id $PackageId --exact --source winget --accept-package-agreements --accept-source-agreements --silent --disable-interactivity
  if ($LASTEXITCODE -ne 0) {
    throw "No se pudo instalar $DisplayName (codigo $LASTEXITCODE)."
  }
  Refresh-ProcessPath
}

function New-DesktopShortcut {
  param(
    [Parameter(Mandatory)][string]$Name,
    [Parameter(Mandatory)][string]$BatchPath,
    [Parameter(Mandatory)][string]$Description
  )
  $desktop = [Environment]::GetFolderPath("Desktop")
  $shortcutPath = Join-Path $desktop "$Name.lnk"
  $shell = New-Object -ComObject WScript.Shell
  $shortcut = $shell.CreateShortcut($shortcutPath)
  $shortcut.TargetPath = $env:ComSpec
  $shortcut.Arguments = "/c `"`"$BatchPath`"`""
  $shortcut.WorkingDirectory = $LauncherDir
  $shortcut.Description = $Description
  $shortcut.Save()
  Write-Host "Acceso directo creado: $shortcutPath"
}

Start-Transcript -Path $InstallerLog -Append | Out-Null
try {
  Write-Host "============================================================"
  Write-Host "  PJN - Instalacion de esta PC"
  Write-Host "============================================================"
  Write-Host "Vault sincronizado: $VaultRoot"
  Write-Host "Estado y credenciales locales: $LocalBase"
  Write-Host "Dependencias Node locales: $(Join-Path $LocalBase 'node-tools')"
  Write-Host "No se instalaran ni modificaran tareas programadas."

  foreach ($requiredPath in @($SetupScript, $StartLauncher, $ResultLauncher, $RepairLauncher, (Join-Path $PjnRoot "node-tools\package-lock.json"))) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
      throw "Falta un archivo sincronizado requerido: $requiredPath"
    }
  }

  if (-not (Test-CommandWorks -Name "python")) {
    Install-Prerequisite -PackageId "Python.Python.3.12" -DisplayName "Python 3.12"
  }
  if (-not (Test-CommandWorks -Name "node")) {
    Install-Prerequisite -PackageId "OpenJS.NodeJS.LTS" -DisplayName "Node.js LTS"
  }
  Refresh-ProcessPath
  if (-not (Test-CommandWorks -Name "npm.cmd")) {
    throw "Node.js esta instalado pero npm.cmd no esta disponible en PATH. Reinicia Windows y volve a ejecutar el instalador."
  }

  Write-Host "Preparando dependencias locales de PJN..."
  & $SetupScript -SkipBrowserInstall:$SkipBrowserInstall
  if ($LASTEXITCODE -ne 0) {
    throw "La preparacion tecnica de PJN fallo con codigo $LASTEXITCODE."
  }

  Write-Host "Ejecutando verificaciones locales sin conectarse a PJN..."
  & python -m unittest discover -s $TestDir -p "test*.py"
  if ($LASTEXITCODE -ne 0) {
    throw "Las pruebas locales de PJN fallaron."
  }
  Get-ChildItem -LiteralPath $PSScriptRoot -Filter "*.js" | ForEach-Object {
    & node --check $_.FullName
    if ($LASTEXITCODE -ne 0) {
      throw "Fallo la validacion JavaScript: $($_.Name)"
    }
  }

  New-DesktopShortcut -Name "PJN - Iniciar sesion y revision" -BatchPath $StartLauncher -Description "Inicia manualmente la revision PJN del estudio"
  New-DesktopShortcut -Name "PJN - Ver ultimo resultado" -BatchPath $ResultLauncher -Description "Abre el informe de la ultima revision PJN"
  New-DesktopShortcut -Name "PJN - Reparar componentes tecnicos" -BatchPath $RepairLauncher -Description "Reinstala las dependencias locales del revisador PJN"

  Write-Host ""
  Write-Host "INSTALACION COMPLETADA"
  Write-Host "La primera revision pedira iniciar sesion en PJN en esta PC."
  Write-Host "No ejecutes la revision simultaneamente desde otra computadora."
  Write-Host "Registro tecnico local: $InstallerLog"
}
finally {
  Stop-Transcript | Out-Null
}
