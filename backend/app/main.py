# Decentralized-BMP V2 — application entry point
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import asyncio
import secrets
import time
from collections import deque
from contextlib import asynccontextmanager
from threading import Lock

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from . import app_settings, db, publisher, security
from .routers import admin, auth, beammp, builds, compat_v1, invites, keys, messages, oauth, publish
from .settings import get_settings


# --- per-IP rate limiter for the auth endpoints -----------------------------
# Lightweight sliding-window counter — keeps brute-force noise down even
# before the per-account lockout kicks in. Single process, in-memory; that's
# fine for a self-hosted backend (which is the deployment shape here).
_AUTH_PATHS = {"/auth/login", "/auth/register", "/auth/refresh"}
_AUTH_LIMIT = 30           # requests
_AUTH_WINDOW = 60          # seconds
_auth_buckets: dict[str, deque[float]] = {}
_auth_lock = Lock()


def _client_ip_of(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def _rate_limited(ip: str) -> bool:
    now = time.monotonic()
    cutoff = now - _AUTH_WINDOW
    with _auth_lock:
        bucket = _auth_buckets.setdefault(ip, deque())
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= _AUTH_LIMIT:
            return True
        bucket.append(now)
        return False


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds the standard hardening headers + a CSP that allows the
    Cloudflare Turnstile widget to load on the login page."""

    CSP = (
        "default-src 'self'; "
        "script-src 'self' https://challenges.cloudflare.com; "
        "frame-src 'self' https://challenges.cloudflare.com; "
        "connect-src 'self' https://challenges.cloudflare.com; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "font-src 'self' data:; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'none'"
    )

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        ctype = response.headers.get("content-type", "")
        if ctype.startswith(("text/html", "application/json", "text/plain")):
            response.headers.setdefault("Content-Security-Policy", self.CSP)
        if request.url.scheme == "https":
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=63072000; includeSubDomains",
            )
        return response


def _bootstrap_admin() -> None:
    """Create the bootstrap admin if no users exist yet."""
    s = get_settings()
    with db.cursor() as cur:
        any_user = cur.execute("SELECT 1 FROM users LIMIT 1").fetchone()
        if any_user:
            return
        pw_hash = security.hash_password(s.bootstrap_admin_password)
        cur.execute(
            """INSERT INTO users (username, password_hash, role, key_allotment, private_key, public_key)
               VALUES (?, ?, 'ADMIN', 9999, ?, ?)""",
            (s.bootstrap_admin_username, pw_hash, secrets.token_hex(32), secrets.token_hex(16)),
        )
    print(f"[bootstrap] created admin user '{s.bootstrap_admin_username}' — change the password immediately")


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init()
    app_settings.seed()
    _bootstrap_admin()
    task = asyncio.create_task(publisher.run_forever())
    try:
        yield
    finally:
        task.cancel()


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="Decentralized-BMP V2", version="2.0.0", lifespan=lifespan)

    # Security headers run first (outermost in the response).
    app.add_middleware(SecurityHeadersMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    # Session middleware is required by Authlib for the OAuth state cookie.
    app.add_middleware(SessionMiddleware, secret_key=s.jwt_secret, same_site="lax", https_only=True)

    @app.middleware("http")
    async def _auth_rate_limit(request: Request, call_next):
        if request.url.path in _AUTH_PATHS:
            ip = _client_ip_of(request)
            if _rate_limited(ip):
                return JSONResponse(
                    status_code=429,
                    content={"detail": "rate_limited"},
                    headers={"Retry-After": "60"},
                )
        return await call_next(request)

    app.include_router(auth.router)
    app.include_router(oauth.router)
    app.include_router(keys.router)
    app.include_router(invites.router)
    app.include_router(admin.router)
    app.include_router(publish.router)
    app.include_router(builds.router)
    app.include_router(messages.router)
    app.include_router(compat_v1.router)
    app.include_router(beammp.router)

    @app.get("/auth/policy")
    def auth_policy() -> dict:
        """Public — lets the login UI hide/show the invite-code field, render
        the Turnstile widget, and mirror the runtime password policy."""
        return {
            "open_registration": app_settings.open_registration(),
            "invite_required": not app_settings.open_registration(),
            "password_min_length": app_settings.password_min_length(),
            "turnstile_site_key": app_settings.turnstile_site_key() or None,
            "turnstile_required": {
                "login": app_settings.turnstile_required_for("login"),
                "register": app_settings.turnstile_required_for("register"),
            },
        }

    @app.get("/theme")
    def public_theme() -> dict:
        """Public — admin-configured wallpaper used by the login form and
        (optionally) by every signed-in page. Empty `background_url` means
        the feature is disabled."""
        return {
            "background_url": app_settings.background_url(),
            "background_blur_px": app_settings.background_blur_px(),
            "background_dim_pct": app_settings.background_dim_pct(),
            "apply_to_auth_only": app_settings.background_apply_to_auth_only(),
        }

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok", "version": app.version}

    return app


app = create_app()
