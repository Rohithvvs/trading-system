"""Fyers API v3 TOTP headless access-token generation (Sprint 2 / 007-fyers-totp-token).

Standalone library + CLI module. Distinct from ``backend.app.models.fyers_token``
(SQLAlchemy persistence model). Import as::

    from fyers_token import generate_fyers_access_token

Environment variables (credentials only — never hardcode secrets):
  - FYERS_CLIENT_ID   Fyers user id (e.g. YJ08718)
  - FYERS_APP_ID      API app id (e.g. L9NY305RTW-100)
  - FYERS_APP_SECRET  App secret (alias: FYERS_SECRET_ID for backend parity)
  - FYERS_TOTP_SECRET Base32 TOTP secret
  - FYERS_PIN         4- or 6-digit login PIN
  - FYERS_REDIRECT_URI Optional OAuth redirect override
"""

from __future__ import annotations

import base64
import concurrent.futures
import logging
import os
import re
import sys
import time
import urllib.parse
from typing import Any

import pyotp
import requests
from fyers_apiv3 import fyersModel

# -----------------------------------------------------------------------------
# Logging (library-safe: no stdout handler; host / CLI configures sinks)
# -----------------------------------------------------------------------------

logger = logging.getLogger("fyers_auth")
# Prevent "No handlers could be found" noise when used as a library.
if not logger.handlers:
    logger.addHandler(logging.NullHandler())

# Finite bound for every external network hop (fail-fast, no indefinite hang).
REQUEST_TIMEOUT_SEC = float(os.getenv("FYERS_HTTP_TIMEOUT_SEC", "10"))
SDK_TIMEOUT_SEC = float(os.getenv("FYERS_SDK_TIMEOUT_SEC", "15"))

DEFAULT_REDIRECT_URI = (
    "https://trade.fyers.in/api-login/redirect-uri/index.html"
)

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Content-Type": "application/json",
}

# Patterns that must never appear in exception messages or logs.
_SENSITIVE_QUERY_RE = re.compile(
    r"(auth_code|access_token|refresh_token|code|token|otp|pin)=([^&\s]+)",
    re.IGNORECASE,
)
_BEARER_RE = re.compile(r"Bearer\s+\S+", re.IGNORECASE)


# -----------------------------------------------------------------------------
# Custom Exception Hierarchy
# -----------------------------------------------------------------------------
# Note: FyersConnectionError is a domain exception. It does NOT subclass the
# builtin ConnectionError / requests.exceptions.ConnectionError — callers must
# catch this type explicitly.


class FyersConfigError(Exception):
    """Raised when required environment variables are missing or invalid."""

    pass


class FyersAuthError(Exception):
    """Raised when authentication stages (OTP, TOTP, PIN, token exchange) fail."""

    pass


class FyersConnectionError(Exception):
    """Raised when requests to Fyers API endpoints fail due to network/server errors.

    Distinct from ``requests.exceptions.ConnectionError`` and the builtin
    ``ConnectionError`` — catch this class for domain connection failures.
    """

    pass


# -----------------------------------------------------------------------------
# Safe diagnostics helpers
# -----------------------------------------------------------------------------


def _redact_sensitive(text: str, max_len: int = 120) -> str:
    """Strip tokens / auth codes / bearer headers from diagnostic text."""
    if not text:
        return ""
    redacted = _SENSITIVE_QUERY_RE.sub(r"\1=<redacted>", str(text))
    redacted = _BEARER_RE.sub("Bearer <redacted>", redacted)
    if len(redacted) > max_len:
        return redacted[:max_len] + "..."
    return redacted


def _safe_response_snippet(resp: requests.Response | None) -> str:
    if resp is None:
        return "no-response"
    body = ""
    try:
        body = resp.text or ""
    except Exception:
        body = ""
    return (
        f"status={getattr(resp, 'status_code', '?')} "
        f"body={_redact_sensitive(body, max_len=80)}"
    )


def _configure_cli_logging() -> None:
    """Attach a stderr INFO handler only when running as CLI (__main__)."""
    # Remove NullHandlers so CLI diagnostics are visible on stderr.
    for h in list(logger.handlers):
        if isinstance(h, logging.NullHandler):
            logger.removeHandler(h)
    if not any(
        isinstance(h, logging.StreamHandler) and getattr(h, "stream", None) is sys.stderr
        for h in logger.handlers
    ):
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(logging.INFO)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
        )
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)


