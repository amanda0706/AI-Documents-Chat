"""
Tests for the local JWT auth endpoints:
  POST /auth/register
  POST /auth/login
  GET  /auth/me

Covers:
- register creates a user and returns a valid token
- register rejects duplicate emails with 409
- register rejects short passwords with 422
- login with correct credentials returns a token
- login with wrong password returns 401
- login with unknown email returns 401
- /auth/me with a valid token returns the user profile
- /auth/me with no token returns 401
- /auth/me with a malformed token returns 401
- /auth/me with an expired token returns 401
- /auth/me with a tampered token returns 401
- no response ever contains password_hash, salt, or AUTH_SECRET
- token is a three-part JWT with a non-trivial payload
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import auth as auth_module
from backend.app import auth_store as store_module
from backend.app import main
from backend.app.main import app
from backend.app.providers import LocalProvider


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated_users(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect the users JSON file to a per-test temp path."""
    monkeypatch.setattr(store_module, "_USERS_FILE", tmp_path / "users.json")


@pytest.fixture(autouse=True)
def force_local_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "provider", LocalProvider())


@pytest.fixture(autouse=True)
def fixed_auth_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin AUTH_SECRET so tokens are deterministic and independent of env."""
    monkeypatch.setenv("AUTH_SECRET", "test-secret-for-unit-tests-only")


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register(client: TestClient, email: str = "alice@example.com", password: str = "secret123") -> dict:
    resp = client.post("/auth/register", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _token(client: TestClient, email: str = "alice@example.com", password: str = "secret123") -> str:
    _register(client, email, password)
    resp = client.post("/auth/login", json={"email": email, "password": password})
    return resp.json()["access_token"]


def _jwt_payload(token: str) -> dict:
    """Decode the middle part of a JWT without verifying the signature."""
    import base64
    part = token.split(".")[1]
    pad = 4 - len(part) % 4
    return json.loads(base64.urlsafe_b64decode(part + "=" * (pad % 4)))


# ---------------------------------------------------------------------------
# POST /auth/register
# ---------------------------------------------------------------------------


class TestRegister:
    def test_register_returns_200(self, client: TestClient):
        resp = client.post("/auth/register", json={"email": "bob@example.com", "password": "password1"})
        assert resp.status_code == 200

    def test_register_returns_access_token(self, client: TestClient):
        body = _register(client)
        assert "access_token" in body
        assert len(body["access_token"]) > 10

    def test_register_token_type_is_bearer(self, client: TestClient):
        body = _register(client)
        assert body["token_type"] == "bearer"

    def test_register_returns_user_email(self, client: TestClient):
        body = _register(client, email="carol@example.com")
        assert body["user"]["email"] == "carol@example.com"

    def test_register_returns_user_id(self, client: TestClient):
        body = _register(client)
        assert "id" in body["user"]
        assert len(body["user"]["id"]) > 0

    def test_register_never_returns_password_hash(self, client: TestClient):
        body = _register(client)
        raw = json.dumps(body)
        assert "password_hash" not in raw
        assert "salt" not in raw

    def test_register_duplicate_email_returns_409(self, client: TestClient):
        _register(client, "dup@example.com")
        resp = client.post("/auth/register", json={"email": "dup@example.com", "password": "another1"})
        assert resp.status_code == 409

    def test_register_short_password_returns_422(self, client: TestClient):
        resp = client.post("/auth/register", json={"email": "short@example.com", "password": "abc"})
        assert resp.status_code == 422

    def test_register_email_is_case_normalised(self, client: TestClient):
        body = _register(client, email="Mixed@Example.COM")
        assert body["user"]["email"] == "mixed@example.com"

    def test_register_duplicate_different_case_returns_409(self, client: TestClient):
        _register(client, "same@example.com")
        resp = client.post("/auth/register", json={"email": "SAME@EXAMPLE.COM", "password": "secret123"})
        assert resp.status_code == 409

    def test_register_token_is_valid_jwt_structure(self, client: TestClient):
        body = _register(client)
        parts = body["access_token"].split(".")
        assert len(parts) == 3, "token must be a three-part JWT"

    def test_register_token_payload_contains_expected_claims(self, client: TestClient):
        body = _register(client, email="alice@example.com")
        payload = _jwt_payload(body["access_token"])
        assert payload["sub"] == "alice@example.com"
        assert "user_id" in payload
        assert "exp" in payload
        assert "iat" in payload

    def test_register_token_exp_is_in_future(self, client: TestClient):
        body = _register(client)
        payload = _jwt_payload(body["access_token"])
        assert payload["exp"] > int(time.time())


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------


class TestLogin:
    def test_login_valid_credentials_returns_200(self, client: TestClient):
        _register(client)
        resp = client.post("/auth/login", json={"email": "alice@example.com", "password": "secret123"})
        assert resp.status_code == 200

    def test_login_returns_access_token(self, client: TestClient):
        _register(client)
        resp = client.post("/auth/login", json={"email": "alice@example.com", "password": "secret123"})
        assert "access_token" in resp.json()

    def test_login_token_is_valid_jwt(self, client: TestClient):
        _register(client)
        resp = client.post("/auth/login", json={"email": "alice@example.com", "password": "secret123"})
        parts = resp.json()["access_token"].split(".")
        assert len(parts) == 3

    def test_login_wrong_password_returns_401(self, client: TestClient):
        _register(client)
        resp = client.post("/auth/login", json={"email": "alice@example.com", "password": "wrongpass"})
        assert resp.status_code == 401

    def test_login_unknown_email_returns_401(self, client: TestClient):
        resp = client.post("/auth/login", json={"email": "nobody@example.com", "password": "secret123"})
        assert resp.status_code == 401

    def test_login_wrong_and_unknown_return_same_status(self, client: TestClient):
        """Both bad-password and unknown-email must return 401 (no user enumeration)."""
        _register(client, "real@example.com")
        wrong_pw = client.post("/auth/login", json={"email": "real@example.com", "password": "bad"})
        no_user = client.post("/auth/login", json={"email": "ghost@example.com", "password": "secret123"})
        assert wrong_pw.status_code == no_user.status_code == 401

    def test_login_never_returns_password_hash(self, client: TestClient):
        _register(client)
        resp = client.post("/auth/login", json={"email": "alice@example.com", "password": "secret123"})
        raw = json.dumps(resp.json())
        assert "password_hash" not in raw
        assert "salt" not in raw

    def test_login_email_case_insensitive(self, client: TestClient):
        _register(client, "case@example.com")
        resp = client.post("/auth/login", json={"email": "CASE@EXAMPLE.COM", "password": "secret123"})
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /auth/me
# ---------------------------------------------------------------------------


class TestMe:
    def test_me_with_valid_token_returns_200(self, client: TestClient):
        token = _token(client)
        resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_me_returns_correct_email(self, client: TestClient):
        token = _token(client, email="alice@example.com")
        resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.json()["email"] == "alice@example.com"

    def test_me_returns_id(self, client: TestClient):
        token = _token(client)
        resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert "id" in resp.json()

    def test_me_returns_created_at(self, client: TestClient):
        token = _token(client)
        resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert "created_at" in resp.json()

    def test_me_never_returns_password_hash(self, client: TestClient):
        token = _token(client)
        resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        raw = json.dumps(resp.json())
        assert "password_hash" not in raw
        assert "salt" not in raw

    def test_me_with_no_header_returns_401(self, client: TestClient):
        resp = client.get("/auth/me")
        assert resp.status_code == 401

    def test_me_with_empty_bearer_returns_401(self, client: TestClient):
        resp = client.get("/auth/me", headers={"Authorization": "Bearer "})
        assert resp.status_code == 401

    def test_me_with_malformed_token_returns_401(self, client: TestClient):
        resp = client.get("/auth/me", headers={"Authorization": "Bearer not.a.real.token.here"})
        assert resp.status_code == 401

    def test_me_with_wrong_secret_returns_401(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        """Token signed with one secret must be rejected when secret changes."""
        token = _token(client)
        monkeypatch.setenv("AUTH_SECRET", "completely-different-secret-xyz")
        resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401

    def test_me_with_tampered_payload_returns_401(self, client: TestClient):
        """Changing any payload byte must invalidate the signature."""
        import base64
        token = _token(client)
        header, payload_b64, sig = token.split(".")
        # Flip a bit in the payload
        raw = base64.urlsafe_b64decode(payload_b64 + "==")
        tampered = bytearray(raw)
        tampered[0] ^= 0x01
        new_payload = base64.urlsafe_b64encode(bytes(tampered)).rstrip(b"=").decode()
        bad_token = f"{header}.{new_payload}.{sig}"
        resp = client.get("/auth/me", headers={"Authorization": f"Bearer {bad_token}"})
        assert resp.status_code == 401

    def test_me_with_expired_token_returns_401(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        """Token created with an expiry in the past must be rejected."""
        # Freeze time so the token is already expired
        past = int(time.time()) - 3600
        monkeypatch.setattr(auth_module, "TOKEN_EXPIRY_SECONDS", -7200)
        token = _token(client)
        resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Secret leakage checks
# ---------------------------------------------------------------------------


class TestNoSecretLeakage:
    def test_auth_secret_not_in_register_response(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        secret = "super-secret-do-not-leak-xyz"
        monkeypatch.setenv("AUTH_SECRET", secret)
        body = _register(client)
        assert secret not in json.dumps(body)

    def test_auth_secret_not_in_login_response(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        secret = "another-secret-xyz-do-not-leak"
        monkeypatch.setenv("AUTH_SECRET", secret)
        _register(client)
        resp = client.post("/auth/login", json={"email": "alice@example.com", "password": "secret123"})
        assert secret not in json.dumps(resp.json())

    def test_auth_secret_not_in_me_response(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        secret = "yet-another-secret-xyz-leak-test"
        monkeypatch.setenv("AUTH_SECRET", secret)
        token = _token(client)
        resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert secret not in json.dumps(resp.json())

    def test_token_does_not_contain_raw_secret(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        secret = "token-must-not-embed-this-value"
        monkeypatch.setenv("AUTH_SECRET", secret)
        body = _register(client)
        assert secret not in body["access_token"]


# ---------------------------------------------------------------------------
# Dev-secret startup warning
# ---------------------------------------------------------------------------


class TestDevSecretWarning:
    def test_warning_emitted_when_auth_secret_unset(self, monkeypatch: pytest.MonkeyPatch):
        """A UserWarning must be emitted when AUTH_SECRET env var is absent."""
        import warnings as _warnings

        from backend.app.auth import _secret

        monkeypatch.delenv("AUTH_SECRET", raising=False)
        # Use catch_warnings + simplefilter("always") to override Python's
        # per-location deduplication so the warning fires even if _secret()
        # was already called earlier in the test session.
        with _warnings.catch_warnings():
            _warnings.simplefilter("always")
            with pytest.warns(UserWarning, match="AUTH_SECRET env var is not set"):
                _secret()
