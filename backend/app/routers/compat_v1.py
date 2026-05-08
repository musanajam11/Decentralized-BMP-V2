# Decentralized-BMP V2 — vanilla BeamMP-Launcher / BeamMP-Server compat
# SPDX-License-Identifier: AGPL-3.0-or-later
"""V1-compatible auth endpoints used by the BeamMP launcher and server.

Vanilla BeamMP binaries (or the modified ones served from ``/builds``)
talk to ``auth.beammp.com`` (or our hex-patched substitute) using two
endpoints:

    POST /userlogin      — launcher login: u/pw → private/public key, or
                           pk → re-validate saved key.
    POST /pkToUser       — server-side: validate a player's public key
                           and return a display name + identifiers.

V2 itself uses JWT for the React UI, but we need to keep these paths
working so the launcher/server can authenticate against this backend.
The user store is the same `users` table — the V2 schema already has
``private_key``/``public_key`` columns for exactly this purpose. Keys are
auto-minted on first successful password login if they don't exist.
"""

from __future__ import annotations

import hashlib
import secrets

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .. import db, security

router = APIRouter(tags=["compat-v1"])


def _user_to_login_payload(row) -> dict:
    return {
        "success": True,
        "message": "Login successful",
        "username": row["username"],
        "role": row["role"] or "USER",
        "id": row["id"],
        "private_key": row["private_key"] or "",
        "public_key": row["public_key"] or "",
    }


def _ensure_keys(user_id: int, row) -> tuple[str, str]:
    """Lazily mint per-user BeamMP keys on first launcher login."""
    pk = row["private_key"]
    pub = row["public_key"]
    if pk and pub:
        return pk, pub
    pk = pk or secrets.token_hex(32)
    pub = pub or secrets.token_hex(16)
    with db.cursor() as cur:
        cur.execute(
            "UPDATE users SET private_key = ?, public_key = ? WHERE id = ?",
            (pk, pub, user_id),
        )
    return pk, pub


@router.post("/userlogin")
async def userlogin(request: Request) -> JSONResponse:
    # Body may legitimately be empty or "LO" (logout) — match V1 behavior:
    # never raise on bad JSON, just return success=False.
    try:
        body = await request.body()
        if not body or body.strip() in (b'"LO"', b"LO"):
            return JSONResponse({"success": False, "message": "Logged out"})
        data = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"success": False, "message": "Invalid request"})

    if not isinstance(data, dict):
        return JSONResponse({"success": False, "message": "Invalid request"})

    # ---- auto-login by saved private key ----
    if "pk" in data:
        pk = str(data.get("pk") or "").strip()
        if not pk:
            return JSONResponse({"success": False, "message": "Invalid key"})
        with db.cursor() as cur:
            row = cur.execute(
                "SELECT id, username, role, private_key, public_key "
                "FROM users WHERE private_key = ?",
                (pk,),
            ).fetchone()
        if not row:
            return JSONResponse({"success": False, "message": "Invalid key"})
        return JSONResponse(_user_to_login_payload(row))

    # ---- manual username/password login ----
    username = str(data.get("username") or "").strip()
    password = str(data.get("password") or "")
    if not username or not password:
        return JSONResponse(
            {"success": False, "message": "Username and password required"}
        )

    with db.cursor() as cur:
        row = cur.execute(
            "SELECT id, username, role, password_hash, private_key, public_key "
            "FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    if not row or not row["password_hash"]:
        return JSONResponse({"success": False, "message": "Invalid credentials"})
    if not security.verify_password(password, row["password_hash"]):
        return JSONResponse({"success": False, "message": "Invalid credentials"})

    pk, pub = _ensure_keys(row["id"], row)
    # Re-fetch is unnecessary; we have everything to assemble the response.
    payload = {
        "success": True,
        "message": "Login successful",
        "username": row["username"],
        "role": row["role"] or "USER",
        "id": row["id"],
        "private_key": pk,
        "public_key": pub,
    }
    return JSONResponse(payload)


@router.post("/pkToUser")
async def pk_to_user(request: Request) -> JSONResponse:
    """Server-side: resolve a joining player's public key to a username.

    The vanilla BeamMP-Server calls this for every join. Unknown keys are
    permitted as ``Guest-<8 hex>`` so single-player testing works without
    every player having a backend account; tighten this to a 4xx if you
    want closed-membership semantics.
    """
    try:
        data = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    player_key = str((data or {}).get("key") or "").strip()
    if not player_key:
        return JSONResponse({"error": "Missing player key"}, status_code=400)

    with db.cursor() as cur:
        row = cur.execute(
            "SELECT id, username, role FROM users WHERE public_key = ?",
            (player_key,),
        ).fetchone()

    if row:
        return JSONResponse({
            "username": row["username"],
            "roles": row["role"] or "USER",
            "guest": False,
            "identifiers": [f"beammp:{row['id']}"],
        })

    guest_id = hashlib.sha256(player_key.encode()).hexdigest()[:8]
    return JSONResponse({
        "username": f"Guest-{guest_id}",
        "roles": "USER",
        "guest": True,
        "identifiers": [f"guest:{guest_id}"],
    })
