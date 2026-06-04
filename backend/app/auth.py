"""
auth.py — JWT token creation/validation and password hashing.

All cryptography uses Python stdlib only; no new pip dependencies are needed.

Token format
------------
Standard three-part JWT (header.payload.signature) signed with HMAC-SHA256.
The token is RFC 7519-compatible and can be verified by any JWT library.

Password hashing
----------------
PBKDF2-SHA256 with 100 000 iterations and a 32-byte random salt.
Meets NIST SP 800-132 recommendations for password-based key derivation.
Timing-attack-safe comparison via ``hmac.compare_digest``.

Security notes for local demo mode
------------------------------------
- AUTH_SECRET falls back to a hardcoded placeholder when the env var is
  absent.  A ``UserWarning`` is raised (once per process) so the gap is
  visible in the startup log.  **Never use the default in production.**
- User records live in ``data/users.json`` — appropriate for a local demo;
  replace with the PostgreSQL ``users`` table before handling real data.
- Token expiry defaults to 24 h (configurable via TOKEN_EXPIRY_SECONDS).

Migration path to production
-----------------------------
- Set AUTH_SECRET to a 256-bit random string (e.g. ``openssl rand -hex 32``).
- Swap ``auth_store.py`` for a PostgreSQL implementation with the same
  function signatures — no endpoint or test changes required.
- Add HTTPS; tokens in Authorization headers are plaintext over HTTP.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import warnings

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEV_SECRET = "luminaclause-dev-secret-do-not-use-in-production"
_PBKDF2_ITERATIONS = 100_000
TOKEN_EXPIRY_SECONDS: int = 60 * 60 * 24  # 24 hours


def _secret() -> str:
    """Return AUTH_SECRET from environment, or the dev placeholder.

    A ``UserWarning`` is emitted (once per process) when the placeholder is
    used so that the gap is visible in the startup log.
    """
    val = os.getenv("AUTH_SECRET", "").strip()
    if not val:
        warnings.warn(
            "AUTH_SECRET env var is not set — using the hardcoded dev placeholder. "
            "Set AUTH_SECRET to a 256-bit random string before deploying.",
            UserWarning,
            stacklevel=2,
        )
        return _DEV_SECRET
    return val


# ---------------------------------------------------------------------------
# Base64url helpers (RFC 4648 §5 — no padding)
# ---------------------------------------------------------------------------

def _b64u_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64u_decode(s: str) -> bytes:
    pad = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * (pad % 4))


# ---------------------------------------------------------------------------
# JWT (HMAC-SHA256 / HS256)
# ---------------------------------------------------------------------------

_JWT_HEADER = _b64u_encode(
    json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode()
)


def create_token(user_id: str, email: str) -> str:
    """
    Return a signed HS256 JWT for the given user.

    Payload claims::

        sub       — email (RFC 7519 subject)
        user_id   — UUID string
        iat       — issued-at (Unix timestamp)
        exp       — expiry  (Unix timestamp)
    """
    payload_bytes = json.dumps(
        {
            "sub": email,
            "user_id": user_id,
            "iat": int(time.time()),
            "exp": int(time.time()) + TOKEN_EXPIRY_SECONDS,
        },
        separators=(",", ":"),
    ).encode()
    payload_b64 = _b64u_encode(payload_bytes)
    signing_input = f"{_JWT_HEADER}.{payload_b64}".encode()
    sig = _b64u_encode(
        hmac.new(_secret().encode(), signing_input, hashlib.sha256).digest()
    )
    return f"{_JWT_HEADER}.{payload_b64}.{sig}"


def decode_token(token: str) -> dict:
    """
    Validate the token signature and expiry; return the payload dict.

    Raises ``ValueError`` for any of:
    - malformed structure (not three dot-separated parts)
    - invalid signature
    - unreadable payload JSON
    - expired token

    Callers should convert ``ValueError`` to HTTP 401.
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Malformed token: expected three dot-separated parts")
    header_b64, payload_b64, sig_b64 = parts

    signing_input = f"{header_b64}.{payload_b64}".encode()
    expected_sig = _b64u_encode(
        hmac.new(_secret().encode(), signing_input, hashlib.sha256).digest()
    )
    if not hmac.compare_digest(expected_sig, sig_b64):
        raise ValueError("Invalid token signature")

    try:
        payload = json.loads(_b64u_decode(payload_b64))
    except Exception as exc:
        raise ValueError("Unreadable token payload") from exc

    if payload.get("exp", 0) < int(time.time()):
        raise ValueError("Token has expired")

    return payload


# ---------------------------------------------------------------------------
# Password hashing (PBKDF2-SHA256)
# ---------------------------------------------------------------------------

def hash_password(password: str) -> tuple[str, str]:
    """
    Return ``(password_hash_hex, salt_hex)`` for the given plaintext password.

    Both values are hex-encoded so they are JSON-serialisable and safe to
    store in ``data/users.json`` or the ``users.password_hash`` / ``users.salt``
    columns in the production PostgreSQL schema.
    """
    salt_bytes = os.urandom(32)
    hash_bytes = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt_bytes, _PBKDF2_ITERATIONS
    )
    return hash_bytes.hex(), salt_bytes.hex()


def verify_password(password: str, stored_hash: str, salt_hex: str) -> bool:
    """
    Return ``True`` iff *password* matches *stored_hash* / *salt_hex*.

    Uses ``hmac.compare_digest`` to prevent timing attacks.
    """
    try:
        salt_bytes = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    expected = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt_bytes, _PBKDF2_ITERATIONS
    ).hex()
    return hmac.compare_digest(expected, stored_hash)
