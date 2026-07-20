# Fully automated Fyers token generation + DB store (no captcha, no browser).
#
# Uses pure API flow in fyers_token.py:
#   OTP → TOTP → PIN → POST /api/v3/token (auth_code) → exchange → Neon DB
#
# Usage:
#   .\scripts\fyers_auto_login.ps1
#   .\scripts\fyers_auto_login.ps1 -LoginOnly   # print token only, no DB
#
# Optional Playwright path (captcha often blocks; not recommended):
#   .\scripts\fyers_auto_login.ps1 -Browser

param(
    [switch]$LoginOnly,
    [switch]$Browser,
    [switch]$FirstRun,
    [switch]$Headless,
    [int]$CaptchaWait = 180
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$py = Join-Path $Root "backend\venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    $py = "python"
}

if ($Browser) {
    # Legacy Playwright path (Cloudflare Turnstile often blocks automation).
    $argsList = @("scripts\fyers_playwright_token.py")
    if ($Headless) {
        $argsList += "--headless"
    }
    if ($FirstRun) {
        $argsList += @("--captcha-wait", "$CaptchaWait")
        Write-Host "=== BROWSER FIRST RUN (captcha may block) ===" -ForegroundColor Yellow
    } else {
        $argsList += @("--captcha-wait", "60")
        Write-Host "=== BROWSER AUTO RUN ===" -ForegroundColor Cyan
    }
    if ($LoginOnly) {
        $argsList += "--auth-code-only"
    }
    Write-Host "Running: $py $($argsList -join ' ')"
    & $py @argsList
    exit $LASTEXITCODE
}

# Default: pure API automation (no captcha)
Write-Host "=== FYERS PURE API AUTOMATION (no captcha) ===" -ForegroundColor Cyan

if ($LoginOnly) {
    & $py -c @"
from dotenv import load_dotenv
load_dotenv('.env', override=True)
from fyers_token import generate_fyers_access_token
t = generate_fyers_access_token()
print('TOKEN_OK len=%s' % len(t))
print(t)
"@
    exit $LASTEXITCODE
}

& $py -c @"
import asyncio
from dotenv import load_dotenv
load_dotenv('.env', override=True)

async def main():
    from backend.app.db.session import AsyncSessionLocal
    from backend.app.services.token_service import (
        generate_and_persist_fyers_token,
        get_token_status,
    )
    async with AsyncSessionLocal() as db:
        res = await generate_and_persist_fyers_token(db)
        print('PERSIST', res)
        st = await get_token_status(db)
        print(
            'STATUS',
            st.get('status'),
            st.get('connection_status'),
            'active=',
            st.get('access_token_active'),
            'masked=',
            st.get('token_masked'),
            'expires=',
            st.get('expires_at'),
        )
        if st.get('access_token_active') or st.get('status') == 'Success':
            print('SUCCESS: Token stored — frontend can use it.')
            return 0
        print('WARN: Store finished but token may not be active.')
        return 1

raise SystemExit(asyncio.run(main()))
"@
exit $LASTEXITCODE
