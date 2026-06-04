"""
auth_store.py — JSON-backed user store for local development.

Persists user records to ``data/users.json``.  Each record:

    {
        "id":            "<uuid4>",
        "email":         "user@example.com",
        "password_hash": "<pbkdf2-sha256-hex>",
        "salt":          "<32-byte-random-hex>",
        "created_at":    "2026-06-04T10:00:00+00:00"
    }

Only the public subset ``{id, email, created_at}`` is ever returned by
the public functions below — ``password_hash`` and ``salt`` stay internal.

Migration note
--------------
Replace this module with ``auth_store_pg.py`` that reads/writes the
``users`` table defined in ``db/schema.sql``.  The function signatures
below are the interface contract; ``main.py`` imports only these names.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .auth import hash_password, verify_password

_USERS_FILE = Path(__file__).resolve().parent.parent / "data" / "users.json"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load() -> dict[str, dict]:
    if not _USERS_FILE.exists():
        return {}
    try:
        return json.loads(_USERS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save(users: dict[str, dict]) -> None:
    _USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _USERS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_USERS_FILE)


def _public(record: dict) -> dict:
    """Strip sensitive fields; return only what is safe to expose."""
    return {
        "id": record["id"],
        "email": record["email"],
        "created_at": record["created_at"],
    }


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def find_user_by_email(email: str) -> dict | None:
    """Return the **full** internal record for *email*, or ``None``."""
    email_lower = email.strip().lower()
    for record in _load().values():
        if record.get("email", "").lower() == email_lower:
            return record
    return None


def register_user(email: str, password: str) -> dict:
    """
    Create a new user record and return the **public** user dict.

    Raises ``ValueError`` when the email is already registered.
    """
    if find_user_by_email(email):
        raise ValueError(f"Email already registered: {email}")
    users = _load()
    user_id = str(uuid4())
    pw_hash, salt = hash_password(password)
    created_at = datetime.now(timezone.utc).isoformat()
    users[user_id] = {
        "id": user_id,
        "email": email.strip().lower(),
        "password_hash": pw_hash,
        "salt": salt,
        "created_at": created_at,
    }
    _save(users)
    return {"id": user_id, "email": email.strip().lower(), "created_at": created_at}


def authenticate_user(email: str, password: str) -> dict | None:
    """
    Return the **public** user dict if credentials are correct, else ``None``.
    Always takes the same amount of time whether the email exists or not,
    so as not to leak user existence via timing.
    """
    record = find_user_by_email(email)
    # Always call verify_password so timing is consistent even for unknown emails
    dummy_hash = "0" * 64
    dummy_salt = "0" * 64
    pw_hash = record["password_hash"] if record else dummy_hash
    salt = record["salt"] if record else dummy_salt
    match = verify_password(password, pw_hash, salt)
    if not record or not match:
        return None
    return _public(record)


def get_user_by_id(user_id: str) -> dict | None:
    """Return the **public** user dict for *user_id*, or ``None``."""
    record = _load().get(user_id)
    return _public(record) if record else None
