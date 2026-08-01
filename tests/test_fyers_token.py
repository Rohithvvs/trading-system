"""Automated tests for Sprint 3 – Retry Logic in Token Generation (008-fyers-token-retry).

Specification: specs/008-fyers-token-retry/spec.md
Also preserves core Sprint 2 regression coverage for generate_fyers_access_token.

All network/SDK interactions are mocked; sleep is mocked where retries occur
so the suite stays offline and fast.
"""

from __future__ import annotations

import logging
import os
from unittest import mock

import pytest
import requests

from fyers_token import (
    FyersAuthError,
    FyersConfigError,
    FyersConnectionError,
    generate_fyers_access_token,
    get_base64_string,
    load_fyers_config,
)

# -----------------------------------------------------------------------------
# Shared helpers
# -----------------------------------------------------------------------------

REQUIRED_ENV = {
    "FYERS_CLIENT_ID": "YJ08718",
    "FYERS_APP_ID": "L9NY305RTW-100",
    "FYERS_APP_SECRET": "secret123",
    "FYERS_TOTP_SECRET": "MFRGGZDFMZTWQ2LK",
    "FYERS_PIN": "1234",
}

DEFAULT_REDIRECT = "https://trade.fyers.in/api-login/redirect-uri/index.html"
FINAL_TOKEN = "final_token_123"
TEMP_TOKEN = "temp_user_token"
AUTH_CODE = "abc123code"


def _json_response(payload: dict, status_code: int = 200) -> mock.Mock:
    resp = mock.Mock()
    resp.status_code = status_code
    resp.json.return_value = payload
    resp.text = str(payload)
    resp.headers = {}
    resp.raise_for_status = mock.Mock()
    resp.close = mock.Mock()
    return resp


def _otp_ok(request_key: str = "key_1") -> mock.Mock:
    return _json_response({"s": "ok", "code": 200, "request_key": request_key})


def _totp_ok(request_key: str = "key_2") -> mock.Mock:
    return _json_response({"s": "ok", "code": 200, "request_key": request_key})


def _pin_ok(access_token: str = TEMP_TOKEN) -> mock.Mock:
    return _json_response(
        {"s": "ok", "code": 200, "data": {"access_token": access_token}}
    )


def _authcode_redirect(
    location: str | None = None,
    status_code: int = 302,
) -> mock.Mock:
    if location is None:
        location = f"{DEFAULT_REDIRECT}?auth_code={AUTH_CODE}&state=sample_state"
    resp = mock.Mock()
    resp.status_code = status_code
    resp.headers = {"Location": location} if location else {}
    resp.text = "redirect"
    resp.json.side_effect = ValueError("no json")
    resp.close = mock.Mock()
    return resp


def _success_posts() -> list:
    return [_otp_ok(), _totp_ok(), _pin_ok()]


@pytest.fixture
def valid_env():
    with mock.patch.dict(os.environ, REQUIRED_ENV, clear=True):
        yield dict(REQUIRED_ENV)


@pytest.fixture
def mock_totp():
    with mock.patch("fyers_token.pyotp.TOTP") as mock_cls:
        inst = mock.Mock()
        inst.now.return_value = "123456"
        mock_cls.return_value = inst
        yield mock_cls, inst


@pytest.fixture
def mock_session_success():
    with mock.patch("fyers_token.fyersModel.SessionModel") as mock_cls:
        inst = mock.Mock()
        inst.generate_token.return_value = {
            "s": "ok",
            "access_token": FINAL_TOKEN,
        }
        mock_cls.return_value = inst
        yield mock_cls, inst


# -----------------------------------------------------------------------------
# Unit — configuration (regression + permanent fail-fast foundation)
# -----------------------------------------------------------------------------


class TestLoadFyersConfig:
    def test_success_returns_required_keys(self, valid_env):
        config = load_fyers_config()
        for key, value in REQUIRED_ENV.items():
            assert config[key] == value

    def test_default_redirect_uri(self, valid_env):
        assert load_fyers_config()["FYERS_REDIRECT_URI"] == DEFAULT_REDIRECT

    def test_missing_required_key_raises_config_error(self):
        env = {k: v for k, v in REQUIRED_ENV.items() if k != "FYERS_APP_SECRET"}
        with mock.patch.dict(os.environ, env, clear=True):
            with pytest.raises(FyersConfigError) as exc:
                load_fyers_config()
        assert "FYERS_APP_SECRET" in str(exc.value)

    def test_empty_key_raises_config_error(self):
        env = {**REQUIRED_ENV, "FYERS_APP_SECRET": "   "}
        with mock.patch.dict(os.environ, env, clear=True):
            with pytest.raises(FyersConfigError):
                load_fyers_config()

    def test_accepts_secret_id_alias(self):
        env = {k: v for k, v in REQUIRED_ENV.items() if k != "FYERS_APP_SECRET"}
        env["FYERS_SECRET_ID"] = "alias_secret"
        with mock.patch.dict(os.environ, env, clear=True):
            assert load_fyers_config()["FYERS_APP_SECRET"] == "alias_secret"