# -----------------------------------------------------------------------------
# Configuration Loader
# -----------------------------------------------------------------------------


def _env_first(*keys: str) -> str | None:
    """Return the first non-None env value for the given keys (raw)."""
    for key in keys:
        if key in os.environ:
            return os.environ.get(key)
    return None


def load_fyers_config() -> dict:
    """Loads and validates Fyers configuration from environment variables.

    ``FYERS_APP_SECRET`` is preferred; ``FYERS_SECRET_ID`` is accepted as an
    alias for compatibility with backend ``settings.fyers_secret_id``.

    Returns:
        dict: Validated credentials dictionary.

    Raises:
        FyersConfigError: If any required env var is missing or empty.
    """
    # Canonical key -> alternate env names (first match wins).
    key_aliases: dict[str, tuple[str, ...]] = {
        "FYERS_CLIENT_ID": ("FYERS_CLIENT_ID",),
        "FYERS_APP_ID": ("FYERS_APP_ID",),
        "FYERS_APP_SECRET": ("FYERS_APP_SECRET", "FYERS_SECRET_ID"),
        "FYERS_TOTP_SECRET": ("FYERS_TOTP_SECRET",),
        "FYERS_PIN": ("FYERS_PIN",),
    }
    config: dict[str, str] = {}

    for canonical, aliases in key_aliases.items():
        raw = _env_first(*aliases)
        if raw is None:
            hint = canonical
            if canonical == "FYERS_APP_SECRET":
                hint = "FYERS_APP_SECRET (or alias FYERS_SECRET_ID)"
            raise FyersConfigError(
                f"Missing required environment variable: {hint}"
            )

        stripped = raw.strip()
        if not stripped:
            hint = canonical
            if canonical == "FYERS_APP_SECRET":
                hint = "FYERS_APP_SECRET (or alias FYERS_SECRET_ID)"
            raise FyersConfigError(
                f"Required environment variable is empty: {hint}"
            )
        config[canonical] = stripped

    # Optional early PIN format check (4 or 6 digits) — fail fast before network.
    pin = config["FYERS_PIN"]
    if not pin.isdigit() or len(pin) not in (4, 6):
        raise FyersConfigError(
            "FYERS_PIN must be a 4-digit or 6-digit numeric PIN"
        )

    redirect_raw = os.getenv("FYERS_REDIRECT_URI", DEFAULT_REDIRECT_URI)
    config["FYERS_REDIRECT_URI"] = (redirect_raw or DEFAULT_REDIRECT_URI).strip()
    if not config["FYERS_REDIRECT_URI"]:
        config["FYERS_REDIRECT_URI"] = DEFAULT_REDIRECT_URI

    return config


# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------


def get_base64_string(string: str) -> str:
    """Encodes a given string into Base64 format."""
    return base64.b64encode(str(string).encode("utf-8")).decode("utf-8")


def _post_json(
    url: str,
    payload: dict,
    headers: dict,
    step: str,
) -> dict[str, Any]:
    """POST JSON with timeout; map network failures to FyersConnectionError."""
    resp: requests.Response | None = None
    try:
        resp = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=REQUEST_TIMEOUT_SEC,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.Timeout as e:
        raise FyersConnectionError(
            f"Timeout during {step} (limit={REQUEST_TIMEOUT_SEC}s): {e}"
        ) from e
    except requests.HTTPError as e:
        status = getattr(getattr(e, "response", None), "status_code", "?")
        raise FyersConnectionError(
            f"HTTP error during {step} (status={status}): {e}"
        ) from e
    except requests.RequestException as e:
        raise FyersConnectionError(
            f"Connection failed during {step}: {e}"
        ) from e
    except ValueError as e:
        # Invalid JSON — do not include response body (may hold secrets).
        raise FyersAuthError(
            f"Invalid JSON response during {step}"
        ) from e
    finally:
        if resp is not None:
            try:
                resp.close()
            except Exception:
                pass


def _extract_redirect_url(res_authcode: requests.Response) -> str | None:
    redirect_url = res_authcode.headers.get("Location")
    if redirect_url:
        return redirect_url
    # Fallback: some environments return 200 + redirect in body.
    if res_authcode.status_code == 200:
        try:
            data = res_authcode.json()
            return (data.get("data") or {}).get("redirect_uri")
        except ValueError:
            return None
    return None


