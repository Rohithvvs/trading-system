"""Automated tests for Sprint 2 – Core TOTP Token Generation (007-fyers-totp-token).

Specification source of truth: specs/007-fyers-totp-token/spec.md
All network and SDK interactions are mocked; suite is offline-safe.
"""

from __future__ import annotations

import base64
import concurrent.futures
import logging
import os
import sys
import time
from unittest import mock

import pytest
import requests

from fyers_token import (
    REQUEST_TIMEOUT_SEC,
    FyersAuthError,
    FyersConfigError,
    FyersConnectionError,
    _redact_sensitive,
    generate_fyers_access_token,
    get_base64_string,
    load_fyers_config,
    logger as fyers_logger,
)

# -----------------------------------------------------------------------------
# Shared fixtures / helpers
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
    json_body: dict | None = None,
) -> mock.Mock:
    if location is None:
        location = (
            f"{DEFAULT_REDIRECT}?auth_code={AUTH_CODE}&state=sample_state"
        )
    resp = mock.Mock()
    resp.status_code = status_code
    resp.headers = {"Location": location} if location else {}
    resp.text = "redirect"
    if json_body is not None:
        resp.json.return_value = json_body
    else:
        resp.json.side_effect = ValueError("no json")
    return resp


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
# Unit Tests — helpers & configuration
# -----------------------------------------------------------------------------


class TestGetBase64String:
    def test_encodes_client_id(self):
        raw = "YJ08718"
        expected = base64.b64encode(raw.encode("utf-8")).decode("utf-8")
        assert get_base64_string(raw) == expected

    def test_encodes_numeric_pin(self):
        assert get_base64_string("1234") == base64.b64encode(b"1234").decode(
            "utf-8"
        )

    def test_encodes_empty_string(self):
        assert get_base64_string("") == base64.b64encode(b"").decode("utf-8")


class TestRedactSensitive:
    def test_redacts_auth_code_query_param(self):
        text = f"{DEFAULT_REDIRECT}?auth_code=supersecret&state=x"
        out = _redact_sensitive(text)
        assert "supersecret" not in out
        assert "auth_code=<redacted>" in out

    def test_redacts_bearer_token(self):
        out = _redact_sensitive("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abc")
        assert "eyJhbGciOiJIUzI1NiJ9" not in out
        assert "Bearer <redacted>" in out


