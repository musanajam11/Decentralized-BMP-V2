# Decentralized-BMP V2 — OAuth router (Discord + GitHub)
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Optional OAuth login. Disabled at runtime if client IDs are not configured.

Implementation note: we use Authlib's `OAuth` registry. The flow:
    GET  /auth/oauth/{provider}/start    -> 302 to provider
    GET  /auth/oauth/{provider}/callback -> upserts user + redirects to frontend
                                            with #access=...&refresh=...
"""

from __future__ import annotations

import secrets
from urllib.parse import urlencode

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from .. import app_settings, db, security
from ..settings import Settings, get_settings

router = APIRouter(prefix="/auth/oauth", tags=["auth"])

_oauth = OAuth()


def _ensure_registered(settings: Settings) -> None:
    if settings.discord_client_id and "discord" not in _oauth._clients:
        _oauth.register(
            name="discord",
            client_id=settings.discord_client_id,
            client_secret=settings.discord_client_secret,
            access_token_url="https://discord.com/api/oauth2/token",
            authorize_url="https://discord.com/api/oauth2/authorize",
            api_base_url="https://discord.com/api/",
            client_kwargs={"scope": "identify email"},
        )
    if settings.github_client_id and "github" not in _oauth._clients:
        _oauth.register(
            name="github",
            client_id=settings.github_client_id,
            client_secret=settings.github_client_secret,
            access_token_url="https://github.com/login/oauth/access_token",
            authorize_url="https://github.com/login/oauth/authorize",
            api_base_url="https://api.github.com/",
            client_kwargs={"scope": "read:user user:email"},
        )


def _redirect_uri(settings: Settings, provider: str) -> str:
    base = (settings.oauth_redirect_base or settings.public_origin).rstrip("/")
    return f"{base}/auth/oauth/{provider}/callback"


@router.get("/{provider}/start")
async def oauth_start(provider: str, request: Request, settings: Settings = Depends(get_settings)):
    _ensure_registered(settings)
    client = _oauth._clients.get(provider)
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"oauth provider '{provider}' not configured")
    redirect_uri = _redirect_uri(settings, provider)
    return await client.authorize_redirect(request, redirect_uri)


async def _profile(provider: str, client) -> tuple[str, str | None, str | None]:
    """Returns (provider_uid, suggested_username, email)."""
    if provider == "discord":
        resp = await client.get("users/@me")
        d = resp.json()
        return str(d["id"]), d.get("username"), d.get("email")
    if provider == "github":
        u = (await client.get("user")).json()
        emails = (await client.get("user/emails")).json()
        primary = next((e["email"] for e in emails if e.get("primary")), None) if isinstance(emails, list) else None
        return str(u["id"]), u.get("login"), primary
    raise HTTPException(status.HTTP_400_BAD_REQUEST, "unknown provider")


@router.get("/{provider}/callback")
async def oauth_callback(provider: str, request: Request, settings: Settings = Depends(get_settings)):
    _ensure_registered(settings)
    client = _oauth._clients.get(provider)
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "provider not configured")
    token = await client.authorize_access_token(request)
    client.token = token
    provider_uid, suggested_name, email = await _profile(provider, client)

    with db.cursor() as cur:
        ident = cur.execute(
            "SELECT user_id FROM oauth_identities WHERE provider = ? AND provider_uid = ?",
            (provider, provider_uid),
        ).fetchone()
        if ident:
            user_row = cur.execute("SELECT * FROM users WHERE id = ?", (ident["user_id"],)).fetchone()
        else:
            # Pick a non-conflicting username.
            base = (suggested_name or f"{provider}-user").lower()
            base = "".join(c if c.isalnum() or c in "-_" else "-" for c in base)[:24] or "user"
            candidate = base
            i = 1
            while cur.execute("SELECT 1 FROM users WHERE username = ?", (candidate,)).fetchone():
                i += 1
                candidate = f"{base}-{i}"
            cur.execute(
                """INSERT INTO users (username, email, role, key_allotment, private_key, public_key)
                   VALUES (?, ?, 'USER', ?, ?, ?)""",
                (candidate, email, app_settings.new_user_allotment(),
                 secrets.token_hex(32), secrets.token_hex(16)),
            )
            new_id = cur.lastrowid
            cur.execute(
                "INSERT INTO oauth_identities (user_id, provider, provider_uid) VALUES (?, ?, ?)",
                (new_id, provider, provider_uid),
            )
            user_row = cur.execute("SELECT * FROM users WHERE id = ?", (new_id,)).fetchone()
        user = dict(user_row)

    access, _, _ = security.issue_token(user["id"], user["username"], user["role"],
                                        kind="access", settings=settings)
    refresh, jti, exp = security.issue_token(user["id"], user["username"], user["role"],
                                             kind="refresh", settings=settings)
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO refresh_tokens (jti, user_id, issued_at, expires_at) VALUES (?, ?, strftime('%s','now'), ?)",
            (jti, user["id"], exp),
        )

    frag = urlencode({"access": access, "refresh": refresh})
    return RedirectResponse(f"{settings.public_origin}/#oauth_done&{frag}")
