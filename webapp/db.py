"""SQLite storage for the CV site.

Schema:
  visitors    - one row per device (device_id = fingerprint hash).
                  Stores IP history, geo, device name, capabilities, visit count,
                  and the per-client block keys the assistant has applied.
  visits      - append-only row per page load (path, ip, ua, lang, ref, ts).
  messages    - chat transcript rows per device.
  blocks      - per-client CSS/HTML/JS blocks (keyed by device_id + kind).
  block_pool  - admin-authored reusable blocks that any client may match.

All writes are behind a single sqlite3 connection with WAL. Reflex backend is
async but access here is short and guarded by a lock; conversions happen in the
State layer.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

_DB = Path("/web/data/site.db")
_LOCK = threading.Lock()

CREATE = """
CREATE TABLE IF NOT EXISTS visitors (
    device_id     TEXT PRIMARY KEY,
    first_seen    REAL NOT NULL,
    last_seen     REAL NOT NULL,
    visits        INTEGER NOT NULL DEFAULT 1,
    ips           TEXT NOT NULL DEFAULT '[]',
    geo           TEXT NOT NULL DEFAULT '{}',
    device_name   TEXT NOT NULL DEFAULT '',
    profile       TEXT NOT NULL DEFAULT '{}',
    block_keys    TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS visits (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         REAL NOT NULL,
    device_id  TEXT NOT NULL,
    path       TEXT NOT NULL DEFAULT '/',
    ip         TEXT NOT NULL DEFAULT '',
    ua         TEXT NOT NULL DEFAULT '',
    lang       TEXT NOT NULL DEFAULT '',
    ref        TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_visits_ts ON visits (ts);
CREATE INDEX IF NOT EXISTS idx_visits_device ON visits (device_id);
CREATE TABLE IF NOT EXISTS messages (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        REAL NOT NULL,
    device_id TEXT NOT NULL,
    role      TEXT NOT NULL,
    content   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_device ON messages (device_id, id);
CREATE TABLE IF NOT EXISTS blocks (
    key        TEXT PRIMARY KEY,
    device_id  TEXT NOT NULL,
    kind       TEXT NOT NULL,          -- css | html | js
    content    TEXT NOT NULL,
    created    REAL NOT NULL,
    updated    REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_blocks_device ON blocks (device_id);
CREATE TABLE IF NOT EXISTS block_pool (
    key        TEXT PRIMARY KEY,
    kind       TEXT NOT NULL,
    content    TEXT NOT NULL,
    created    REAL NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB, timeout=15)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=15000")
    conn.row_factory = sqlite3.Row
    return conn


def init() -> None:
    _DB.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        conn = _connect()
        try:
            conn.executescript(CREATE)
            conn.commit()
        finally:
            conn.close()


def upsert_visitor(
    device_id: str,
    ip: str,
    geo: dict,
    device_name: str,
    profile: dict,
    block_keys: list[str] | None = None,
) -> None:
    now = time.time()
    with _LOCK:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT ips, geo, visits, block_keys FROM visitors WHERE device_id=?",
                (device_id,),
            ).fetchone()
            now_ = now
            if row:
                ips_l = json.loads(row["ips"] or "[]")
                if ip and ip not in ips_l:
                    ips_l.append(ip)
                ips_l = ips_l[-25:]
                visits_n = int(row["visits"]) + 1
                merged_blocks = list(json.loads(row["block_keys"] or "[]"))
                if block_keys:
                    for k in block_keys:
                        if k not in merged_blocks:
                            merged_blocks.append(k)
                conn.execute(
                    """UPDATE visitors SET last_seen=?, visits=?, ips=?, geo=?,
                       device_name=?, profile=?, block_keys=? WHERE device_id=?""",
                    (
                        now_,
                        visits_n,
                        json.dumps(ips_l),
                        json.dumps(geo or {}),
                        device_name,
                        json.dumps(profile or {}),
                        json.dumps(merged_blocks),
                        device_id,
                    ),
                )
            else:
                conn.execute(
                    """INSERT INTO visitors
                       (device_id, first_seen, last_seen, visits, ips, geo,
                        device_name, profile, block_keys)
                       VALUES (?,?,?,1,?,?,?,?,?)""",
                    (
                        device_id,
                        now_,
                        now_,
                        json.dumps([ip] if ip else []),
                        json.dumps(geo or {}),
                        device_name,
                        json.dumps(profile or {}),
                        json.dumps(block_keys or []),
                    ),
                )
            conn.commit()
        finally:
            conn.close()


def log_visit(
    device_id: str,
    path: str,
    ip: str,
    ua: str,
    lang: str,
    ref: str,
) -> None:
    with _LOCK:
        conn = _connect()
        try:
            conn.execute(
                "INSERT INTO visits (ts, device_id, path, ip, ua, lang, ref) VALUES (?,?,?,?,?,?,?)",
                (time.time(), device_id, path, ip, ua, lang, ref),
            )
            conn.commit()
        finally:
            conn.close()


def get_visitor(device_id: str) -> dict | None:
    with _LOCK:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT * FROM visitors WHERE device_id=?", (device_id,)
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            for k in ("ips", "geo", "profile", "block_keys"):
                try:
                    d[k] = json.loads(d[k] or "[]" if k != "geo" else (d[k] or "{}"))
                except Exception:
                    d[k] = [] if k != "geo" else {}
            return d
        finally:
            conn.close()


def log_message(device_id: str, role: str, content: str) -> None:
    with _LOCK:
        conn = _connect()
        try:
            conn.execute(
                "INSERT INTO messages (ts, device_id, role, content) VALUES (?,?,?,?)",
                (time.time(), device_id, role, content),
            )
            conn.commit()
        finally:
            conn.close()


def recent_messages(device_id: str, limit: int = 40) -> list[dict]:
    with _LOCK:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT id, ts, role, content FROM messages WHERE device_id=? "
                "ORDER BY id DESC LIMIT ?",
                (device_id, limit),
            ).fetchall()
            return [{"id": r["id"], "ts": r["ts"], "role": r["role"], "content": r["content"]} for r in rows][::-1]
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Per-client blocks + admin pool
# ---------------------------------------------------------------------------

def save_block(device_id: str, key: str, kind: str, content: str) -> None:
    now = time.time()
    with _LOCK:
        conn = _connect()
        try:
            conn.execute(
                """INSERT INTO blocks (key, device_id, kind, content, created, updated)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(key) DO UPDATE SET content=excluded.content,
                     kind=excluded.kind, updated=excluded.updated""",
                (key, device_id, kind, content, now, now),
            )
            conn.commit()
        finally:
            conn.close()


def delete_block(device_id: str, key: str) -> None:
    with _LOCK:
        conn = _connect()
        try:
            conn.execute("DELETE FROM blocks WHERE device_id=? AND key=?", (device_id, key))
            conn.commit()
        finally:
            conn.close()


def get_blocks(device_id: str) -> list[dict]:
    with _LOCK:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT key, kind, content FROM blocks WHERE device_id=? ORDER BY updated",
                (device_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def pool_add(key: str, kind: str, content: str) -> None:
    with _LOCK:
        conn = _connect()
        try:
            conn.execute(
                """INSERT INTO block_pool (key, kind, content, created)
                   VALUES (?,?,?,?)
                   ON CONFLICT(key) DO UPDATE SET content=excluded.content""",
                (key, kind, content, time.time()),
            )
            conn.commit()
        finally:
            conn.close()


def pool_all() -> list[dict]:
    with _LOCK:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT key, kind, content FROM block_pool ORDER BY created"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def recent_visitors(limit: int = 50) -> list[dict]:
    with _LOCK:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT device_id, device_name, first_seen, last_seen, visits, ips, profile "
                "FROM visitors ORDER BY last_seen DESC LIMIT ?",
                (limit,),
            ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                try:
                    d["ips"] = json.loads(d["ips"] or "[]")
                except Exception:
                    d["ips"] = []
                try:
                    d["profile"] = json.loads(d["profile"] or "{}")
                except Exception:
                    d["profile"] = {}
                out.append(d)
            return out
        finally:
            conn.close()