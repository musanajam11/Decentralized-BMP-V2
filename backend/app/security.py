# Decentralized-BMP V2 — auth primitives
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Argon2id password hashing + JWT issue/verify + FastAPI dependency."""

from __future__ import annotations

import json
import secrets
import time
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher, Type
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Request, status

from . import app_settings, db
from .settings import Settings, get_settings

# Argon2id with parity to BeamNG Mod Registry: 64 MiB, 3 iterations, 4 lanes,
# 32-byte hash. These are above OWASP's 2024 minimums.
_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=64 * 1024,
    parallelism=4,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)

# A pre-computed Argon2id hash of an unguessable random string. Used to keep
# login timing constant when the username is unknown — verifying against this
# costs the same as verifying a real hash, foiling username enumeration via
# timing side-channels.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(32))

TokenType = Literal["access", "refresh"]


# --- passwords ----------------------------------------------------------------

def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, stored_hash: str) -> bool:
    if not stored_hash:
        # Still spend the time to keep the response constant.
        try:
            _hasher.verify(_DUMMY_HASH, plain)
        except Exception:
            pass
        return False
    try:
        return _hasher.verify(stored_hash, plain)
    except VerifyMismatchError:
        return False


def dummy_verify(plain: str) -> None:
    """Spend the cost of an Argon2 verify against a throwaway hash so login
    timings don't reveal whether a username exists."""
    try:
        _hasher.verify(_DUMMY_HASH, plain)
    except Exception:
        pass


def needs_rehash(stored_hash: str) -> bool:
    return _hasher.check_needs_rehash(stored_hash)


# --- account lockout --------------------------------------------------------

def is_locked(user_row: Any) -> bool:
    """`user_row` may be a sqlite3.Row or dict."""
    locked_until = user_row["locked_until"] if "locked_until" in user_row.keys() else None  # type: ignore[union-attr]
    if not locked_until:
        return False
    return int(locked_until) > int(time.time())


def record_failed_login(user_id: int) -> None:
    max_failures, lockout_seconds = app_settings.lockout_policy()
    if max_failures <= 0:
        return  # lockout disabled
    lock_at = int(time.time()) + lockout_seconds
    with db.cursor() as cur:
        cur.execute(
            """UPDATE users
                  SET failed_logins = failed_logins + 1,
                      locked_until  = CASE WHEN failed_logins + 1 >= ? THEN ? ELSE locked_until END
                WHERE id = ?""",
            (max_failures, lock_at, user_id),
        )


def clear_failed_logins(user_id: int) -> None:
    with db.cursor() as cur:
        cur.execute(
            "UPDATE users SET failed_logins = 0, locked_until = NULL WHERE id = ?",
            (user_id,),
        )


# --- audit log --------------------------------------------------------------

def audit(
    *,
    event: str,
    user_id: int | None = None,
    username: str | None = None,
    request: Request | None = None,
    success: bool = True,
    detail: dict | str | None = None,
) -> None:
    """Best-effort append to auth_events. Never raises — failure to log
    must not break a real auth request."""
    try:
        ip = request.client.host if request and request.client else None
        ua = request.headers.get("user-agent") if request else None
        if isinstance(detail, dict):
            detail_text: str | None = json.dumps(detail, separators=(",", ":"))
        else:
            detail_text = detail
        with db.cursor() as cur:
            cur.execute(
                """INSERT INTO auth_events (user_id, username, event, ip, user_agent, success, detail, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    user_id,
                    username,
                    event,
                    ip,
                    ua,
                    1 if success else 0,
                    detail_text,
                    int(time.time()),
                ),
            )
    except Exception:
        pass


# --- JWT ----------------------------------------------------------------------

def _now() -> int:
    return int(time.time())


def issue_token(
    user_id: int,
    username: str,
    role: str,
    *,
    kind: TokenType,
    settings: Settings,
) -> tuple[str, str, int]:
    """Returns (token, jti, exp). Caller persists refresh JTIs to the DB."""
    jti = secrets.token_urlsafe(16)
    if kind == "access":
        exp = _now() + settings.jwt_access_ttl_minutes * 60
    else:
        exp = _now() + settings.jwt_refresh_ttl_days * 86400
    payload = {
        "sub": str(user_id),
        "uname": username,
        "role": role,
        "type": kind,
        "iat": _now(),
        "exp": exp,
        "jti": jti,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    return token, jti, exp


def decode_token(token: str, *, expected_type: TokenType, settings: Settings) -> dict:
    try:
        data = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")
    if data.get("type") != expected_type:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong token type")
    return data


# --- FastAPI dependencies -----------------------------------------------------

def _bearer(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    return auth[7:].strip()


def current_user(request: Request, settings: Settings = Depends(get_settings)) -> dict:
    """Dependency: returns the authenticated user record (dict)."""
    token = _bearer(request)
    data = decode_token(token, expected_type="access", settings=settings)
    user_id = int(data["sub"])
    with db.cursor() as cur:
        row = cur.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user no longer exists")
    return dict(row)


def require_admin(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "ADMIN":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only")
    return user
