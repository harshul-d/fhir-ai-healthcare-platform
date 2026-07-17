import json
import sqlite3
from pathlib import Path

DB_PATH = Path("backend/ehr.sqlite")


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _connect()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bundles (
            patient_mrn TEXT PRIMARY KEY,
            patient_name TEXT,
            bundle_json TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS summaries (
            cache_key TEXT PRIMARY KEY,
            patient_mrn TEXT,
            summary_json TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def save_bundle(mrn: str, name: str, bundle_json: str):
    conn = _connect()
    conn.execute(
        "INSERT OR REPLACE INTO bundles (patient_mrn, patient_name, bundle_json) VALUES (?, ?, ?)",
        (mrn, name, bundle_json),
    )
    conn.commit()
    conn.close()


def get_bundle(mrn: str):
    conn = _connect()
    row = conn.execute("SELECT * FROM bundles WHERE patient_mrn = ?", (mrn,)).fetchone()
    conn.close()
    return dict(row) if row else None


def all_bundles():
    conn = _connect()
    rows = conn.execute("SELECT * FROM bundles").fetchall()
    conn.close()
    return [dict(r) for r in rows]