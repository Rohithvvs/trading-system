$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Artifacts = Join-Path $Root "tests\artifacts"

if (Test-Path $Artifacts) {
  # Try to terminate likely leftover E2E processes that can keep files locked.
  try {
    $filters = 'playwright|vite|npm|uvicorn|node.exe|python.exe'
    $procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match $filters }
    foreach ($p in $procs) {
      try {
        Start-Process -FilePath "taskkill" -ArgumentList "/PID $($p.ProcessId) /T /F" -NoNewWindow -Wait -ErrorAction SilentlyContinue
      } catch {}
    }
  } catch {}

  # Retry deletion a few times to handle transient file locks on Windows.
  $maxAttempts = 3
  $attempt = 0
  while ($attempt -lt $maxAttempts) {
    try {
      Remove-Item -LiteralPath $Artifacts -Recurse -Force -ErrorAction Stop
      break
    } catch {
      $attempt++
      Start-Sleep -Milliseconds 500
      if ($attempt -eq $maxAttempts) {
        Write-Warning "Failed to delete $Artifacts after $maxAttempts attempts."
      }
    }
  }
}

New-Item -ItemType Directory -Force -Path (Join-Path $Artifacts "backend") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Artifacts "playwright") | Out-Null
Write-Host "Cleaned test artifacts at $Artifacts"
