# Decentralized-BMP V2 — admin router
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Admin-only endpoints: list users, set allotments, change roles."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from .. import app_settings, db, security
from ..settings import Settings, get_settings

router = APIRouter(prefix="/admin", tags=["admin"])


class UserOut(BaseModel):
    id: int
    username: str
    email: str | None
    role: str
    key_allotment: int
    keys_in_use: int
    created_at: str
    last_login_at: str | None


@router.get("/users", response_model=list[UserOut])
def list_users(_: dict = Depends(security.require_admin)) -> list[UserOut]:
    with db.cursor() as cur:
        rows = cur.execute("""
            SELECT u.*, COALESCE(k.n, 0) AS keys_in_use
            FROM users u
            LEFT JOIN (SELECT owner_id, COUNT(*) AS n FROM server_keys GROUP BY owner_id) k
              ON k.owner_id = u.id
            ORDER BY u.id ASC
        """).fetchall()
    return [UserOut(**dict(r)) for r in rows]


class AllotmentIn(BaseModel):
    key_allotment: int = Field(ge=0, le=10_000)


@router.patch("/users/{user_id}/allotment", response_model=UserOut)
def set_allotment(user_id: int, body: AllotmentIn,
                  _: dict = Depends(security.require_admin)) -> UserOut:
    with db.cursor() as cur:
        cur.execute("UPDATE users SET key_allotment = ? WHERE id = ?",
                    (body.key_allotment, user_id))
        row = cur.execute("""
            SELECT u.*, COALESCE(k.n, 0) AS keys_in_use FROM users u
            LEFT JOIN (SELECT owner_id, COUNT(*) AS n FROM server_keys GROUP BY owner_id) k
              ON k.owner_id = u.id WHERE u.id = ?""", (user_id,)).fetchone()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    return UserOut(**dict(row))


class RoleIn(BaseModel):
    role: str  # USER | ADMIN


@router.patch("/users/{user_id}/role", response_model=UserOut)
def set_role(user_id: int, body: RoleIn, admin: dict = Depends(security.require_admin)) -> UserOut:
    if body.role not in ("USER", "ADMIN"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "role must be USER or ADMIN")
    if admin["id"] == user_id and body.role != "ADMIN":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "cannot demote yourself")
    with db.cursor() as cur:
        cur.execute("UPDATE users SET role = ? WHERE id = ?", (body.role, user_id))
        row = cur.execute("""
            SELECT u.*, COALESCE(k.n, 0) AS keys_in_use FROM users u
            LEFT JOIN (SELECT owner_id, COUNT(*) AS n FROM server_keys GROUP BY owner_id) k
              ON k.owner_id = u.id WHERE u.id = ?""", (user_id,)).fetchone()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    return UserOut(**dict(row))


class DefaultsOut(BaseModel):
    default_key_allotment: int


@router.get("/defaults", response_model=DefaultsOut)
def get_defaults(_: dict = Depends(security.require_admin),
                 settings: Settings = Depends(get_settings)) -> DefaultsOut:
    return DefaultsOut(default_key_allotment=settings.default_key_allotment)


# --- Runtime settings (open registration + new-user key allotment) ----------

class AppSettingsOut(BaseModel):
    open_registration: bool
    key_allotment_mode: str        # 'admin_issued' | 'default_amount'
    key_default_amount: int


class AppSettingsIn(BaseModel):
    open_registration: bool | None = None
    key_allotment_mode: str | None = None
    key_default_amount: int | None = Field(default=None, ge=0, le=10_000)


def _current_app_settings() -> AppSettingsOut:
    return AppSettingsOut(
        open_registration=app_settings.open_registration(),
        key_allotment_mode=app_settings.key_allotment_mode(),
        key_default_amount=app_settings.key_default_amount(),
    )


@router.get("/settings", response_model=AppSettingsOut)
def get_app_settings(_: dict = Depends(security.require_admin)) -> AppSettingsOut:
    return _current_app_settings()


