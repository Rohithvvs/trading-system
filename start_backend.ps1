$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvCandidates = @(
  (Join-Path $repoRoot "backend\venv\Scripts\python.exe"),
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

# Load repo-root .env into this process so keys like SCHEDULER_SECRET are available
# to routes that read os.environ (not only pydantic Settings fields).
$envFile = Join-Path $repoRoot ".env"
if (Test-Path $envFile) {
  Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#")) { return }
    $eq = $line.IndexOf("=")
    if ($eq -lt 1) { return }
    $key = $line.Substring(0, $eq).Trim()
    $val = $line.Substring($eq + 1).Trim()
    if (($val.StartsWith('"') -and $val.EndsWith('"')) -or ($val.StartsWith("'") -and $val.EndsWith("'"))) {
      $val = $val.Substring(1, $val.Length - 2)
    }
    if (-not [string]::IsNullOrWhiteSpace($key) -and -not (Test-Path "Env:$key")) {
      Set-Item -Path "Env:$key" -Value $val
    }
  }
  Write-Host "Loaded environment variables from $envFile"
} else {
  Write-Host "WARNING: .env not found at $envFile"
}

Write-Host "Starting backend on http://127.0.0.1:$port"
Write-Host "Using Python interpreter: $pythonExe"
Set-Location (Join-Path $repoRoot "backend")
$uvicornArgs = @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", $port)
if ($enableReload) {
  Write-Host "APP_ENABLE_RELOAD=true detected; enabling uvicorn auto-reload"
  $uvicornArgs += "--reload"
}

& $pythonExe @uvicornArgs
