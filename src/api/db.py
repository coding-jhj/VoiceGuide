import sqlite3
import json
from datetime import datetime

DB_PATH = "voiceguide.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            space_id  TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            objects   TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def get_snapshot(space_id: str) -> list[dict] | None:
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT objects FROM snapshots WHERE space_id = ? ORDER BY id DESC LIMIT 1",
        (space_id,)
    ).fetchone()
    conn.close()
    return json.loads(row[0]) if row else None


def save_snapshot(space_id: str, objects: list[dict]):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO snapshots (space_id, timestamp, objects) VALUES (?, ?, ?)",
        (space_id, datetime.now().isoformat(), json.dumps(objects, ensure_ascii=False))
    )
    conn.commit()
    conn.close()
