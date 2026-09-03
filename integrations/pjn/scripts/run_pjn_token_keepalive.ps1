param(
  [int]$IntervalSeconds = 600,
  [switch]$HeadedOnMissing,
  [switch]$Once,
  [string]$PythonCommand = "python"
)

$ErrorActionPreference = "Stop"

$mutexName = "Global\PJNTokenKeepalive00CEREBRO"
$mutex = New-Object System.Threading.Mutex($false, $mutexName)
$hasLock = $false

$BrainRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\..")).Path
$ScriptPath = Join-Path $PSScriptRoot "pjn_browser_token.py"
$LogDir = Join-Path $BrainRoot "integrations\pjn\logs"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logPath = Join-Path $LogDir "pjn-token-keepalive-$timestamp.log"

Start-Transcript -Path $logPath -Append | Out-Null
try {
  $hasLock = $mutex.WaitOne(0)
  if (-not $hasLock) {
    Write-Host "Another PJN token keepalive instance is already running. Exiting."
    exit 0
  }

  Set-Location -LiteralPath $BrainRoot
  $env:PJN_BEARER_TOKEN = $null

  Write-Host "PJN token keepalive started at $(Get-Date -Format s)"
  Write-Host "Working directory: $BrainRoot"
  Write-Host "Interval seconds: $IntervalSeconds"

  & $PythonCommand $ScriptPath --refresh-only --min-ttl-sec 400
  if ($LASTEXITCODE -ne 0) {
    if (-not $HeadedOnMissing) {
      throw "No refreshable PJN token available and HeadedOnMissing was not set"
    }
    Write-Host "No refreshable token available. Opening Portal PJN for assisted login."
    & $PythonCommand $ScriptPath --headed --force-browser --timeout-sec 300 --min-ttl-sec 60
    $loginExitCode = $LASTEXITCODE
    if ($loginExitCode -ne 0) {
      throw "PJN headed login failed with exit code $loginExitCode"
    }
  }

  if ($Once) {
    Write-Host "PJN token refresh completed at $(Get-Date -Format s)"
    exit 0
  }

  & $PythonCommand $ScriptPath --watch --watch-interval-sec $IntervalSeconds --min-ttl-sec 400
  $exitCode = $LASTEXITCODE
  if ($exitCode -ne 0) {
    throw "pjn_browser_token.py keepalive failed with exit code $exitCode"
  }
}
finally {
  if ($hasLock) {
    $mutex.ReleaseMutex()
  }
  $mutex.Dispose()
  Stop-Transcript | Out-Null
}
