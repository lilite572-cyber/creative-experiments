"""Small transactional store. Media paths never come from clients."""

import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(
    os.environ.get("CE_DATA_DIR", Path(__file__).resolve().parents[1] / "data")
).resolve()


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return uuid.uuid4().hex


def connect():
    ROOT.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(ROOT / "creative.sqlite", timeout=20)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c


def init():
    with connect() as c:
        c.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,password TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT REFERENCES users(id),expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS workspaces(id TEXT PRIMARY KEY,owner TEXT REFERENCES users(id),payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY,wid TEXT REFERENCES workspaces(id),kind TEXT NOT NULL,payload TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS records_scope ON records(wid,kind);
        """)


def pack(x):
    return json.dumps(x, ensure_ascii=False, allow_nan=False)


def save(c, wid, kind, value):
    c.execute(
        "INSERT INTO records(id,wid,kind,payload) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
        (value["id"], wid, kind, pack(value)),
    )


def rows(c, wid, kind):
    return [
        json.loads(r[0])
        for r in c.execute(
            "SELECT payload FROM records WHERE wid=? AND kind=? ORDER BY rowid",
            (wid, kind),
        )
    ]


def record(c, wid, kind, rid):
    r = c.execute(
        "SELECT payload FROM records WHERE wid=? AND kind=? AND id=?", (wid, kind, rid)
    ).fetchone()
    return json.loads(r[0]) if r else None


def password(value, salt=None):
    salt = salt or os.urandom(16).hex()
    return (
        salt
        + ":"
        + hashlib.pbkdf2_hmac(
            "sha256", value.encode(), bytes.fromhex(salt), 240000
        ).hex()
    )
