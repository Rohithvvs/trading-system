param()

$ErrorActionPreference = "Continue"

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "   SYSTEM TEST AUTOMATION PIPELINE       " -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

# 1. Active Environment Check
Write-Host "`n[1/3] Checking Virtual Environment..." -ForegroundColor Yellow
if ([string]::IsNullOrEmpty($env:VIRTUAL_ENV)) {
    Write-Host "ERROR: Virtual environment is not active!" -ForegroundColor Red
    Write-Host "Please activate it (e.g., '.\venv\Scripts\Activate.ps1') before running this script." -ForegroundColor Red
    exit 1
} else {
    Write-Host "Virtual environment is active: $($env:VIRTUAL_ENV)" -ForegroundColor Green
}

# 2. Force Dependency Sync
Write-Host "`n[2/3] Syncing Dependencies..." -ForegroundColor Yellow
Write-Host "Installing missing dependencies (yfinance, apscheduler)..."
pip install yfinance apscheduler
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to install dependencies." -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host "Exporting active dependencies to requirements.txt..."
# Using Out-File to ensure UTF-8 without BOM issues in PowerShell
pip freeze | Out-File -FilePath requirements.txt -Encoding utf8
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to export requirements." -ForegroundColor Red
    exit $LASTEXITCODE
}
Write-Host "Dependencies successfully synced." -ForegroundColor Green

# 3. Backend Test Suite Execution
Write-Host "`n[3/3] Executing Backend Test Suites..." -ForegroundColor Yellow
$testsFailed = $false

# Executing all test domains sequentially in verbose mode
pytest backend/tests/unit/ backend/tests/integration/ backend/tests/api/ backend/tests/regression/ backend/tests/async/ backend/tests/scheduler/ -v
if ($LASTEXITCODE -ne 0) {
    $testsFailed = $true
}

# 4. Graceful Exit
Write-Host "`n=========================================" -ForegroundColor Cyan
if ($testsFailed) {
    Write-Host "[X] TEST SUITE FAILED: One or more backend tests failed. See logs above." -ForegroundColor Red
    exit 1
} else {
    Write-Host "[✓] TEST SUITE PASSED: All testing domains successfully passed!" -ForegroundColor Green
    exit 0
}
