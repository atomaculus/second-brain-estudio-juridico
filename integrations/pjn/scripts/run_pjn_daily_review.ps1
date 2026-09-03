param(
  [switch]$Headed,
  [switch]$NoHeaded,
  [switch]$NoPdf,
  [switch]$Apply,
  [switch]$SkipResolveIds,
  [switch]$SkipApi,
  [string]$MatterId,
  [switch]$ScwFallback,
  [switch]$ScwAssistedLogin,
  [int]$ScwTimeoutSec = 180,
  [switch]$ScwKeepOpenOnError,
  [int]$ScwErrorPauseSec = 180,
  [string]$PythonCommand = "python"
)

$ErrorActionPreference = "Stop"

$BrainRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\..")).Path
$ScriptPath = Join-Path $PSScriptRoot "pjn_daily_review.py"
$LocalBase = if ($env:PJN_LOCAL_STATE_DIR) { [Environment]::ExpandEnvironmentVariables($env:PJN_LOCAL_STATE_DIR) } else { Join-Path $env:LOCALAPPDATA "SegundoCerebroJuridico\PJN" }
$LogDir = Join-Path $LocalBase "logs"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logPath = Join-Path $LogDir "pjn-daily-review-$timestamp.log"

Start-Transcript -Path $logPath -Append | Out-Null
try {
  Set-Location -LiteralPath $BrainRoot
  $env:PJN_BEARER_TOKEN = $null

  $argsList = @($ScriptPath)
  if ($Headed -and -not $NoHeaded) {
    $argsList += "--headed"
  }
  if ($NoPdf) {
    $argsList += "--no-pdf"
  }
  if ($Apply) {
    $argsList += "--apply"
  }
  if ($SkipResolveIds) {
    $argsList += "--skip-resolve-ids"
  }
  if ($SkipApi) {
    $argsList += "--skip-api"
  }
  if ($MatterId) {
    $argsList += "--matter-id"
    $argsList += $MatterId
  }
  if ($ScwFallback) {
    $argsList += "--scw-fallback"
    $argsList += "--scw-timeout-sec"
    $argsList += "$ScwTimeoutSec"
    if ($ScwKeepOpenOnError) {
      $argsList += "--scw-keep-open-on-error"
      $argsList += "--scw-error-pause-sec"
      $argsList += "$ScwErrorPauseSec"
    }
    if ($ScwAssistedLogin) {
      $argsList += "--scw-assisted-login"
    }
  }

  Write-Host "PJN daily review started at $(Get-Date -Format s)"
  Write-Host "Working directory: $BrainRoot"
  Write-Host "Command: $PythonCommand $($argsList -join ' ')"

  & $PythonCommand @argsList
  $exitCode = $LASTEXITCODE
  if ($exitCode -ne 0) {
    throw "pjn_daily_review.py failed with exit code $exitCode"
  }

  Write-Host "PJN daily review finished at $(Get-Date -Format s)"

  try {
    $friendlyReportScript = Join-Path $PSScriptRoot "pjn_friendly_report.py"
    Write-Host "Generando vista simple del ultimo resultado..."
    & $PythonCommand $friendlyReportScript
  }
  catch {
    Write-Host "Generacion de vista simple fallo (no fatal): $_"
  }

}
finally {
  Stop-Transcript | Out-Null
}