@router.patch("/settings", response_model=AppSettingsOut)
def update_app_settings(body: AppSettingsIn,
                        _: dict = Depends(security.require_admin)) -> AppSettingsOut:
    updates: dict[str, str] = {}
    if body.open_registration is not None:
        updates["open_registration"] = "true" if body.open_registration else "false"
    if body.key_allotment_mode is not None:
        if body.key_allotment_mode not in ("admin_issued", "default_amount"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "key_allotment_mode must be 'admin_issued' or 'default_amount'")
        updates["key_allotment_mode"] = body.key_allotment_mode
    if body.key_default_amount is not None:
        updates["key_default_amount"] = str(body.key_default_amount)
    if updates:
        try:
            app_settings.set_many(updates)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return _current_app_settings()


# --- Cloudflare Turnstile settings ------------------------------------------

class TurnstileOut(BaseModel):
    configured: bool
    site_key: str
    secret_key_set: bool
    require_login: bool
    require_register: bool


class TurnstileIn(BaseModel):
    site_key: str | None = None
    # Pass the literal string "__clear__" to wipe the stored secret. Mirrors
    # the BMR admin convention so the secret never has to round-trip the wire.
    secret_key: str | None = None
    require_login: bool | None = None
    require_register: bool | None = None


def _current_turnstile() -> TurnstileOut:
    return TurnstileOut(
        configured=app_settings.turnstile_configured(),
        site_key=app_settings.turnstile_site_key(),
        secret_key_set=bool(app_settings.turnstile_secret_key()),
        require_login=app_settings.turnstile_required_for("login"),
        require_register=app_settings.turnstile_required_for("register"),
    )


@router.get("/settings/turnstile", response_model=TurnstileOut)
def get_turnstile_settings(_: dict = Depends(security.require_admin)) -> TurnstileOut:
    return _current_turnstile()


@router.post("/settings/turnstile", response_model=TurnstileOut)
def update_turnstile_settings(
    body: TurnstileIn,
    request: Request,
    admin: dict = Depends(security.require_admin),
) -> TurnstileOut:
    updates: dict[str, str] = {}
    changed: list[str] = []
    if body.site_key is not None:
        updates["turnstile_site_key"] = body.site_key.strip()
        changed.append("site_key")
    if body.secret_key is not None:
        if body.secret_key == "__clear__":
            updates["turnstile_secret_key"] = ""
        elif body.secret_key.strip():
            updates["turnstile_secret_key"] = body.secret_key.strip()
        # Empty string with no sentinel = no-op (keeps existing secret).
        if "turnstile_secret_key" in updates:
            changed.append("secret_key")
    if body.require_login is not None:
        updates["turnstile_require_login"] = "true" if body.require_login else "false"
        changed.append("require_login")
    if body.require_register is not None:
        updates["turnstile_require_register"] = "true" if body.require_register else "false"
        changed.append("require_register")
    if updates:
        try:
            app_settings.set_many(updates)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
        security.audit(
            event="admin.settings.turnstile_updated",
            user_id=admin["id"], username=admin["username"],
            request=request, success=True, detail={"changed": changed},
        )
    return _current_turnstile()


# --- Audit log viewer -------------------------------------------------------

class AuditEventOut(BaseModel):
    id: int
    user_id: int | None
    username: str | None
    event: str
    ip: str | None
    user_agent: str | None
    success: bool
    detail: str | None
    created_at: int


@router.get("/audit", response_model=list[AuditEventOut])
def list_audit_events(
    limit: int = 200,
    event: str | None = None,
    user_id: int | None = None,
    _: dict = Depends(security.require_admin),
) -> list[AuditEventOut]:
    limit = max(1, min(1000, limit))
    where: list[str] = []
    args: list = []
    if event:
        where.append("event = ?")
        args.append(event)
    if user_id is not None:
        where.append("user_id = ?")
        args.append(user_id)
    sql = "SELECT * FROM auth_events"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    with db.cursor() as cur:
        rows = cur.execute(sql, args).fetchall()
    out: list[AuditEventOut] = []
    for r in rows:
        d = dict(r)
        d["success"] = bool(d.get("success"))
        out.append(AuditEventOut(**d))
    return out

