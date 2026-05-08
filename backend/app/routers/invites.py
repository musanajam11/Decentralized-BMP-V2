# Decentralized-BMP V2 — invite codes
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Invite codes — admin-minted signup gate when open registration is off."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from .. import db, security

router = APIRouter(prefix="/invites", tags=["invites"])


class InviteOut(BaseModel):
    id: int
    code: str
    created_by: str
    created_at: str
    used_by: str | None
    used_at: str | None


def _row_to_out(row: dict) -> InviteOut:
    return InviteOut(
        id=row["id"],
        code=row["code"],
        created_by=row["created_by_username"],
        created_at=row["created_at"],
        used_by=row["used_by_username"],
        used_at=row["used_at"],
    )


def _query(where: str, params: tuple) -> list[dict]:
    with db.cursor() as cur:
        rows = cur.execute(
            f"""SELECT i.*,
                       cb.username AS created_by_username,
                       ub.username AS used_by_username
                FROM invite_codes i
                JOIN users cb ON cb.id = i.created_by
                LEFT JOIN users ub ON ub.id = i.used_by
                WHERE {where}
                ORDER BY i.id DESC""",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("", response_model=list[InviteOut])
def list_invites(_: dict = Depends(security.require_admin)) -> list[InviteOut]:
    """List all invite codes (admin-only)."""
    rows = _query("1=1", ())
    return [_row_to_out(r) for r in rows]


class MintIn(BaseModel):
    count: int = Field(ge=1, le=100, default=1)


@router.post("", response_model=list[InviteOut], status_code=status.HTTP_201_CREATED)
def mint(body: MintIn, admin: dict = Depends(security.require_admin)) -> list[InviteOut]:
    """Mint invite codes (admin-only)."""
    new_ids: list[int] = []
    with db.cursor() as cur:
        for _ in range(body.count):
            code = secrets.token_urlsafe(12)
            cur.execute(
                "INSERT INTO invite_codes (code, created_by) VALUES (?, ?)",
                (code, admin["id"]),
            )
            new_ids.append(cur.lastrowid)
    rows = _query(f"i.id IN ({','.join('?' * len(new_ids))})", tuple(new_ids))
    return [_row_to_out(r) for r in rows]


@router.delete("/{invite_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def revoke(invite_id: int, _: dict = Depends(security.require_admin)):
    with db.cursor() as cur:
        row = cur.execute("SELECT * FROM invite_codes WHERE id = ?", (invite_id,)).fetchone()
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "invite not found")
        if row["used_by"]:
            raise HTTPException(status.HTTP_409_CONFLICT, "invite already used")
        cur.execute("DELETE FROM invite_codes WHERE id = ?", (invite_id,))


# --- helper used by the auth router ---------------------------------------

def consume(code: str, by_user_id: int) -> bool:
    """Mark `code` as used by `by_user_id`. Returns True on success."""
    with db.cursor() as cur:
        row = cur.execute(
            "SELECT id FROM invite_codes WHERE code = ? AND used_by IS NULL", (code,)
        ).fetchone()
        if not row:
            return False
        cur.execute(
            "UPDATE invite_codes SET used_by = ?, used_at = datetime('now') WHERE id = ?",
            (by_user_id, row["id"]),
        )
    return True
