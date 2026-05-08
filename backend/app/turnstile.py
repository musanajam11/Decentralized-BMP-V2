# Decentralized-BMP V2 — Cloudflare Turnstile verification
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Server-side Turnstile siteverify. Mirrors BMR's behaviour:
returns {ok: True} when not configured (safe no-op) so admins can roll the
feature out gradually."""

from __future__ import annotations

from typing import TypedDict

import httpx

from . import app_settings

VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


class VerifyResult(TypedDict):
    ok: bool
    reason: str


async def verify(token: str | None, remote_ip: str | None) -> VerifyResult:
    if not app_settings.turnstile_configured():
        return {"ok": True, "reason": "not_configured"}
    if not token or not isinstance(token, str):
        return {"ok": False, "reason": "missing_token"}
    secret = app_settings.turnstile_secret_key()
    data = {"secret": secret, "response": token}
    if remote_ip:
        data["remoteip"] = remote_ip
    try:
        async with httpx.AsyncClient(timeout=8.0) as c:
            r = await c.post(VERIFY_URL, data=data)
        if r.status_code != 200:
            return {"ok": False, "reason": f"siteverify_http_{r.status_code}"}
        body = r.json()
        if body.get("success"):
            return {"ok": True, "reason": "verified"}
        codes = body.get("error-codes") or ["unknown"]
        return {"ok": False, "reason": ",".join(str(c) for c in codes)}
    except Exception as exc:  # network / JSON failure
        return {"ok": False, "reason": f"siteverify_failed:{type(exc).__name__}"}
