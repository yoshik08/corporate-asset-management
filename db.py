"""Database helpers for the Corporate Asset Management System.

Uses SQLite (stdlib sqlite3). One connection per request via Flask's
app context; schema lives in schema.sql next to this file.
"""
import json
import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# On Vercel the deployment filesystem is read-only except /tmp, so the
# SQLite database lives there (fresh seeded demo data per instance).
ON_VERCEL = os.environ.get("VERCEL") == "1"
DB_PATH = ("/tmp/asset_manager.db" if ON_VERCEL
           else os.path.join(BASE_DIR, "asset_manager.db"))
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create tables from schema.sql (idempotent)."""
    conn = get_connection()
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()


def db_exists():
    return os.path.exists(DB_PATH)


def row_to_dict(row):
    return dict(row) if row is not None else None


def rows_to_dicts(rows):
    return [dict(r) for r in rows]


def audit(conn, entity_type, entity_id, action, details, actor="admin"):
    """Append one row to the audit log. Call inside the same transaction
    as the change it records, so both commit or neither does."""
    if isinstance(details, dict):
        details = json.dumps(details)
    conn.execute(
        "INSERT INTO audit_log (entity_type, entity_id, action, actor, details)"
        " VALUES (?, ?, ?, ?, ?)",
        (entity_type, entity_id, action, actor, details),
    )
