# Decentralized-BMP V2 — auth router
# SPDX-License-Identifier: AGPL-3.0-or-later
"""/auth — register / login / refresh / logout / me."""

from __future__ import annotations

import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field

from .. import app_settings, db, security, turnstile
from ..settings import Settings, get_settings
from . import invites

router = APIRouter(prefix="/auth", tags=["auth"])

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_-]{3,32}$")


class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    email: EmailStr | None = None
    password: str = Field(min_length=8, max_length=256)  # backend re-validates against runtime policy
    invite_code: str | None = None
    turnstile_token: str | None = None


class LoginIn(BaseModel):
    username: str
    password: str
    turnstile_token: str | None = None


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


def _client_ip(request: Request) -> str | None:
    return request.client.host if request and request.client else None


async def _enforce_turnstile(action: str, token: str | None, request: Request) -> None:
    if not app_settings.turnstile_required_for(action):
        return
    res = await turnstile.verify(token, _client_ip(request))
    if not res["ok"]:
        security.audit(
            event=f"{action}.captcha_failed",
            request=request,
            success=False,
            detail={"reason": res["reason"]},
        )
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "captcha_failed")


def _issue_pair(user: dict, settings: Settings) -> TokenPair:
    access, _, _ = security.issue_token(
        user["id"], user["username"], user["role"], kind="access", settings=settings
    )
    refresh, jti, exp = security.issue_token(
        user["id"], user["username"], user["role"], kind="refresh", settings=settings
    )
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO refresh_tokens (jti, user_id, issued_at, expires_at) VALUES (?, ?, strftime('%s','now'), ?)",
            (jti, user["id"], exp),
        )
        cur.execute(
            "UPDATE users SET last_login_at = datetime('now') WHERE id = ?", (user["id"],)
        )
    return TokenPair(access_token=access, refresh_token=refresh)


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterIn, request: Request, settings: Settings = Depends(get_settings)) -> TokenPair:
    if not USERNAME_RE.match(body.username):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid username")

    # Runtime password policy
    min_len = app_settings.password_min_length()
    if len(body.password) < min_len:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"password must be at least {min_len} characters",
        )

    await _enforce_turnstile("register", body.turnstile_token, request)

    # Gate registration: open vs invite-only.
    invite_required = not app_settings.open_registration()
    if invite_required and not body.invite_code:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "registration is invite-only")

    pw_hash = security.hash_password(body.password)
    private_key = secrets.token_hex(32)
    public_key = secrets.token_hex(16)
    allotment = app_settings.new_user_allotment()
    try:
        with db.cursor() as cur:
            cur.execute(
                """INSERT INTO users
                   (username, email, password_hash, role, key_allotment, private_key, public_key)
                   VALUES (?, ?, ?, 'USER', ?, ?, ?)""",
                (body.username, body.email, pw_hash, allotment,
                 private_key, public_key),
            )
            user_id = cur.lastrowid
            user = dict(cur.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())
    except Exception as exc:  # IntegrityError on dup username/email
        security.audit(
            event="register.conflict", username=body.username,
            request=request, success=False,
        )
        raise HTTPException(status.HTTP_409_CONFLICT, "username or email already in use") from exc

    if invite_required:
        if not invites.consume(body.invite_code or "", user["id"]):
            # Roll back the new user so a bad code can't squat the username.
            with db.cursor() as cur:
                cur.execute("DELETE FROM users WHERE id = ?", (user["id"],))
            security.audit(
                event="register.bad_invite", username=body.username,
                request=request, success=False,
            )
            raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid or already-used invite code")

    security.audit(
        event="register.ok", user_id=user["id"], username=user["username"],
        request=request, success=True,
    )
    return _issue_pair(user, settings)


