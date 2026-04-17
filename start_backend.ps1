$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
  throw "Python virtualenv not found at $pythonExe"
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
$existingPids = @(Get-ListeningPids -port $port)
if ($existingPids.Count -gt 0) {
  Write-Host "Port $port already in use by PID(s): $($existingPids -join ', '). Stopping them..."
  foreach ($existingPid in $existingPids) {
    Stop-Process -Id $existingPid -Force -ErrorAction SilentlyContinue
  }
  Start-Sleep -Seconds 1
}

Write-Host "Starting backend on http://127.0.0.1:$port with --reload"
Set-Location $repoRoot
& $pythonExe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port $port