def _exchange_auth_code(
    app_id: str,
    app_secret: str,
    redirect_uri: str,
    auth_code: str,
) -> dict[str, Any]:
    """Exchange auth code via Fyers SDK with a hard timeout bound.

    On timeout the caller fails fast. The pool is shut down with wait=False so
    a hung SDK call cannot block the process on executor teardown (H1 / resource
    management hardening).
    """

    def _run() -> dict[str, Any]:
        session = fyersModel.SessionModel(
            client_id=app_id,
            secret_key=app_secret,
            redirect_uri=redirect_uri,
            response_type="code",
            grant_type="authorization_code",
        )
        session.set_token(auth_code)
        return session.generate_token()

    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(_run)
        return future.result(timeout=SDK_TIMEOUT_SEC)
    except concurrent.futures.TimeoutError as e:
        raise FyersConnectionError(
            f"Timeout during token exchange SDK step "
            f"(limit={SDK_TIMEOUT_SEC}s)"
        ) from e
    except FyersConnectionError:
        raise
    except Exception as e:
        raise FyersAuthError(
            f"Fyers SDK SessionModel execution error: {type(e).__name__}"
        ) from e
    finally:
        # Do not wait for a stuck worker — fail-fast for the main thread.
        pool.shutdown(wait=False, cancel_futures=True)


# -----------------------------------------------------------------------------
# Core Login Function
# -----------------------------------------------------------------------------


