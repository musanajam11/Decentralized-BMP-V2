# Decentralized-BMP V2 — user/admin messaging
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Lightweight support inbox.

Users open a thread from the dashboard; admins see and reply to all open
threads from the same UI. Read-state is tracked per side (user vs. admin
team) so the dashboard can surface a notification badge.

This is intentionally not a generic chat system — there's one conversation
between each user and the admin team per topic, and admins are treated as
a single role-based audience (any admin can read/reply).
"""

from __future__ import annotations

import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from .. import db, security

router = APIRouter(prefix="/messages", tags=["messages"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CreateThreadIn(BaseModel):
    subject: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=4000)


class ReplyIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class MessageOut(BaseModel):
    id: int
    sender_id: int
    sender_username: str
    sender_role: Literal["USER", "ADMIN"]
    body: str
    created_at: int


class ThreadSummaryOut(BaseModel):
    id: int
    subject: str
    status: Literal["open", "closed"]
    user_id: int
    user_username: str
    created_at: int
    updated_at: int
    last_user_at: int | None
    last_admin_at: int | None
    unread: int  # unread messages from the *other* side


class ThreadOut(ThreadSummaryOut):
    messages: list[MessageOut]


class UnreadCountOut(BaseModel):
    inbox: int   # messages addressed to the caller they haven't read yet
    threads: int # threads with at least one unread message


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> int:
    return int(time.time())


def _is_admin(user: dict) -> bool:
    return user.get("role") == "ADMIN"


def _username(cur, user_id: int) -> str:
    row = cur.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()
    return row["username"] if row else f"user#{user_id}"


def _row_to_message(cur, row) -> MessageOut:
    return MessageOut(
        id=row["id"],
        sender_id=row["sender_id"],
        sender_username=_username(cur, row["sender_id"]),
        sender_role=row["sender_role"],
        body=row["body"],
        created_at=row["created_at"],
    )


def _ensure_visible(cur, thread_row, user: dict) -> None:
    if thread_row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "thread not found")
    if not _is_admin(user) and thread_row["user_id"] != user["id"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your thread")


def _unread_for(cur, thread_id: int, user: dict) -> int:
    if _is_admin(user):
        # Admins haven't read messages with read_by_admin=0 from the user.
        col = "read_by_admin"
        sender_role = "USER"
    else:
        col = "read_by_user"
        sender_role = "ADMIN"
    return int(
        cur.execute(
            f"SELECT COUNT(*) AS c FROM messages "
            f"WHERE thread_id = ? AND {col} = 0 AND sender_role = ?",
            (thread_id, sender_role),
        ).fetchone()["c"]
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/unread", response_model=UnreadCountOut)
def unread_count(user: dict = Depends(security.current_user)) -> UnreadCountOut:
    """Notification badge data for the navbar."""
    with db.cursor() as cur:
        if _is_admin(user):
            row = cur.execute(
                """SELECT COUNT(*) AS c, COUNT(DISTINCT thread_id) AS t
                     FROM messages
                    WHERE read_by_admin = 0 AND sender_role = 'USER'"""
            ).fetchone()
        else:
            row = cur.execute(
                """SELECT COUNT(*) AS c, COUNT(DISTINCT m.thread_id) AS t
                     FROM messages m
                     JOIN message_threads t ON t.id = m.thread_id
                    WHERE t.user_id = ? AND m.read_by_user = 0
                      AND m.sender_role = 'ADMIN'""",
                (user["id"],),
            ).fetchone()
    return UnreadCountOut(inbox=int(row["c"] or 0), threads=int(row["t"] or 0))


@router.get("/threads", response_model=list[ThreadSummaryOut])
def list_threads(
    user: dict = Depends(security.current_user),
) -> list[ThreadSummaryOut]:
    """Admin sees every thread; users see only their own."""
    with db.cursor() as cur:
        if _is_admin(user):
            rows = cur.execute(
                """SELECT t.*, u.username AS user_username
                     FROM message_threads t
                     JOIN users u ON u.id = t.user_id
                    ORDER BY (t.status = 'open') DESC, t.updated_at DESC
                    LIMIT 500"""
            ).fetchall()
        else:
            rows = cur.execute(
                """SELECT t.*, u.username AS user_username
                     FROM message_threads t
                     JOIN users u ON u.id = t.user_id
                    WHERE t.user_id = ?
                    ORDER BY t.updated_at DESC
                    LIMIT 500""",
                (user["id"],),
            ).fetchall()
        out: list[ThreadSummaryOut] = []
        for r in rows:
            out.append(
                ThreadSummaryOut(
                    id=r["id"],
                    subject=r["subject"],
                    status=r["status"],
                    user_id=r["user_id"],
                    user_username=r["user_username"],
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                    last_user_at=r["last_user_at"],
                    last_admin_at=r["last_admin_at"],
                    unread=_unread_for(cur, r["id"], user),
                )
            )
        return out


@router.post("/threads", response_model=ThreadOut, status_code=status.HTTP_201_CREATED)
def create_thread(
    body: CreateThreadIn,
    user: dict = Depends(security.current_user),
) -> ThreadOut:
    """User-only: open a new thread with the admin team."""
    if _is_admin(user):
        # Admins reply to user-opened threads; they can't open one *to* themselves.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "admins reply to existing threads")
    now = _now()
    with db.cursor() as cur:
        # Anti-spam: cap simultaneous open threads per user.
        open_count = cur.execute(
            "SELECT COUNT(*) AS c FROM message_threads WHERE user_id = ? AND status = 'open'",
            (user["id"],),
        ).fetchone()["c"]
        if open_count >= 5:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "you already have 5 open threads — close one before opening another",
            )
        cur.execute(
            """INSERT INTO message_threads
                  (user_id, subject, status, created_at, updated_at, last_user_at)
               VALUES (?, ?, 'open', ?, ?, ?)""",
            (user["id"], body.subject.strip(), now, now, now),
        )
        thread_id = cur.lastrowid
        cur.execute(
            """INSERT INTO messages
                  (thread_id, sender_id, sender_role, body, created_at,
                   read_by_user, read_by_admin)
               VALUES (?, ?, 'USER', ?, ?, 1, 0)""",
            (thread_id, user["id"], body.body.strip(), now),
        )
    return get_thread(thread_id, user)  # type: ignore[arg-type]


@router.get("/threads/{thread_id}", response_model=ThreadOut)
def get_thread(
    thread_id: int,
    user: dict = Depends(security.current_user),
) -> ThreadOut:
    """Fetch a thread + its messages. Marks unread messages from the other
    side as read for the caller in the same transaction."""
    with db.cursor() as cur:
        t = cur.execute(
            """SELECT t.*, u.username AS user_username
                 FROM message_threads t
                 JOIN users u ON u.id = t.user_id
                WHERE t.id = ?""",
            (thread_id,),
        ).fetchone()
        _ensure_visible(cur, t, user)
        # Mark unread-from-other-side messages as read for this caller.
        if _is_admin(user):
            cur.execute(
                """UPDATE messages SET read_by_admin = 1
                    WHERE thread_id = ? AND read_by_admin = 0 AND sender_role = 'USER'""",
                (thread_id,),
            )
        else:
            cur.execute(
                """UPDATE messages SET read_by_user = 1
                    WHERE thread_id = ? AND read_by_user = 0 AND sender_role = 'ADMIN'""",
                (thread_id,),
            )
        msg_rows = cur.execute(
            """SELECT * FROM messages WHERE thread_id = ? ORDER BY created_at ASC, id ASC""",
            (thread_id,),
        ).fetchall()
        messages = [_row_to_message(cur, m) for m in msg_rows]
    return ThreadOut(
        id=t["id"],
        subject=t["subject"],
        status=t["status"],
        user_id=t["user_id"],
        user_username=t["user_username"],
        created_at=t["created_at"],
        updated_at=t["updated_at"],
        last_user_at=t["last_user_at"],
        last_admin_at=t["last_admin_at"],
        unread=0,
        messages=messages,
    )


@router.post("/threads/{thread_id}/reply", response_model=ThreadOut)
def reply(
    thread_id: int,
    body: ReplyIn,
    user: dict = Depends(security.current_user),
) -> ThreadOut:
    now = _now()
    with db.cursor() as cur:
        t = cur.execute(
            "SELECT * FROM message_threads WHERE id = ?", (thread_id,)
        ).fetchone()
        _ensure_visible(cur, t, user)
        if t["status"] != "open":
            raise HTTPException(status.HTTP_409_CONFLICT, "thread is closed")
        role = "ADMIN" if _is_admin(user) else "USER"
        # The sender has implicitly read their own message.
        read_by_user = 1 if role == "USER" or t["user_id"] == user["id"] else 0
        read_by_admin = 1 if role == "ADMIN" else 0
        cur.execute(
            """INSERT INTO messages
                  (thread_id, sender_id, sender_role, body, created_at,
                   read_by_user, read_by_admin)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (thread_id, user["id"], role, body.body.strip(), now, read_by_user, read_by_admin),
        )
        if role == "ADMIN":
            cur.execute(
                "UPDATE message_threads SET updated_at = ?, last_admin_at = ? WHERE id = ?",
                (now, now, thread_id),
            )
        else:
            cur.execute(
                "UPDATE message_threads SET updated_at = ?, last_user_at = ? WHERE id = ?",
                (now, now, thread_id),
            )
    return get_thread(thread_id, user)


@router.post("/threads/{thread_id}/close", response_model=ThreadOut)
def close_thread(
    thread_id: int,
    user: dict = Depends(security.current_user),
) -> ThreadOut:
    with db.cursor() as cur:
        t = cur.execute(
            "SELECT * FROM message_threads WHERE id = ?", (thread_id,)
        ).fetchone()
        _ensure_visible(cur, t, user)
        cur.execute(
            "UPDATE message_threads SET status = 'closed', updated_at = ? WHERE id = ?",
            (_now(), thread_id),
        )
    return get_thread(thread_id, user)


@router.post("/threads/{thread_id}/reopen", response_model=ThreadOut)
def reopen_thread(
    thread_id: int,
    user: dict = Depends(security.current_user),
) -> ThreadOut:
    with db.cursor() as cur:
        t = cur.execute(
            "SELECT * FROM message_threads WHERE id = ?", (thread_id,)
        ).fetchone()
        _ensure_visible(cur, t, user)
        cur.execute(
            "UPDATE message_threads SET status = 'open', updated_at = ? WHERE id = ?",
            (_now(), thread_id),
        )
    return get_thread(thread_id, user)
