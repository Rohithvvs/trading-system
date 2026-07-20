"""Fyers LOGIN automation (best practice: first-run captcha, then auto).

BEST IMPLEMENTATION
-------------------
Cloudflare captcha cannot be fully auto-solved. Industry best practice:

  FIRST SUCCESS (one time):
    - Run headed browser
    - You click "Verify you are human" if shown (once)
    - Script does mobile + TOTP + PIN + auth_code + store token
    - Browser profile is saved → HTML/fyers_pw_profile

  AFTER FIRST SUCCESS (daily / cron):
    - Same script reuses profile
    - Usually NO captcha
    - Fully automatic login (mobile → TOTP → PIN → token → DB)

Usage (Windows):
  .\\scripts\\fyers_auto_login.ps1 -FirstRun     # first time (click captcha if shown)
  .\\scripts\\fyers_auto_login.ps1               # later automatic runs

  python scripts/fyers_playwright_token.py --headed --captcha-wait 180
  python scripts/fyers_playwright_token.py --headed   # after profile exists

  # Login only (auth_code), skip DB store:
  python scripts/fyers_playwright_token.py --headed --auth-code-only

Requires .env:
  FYERS_APP_ID, FYERS_SECRET_ID (or FYERS_APP_SECRET), FYERS_REDIRECT_URI
  FYERS_PIN, FYERS_TOTP_SECRET, PHONE_NUMBER, DATABASE_URL
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=True)


def _env(*names: str, required: bool = True) -> str:
    for n in names:
        v = (os.getenv(n) or "").strip().strip('"').strip("'")
        if v:
            return v
    if required:
        raise SystemExit(f"Missing required env: one of {names}")
    return ""


def _build_auth_url() -> str:
    from fyers_apiv3 import fyersModel

    client_id = _env("FYERS_APP_ID", "CLIENT_ID")
    secret = _env("FYERS_APP_SECRET", "FYERS_SECRET_ID", "SECRET_KEY")
    redirect = _env(
        "FYERS_REDIRECT_URI",
        required=False,
    ) or "https://trade.fyers.in/api-login/redirect-uri/index.html"

    session = fyersModel.SessionModel(
        client_id=client_id,
        secret_key=secret,
        redirect_uri=redirect,
        response_type="code",
        grant_type="authorization_code",
        state="sample_state",
    )
    return session.generate_authcode()


def _totp_now() -> str:
    import pyotp

    secret = _env("FYERS_TOTP_SECRET")
    return pyotp.TOTP(secret).now()


def _extract_auth_code(url: str) -> str | None:
    try:
        q = parse_qs(urlparse(url).query)
        vals = q.get("auth_code") or q.get("authcode")
        if vals and vals[0]:
            return vals[0]
    except Exception:
        pass
    m = re.search(r"[?&]auth_code=([^&]+)", url)
    return m.group(1) if m else None


async def _solve_turnstile_if_present(page) -> None:
    """Click Cloudflare Turnstile 'Verify you are human' if shown.

    Note: Turnstile may still block pure bots; headed mode improves success rate.
    """
    try:
        # Visible checkbox label / widget
        captcha = page.locator(
            "text=Verify you are human, "
            "iframe[src*='challenges.cloudflare.com'], "
            "iframe[title*='Cloudflare'], "
            "#captcha1, #captcha2"
        )
        if await captcha.count() == 0:
            return
        print("Captcha detected — attempting to solve Turnstile...")
        # Prefer iframe body checkbox
        frames = page.frames
        clicked = False
        for frame in frames:
            try:
                url = frame.url or ""
                if "challenges.cloudflare" in url or "turnstile" in url:
                    box = frame.locator("input[type='checkbox'], body")
                    if await box.count() > 0:
                        await box.first.click(timeout=3_000)
                        clicked = True
                        break
            except Exception:
                continue
        if not clicked:
            # Click the captcha container itself
            try:
                await page.locator("text=Verify you are human").click(timeout=3_000)
                clicked = True
            except Exception:
                pass
        if clicked:
            # Wait for token field to be populated
            for _ in range(30):
                token = await page.evaluate(
                    """() => {
                    const el = document.querySelector('[name=\"cf-turnstile-response\"]');
                    return el && el.value ? el.value.length : 0;
                }"""
                )
                if token and int(token) > 20:
                    print("Turnstile token present")
                    return
                await page.wait_for_timeout(500)
            print("Turnstile click done (token may still be pending)")
    except Exception as e:
        print("Captcha handling note:", e)


async def _type_otp_boxes(page, container_locator, code: str) -> None:
    """Fill sequential single-digit OTP/TOTP/PIN boxes inside a container locator."""
    if isinstance(container_locator, str):
        container = page.locator(container_locator).first
    else:
        container = container_locator
    boxes = container.locator("input")
    # Prefer visible inputs only
    count = await boxes.count()
    if count == 0:
        raise RuntimeError("No inputs found in OTP/PIN container")
    digits = list(code.strip())
    visible_idxs = []
    for i in range(count):
        if await boxes.nth(i).is_visible():
            visible_idxs.append(i)
    if not visible_idxs:
        visible_idxs = list(range(min(count, len(digits))))
    n = min(len(digits), len(visible_idxs))
    for j in range(n):
        box = boxes.nth(visible_idxs[j])
        await box.click()
        await box.fill("")
        await box.type(digits[j], delay=35)


async def run_browser_flow(
    *,
    headed: bool,
    slow_mo: int,
    captcha_wait: int = 180,
    use_persistent: bool = True,
) -> str:
    from playwright.async_api import async_playwright, TimeoutError as PwTimeout

    phone = _env("PHONE_NUMBER", "FYERS_MOBILE", "MOBILE_NUMBER")
    # normalize to 10 digits if +91 prefixed
    phone_digits = re.sub(r"\D", "", phone)
    if phone_digits.startswith("91") and len(phone_digits) == 12:
        phone_digits = phone_digits[2:]
    if len(phone_digits) < 10:
        raise SystemExit(f"PHONE_NUMBER looks invalid (len={len(phone_digits)})")

    pin = _env("FYERS_PIN")
    if not pin.isdigit() or len(pin) not in (4, 6):
        raise SystemExit("FYERS_PIN must be 4 or 6 digits")

    auth_url = _build_auth_url()
    print("Auth URL:", auth_url)
    print("Using mobile:", phone_digits[:2] + "******" + phone_digits[-2:])

    # Persistent profile = best fix after first success (trust cookies / fingerprint)
    profile_dir = ROOT / "HTML" / "fyers_pw_profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    marker = profile_dir / ".first_success"
    if marker.exists():
        print("MODE: AFTER FIRST SUCCESS (reusing trusted browser profile)")
    else:
        print("MODE: FIRST RUN — if captcha appears, click it once in the browser")
    timeout_ms = 120_000

    if not headed:
        print(
            "NOTE: headless often fails captcha. Prefer --headed "
            "(especially on first run)."
        )

    async with async_playwright() as p:
        browser = None
        if use_persistent:
            print(f"Browser profile: {profile_dir}")
            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=not headed,
                slow_mo=slow_mo or 0,
                viewport={"width": 1280, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                args=["--disable-blink-features=AutomationControlled"],
            )
            page = context.pages[0] if context.pages else await context.new_page()
        else:
            browser = await p.chromium.launch(
                headless=not headed,
                slow_mo=slow_mo or 0,
                args=["--disable-blink-features=AutomationControlled"],
            )
            context = await browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()

        try:
            print("Opening auth URL...")
            await page.goto(auth_url, wait_until="domcontentloaded", timeout=timeout_ms)

            # --- Login: mobile number (default tab on 02_userid.html) ---
            # Wait for either mobile form or client-id form
            try:
                await page.wait_for_selector(
                    "#mobile-code, #fy_client_id, #mobile_rb",
                    timeout=30_000,
                )
            except PwTimeout:
                # Maybe already past login
                print("Login form not found immediately; checking next steps...")

            if await page.locator("#mobile-code").count() > 0:
                print("Step: mobile login")
                if await page.locator("#mobile_rb").count() > 0:
                    await page.locator("#mobile_rb").check()
                    await page.wait_for_timeout(300)

                mobile = page.locator("#mobile-code")
                await mobile.click()
                await mobile.fill("")
                await mobile.type(phone_digits, delay=40)
                await mobile.dispatch_event("input")
                await mobile.dispatch_event("change")
                await mobile.dispatch_event("blur")
                await page.wait_for_timeout(500)

                # Cloudflare Turnstile often appears after typing mobile (bot check).
                await _solve_turnstile_if_present(page)

                submit = page.locator("#mobileNumberSubmit")
                for _ in range(40):
                    disabled = await submit.get_attribute("disabled")
                    if disabled is None:
                        break
                    await page.wait_for_timeout(150)
                    # captcha may finish enabling the button
                    await _solve_turnstile_if_present(page)

                try:
                    await submit.click(timeout=8_000)
                except Exception:
                    await page.evaluate(
                        """() => {
                        const b = document.getElementById('mobileNumberSubmit');
                        if (b) { b.removeAttribute('disabled'); b.click(); }
                        const f = document.getElementById('mobileIdForm');
                        if (f) f.requestSubmit ? f.requestSubmit() : f.submit();
                    }"""
                    )
                print("Submitted mobile number")
                print("=" * 60)
                print("CAPTCHA (if shown): click 'Verify you are human' in the browser,")
                print("then Continue. Waiting up to %ss for TOTP page..." % captcha_wait)
                print("=" * 60)
                deadline = time.time() + max(30, captcha_wait)
                while time.time() < deadline:
                    if await page.locator("#confirmOtpSubmit").is_visible():
                        print("TOTP page is visible")
                        break
                    if await page.locator("#verify_totp_content").is_visible():
                        print("TOTP content visible")
                        break
                    if await page.locator("text=Verify you are human").count() > 0:
                        await _solve_turnstile_if_present(page)
                    try:
                        sub = page.locator("#mobileNumberSubmit")
                        if await sub.is_visible() and await sub.get_attribute("disabled") is None:
                            await sub.click(timeout=1_500)
                    except Exception:
                        pass
                    await page.wait_for_timeout(800)
                else:
                    shot = ROOT / "HTML" / "playwright_after_mobile.png"
                    await page.screenshot(path=str(shot), full_page=True)
                    raise RuntimeError(
                        f"TOTP page did not become visible after mobile submit.\n"
                        f"Screenshot: {shot}\n"
                        "Cloudflare captcha is blocking automation.\n"
                        "Run: python scripts/fyers_playwright_token.py --headed --captcha-wait 180\n"
                        "When the browser opens, CLICK the captcha checkbox yourself."
                    )
            elif await page.locator("#fy_client_id").count() > 0:
                print("Step: client-id login (fallback)")
                client = _env("FYERS_CLIENT_ID", required=False) or phone_digits
                if await page.locator("#clientId_rb").count() > 0:
                    await page.locator("#clientId_rb").check()
                    await page.wait_for_timeout(300)
                await page.locator("#fy_client_id").fill(client)
                await page.locator("#clientIdSubmit").click()
                # same wait for TOTP after client-id path
                deadline = time.time() + 100
                while time.time() < deadline:
                    if await page.locator("#confirmOtpSubmit").is_visible():
                        break
                    await _solve_turnstile_if_present(page)
                    await page.wait_for_timeout(800)

            # --- TOTP (section becomes visible after mobile submit) ---
            print("Step: TOTP page ready")
            try:
                await page.locator("#confirmOtpSubmit").wait_for(state="visible", timeout=15_000)
            except PwTimeout:
                pass

            # Ensure TOTP content (not SMS OTP only) if both exist
            totp_hint = page.locator("#verify_totp_content")
            if await totp_hint.count() > 0:
                try:
                    await totp_hint.wait_for(state="visible", timeout=5_000)
                except Exception:
                    pass

            # Fresh TOTP just before typing (30s window)
            totp_code = _totp_now()
            print("Entering TOTP")
            otp_loc = page.locator("#confirm-otp-page #otp-container")
            if await otp_loc.count() == 0:
                otp_loc = page.locator("#otp-container")
            await _type_otp_boxes(page, otp_loc.first, totp_code)

            btn = page.locator("#confirmOtpSubmit")
            if await btn.count() > 0 and await btn.is_visible():
                await btn.click()
            else:
                await page.keyboard.press("Enter")
            print("Submitted TOTP")

            # --- PIN ---
            print("Step: waiting for PIN page...")
            try:
                await page.locator("#verifyPinSubmit").wait_for(state="visible", timeout=60_000)
            except PwTimeout:
                await page.locator("#pin-container").wait_for(state="visible", timeout=15_000)

            print("Entering PIN")
            pin_loc = page.locator("#verify-pin-page #pin-container")
            if await pin_loc.count() == 0:
                pin_loc = page.locator("#pin-container")
            await _type_otp_boxes(page, pin_loc.first, pin)

            pin_btn = page.locator("#verifyPinSubmit")
            if await pin_btn.count() > 0 and await pin_btn.is_visible():
                try:
                    if await pin_btn.get_attribute("disabled") is None:
                        await pin_btn.click(timeout=3_000)
                except Exception:
                    # last digit often auto-submits
                    pass
            print("Submitted PIN — waiting for redirect with auth_code...")

            # --- Redirect with auth_code ---
            # Wait until URL contains auth_code (redirect page)
            deadline = time.time() + 90
            auth_code = None
            last_url = page.url
            while time.time() < deadline:
                last_url = page.url
                auth_code = _extract_auth_code(last_url)
                if auth_code:
                    break
                # also check all pages in context
                for pg in context.pages:
                    auth_code = _extract_auth_code(pg.url)
                    if auth_code:
                        last_url = pg.url
                        break
                if auth_code:
                    break
                await page.wait_for_timeout(500)

            if not auth_code:
                # dump for debug
                debug_path = ROOT / "HTML" / "playwright_fail_url.txt"
                debug_path.write_text(last_url or "", encoding="utf-8")
                shot = ROOT / "HTML" / "playwright_fail.png"
                try:
                    await page.screenshot(path=str(shot), full_page=True)
                except Exception:
                    pass
                raise RuntimeError(
                    f"Timed out waiting for auth_code in URL. Last URL saved to {debug_path}"
                )

            print("Got auth_code from URL (len=%s)" % len(auth_code))
            print("Redirect URL host:", urlparse(last_url).netloc + urlparse(last_url).path)
            # Mark profile as trusted after we successfully passed full login
            try:
                marker.write_text("ok\n", encoding="utf-8")
                print("Saved first-success marker — next runs should be automatic.")
            except Exception:
                pass
            return auth_code

        finally:
            await context.close()
            if browser is not None:
                await browser.close()


def exchange_and_store(auth_code: str) -> dict:
    from fyers_apiv3 import fyersModel

    client_id = _env("FYERS_APP_ID", "CLIENT_ID")
    secret = _env("FYERS_APP_SECRET", "FYERS_SECRET_ID", "SECRET_KEY")
    redirect = _env("FYERS_REDIRECT_URI", required=False) or (
        "https://trade.fyers.in/api-login/redirect-uri/index.html"
    )

    session = fyersModel.SessionModel(
        client_id=client_id,
        secret_key=secret,
        redirect_uri=redirect,
        response_type="code",
        grant_type="authorization_code",
        state="sample_state",
    )
    session.set_token(auth_code)
    response = session.generate_token()
    if not isinstance(response, dict):
        raise RuntimeError(f"Unexpected token response: {type(response)}")
    access = response.get("access_token")
    if not access:
        raise RuntimeError(f"Token exchange failed: {response}")

    print("Access token received (len=%s)" % len(access))

    async def _store() -> dict:
        os.chdir(ROOT)
        from datetime import datetime, timezone

        from sqlalchemy import select

        from backend.app.db.session import AsyncSessionLocal
        from backend.app.models import FyersToken, FyersTokenHistory
        from backend.app.services.token_service import (
            _decode_jwt_expiry,
            _encrypt_for_storage,
            _invalidate_token_status_cache,
            _mask_token,
            _set_token_cache,
            get_token_status,
            save_access_token,
        )

        async with AsyncSessionLocal() as db:
            res = await save_access_token(access, db)
            if res.get("status") != "ok":
                print("WARN save_access_token:", res.get("message"))
                print("Falling back to direct encrypted persist...")
                now = datetime.now(timezone.utc)
                stored = _encrypt_for_storage(access)
                expires_at = _decode_jwt_expiry(access)
                row = (
                    await db.scalars(select(FyersToken).where(FyersToken.id == 1))
                ).first()
                if row is None:
                    db.add(
                        FyersToken(
                            id=1,
                            access_token=stored,
                            created_at=now,
                            is_active=True,
                            status="Success",
                            last_error=None,
                            access_token_saved_at=now,
                            validated_at=now,
                            expires_at=expires_at,
                        )
                    )
                else:
                    row.access_token = stored
                    row.is_active = True
                    row.status = "Success"
                    row.last_error = None
                    row.access_token_saved_at = now
                    row.validated_at = now
                    row.expires_at = expires_at
                db.add(
                    FyersTokenHistory(
                        access_token_masked=_mask_token(access),
                        saved_at=now,
                        status="Success",
                        note="Playwright browser OAuth automation",
                    )
                )
                await db.commit()
                _set_token_cache(access, now)
                await _invalidate_token_status_cache()
                res = {"status": "ok", "note": "direct_persist"}

            st = await get_token_status(db)
            return {
                "save": res,
                "db_status": st.get("status"),
                "connection_status": st.get("connection_status"),
                "access_token_active": st.get("access_token_active"),
                "token_masked": st.get("token_masked"),
                "expires_at": st.get("expires_at"),
            }

    return asyncio.run(_store())


def main() -> int:
    parser = argparse.ArgumentParser(description="Playwright Fyers full token automation")
    parser.add_argument(
        "--headed",
        action="store_true",
        default=True,
        help="Show browser window (default ON — needed for captcha)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Force headless (often fails captcha)",
    )
    parser.add_argument("--slow-mo", type=int, default=0, help="Slow each action (ms)")
    parser.add_argument(
        "--captcha-wait",
        type=int,
        default=180,
        help="Seconds to wait for captcha solve + TOTP page (default 180)",
    )
    parser.add_argument(
        "--no-persistent",
        action="store_true",
        help="Do not reuse browser profile (fresh session every run)",
    )
    parser.add_argument(
        "--auth-code-only",
        action="store_true",
        help="Only obtain auth_code (do not exchange/store)",
    )
    args = parser.parse_args()
    headed = not args.headless

    try:
        auth_code = asyncio.run(
            run_browser_flow(
                headed=headed,
                slow_mo=args.slow_mo,
                captcha_wait=args.captcha_wait,
                use_persistent=not args.no_persistent,
            )
        )
        print("AUTH_CODE_OK len=%s" % len(auth_code))
        if args.auth_code_only:
            print(auth_code)
            return 0

        out = exchange_and_store(auth_code)
        print("DB status:", out.get("db_status"))
        print("Connection:", out.get("connection_status"))
        print("Active:", out.get("access_token_active"))
        print("Masked:", out.get("token_masked"))
        print("Expires:", out.get("expires_at"))
        if out.get("access_token_active") or out.get("db_status") == "Success":
            print("SUCCESS: Token stored — frontend can use it.")
            return 0
        print("WARN: Store finished but token may not be active.")
        return 1
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
