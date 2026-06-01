$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvCandidates = @(
  (Join-Path $repoRoot ".venv313\Scripts\python.exe"),
  (Join-Path $repoRoot ".venv\Scripts\python.exe"),
  (Join-Path $repoRoot "venv\Scripts\python.exe")
)

$pythonExe = $venvCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $pythonExe) {
  $searched = $venvCandidates -join ", "
  throw "Python virtualenv not found. Checked: $searched"
}

function Get-ListeningPids([int]$port) {
  $matches = netstat -ano | Select-String ":$port\s+.*LISTENING\s+(\d+)$"
  $pids = @()
  foreach ($match in $matches) {
    $pidText = [regex]::Match($match.Line, "LISTENING\s+(\d+)$").Groups[1].Value
    if ($pidText) {
      $pids += [int]$pidText
    }
  }
  return $pids | Select-Object -Unique
}

$port = 8000
$enableReload = $env:APP_ENABLE_RELOAD -eq "true"
$existingPids = @(Get-ListeningPids -port $port)
if ($existingPids.Count -gt 0) {
  Write-Host "Port $port already in use by PID(s): $($existingPids -join ', '). Stopping them..."
  foreach ($existingPid in $existingPids) {
    Stop-Process -Id $existingPid -Force -ErrorAction SilentlyContinue
  }
  Start-Sleep -Seconds 1
}

Write-Host "Starting backend on http://127.0.0.1:$port"
Write-Host "Using Python interpreter: $pythonExe"
Set-Location $repoRoot
$uvicornArgs = @("-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", $port)
if ($enableReload) {
  Write-Host "APP_ENABLE_RELOAD=true detected; enabling uvicorn auto-reload"
  $uvicornArgs += "--reload"
}

& $pythonExe @uvicornArgs
