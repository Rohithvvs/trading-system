$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Frontend = Join-Path $Root "frontend"
$Artifacts = Join-Path $Root "tests\artifacts"
$BackendLog = Join-Path $Artifacts "e2e-backend.out.log"
$BackendErr = Join-Path $Artifacts "e2e-backend.err.log"
$FrontendLog = Join-Path $Artifacts "e2e-frontend.out.log"
$FrontendErr = Join-Path $Artifacts "e2e-frontend.err.log"
$Python = Join-Path $Root "venv\Scripts\python.exe"
$Npm = "C:\Program Files\nodejs\npm.cmd"
$Npx = "C:\Program Files\nodejs\npx.cmd"

$BackendPort = if ($env:E2E_BACKEND_PORT) { $env:E2E_BACKEND_PORT } else { "8002" }
$FrontendPort = if ($env:E2E_FRONTEND_PORT) { $env:E2E_FRONTEND_PORT } else { "5175" }
$ApiBase = "http://127.0.0.1:$BackendPort"
$BaseUrl = "http://127.0.0.1:$FrontendPort"

New-Item -ItemType Directory -Force -Path $Artifacts | Out-Null

$backendProcess = $null
$frontendProcess = $null

function Wait-ForUrl($Url, $Name) {
  $deadline = (Get-Date).AddSeconds(90)
  do {
    try {
      Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2 | Out-Null
      return
    } catch {
      Start-Sleep -Milliseconds 500
    }
  } while ((Get-Date) -lt $deadline)
  throw "$Name did not become ready at $Url"
}

# Backend health is JSON `{ status: "ok", ... }` - wait for that for deterministic readiness
function Wait-ForBackendReady($Url, $Name, $timeoutSec) {
  if (-not $timeoutSec) { $timeoutSec = 90 }
  $deadline = (Get-Date).AddSeconds($timeoutSec)
  do {
    try {
      $resp = Invoke-RestMethod -Uri $Url -TimeoutSec 2 -ErrorAction Stop
      if ($null -ne $resp -and $resp.status -eq 'ok') {
        return
      }
    } catch {
      # ignore transient failures
    }
    Start-Sleep -Milliseconds 500
  } while ((Get-Date) -lt $deadline)
  throw "$Name did not become ready at $Url within $timeoutSec seconds"
}

try {
  $backendArgs = @(
    "-m", "uvicorn", "backend.app.main:app",
    "--host", "127.0.0.1",
    "--port", $BackendPort
  )
  $backendEnv = @{
    APP_ENV = "test"
    DATABASE_URL = "sqlite:///./tests/artifacts/e2e_app.db"
    NIFTY500_SYMBOLS = "INFY-EQ,TCS-EQ,RELIANCE-EQ"
  }
  foreach ($key in $backendEnv.Keys) {
    [Environment]::SetEnvironmentVariable($key, $backendEnv[$key], "Process")
  }
  $backendProcess = Start-Process -FilePath $Python -ArgumentList $backendArgs -WorkingDirectory $Root -RedirectStandardOutput $BackendLog -RedirectStandardError $BackendErr -WindowStyle Hidden -PassThru
  Wait-ForBackendReady "$ApiBase/health" "Backend" 90

  $env:VITE_API_BASE_URL = $ApiBase
  $frontendProcess = Start-Process -FilePath $Npm -ArgumentList "run", "dev", "--", "--host", "127.0.0.1", "--port", $FrontendPort -WorkingDirectory $Frontend -RedirectStandardOutput $FrontendLog -RedirectStandardError $FrontendErr -WindowStyle Hidden -PassThru
  Wait-ForUrl $BaseUrl "Frontend"

  $env:E2E_API_BASE_URL = $ApiBase
  $env:E2E_BASE_URL = $BaseUrl
  $env:E2E_BACKEND_PORT = $BackendPort
  $env:E2E_FRONTEND_PORT = $FrontendPort
  $env:PLAYWRIGHT_SKIP_WEBSERVER = "1"

  Push-Location $Frontend
  try {
    & $Npx playwright test
  } finally {
    Pop-Location
  }
  if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
  }
} finally {
  function Kill-ProcessTree($ProcessId) {
    if (-not $ProcessId) { return }
    try {
      Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
    } catch {}
    try {
      Start-Process -FilePath "taskkill" -ArgumentList "/PID $ProcessId /T /F" -NoNewWindow -Wait -ErrorAction SilentlyContinue
    } catch {}
  }

  if ($frontendProcess -and (Get-Process -Id $frontendProcess.Id -ErrorAction SilentlyContinue)) {
    Kill-ProcessTree $frontendProcess.Id
  }
  if ($backendProcess -and (Get-Process -Id $backendProcess.Id -ErrorAction SilentlyContinue)) {
    Kill-ProcessTree $backendProcess.Id
  }
}