# -----------------------------------------------------------------------------
# US1 / US2 — Success path (no retry) — FR-004, SC-004
# -----------------------------------------------------------------------------


class TestGenerateSuccessNoRetry:
    @mock.patch("fyers_token.time.sleep")
    @mock.patch("fyers_token.random.uniform")
    @mock.patch("fyers_token.requests.post")
    @mock.patch("fyers_token.requests.get")
    def test_first_attempt_success_returns_token_without_retry(
        self,
        mock_get,
        mock_post,
        mock_uniform,
        mock_sleep,
        valid_env,
        mock_totp,
        mock_session_success,
    ):
        """US1-AS3 / SC-004: success on first attempt incurs zero retry delay."""
        mock_post.side_effect = _success_posts()
        mock_get.return_value = _authcode_redirect()

        token = generate_fyers_access_token()
        assert token == FINAL_TOKEN
        mock_sleep.assert_not_called()
        mock_uniform.assert_not_called()
        # Single attempt: OTP + TOTP + PIN
        assert mock_post.call_count == 3
        assert mock_get.call_count == 1


# -----------------------------------------------------------------------------
# US1 — Automated retry on transient failures — FR-001..FR-005
# -----------------------------------------------------------------------------


class TestTransientRetry:
    @mock.patch("fyers_token.time.sleep")
    @mock.patch("fyers_token.random.uniform")
    @mock.patch("fyers_token.requests.post")
    def test_exhausted_retries_message_includes_max_attempts(
        self, mock_post, mock_uniform, mock_sleep, valid_env
    ):
        """FR-005: final error keeps original text + max-attempts suffix/metadata."""
        mock_uniform.return_value = 5.0
        mock_post.side_effect = requests.Timeout("Gateway timeout")
        with pytest.raises(FyersConnectionError) as exc:
            generate_fyers_access_token()
        err = exc.value
        msg = str(err)
        # Original failure text preserved first for substring matchers
        assert "Timeout" in msg or "Connection failed" in msg
        assert "after 3 attempts" in msg
        assert "maximum retries" in msg.lower()
        assert getattr(err, "attempts", None) == 3
        assert getattr(err, "max_attempts", None) == 3
        assert err.__cause__ is not None

    @mock.patch("fyers_token.time.sleep")
    @mock.patch("fyers_token.random.uniform")
    @mock.patch("fyers_token.requests.post")
    @mock.patch("fyers_token.requests.get")
    def test_succeeds_on_third_attempt_after_two_timeouts(
        self,
        mock_get,
        mock_post,
        mock_uniform,
        mock_sleep,
        valid_env,
        mock_totp,
        mock_session_success,
    ):
        """US1-AS1: transient failures on attempts 1–2; token returned on attempt 3."""
        mock_uniform.side_effect = [7.5, 8.2]
        mock_post.side_effect = [
            requests.Timeout("Connection timed out"),
            requests.Timeout("Connection timed out"),
            *_success_posts(),
        ]
        mock_get.return_value = _authcode_redirect()

        token = generate_fyers_access_token()
        assert token == FINAL_TOKEN
        assert mock_sleep.call_count == 2
        mock_sleep.assert_has_calls([mock.call(7.5), mock.call(8.2)])
        mock_uniform.assert_has_calls(
            [mock.call(5.0, 10.0), mock.call(5.0, 10.0)]
        )

    @mock.patch("fyers_token.time.sleep")
    @mock.patch("fyers_token.random.uniform")
    @mock.patch("fyers_token.requests.post")
    def test_all_three_attempts_fail_raises_connection_error(
        self, mock_post, mock_uniform, mock_sleep, valid_env
    ):
        """US1-AS2 / FR-005: persistent transient errors raise after 3 attempts."""
        mock_uniform.return_value = 5.0
        mock_post.side_effect = requests.Timeout("Gateway timeout")

        with pytest.raises(FyersConnectionError) as exc:
            generate_fyers_access_token()
        msg = str(exc.value)
        assert "Timeout" in msg or "Connection failed" in msg
        # Delays only between attempts → 2 sleeps, 3 HTTP attempts
        assert mock_post.call_count == 3
        assert mock_sleep.call_count == 2
        mock_sleep.assert_has_calls([mock.call(5.0), mock.call(5.0)])

    @mock.patch("fyers_token.time.sleep")
    @mock.patch("fyers_token.random.uniform")
    @mock.patch("fyers_token.requests.post")
    @mock.patch("fyers_token.requests.get")
    def test_http_5xx_on_authcode_is_retried_then_succeeds(
        self,
        mock_get,
        mock_post,
        mock_uniform,
        mock_sleep,
        valid_env,
        mock_totp,
        mock_session_success,
    ):
        """Transient HTTP 5xx (connection-class) retries full login sequence."""
        mock_uniform.return_value = 6.0
        # Attempt 1: full login through PIN, then 503 on authcode
        # Attempt 2: full success path
        mock_post.side_effect = [
            *_success_posts(),
            *_success_posts(),
        ]
        resp_503 = mock.Mock()
        resp_503.status_code = 503
        resp_503.headers = {}
        resp_503.text = "Service Unavailable"
        resp_503.close = mock.Mock()
        mock_get.side_effect = [resp_503, _authcode_redirect()]

        token = generate_fyers_access_token()
        assert token == FINAL_TOKEN
        mock_sleep.assert_called_once_with(6.0)
        assert mock_get.call_count == 2

    @mock.patch("fyers_token.time.sleep")
    @mock.patch("fyers_token.random.uniform")
    @mock.patch("fyers_token.requests.post")
    def test_connection_error_retries_up_to_three_times(
        self, mock_post, mock_uniform, mock_sleep, valid_env
    ):
        mock_uniform.return_value = 5.5
        mock_post.side_effect = requests.ConnectionError("DNS failure")

        with pytest.raises(FyersConnectionError):
            generate_fyers_access_token()
        assert mock_post.call_count == 3
        assert mock_sleep.call_count == 2


