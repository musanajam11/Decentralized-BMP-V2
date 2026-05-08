# Decentralized-BMP V2 — database
# SPDX-License-Identifier: AGPL-3.0-or-later
"""SQLite layer. Single connection per request; WAL mode for concurrent reads.

Schema lives here so app/main.py stays focused on wiring."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .settings import get_settings


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT UNIQUE NOT NULL,
    email           TEXT UNIQUE,
    password_hash   TEXT,                   -- NULL when user is OAuth-only
    role            TEXT NOT NULL DEFAULT 'USER',     -- USER | ADMIN
    key_allotment   INTEGER NOT NULL DEFAULT 1,
    private_key     TEXT,                   -- BeamMP per-user secret
    public_key      TEXT,                   -- BeamMP per-user public id
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    last_login_at   TEXT,
    failed_logins   INTEGER NOT NULL DEFAULT 0,
    locked_until    INTEGER                    -- unix seconds; NULL when not locked
);

CREATE TABLE IF NOT EXISTS oauth_identities (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider        TEXT NOT NULL,          -- 'discord' | 'github'
    provider_uid    TEXT NOT NULL,
    UNIQUE(provider, provider_uid)
);

CREATE TABLE IF NOT EXISTS server_keys (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    key             TEXT UNIQUE NOT NULL,
    server_name     TEXT NOT NULL DEFAULT 'My Server',
    owner_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    public          INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    jti             TEXT UNIQUE NOT NULL,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    issued_at       INTEGER NOT NULL,
    expires_at      INTEGER NOT NULL,
    revoked         INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS server_state (
    -- Live BeamMP-Server heartbeats (server_keys.key -> last seen JSON)
    auth_key        TEXT PRIMARY KEY,
    payload_json    TEXT NOT NULL,
    last_heartbeat  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS publish_state (
    -- Single-row table (id=1) tracking the last BMR publish POST.
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    last_push_at    INTEGER,
    last_push_ok    INTEGER,
    last_push_error TEXT
);

CREATE TABLE IF NOT EXISTS app_settings (
    -- Admin-tunable runtime config (env values are only the bootstrap defaults).
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS invite_codes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT UNIQUE NOT NULL,
    created_by  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    used_by     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    used_at     TEXT
);

CREATE TABLE IF NOT EXISTS message_threads (
    -- One conversation between a user and the admin team. Created by users
    -- from the dashboard; admins reply via the same UI. Lightweight support
    -- inbox — not a generic chat system.
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subject         TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'open',   -- 'open' | 'closed'
    created_at      INTEGER NOT NULL,
    updated_at      INTEGER NOT NULL,
    last_user_at    INTEGER,                        -- timestamp of last user post
    last_admin_at   INTEGER                         -- timestamp of last admin post
);

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id       INTEGER NOT NULL REFERENCES message_threads(id) ON DELETE CASCADE,
    sender_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    sender_role     TEXT NOT NULL,                  -- 'USER' | 'ADMIN' (snapshot)
    body            TEXT NOT NULL,
    created_at      INTEGER NOT NULL,
    read_by_user    INTEGER NOT NULL DEFAULT 0,    -- 1 once thread owner has seen it
    read_by_admin   INTEGER NOT NULL DEFAULT 0    -- 1 once any admin has seen it
);

CREATE TABLE IF NOT EXISTS auth_events (
    -- Append-only audit log for security-sensitive events. Survives user
    -- deletion (user_id is left dangling) so admins can still audit removed
    -- accounts. Read via /admin/audit.
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER,
    username        TEXT,                           -- snapshot at event time
    event           TEXT NOT NULL,                  -- 'login.ok','login.fail','register','admin.role_change',...
    ip              TEXT,
    user_agent      TEXT,
    success         INTEGER NOT NULL DEFAULT 1,
    detail          TEXT,
    created_at      INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_keys_owner   ON server_keys(owner_id);
CREATE INDEX IF NOT EXISTS idx_invite_owner ON invite_codes(created_by);
CREATE INDEX IF NOT EXISTS idx_oauth_user   ON oauth_identities(user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_user ON refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_threads_user ON message_threads(user_id);
CREATE INDEX IF NOT EXISTS idx_threads_status ON message_threads(status, updated_at);
CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id, created_at);
CREATE INDEX IF NOT EXISTS idx_auth_events_user ON auth_events(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_auth_events_event ON auth_events(event, created_at);
"""


def _db_path() -> Path:
    return get_settings().data_dir / "dbmp_v2.db"


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()), timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def cursor() -> Iterator[sqlite3.Cursor]:
    conn = connect()
    try:
        yield conn.cursor()
        conn.commit()
    finally:
        conn.close()


def init() -> None:
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        # Lightweight migrations for older DBs.
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(server_keys)").fetchall()}
        if "public" not in cols:
            conn.execute("ALTER TABLE server_keys ADD COLUMN public INTEGER NOT NULL DEFAULT 0")
        ucols = {r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "failed_logins" not in ucols:
            conn.execute("ALTER TABLE users ADD COLUMN failed_logins INTEGER NOT NULL DEFAULT 0")
        if "locked_until" not in ucols:
            conn.execute("ALTER TABLE users ADD COLUMN locked_until INTEGER")
        conn.commit()
    finally:
        conn.close()