def generate_fyers_access_token() -> str:
    """Generates a valid Fyers API v3 access token using TOTP.

    Reads configuration from environment variables:
      - FYERS_CLIENT_ID
      - FYERS_APP_ID
      - FYERS_APP_SECRET (or FYERS_SECRET_ID)
      - FYERS_TOTP_SECRET
      - FYERS_PIN

    Returns:
        str: The generated Fyers API v3 access token.

    Raises:
        FyersConfigError: If any required environment variable is missing.
        FyersAuthError: If login, TOTP verification, or PIN verification fails.
        FyersConnectionError: If API requests fail due to network/server errors.
    """
    config = load_fyers_config()
    client_id = config["FYERS_CLIENT_ID"]
    app_id = config["FYERS_APP_ID"]
    app_secret = config["FYERS_APP_SECRET"]
    totp_secret = config["FYERS_TOTP_SECRET"]
    pin = config["FYERS_PIN"]
    redirect_uri = config["FYERS_REDIRECT_URI"]

    headers = dict(_BROWSER_HEADERS)

    # Step 1: Send Login OTP Request
    logger.info("step=otp_request outcome=start")
    data_otp = _post_json(
        "https://api-t2.fyers.in/vagator/v2/send_login_otp_v2",
        {
            "fy_id": get_base64_string(client_id),
            "app_id": "2",
        },
        headers,
        step="OTP request",
    )

    if data_otp.get("s") != "ok":
        raise FyersAuthError(
            f"OTP request failed: {data_otp.get('message', 'Unknown error')}"
        )

    request_key_1 = data_otp.get("request_key")
    if not request_key_1:
        raise FyersAuthError("Missing request_key in OTP request response")

    # Step 2: Generate and Verify TOTP
    logger.info("step=totp_verify outcome=start")
    try:
        totp_generator = pyotp.TOTP(totp_secret)
        totp_code = totp_generator.now()
    except Exception as e:
        raise FyersConfigError(f"Invalid TOTP secret format: {e}") from e

    url_verify_totp = "https://api-t2.fyers.in/vagator/v2/verify_otp"
    data_totp = _post_json(
        url_verify_totp,
        {"request_key": request_key_1, "otp": totp_code},
        headers,
        step="TOTP verification",
    )

    # FR-010: on failure, wait for next 30s window, regenerate TOTP, retry once.
    if data_totp.get("s") != "ok":
        fail_msg = data_totp.get("message", "Unknown error")
        logger.warning(
            "step=totp_verify outcome=retry message=%s",
            _redact_sensitive(str(fail_msg), max_len=80),
        )
        time_remaining = 30 - (int(time.time()) % 30)
        sleep_for = time_remaining + 1
        logger.info(
            "step=totp_verify outcome=sleep_next_window seconds=%s",
            sleep_for,
        )
        time.sleep(sleep_for)

        retry_code = totp_generator.now()
        # New payload dict (avoid in-place mutation of prior request body).
        data_totp = _post_json(
            url_verify_totp,
            {"request_key": request_key_1, "otp": retry_code},
            headers,
            step="TOTP retry verification",
        )
        if data_totp.get("s") != "ok":
            raise FyersAuthError(
                "TOTP verification failed after retry: "
                f"{data_totp.get('message', 'Unknown error')}"
            )

    request_key_2 = data_totp.get("request_key")
    if not request_key_2:
        raise FyersAuthError(
            "Missing request_key in TOTP verification response"
        )

    # Step 3: Verify PIN
    logger.info("step=pin_verify outcome=start")
    data_pin = _post_json(
        "https://api-t2.fyers.in/vagator/v2/verify_pin_v2",
        {
            "request_key": request_key_2,
            "identity_type": "pin",
            "identifier": get_base64_string(pin),
        },
        headers,
        step="PIN verification",
    )

    if data_pin.get("s") != "ok":
        raise FyersAuthError(
            f"PIN verification failed: {data_pin.get('message', 'Unknown error')}"
        )

    temp_token = (data_pin.get("data") or {}).get("access_token")
    if not temp_token:
        raise FyersAuthError(
            "Missing temporary access_token in PIN verification response data"
        )

    # Step 4: Request Authorization Code
    logger.info("step=authcode_request outcome=start")
    url_authcode = "https://api-t1.fyers.in/api/v3/generate-authcode"
    params_authcode = {
        "client_id": app_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": "sample_state",
    }
    headers_authcode = {"Authorization": f"Bearer {temp_token}"}

    res_authcode: requests.Response | None = None
    try:
        try:
            res_authcode = requests.get(
                url_authcode,
                params=params_authcode,
                headers=headers_authcode,
                allow_redirects=False,
                timeout=REQUEST_TIMEOUT_SEC,
            )
        except requests.Timeout as e:
            raise FyersConnectionError(
                f"Timeout during authorization code request "
                f"(limit={REQUEST_TIMEOUT_SEC}s): {e}"
            ) from e
        except requests.RequestException as e:
            raise FyersConnectionError(
                f"Connection failed during authorization code request: {e}"
            ) from e

        status = res_authcode.status_code
        # 5xx → connection/server failure (fail-fast; M1).
        if status >= 500:
            raise FyersConnectionError(
                f"HTTP server error during authorization code request "
                f"(status={status})"
            )
        # 4xx without redirect is an auth problem.
        if status >= 400 and "Location" not in res_authcode.headers:
            raise FyersAuthError(
                f"Authorization code request rejected (status={status})"
            )

        redirect_url = _extract_redirect_url(res_authcode)
        if not redirect_url:
            raise FyersAuthError(
                f"Redirect Location not found (status={status}, "
                f"{_safe_response_snippet(res_authcode)})"
            )

        parsed_url = urllib.parse.urlparse(redirect_url)
        query_params = urllib.parse.parse_qs(parsed_url.query)
        auth_code_list = query_params.get("auth_code")
        if not auth_code_list:
            # Do not include the full redirect URL (contains auth_code) — H3.
            raise FyersAuthError(
                "auth_code parameter is missing in redirect URL "
                f"(path={parsed_url.path or '/'})"
            )
        auth_code = auth_code_list[0]
    finally:
        if res_authcode is not None:
            try:
                res_authcode.close()
            except Exception:
                pass

    # Step 5: Exchange Authorization Code for Final Access Token
    logger.info("step=token_exchange outcome=start")
    response = _exchange_auth_code(
        app_id=app_id,
        app_secret=app_secret,
        redirect_uri=redirect_uri,
        auth_code=auth_code,
    )

    if not isinstance(response, dict):
        raise FyersAuthError("Token exchange returned an unexpected response type")

    if response.get("s") != "ok":
        raise FyersAuthError(
            f"Token exchange failed: {response.get('message', 'Unknown error')}"
        )

    final_access_token = response.get("access_token")
    if not final_access_token:
        raise FyersAuthError("Final access token was missing in response")

    logger.info("step=token_exchange outcome=success")
    return final_access_token


# -----------------------------------------------------------------------------
# CLI Entry Point
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    _configure_cli_logging()
    try:
        token = generate_fyers_access_token()
        # Contract: only the clean raw access token on stdout.
        print(token)
        sys.exit(0)
    except Exception as e:
        sys.stderr.write(f"Error: {e.__class__.__name__} - {str(e)}\n")
        sys.exit(1)