# -----------------------------------------------------------------------------
# US2 — Randomized delay bounds — FR-003, SC-002
# -----------------------------------------------------------------------------


class TestRetryDelayBounds:
    @mock.patch("fyers_token.time.sleep")
    @mock.patch("fyers_token.random.uniform")
    @mock.patch("fyers_token.requests.post")
    def test_delay_uses_uniform_between_5_and_10(
        self, mock_post, mock_uniform, mock_sleep, valid_env
    ):
        """US2-AS1: delay is random.uniform(5.0, 10.0) and sleep uses that value."""
        mock_uniform.side_effect = [5.0, 9.99]
        mock_post.side_effect = requests.Timeout("t")

        with pytest.raises(FyersConnectionError):
            generate_fyers_access_token()

        for call in mock_uniform.call_args_list:
            assert call.args == (5.0, 10.0)
        mock_sleep.assert_has_calls([mock.call(5.0), mock.call(9.99)])

    @mock.patch("fyers_token.time.sleep")
    @mock.patch("fyers_token.random.uniform", side_effect=[7.25, 6.1])
    @mock.patch("fyers_token.requests.post")
    def test_exactly_two_delays_for_three_failed_attempts(
        self, mock_post, mock_uniform, mock_sleep, valid_env
    ):
        mock_post.side_effect = requests.Timeout("t")
        with pytest.raises(FyersConnectionError):
            generate_fyers_access_token()
        assert mock_uniform.call_count == 2
        assert mock_sleep.call_count == 2


# -----------------------------------------------------------------------------
# FR-006 — Permanent errors fail fast (no retry)
# -----------------------------------------------------------------------------