@router.post("/login", response_model=TokenPair)
async def login(body: LoginIn, request: Request, settings: Settings = Depends(get_settings)) -> TokenPair:
    await _enforce_turnstile("login", body.turnstile_token, request)

    with db.cursor() as cur:
        row = cur.execute("SELECT * FROM users WHERE username = ?", (body.username,)).fetchone()

    if not row:
        # Spend an Argon2 verify so timing doesn't reveal the username miss.
        security.dummy_verify(body.password)
        security.audit(
            event="login.unknown_user", username=body.username,
            request=request, success=False,
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")

    user = dict(row)

    if security.is_locked(row):
        security.audit(
            event="login.locked", user_id=user["id"], username=user["username"],
            request=request, success=False,
        )
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "account_locked")

    if not security.verify_password(body.password, user["password_hash"] or ""):
        security.record_failed_login(user["id"])
        security.audit(
            event="login.bad_password", user_id=user["id"], username=user["username"],
            request=request, success=False,
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")

    # Success path
    security.clear_failed_logins(user["id"])
    if security.needs_rehash(user["password_hash"]):
        new_hash = security.hash_password(body.password)
        with db.cursor() as cur:
            cur.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user["id"]))
    security.audit(
        event="login.ok", user_id=user["id"], username=user["username"],
        request=request, success=True,
    )
    return _issue_pair(user, settings)


class RefreshIn(BaseModel):
    refresh_token: str


@router.post("/refresh", response_model=TokenPair)
def refresh(body: RefreshIn, settings: Settings = Depends(get_settings)) -> TokenPair:
    data = security.decode_token(body.refresh_token, expected_type="refresh", settings=settings)
    jti = data["jti"]
    user_id = int(data["sub"])
    with db.cursor() as cur:
        row = cur.execute(
            "SELECT * FROM refresh_tokens WHERE jti = ? AND user_id = ?", (jti, user_id)
        ).fetchone()
        if not row or row["revoked"]:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "refresh token revoked")
        # Rotate: revoke old, issue new pair.
        cur.execute("UPDATE refresh_tokens SET revoked = 1 WHERE jti = ?", (jti,))
        user = dict(cur.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())
    return _issue_pair(user, settings)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def logout(body: RefreshIn, request: Request, settings: Settings = Depends(get_settings)):
    try:
        data = security.decode_token(body.refresh_token, expected_type="refresh", settings=settings)
        with db.cursor() as cur:
            cur.execute("UPDATE refresh_tokens SET revoked = 1 WHERE jti = ?", (data["jti"],))
            row = cur.execute("SELECT user_id FROM refresh_tokens WHERE jti = ?", (data["jti"],)).fetchone()
        security.audit(
            event="logout", user_id=int(row["user_id"]) if row else None,
            request=request, success=True,
        )
    except HTTPException:
        # Logout is best-effort; never leak whether the token was valid.
        pass


@router.get("/me")
def me(user: dict = Depends(security.current_user)) -> dict:
    return {
        "id": user["id"],
        "username": user["username"],
        "email": user["email"],
        "role": user["role"],
        "key_allotment": user["key_allotment"],
        "created_at": user["created_at"],
    }


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def change_password(
    body: ChangePasswordIn,
    request: Request,
    user: dict = Depends(security.current_user),
) -> Response:
    """Authenticated user changes their own password.

    Verifies the current password (constant-time via Argon2 verify), enforces
    the runtime min-length policy, rehashes, and revokes all existing refresh
    tokens so other sessions are forced to re-login.
    """
    min_len = app_settings.password_min_length()
    if len(body.new_password) < min_len:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"password must be at least {min_len} characters",
        )

    with db.cursor() as cur:
        row = cur.execute(
            "SELECT password_hash FROM users WHERE id = ?", (user["id"],)
        ).fetchone()
    stored = (row["password_hash"] if row else "") or ""
    if not security.verify_password(body.current_password, stored):
        security.audit(
            event="password.change_bad_current", user_id=user["id"],
            username=user["username"], request=request, success=False,
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid current password")

    new_hash = security.hash_password(body.new_password)
    with db.cursor() as cur:
        cur.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user["id"]),
        )
        # Force other sessions to re-authenticate.
        cur.execute(
            "UPDATE refresh_tokens SET revoked = 1 WHERE user_id = ?", (user["id"],),
        )
    security.audit(
        event="password.changed", user_id=user["id"], username=user["username"],
        request=request, success=True,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
