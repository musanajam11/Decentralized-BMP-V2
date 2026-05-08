# Decentralized-BMP V2 — server keys
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Server key management — users mint up to their allotment, admins manage all."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from .. import db, security

router = APIRouter(prefix="/keys", tags=["keys"])


class CreateKeyIn(BaseModel):
    server_name: str = Field(min_length=1, max_length=64, default="My Server")
    public: bool = False


class UpdateKeyIn(BaseModel):
    server_name: str | None = Field(default=None, min_length=1, max_length=64)
    public: bool | None = None


class KeyOut(BaseModel):
    id: int
    key: str
    server_name: str
    owner: str
    public: bool
    created_at: str


def _row_to_out(row, owner_username: str) -> KeyOut:
    return KeyOut(
        id=row["id"],
        key=row["key"],
        server_name=row["server_name"],
        owner=owner_username,
        public=bool(row["public"]),
        created_at=row["created_at"],
    )


@router.get("", response_model=list[KeyOut])
def list_my_keys(user: dict = Depends(security.current_user)) -> list[KeyOut]:
    with db.cursor() as cur:
        rows = cur.execute(
            "SELECT * FROM server_keys WHERE owner_id = ? ORDER BY id DESC", (user["id"],)
        ).fetchall()
    return [_row_to_out(r, user["username"]) for r in rows]


@router.post("", response_model=KeyOut, status_code=status.HTTP_201_CREATED)
def mint_key(body: CreateKeyIn, user: dict = Depends(security.current_user)) -> KeyOut:
    with db.cursor() as cur:
        count = cur.execute(
            "SELECT COUNT(*) AS n FROM server_keys WHERE owner_id = ?", (user["id"],)
        ).fetchone()["n"]
        if user["role"] != "ADMIN" and count >= user["key_allotment"]:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"key allotment exhausted ({count}/{user['key_allotment']}); ask an admin to increase it",
            )
        new_key = secrets.token_urlsafe(32)
        cur.execute(
            "INSERT INTO server_keys (key, server_name, owner_id, public) VALUES (?, ?, ?, ?)",
            (new_key, body.server_name, user["id"], 1 if body.public else 0),
        )
        new_id = cur.lastrowid
        row = cur.execute("SELECT * FROM server_keys WHERE id = ?", (new_id,)).fetchone()
    return _row_to_out(row, user["username"])


@router.patch("/{key_id}", response_model=KeyOut)
def update_key(key_id: int, body: UpdateKeyIn,
               user: dict = Depends(security.current_user)) -> KeyOut:
    with db.cursor() as cur:
        row = cur.execute("SELECT * FROM server_keys WHERE id = ?", (key_id,)).fetchone()
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "key not found")
        if row["owner_id"] != user["id"] and user["role"] != "ADMIN":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "not your key")
        sets, params = [], []
        if body.server_name is not None:
            sets.append("server_name = ?"); params.append(body.server_name)
        if body.public is not None:
            sets.append("public = ?"); params.append(1 if body.public else 0)
        if sets:
            params.append(key_id)
            cur.execute(f"UPDATE server_keys SET {', '.join(sets)} WHERE id = ?", params)
        row = cur.execute("SELECT * FROM server_keys WHERE id = ?", (key_id,)).fetchone()
        owner = cur.execute("SELECT username FROM users WHERE id = ?", (row["owner_id"],)).fetchone()
    return _row_to_out(row, owner["username"])


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_key(key_id: int, user: dict = Depends(security.current_user)):
    with db.cursor() as cur:
        row = cur.execute("SELECT * FROM server_keys WHERE id = ?", (key_id,)).fetchone()
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "key not found")
        if row["owner_id"] != user["id"] and user["role"] != "ADMIN":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "not your key")
        cur.execute("DELETE FROM server_keys WHERE id = ?", (key_id,))