class TestPermanentFailFast:
    @mock.patch("fyers_token.time.sleep")
    @mock.patch("fyers_token.random.uniform")
    def test_missing_config_does_not_retry_or_sleep(
        self, mock_uniform, mock_sleep
    ):
        """FR-006: configuration errors fail immediately."""
        env = {k: v for k, v in REQUIRED_ENV.items() if k != "FYERS_APP_ID"}
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch("fyers_token.requests.post") as mock_post:
                with pytest.raises(FyersConfigError):
                    generate_fyers_access_token()
                mock_post.assert_not_called()
        mock_sleep.assert_not_called()
        mock_uniform.assert_not_called()

    @mock.patch("fyers_token.time.sleep")
    @mock.patch("fyers_token.random.uniform")
    @mock.patch("fyers_token.requests.post")
    def test_invalid_pin_does_not_retry(
        self, mock_post, mock_uniform, mock_sleep, valid_env, mock_totp
    ):
        """FR-006: permanent PIN failure fails fast."""
        mock_post.side_effect = [
            _otp_ok(),
            _totp_ok(),
            _json_response({"s": "error", "message": "Invalid PIN"}),
        ]
        with pytest.raises(FyersAuthError) as exc:
            generate_fyers_access_token()
        assert "PIN" in str(exc.value)
        mock_sleep.assert_not_called()
        mock_uniform.assert_not_called()
        assert mock_post.call_count == 3  # single attempt only

    @mock.patch("fyers_token.time.sleep")
    @mock.patch("fyers_token.random.uniform")
    @mock.patch("fyers_token.requests.post")
    def test_otp_request_api_error_does_not_retry(
        self, mock_post, mock_uniform, mock_sleep, valid_env
    ):
        """Permanent auth-class OTP failure (Invalid User ID path)."""
        mock_post.return_value = _json_response(
            {"s": "error", "message": "OTP request failed: Invalid User ID"}
        )
        with pytest.raises(FyersAuthError) as exc:
            generate_fyers_access_token()
        assert "OTP request failed" in str(exc.value)
        mock_sleep.assert_not_called()
        assert mock_post.call_count == 1

    @mock.patch("fyers_token.time.sleep")
    @mock.patch("fyers_token.random.uniform")
    @mock.patch("fyers_token.requests.post")
    @mock.patch("fyers_token.requests.get")
    def test_missing_redirect_is_permanent_fail_fast(
        self, mock_get, mock_post, mock_uniform, mock_sleep, valid_env, mock_totp
    ):
        mock_post.side_effect = _success_posts()
        resp = mock.Mock()
        resp.status_code = 200
        resp.headers = {}
        resp.json.return_value = {}
        resp.text = "landing"
        resp.close = mock.Mock()
        mock_get.return_value = resp

        with pytest.raises(FyersAuthError) as exc:
            generate_fyers_access_token()
        assert "Redirect Location not found" in str(exc.value)
        mock_sleep.assert_not_called()
        mock_uniform.assert_not_called()

    @mock.patch("fyers_token.time.sleep")
    @mock.patch("fyers_token.random.uniform")
    @mock.patch("fyers_token.requests.post")
    def test_totp_failure_after_inner_retry_is_permanent(
        self, mock_post, mock_uniform, mock_sleep, valid_env, mock_totp
    ):
        """H1 / FR-006: wrong TOTP must not outer-retry with 5–10s delays."""
        # OTP ok, TOTP fail, TOTP retry fail → permanent
        mock_post.side_effect = [
            _otp_ok(),
            _json_response({"s": "error", "message": "OTP incorrect"}),
            _json_response({"s": "error", "message": "OTP incorrect"}),
        ]
        with pytest.raises(FyersAuthError) as exc:
            generate_fyers_access_token()
        assert "TOTP verification failed" in str(exc.value)
        # Outer retry jitter must not run
        mock_uniform.assert_not_called()
        # Only inner window sleep (if any), not two outer delays
        assert mock_post.call_count == 3


# -----------------------------------------------------------------------------
# FR-007 — Fresh TOTP each attempt
# -----------------------------------------------------------------------------


class TestFreshTotpPerAttempt:
    @mock.patch("fyers_token.time.sleep")
    @mock.patch("fyers_token.random.uniform", return_value=5.0)
    @mock.patch("fyers_token.requests.post")
    @mock.patch("fyers_token.requests.get")
    def test_totp_regenerated_on_each_outer_attempt(
        self,
        mock_get,
        mock_post,
        mock_uniform,
        mock_sleep,
        valid_env,
        mock_session_success,
    ):
        """FR-007: each outer attempt creates a new TOTP and calls now()."""
        with mock.patch("fyers_token.pyotp.TOTP") as mock_totp_cls:
            inst = mock.Mock()
            inst.now.side_effect = ["111111", "222222", "333333"]
            mock_totp_cls.return_value = inst

            # Fail OTP step twice, succeed full path third
            mock_post.side_effect = [
                requests.Timeout("t1"),
                requests.Timeout("t2"),
                *_success_posts(),
            ]
            mock_get.return_value = _authcode_redirect()

            token = generate_fyers_access_token()
            assert token == FINAL_TOKEN
            # New TOTP instance per successful attempt path that reaches step 2
            # Attempt 3 reaches TOTP; attempts 1–2 fail at OTP before TOTP.
            # So now() called once on attempt 3 only in this scenario.
            assert mock_totp_cls.call_count == 1
            assert inst.now.call_count >= 1

    @mock.patch("fyers_token.time.sleep")
    @mock.patch("fyers_token.random.uniform", return_value=5.0)
    @mock.patch("fyers_token.requests.post")
    @mock.patch("fyers_token.requests.get")
    def test_totp_now_called_fresh_when_each_attempt_reaches_verify(
        self,
        mock_get,
        mock_post,
        mock_uniform,
        mock_sleep,
        valid_env,
        mock_session_success,
    ):
        """When each attempt reaches TOTP verify, now() is invoked per attempt."""
        with mock.patch("fyers_token.pyotp.TOTP") as mock_totp_cls:
            inst = mock.Mock()
            inst.now.side_effect = ["111111", "222222"]
            mock_totp_cls.return_value = inst

            # Attempt 1: OTP ok, TOTP ok, PIN ok, then GET 503 (transient)
            # Attempt 2: full success
            mock_post.side_effect = [
                _otp_ok(),
                _totp_ok(),
                _pin_ok(),
                _otp_ok(),
                _totp_ok(),
                _pin_ok(),
            ]
            resp_503 = mock.Mock()
            resp_503.status_code = 503
            resp_503.headers = {}
            resp_503.text = "down"
            resp_503.close = mock.Mock()
            mock_get.side_effect = [resp_503, _authcode_redirect()]

            token = generate_fyers_access_token()
            assert token == FINAL_TOKEN
            assert mock_totp_cls.call_count == 2
            assert inst.now.call_count == 2
            # Capture OTP values sent on verify_otp posts
            totp_otps = [
                c.kwargs["json"]["otp"]
                for c in mock_post.call_args_list
                if c.args and "verify_otp" in c.args[0]
            ]
            assert totp_otps == ["111111", "222222"]