class TestLoadFyersConfig:
    def test_success_returns_all_required_keys(self, valid_env):
        config = load_fyers_config()
        for key, value in REQUIRED_ENV.items():
            assert config[key] == value

    def test_default_redirect_uri_when_unset(self, valid_env):
        config = load_fyers_config()
        assert config["FYERS_REDIRECT_URI"] == DEFAULT_REDIRECT

    def test_custom_redirect_uri_override(self):
        env = {**REQUIRED_ENV, "FYERS_REDIRECT_URI": "https://example.com/cb"}
        with mock.patch.dict(os.environ, env, clear=True):
            config = load_fyers_config()
        assert config["FYERS_REDIRECT_URI"] == "https://example.com/cb"

    def test_accepts_fyers_secret_id_alias(self):
        env = {k: v for k, v in REQUIRED_ENV.items() if k != "FYERS_APP_SECRET"}
        env["FYERS_SECRET_ID"] = "alias_secret_value"
        with mock.patch.dict(os.environ, env, clear=True):
            config = load_fyers_config()
        assert config["FYERS_APP_SECRET"] == "alias_secret_value"

    def test_prefers_fyers_app_secret_over_alias(self):
        env = {
            **REQUIRED_ENV,
            "FYERS_APP_SECRET": "primary_secret",
            "FYERS_SECRET_ID": "alias_secret",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            config = load_fyers_config()
        assert config["FYERS_APP_SECRET"] == "primary_secret"

    @pytest.mark.parametrize(
        "missing_key",
        [
            "FYERS_CLIENT_ID",
            "FYERS_APP_ID",
            "FYERS_APP_SECRET",
            "FYERS_TOTP_SECRET",
            "FYERS_PIN",
        ],
    )
    def test_missing_required_env_raises_config_error(self, missing_key):
        env = {k: v for k, v in REQUIRED_ENV.items() if k != missing_key}
        with mock.patch.dict(os.environ, env, clear=True):
            with pytest.raises(FyersConfigError) as exc_info:
                load_fyers_config()
        # APP_SECRET missing may mention alias in message
        if missing_key == "FYERS_APP_SECRET":
            assert "FYERS_APP_SECRET" in str(exc_info.value)
        else:
            assert missing_key in str(exc_info.value)

    @pytest.mark.parametrize(
        "empty_key,empty_value",
        [
            ("FYERS_CLIENT_ID", ""),
            ("FYERS_APP_SECRET", "   "),
            ("FYERS_TOTP_SECRET", "  \n"),
        ],
    )
    def test_empty_or_whitespace_only_env_raises_config_error(
        self, empty_key, empty_value
    ):
        env = {**REQUIRED_ENV, empty_key: empty_value}
        with mock.patch.dict(os.environ, env, clear=True):
            with pytest.raises(FyersConfigError) as exc_info:
                load_fyers_config()
        assert empty_key in str(exc_info.value)

    def test_strips_whitespace_from_env_values(self):
        env = {
            "FYERS_CLIENT_ID": "  YJ08718  ",
            "FYERS_APP_ID": "\tL9NY305RTW-100\n",
            "FYERS_APP_SECRET": " secret123 ",
            "FYERS_TOTP_SECRET": " MFRGGZDFMZTWQ2LK ",
            "FYERS_PIN": " 1234 ",
            "FYERS_REDIRECT_URI": "  https://example.com/cb  ",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            config = load_fyers_config()
        assert config["FYERS_CLIENT_ID"] == "YJ08718"
        assert config["FYERS_APP_ID"] == "L9NY305RTW-100"
        assert config["FYERS_APP_SECRET"] == "secret123"
        assert config["FYERS_TOTP_SECRET"] == "MFRGGZDFMZTWQ2LK"
        assert config["FYERS_PIN"] == "1234"
        assert config["FYERS_REDIRECT_URI"] == "https://example.com/cb"

    @pytest.mark.parametrize("bad_pin", ["12", "12345", "abcdef", "12ab"])
    def test_invalid_pin_format_raises_config_error(self, bad_pin):
        env = {**REQUIRED_ENV, "FYERS_PIN": bad_pin}
        with mock.patch.dict(os.environ, env, clear=True):
            with pytest.raises(FyersConfigError) as exc_info:
                load_fyers_config()
        assert "PIN" in str(exc_info.value)

    def test_six_digit_pin_accepted(self):
        env = {**REQUIRED_ENV, "FYERS_PIN": "123456"}
        with mock.patch.dict(os.environ, env, clear=True):
            config = load_fyers_config()
        assert config["FYERS_PIN"] == "123456"

    def test_config_error_fails_fast_under_100ms(self):
        """SC-002: missing env fails within 100ms without network I/O."""
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch("fyers_token.requests.post") as mock_post:
                with mock.patch("fyers_token.requests.get") as mock_get:
                    start = time.perf_counter()
                    with pytest.raises(FyersConfigError):
                        generate_fyers_access_token()
                    elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 100
        mock_post.assert_not_called()
        mock_get.assert_not_called()


class TestExceptionHierarchy:
    def test_domain_exceptions_are_standard_exceptions(self):
        assert issubclass(FyersConfigError, Exception)
        assert issubclass(FyersAuthError, Exception)
        assert issubclass(FyersConnectionError, Exception)

    def test_connection_error_does_not_subclass_builtin(self):
        assert not issubclass(FyersConnectionError, ConnectionError)


class TestLoggingSetup:
    def test_library_logger_has_no_stdout_stream_handler(self):
        for h in fyers_logger.handlers:
            if isinstance(h, logging.StreamHandler):
                stream = getattr(h, "stream", None)
                assert stream is not sys.stdout


# -----------------------------------------------------------------------------
# Integration — happy path
# -----------------------------------------------------------------------------


class TestGenerateTokenSuccess:
    @mock.patch("fyers_token.requests.post")
    @mock.patch("fyers_token.requests.get")
    def test_full_flow_returns_access_token(
        self, mock_get, mock_post, valid_env, mock_totp, mock_session_success
    ):
        mock_post.side_effect = [_otp_ok(), _totp_ok(), _pin_ok()]
        mock_get.return_value = _authcode_redirect()

        token = generate_fyers_access_token()
        assert token == FINAL_TOKEN
        assert isinstance(token, str)

    @mock.patch("fyers_token.requests.post")
    @mock.patch("fyers_token.requests.get")
    def test_http_calls_include_timeout(
        self, mock_get, mock_post, valid_env, mock_totp, mock_session_success
    ):
        mock_post.side_effect = [_otp_ok(), _totp_ok(), _pin_ok()]
        mock_get.return_value = _authcode_redirect()

        generate_fyers_access_token()

        for call in mock_post.call_args_list:
            assert call.kwargs.get("timeout") == REQUEST_TIMEOUT_SEC
        assert mock_get.call_args.kwargs.get("timeout") == REQUEST_TIMEOUT_SEC

    @mock.patch("fyers_token.requests.post")
    @mock.patch("fyers_token.requests.get")
    def test_otp_payload_uses_base64_client_id_and_app_id_two(
        self, mock_get, mock_post, valid_env, mock_totp, mock_session_success
    ):
        mock_post.side_effect = [_otp_ok(), _totp_ok(), _pin_ok()]
        mock_get.return_value = _authcode_redirect()

        generate_fyers_access_token()

        otp_call = mock_post.call_args_list[0]
        assert "send_login_otp_v2" in otp_call.args[0]
        payload = otp_call.kwargs["json"]
        assert payload["app_id"] == "2"
        assert payload["fy_id"] == get_base64_string(REQUIRED_ENV["FYERS_CLIENT_ID"])

    @mock.patch("fyers_token.requests.post")
    @mock.patch("fyers_token.requests.get")
    def test_totp_payload_includes_generated_otp(
        self, mock_get, mock_post, valid_env, mock_totp, mock_session_success
    ):
        _, totp_inst = mock_totp
        mock_post.side_effect = [_otp_ok(), _totp_ok(), _pin_ok()]
        mock_get.return_value = _authcode_redirect()

        generate_fyers_access_token()

        totp_call = mock_post.call_args_list[1]
        assert "verify_otp" in totp_call.args[0]
        assert totp_call.kwargs["json"] == {
            "request_key": "key_1",
            "otp": "123456",
        }
        totp_inst.now.assert_called()

    @mock.patch("fyers_token.requests.post")
    @mock.patch("fyers_token.requests.get")
    def test_pin_payload_uses_base64_pin(
        self, mock_get, mock_post, valid_env, mock_totp, mock_session_success
    ):
        mock_post.side_effect = [_otp_ok(), _totp_ok(), _pin_ok()]
        mock_get.return_value = _authcode_redirect()

        generate_fyers_access_token()

        pin_call = mock_post.call_args_list[2]
        assert "verify_pin_v2" in pin_call.args[0]
        payload = pin_call.kwargs["json"]
        assert payload["request_key"] == "key_2"
        assert payload["identity_type"] == "pin"
        assert payload["identifier"] == get_base64_string(REQUIRED_ENV["FYERS_PIN"])

    @mock.patch("fyers_token.requests.post")
    @mock.patch("fyers_token.requests.get")
    def test_authcode_request_uses_bearer_and_disables_redirects(
        self, mock_get, mock_post, valid_env, mock_totp, mock_session_success
    ):
        mock_post.side_effect = [_otp_ok(), _totp_ok(), _pin_ok()]
        mock_get.return_value = _authcode_redirect()

        generate_fyers_access_token()

        get_kwargs = mock_get.call_args.kwargs
        assert get_kwargs["allow_redirects"] is False
        assert get_kwargs["headers"]["Authorization"] == f"Bearer {TEMP_TOKEN}"
        params = get_kwargs["params"]
        assert params["client_id"] == REQUIRED_ENV["FYERS_APP_ID"]
        assert params["response_type"] == "code"
        assert params["state"] == "sample_state"
        assert params["redirect_uri"] == DEFAULT_REDIRECT
        assert "generate-authcode" in mock_get.call_args.args[0]

    @mock.patch("fyers_token.requests.post")
    @mock.patch("fyers_token.requests.get")
    def test_authcode_fallback_from_json_body_when_no_location(
        self, mock_get, mock_post, valid_env, mock_totp, mock_session_success
    ):
        mock_post.side_effect = [_otp_ok(), _totp_ok(), _pin_ok()]
        redirect = f"{DEFAULT_REDIRECT}?auth_code={AUTH_CODE}&state=sample_state"
        mock_get.return_value = _authcode_redirect(
            location="",
            status_code=200,
            json_body={"data": {"redirect_uri": redirect}},
        )
        mock_get.return_value.headers = {}

        token = generate_fyers_access_token()
        assert token == FINAL_TOKEN

    @mock.patch("fyers_token.requests.post")
    @mock.patch("fyers_token.requests.get")
    def test_session_model_receives_auth_code(
        self, mock_get, mock_post, valid_env, mock_totp, mock_session_success
    ):
        mock_cls, session_inst = mock_session_success
        mock_post.side_effect = [_otp_ok(), _totp_ok(), _pin_ok()]
        mock_get.return_value = _authcode_redirect()

        generate_fyers_access_token()

        mock_cls.assert_called_once_with(
            client_id=REQUIRED_ENV["FYERS_APP_ID"],
            secret_key=REQUIRED_ENV["FYERS_APP_SECRET"],
            redirect_uri=DEFAULT_REDIRECT,
            response_type="code",
            grant_type="authorization_code",
        )
        session_inst.set_token.assert_called_once_with(AUTH_CODE)
        session_inst.generate_token.assert_called_once()

    @mock.patch("fyers_token.requests.post")
    @mock.patch("fyers_token.requests.get")
    def test_works_with_secret_id_alias(
        self, mock_get, mock_post, mock_totp, mock_session_success
    ):
        env = {k: v for k, v in REQUIRED_ENV.items() if k != "FYERS_APP_SECRET"}
        env["FYERS_SECRET_ID"] = "from_backend_alias"
        mock_post.side_effect = [_otp_ok(), _totp_ok(), _pin_ok()]
        mock_get.return_value = _authcode_redirect()
        with mock.patch.dict(os.environ, env, clear=True):
            token = generate_fyers_access_token()
        assert token == FINAL_TOKEN


# -----------------------------------------------------------------------------
# Failure Path Tests
# -----------------------------------------------------------------------------


class TestAuthFailures:
    @mock.patch("fyers_token.requests.post")
    def test_otp_request_api_error_raises_auth_error(self, mock_post, valid_env):
        mock_post.return_value = _json_response(
            {"s": "error", "message": "Invalid User ID"}
        )
        with pytest.raises(FyersAuthError) as exc_info:
            generate_fyers_access_token()
        assert "Invalid User ID" in str(exc_info.value)

    @mock.patch("fyers_token.requests.post")
    def test_otp_missing_request_key_raises_auth_error(self, mock_post, valid_env):
        mock_post.return_value = _json_response({"s": "ok", "code": 200})
        with pytest.raises(FyersAuthError) as exc_info:
            generate_fyers_access_token()
        assert "request_key" in str(exc_info.value).lower()

    @mock.patch("fyers_token.requests.post")
    def test_otp_invalid_json_raises_auth_error(self, mock_post, valid_env):
        resp = mock.Mock()
        resp.raise_for_status = mock.Mock()
        resp.json.side_effect = ValueError("bad json")
        resp.text = "not-json-with-secret=should-not-leak"
        mock_post.return_value = resp
        with pytest.raises(FyersAuthError) as exc_info:
            generate_fyers_access_token()
        assert "Invalid JSON" in str(exc_info.value)
        assert "should-not-leak" not in str(exc_info.value)

    @mock.patch("fyers_token.requests.post")
    @mock.patch("fyers_token.time.sleep")
    def test_invalid_pin_raises_auth_error(
        self, mock_sleep, mock_post, valid_env, mock_totp
    ):
        mock_post.side_effect = [
            _otp_ok(),
            _totp_ok(),
            _json_response({"s": "error", "message": "Invalid PIN"}),
        ]
        with pytest.raises(FyersAuthError) as exc_info:
            generate_fyers_access_token()
        assert "PIN" in str(exc_info.value)
        assert "Invalid PIN" in str(exc_info.value)

    @mock.patch("fyers_token.requests.post")
    @mock.patch("fyers_token.time.sleep")
    def test_pin_missing_temp_token_raises_auth_error(
        self, mock_sleep, mock_post, valid_env, mock_totp
    ):
        mock_post.side_effect = [
            _otp_ok(),
            _totp_ok(),
            _json_response({"s": "ok", "data": {}}),
        ]
        with pytest.raises(FyersAuthError) as exc_info:
            generate_fyers_access_token()
        assert "access_token" in str(exc_info.value)

    @mock.patch("fyers_token.requests.post")
    @mock.patch("fyers_token.time.sleep")
    def test_totp_fails_after_retry_raises_auth_error(
        self, mock_sleep, mock_post, valid_env, mock_totp
    ):
        fail = _json_response({"s": "error", "message": "OTP incorrect"})
        mock_post.side_effect = [_otp_ok(), fail, fail]
        with pytest.raises(FyersAuthError) as exc_info:
            generate_fyers_access_token()
        assert "TOTP verification failed after retry" in str(exc_info.value)
        mock_sleep.assert_called_once()

    @mock.patch("fyers_token.requests.post")
    def test_invalid_totp_secret_format_raises_config_error(
        self, mock_post, valid_env
    ):
        mock_post.return_value = _otp_ok()
        with mock.patch("fyers_token.pyotp.TOTP", side_effect=ValueError("bad base32")):
            with pytest.raises(FyersConfigError) as exc_info:
                generate_fyers_access_token()
        assert "TOTP secret" in str(exc_info.value)

    @mock.patch("fyers_token.requests.post")
    @mock.patch("fyers_token.requests.get")
    def test_authcode_redirect_missing_raises_auth_error(
        self, mock_get, mock_post, valid_env, mock_totp
    ):
        mock_post.side_effect = [_otp_ok(), _totp_ok(), _pin_ok()]
        resp = mock.Mock()
        resp.status_code = 200
        resp.headers = {}
        resp.json.return_value = {}
        resp.text = "Error landing page with auth_code=leakme"
        mock_get.return_value = resp

        with pytest.raises(FyersAuthError) as exc_info:
            generate_fyers_access_token()
        msg = str(exc_info.value)
        assert "Redirect Location not found" in msg
        assert "leakme" not in msg

    @mock.patch("fyers_token.requests.post")
    @mock.patch("fyers_token.requests.get")
    def test_authcode_missing_query_param_does_not_leak_url(
        self, mock_get, mock_post, valid_env, mock_totp
    ):
        mock_post.side_effect = [_otp_ok(), _totp_ok(), _pin_ok()]
        mock_get.return_value = _authcode_redirect(
            location=f"{DEFAULT_REDIRECT}?state=sample_state&other=xyz"
        )

        with pytest.raises(FyersAuthError) as exc_info:
            generate_fyers_access_token()
        msg = str(exc_info.value)
        assert "auth_code" in msg
        # Full redirect URL must not be dumped (path only is ok)
        assert "sample_state" not in msg
        assert "other=xyz" not in msg

    @mock.patch("fyers_token.requests.post")
    @mock.patch("fyers_token.requests.get")
    def test_authcode_5xx_raises_connection_error(
        self, mock_get, mock_post, valid_env, mock_totp
    ):
        mock_post.side_effect = [_otp_ok(), _totp_ok(), _pin_ok()]
        resp = mock.Mock()
        resp.status_code = 503
        resp.headers = {}
        resp.text = "Service Unavailable"
        mock_get.return_value = resp

        with pytest.raises(FyersConnectionError) as exc_info:
            generate_fyers_access_token()
        assert "503" in str(exc_info.value) or "server error" in str(
            exc_info.value
        ).lower()

    @mock.patch("fyers_token.requests.post")
    @mock.patch("fyers_token.requests.get")
    def test_authcode_4xx_raises_auth_error(
        self, mock_get, mock_post, valid_env, mock_totp
    ):
        mock_post.side_effect = [_otp_ok(), _totp_ok(), _pin_ok()]
        resp = mock.Mock()
        resp.status_code = 401
        resp.headers = {}
        resp.text = "Unauthorized"
        mock_get.return_value = resp

        with pytest.raises(FyersAuthError) as exc_info:
            generate_fyers_access_token()
        assert "401" in str(exc_info.value)

    @mock.patch("fyers_token.requests.post")
    @mock.patch("fyers_token.requests.get")
    def test_token_exchange_api_failure_raises_auth_error(
        self, mock_get, mock_post, valid_env, mock_totp
    ):
        mock_post.side_effect = [_otp_ok(), _totp_ok(), _pin_ok()]
        mock_get.return_value = _authcode_redirect()
        with mock.patch("fyers_token.fyersModel.SessionModel") as mock_cls:
            inst = mock.Mock()
            inst.generate_token.return_value = {
                "s": "error",
                "message": "Invalid auth code",
            }
            mock_cls.return_value = inst
            with pytest.raises(FyersAuthError) as exc_info:
                generate_fyers_access_token()
        assert "Token exchange failed" in str(exc_info.value)

    @mock.patch("fyers_token.requests.post")
    @mock.patch("fyers_token.requests.get")
    def test_token_exchange_missing_access_token_raises_auth_error(
        self, mock_get, mock_post, valid_env, mock_totp
    ):
        mock_post.side_effect = [_otp_ok(), _totp_ok(), _pin_ok()]
        mock_get.return_value = _authcode_redirect()
        with mock.patch("fyers_token.fyersModel.SessionModel") as mock_cls:
            inst = mock.Mock()
            inst.generate_token.return_value = {"s": "ok"}
            mock_cls.return_value = inst
            with pytest.raises(FyersAuthError) as exc_info:
                generate_fyers_access_token()
        assert "Final access token" in str(exc_info.value)

    @mock.patch("fyers_token.requests.post")
    @mock.patch("fyers_token.requests.get")
    def test_session_model_exception_raises_auth_error(
        self, mock_get, mock_post, valid_env, mock_totp
    ):
        mock_post.side_effect = [_otp_ok(), _totp_ok(), _pin_ok()]
        mock_get.return_value = _authcode_redirect()
        with mock.patch(
            "fyers_token.fyersModel.SessionModel",
            side_effect=RuntimeError("SDK boom"),
        ):
            with pytest.raises(FyersAuthError) as exc_info:
                generate_fyers_access_token()
        assert "SessionModel" in str(exc_info.value)


class TestConnectionFailures:
    @mock.patch("fyers_token.requests.post")
    def test_otp_timeout_raises_connection_error(self, mock_post, valid_env):
        mock_post.side_effect = requests.Timeout("Connection timed out")
        with pytest.raises(FyersConnectionError) as exc_info:
            generate_fyers_access_token()
        assert "Timeout" in str(exc_info.value) or "Connection failed" in str(
            exc_info.value
        )

    @mock.patch("fyers_token.requests.post")
    def test_otp_http_error_raises_connection_error(self, mock_post, valid_env):
        resp = mock.Mock()
        resp.status_code = 503
        resp.raise_for_status.side_effect = requests.HTTPError(
            "503 Server Error", response=resp
        )
        mock_post.return_value = resp
        with pytest.raises(FyersConnectionError) as exc_info:
            generate_fyers_access_token()
        assert "OTP" in str(exc_info.value)

    @mock.patch("fyers_token.requests.post")
    def test_totp_connection_error(self, mock_post, valid_env, mock_totp):
        mock_post.side_effect = [
            _otp_ok(),
            requests.ConnectionError("DNS failure"),
        ]
        with pytest.raises(FyersConnectionError) as exc_info:
            generate_fyers_access_token()
        assert "TOTP" in str(exc_info.value)

    @mock.patch("fyers_token.requests.post")
    @mock.patch("fyers_token.time.sleep")
    def test_totp_retry_connection_error(
        self, mock_sleep, mock_post, valid_env, mock_totp
    ):
        fail = _json_response({"s": "error", "message": "OTP expired"})
        mock_post.side_effect = [
            _otp_ok(),
            fail,
            requests.Timeout("retry timeout"),
        ]
        with pytest.raises(FyersConnectionError) as exc_info:
            generate_fyers_access_token()
        assert "retry" in str(exc_info.value).lower()

    @mock.patch("fyers_token.requests.post")
    def test_pin_connection_error(self, mock_post, valid_env, mock_totp):
        mock_post.side_effect = [
            _otp_ok(),
            _totp_ok(),
            requests.Timeout("PIN timeout"),
        ]
        with pytest.raises(FyersConnectionError) as exc_info:
            generate_fyers_access_token()
        assert "PIN" in str(exc_info.value)

    @mock.patch("fyers_token.requests.post")
    @mock.patch("fyers_token.requests.get")
    def test_authcode_connection_error(
        self, mock_get, mock_post, valid_env, mock_totp
    ):
        mock_post.side_effect = [_otp_ok(), _totp_ok(), _pin_ok()]
        mock_get.side_effect = requests.ConnectionError("network down")
        with pytest.raises(FyersConnectionError) as exc_info:
            generate_fyers_access_token()
        assert "authorization code" in str(exc_info.value).lower()

    @mock.patch("fyers_token.requests.post")
    @mock.patch("fyers_token.requests.get")
    def test_sdk_timeout_raises_connection_error(
        self, mock_get, mock_post, valid_env, mock_totp
    ):
        mock_post.side_effect = [_otp_ok(), _totp_ok(), _pin_ok()]
        mock_get.return_value = _authcode_redirect()

        with mock.patch(
            "fyers_token.concurrent.futures.ThreadPoolExecutor"
        ) as mock_pool_cls:
            mock_pool = mock.MagicMock()
            mock_pool_cls.return_value = mock_pool
            future = mock.Mock()
            future.result.side_effect = concurrent.futures.TimeoutError()
            mock_pool.submit.return_value = future

            with pytest.raises(FyersConnectionError) as exc_info:
                generate_fyers_access_token()
        assert "token exchange" in str(exc_info.value).lower()
        mock_pool.shutdown.assert_called_with(wait=False, cancel_futures=True)


# -----------------------------------------------------------------------------
# Edge Cases — TOTP window retry
# -----------------------------------------------------------------------------


class TestTotpRetryEdgeCases:
    @mock.patch("fyers_token.requests.post")
    @mock.patch("fyers_token.requests.get")
    @mock.patch("fyers_token.time.sleep")
    def test_totp_retry_then_full_success(
        self, mock_sleep, mock_get, mock_post, valid_env, mock_totp, mock_session_success
    ):
        fail = _json_response({"s": "error", "message": "OTP expired"})
        mock_post.side_effect = [_otp_ok(), fail, _totp_ok(), _pin_ok()]
        mock_get.return_value = _authcode_redirect()

        token = generate_fyers_access_token()
        assert token == FINAL_TOKEN
        mock_sleep.assert_called_once()
        assert mock_post.call_count == 4

    @mock.patch("fyers_token.requests.post")
    @mock.patch("fyers_token.time.sleep")
    def test_totp_retry_regenerates_otp_code(
        self, mock_sleep, mock_post, valid_env, mock_totp
    ):
        """Capture OTP at call time — each request uses a fresh payload dict."""
        _, totp_inst = mock_totp
        totp_inst.now.side_effect = ["111111", "222222"]
        fail = _json_response({"s": "error", "message": "OTP expired"})
        pin_fail = _json_response({"s": "error", "message": "stop"})
        responses = iter([_otp_ok(), fail, _totp_ok(), pin_fail])
        otps_seen: list[str] = []

        def post_side(*args, **kwargs):
            if args and "verify_otp" in args[0]:
                otps_seen.append(kwargs["json"]["otp"])
            return next(responses)

        mock_post.side_effect = post_side

        with pytest.raises(FyersAuthError):
            generate_fyers_access_token()

        assert totp_inst.now.call_count == 2
        assert otps_seen == ["111111", "222222"]
        mock_sleep.assert_called_once()

    @mock.patch("fyers_token.requests.post")
    @mock.patch("fyers_token.time.sleep")
    def test_totp_success_missing_request_key(
        self, mock_sleep, mock_post, valid_env, mock_totp
    ):
        mock_post.side_effect = [
            _otp_ok(),
            _json_response({"s": "ok", "code": 200}),
        ]
        with pytest.raises(FyersAuthError) as exc_info:
            generate_fyers_access_token()
        assert "request_key" in str(exc_info.value).lower()


# -----------------------------------------------------------------------------
# Observability — logging without secrets
# -----------------------------------------------------------------------------


class TestLoggingNoSecrets:
    @mock.patch("fyers_token.requests.post")
    @mock.patch("fyers_token.requests.get")
    def test_success_logs_steps_without_sensitive_values(
        self,
        mock_get,
        mock_post,
        valid_env,
        mock_totp,
        mock_session_success,
        caplog,
    ):
        mock_post.side_effect = [_otp_ok(), _totp_ok(), _pin_ok()]
        mock_get.return_value = _authcode_redirect()

        with caplog.at_level(logging.INFO, logger="fyers_auth"):
            generate_fyers_access_token()

        joined = " ".join(caplog.messages)
        assert "step=otp_request" in joined or "step=token_exchange" in joined
        for secret in (
            REQUIRED_ENV["FYERS_APP_SECRET"],
            REQUIRED_ENV["FYERS_TOTP_SECRET"],
            REQUIRED_ENV["FYERS_PIN"],
            "123456",
            TEMP_TOKEN,
            FINAL_TOKEN,
            AUTH_CODE,
        ):
            assert secret not in joined
            assert secret not in caplog.text


# -----------------------------------------------------------------------------
# CLI Interface
# -----------------------------------------------------------------------------


def _execute_cli_entrypoint():
    """Mirror fyers_token.py __main__ contract for offline unit tests."""
    import fyers_token as mod

    try:
        token = mod.generate_fyers_access_token()
        print(token)
        raise SystemExit(0)
    except Exception as e:
        sys.stderr.write(f"Error: {e.__class__.__name__} - {str(e)}\n")
        raise SystemExit(1)


class TestCliEntryPoint:
    def test_cli_success_prints_token_to_stdout_and_exits_zero(self, capsys):
        with mock.patch(
            "fyers_token.generate_fyers_access_token",
            return_value=FINAL_TOKEN,
        ):
            with pytest.raises(SystemExit) as exc_info:
                _execute_cli_entrypoint()
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == FINAL_TOKEN
        assert captured.err == ""

    def test_cli_error_writes_exception_to_stderr_and_exits_nonzero(self, capsys):
        with mock.patch(
            "fyers_token.generate_fyers_access_token",
            side_effect=FyersAuthError("PIN verification failed"),
        ):
            with pytest.raises(SystemExit) as exc_info:
                _execute_cli_entrypoint()
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "FyersAuthError" in captured.err
        assert "PIN verification failed" in captured.err
        assert captured.out == ""

    def test_cli_config_error_format(self, capsys):
        with mock.patch(
            "fyers_token.generate_fyers_access_token",
            side_effect=FyersConfigError(
                "Missing required environment variable: FYERS_PIN"
            ),
        ):
            with pytest.raises(SystemExit) as exc_info:
                _execute_cli_entrypoint()
        assert exc_info.value.code == 1
        err = capsys.readouterr().err
        assert err.startswith("Error: FyersConfigError - ")
        assert "FYERS_PIN" in err

    def test_module_source_defines_cli_main_guard(self):
        import fyers_token as mod

        with open(mod.__file__, encoding="utf-8") as f:
            source = f.read()
        assert 'if __name__ == "__main__"' in source
        assert "sys.exit(0)" in source
        assert "sys.exit(1)" in source
        assert "sys.stderr.write" in source
        assert "_configure_cli_logging" in source


# -----------------------------------------------------------------------------
# Regression / constitution checks (SC-004)
# -----------------------------------------------------------------------------


class TestNoBrowserAutomation:
    def test_module_does_not_import_browser_automation(self):
        import fyers_token as mod

        with open(mod.__file__, encoding="utf-8") as f:
            source = f.read().lower()
        for banned in (
            "playwright",
            "selenium",
            "puppeteer",
            "webdriver",
            "chromium",
            "pyppeteer",
        ):
            assert banned not in source

    def test_generate_does_not_invoke_browser_libraries(
        self, valid_env, mock_totp, mock_session_success
    ):
        with mock.patch("fyers_token.requests.post") as mock_post:
            with mock.patch("fyers_token.requests.get") as mock_get:
                mock_post.side_effect = [_otp_ok(), _totp_ok(), _pin_ok()]
                mock_get.return_value = _authcode_redirect()
                generate_fyers_access_token()
        assert mock_post.call_count == 3
        assert mock_get.call_count == 1
