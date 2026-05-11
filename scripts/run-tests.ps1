param(
  [ValidateSet("fast", "unit", "integration", "e2e", "live", "all")]
  [string]$Suite = "fast"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root "venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
  $Python = "python"
}

New-Item -ItemType Directory -Force -Path (Join-Path $Root "tests\artifacts") | Out-Null

switch ($Suite) {
  "fast" {
    & $Python -m pytest -m "unit or (integration and not slow and not live)"
  }
  "unit" {
    & $Python -m pytest -m "unit"
  }
  "integration" {
    & $Python -m pytest -m "integration and not live"
  }
  "e2e" {
    & (Join-Path $Root "scripts\run-e2e.ps1")
  }
  "live" {
    & $Python -m pytest -m "live" --runxfail
  }
  "all" {
    & $Python -m pytest -m "not live"
    & (Join-Path $Root "scripts\run-e2e.ps1")
  }
}