# -----------------------------------------------------------------------------
# FR-008 — Logging WARNING failures / INFO retry schedule
# -----------------------------------------------------------------------------


class TestRetryLogging:
    @mock.patch("fyers_token.time.sleep")
    @mock.patch("fyers_token.random.uniform", return_value=6.5)
    @mock.patch("fyers_token.requests.post")
    def test_transient_failure_logs_warning_and_retry_info(
        self, mock_post, mock_uniform, mock_sleep, valid_env, caplog
    ):
        mock_post.side_effect = requests.Timeout("Gateway timeout")

        with caplog.at_level(logging.INFO, logger="fyers_auth"):
            with pytest.raises(FyersConnectionError) as exc:
                generate_fyers_access_token()

        msg = str(exc.value)
        assert "after 3 attempts" in msg or "maximum retries" in msg.lower()

        warnings = [
            r for r in caplog.records if r.levelno == logging.WARNING
        ]
        infos = [r for r in caplog.records if r.levelno == logging.INFO]
        assert any(
            "transient_failure" in r.getMessage() for r in warnings
        )
        assert any("retry_scheduled" in r.getMessage() for r in infos)
        assert any("delay=" in r.getMessage() for r in infos)
        assert any("attempt=1" in r.getMessage() for r in warnings)
        assert any("attempt=2" in r.getMessage() for r in warnings)
        # M2: final attempt also logged as WARNING
        assert any(
            "transient_failure_final" in r.getMessage() for r in warnings
        )
        assert any("attempt=3" in r.getMessage() for r in warnings)


# -----------------------------------------------------------------------------
# Regression — helpers / permanent error shapes still work
# -----------------------------------------------------------------------------


class TestRegressionHelpers:
    def test_get_base64_string(self):
        import base64

        assert get_base64_string("YJ08718") == base64.b64encode(
            b"YJ08718"
        ).decode()

    @mock.patch("fyers_token.time.sleep")
    @mock.patch("fyers_token.requests.post")
    def test_otp_timeout_maps_to_connection_error(
        self, mock_post, mock_sleep, valid_env
    ):
        mock_post.side_effect = requests.Timeout("Connection timed out")
        with pytest.raises(FyersConnectionError) as exc:
            generate_fyers_access_token()
        assert "Timeout" in str(exc.value) or "Connection failed" in str(
            exc.value
        )
        # Exhausts 3 attempts
        assert mock_post.call_count == 3

    @mock.patch("fyers_token.time.sleep")
    @mock.patch("fyers_token.requests.post")
    @mock.patch("fyers_token.requests.get")
    def test_payload_otp_uses_base64_client_id(
        self,
        mock_get,
        mock_post,
        mock_sleep,
        valid_env,
        mock_totp,
        mock_session_success,
    ):
        mock_post.side_effect = _success_posts()
        mock_get.return_value = _authcode_redirect()
        generate_fyers_access_token()
        otp_payload = mock_post.call_args_list[0].kwargs["json"]
        assert otp_payload["fy_id"] == get_base64_string(
            REQUIRED_ENV["FYERS_CLIENT_ID"]
        )
        assert otp_payload["app_id"] == "2"
