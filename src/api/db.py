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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS saved_locations (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            label     TEXT NOT NULL,
            wifi_ssid TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


# ── 공간 스냅샷 ──────────────────────────────────────────────────────────────

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


# ── 개인 장소 저장 (개인 네비게이팅) ─────────────────────────────────────────

def save_location(label: str, wifi_ssid: str):
    """현재 WiFi 위치에 이름표를 붙여 저장."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO saved_locations (label, wifi_ssid, timestamp) VALUES (?, ?, ?)",
        (label, wifi_ssid, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def delete_location(label: str):
    """저장된 장소 삭제."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM saved_locations WHERE label = ?", (label,))
    conn.commit()
    conn.close()


def get_locations(wifi_ssid: str = "") -> list[dict]:
    """저장된 장소 목록. wifi_ssid 지정 시 해당 SSID의 장소만 반환."""
    conn = sqlite3.connect(DB_PATH)
    if wifi_ssid:
        rows = conn.execute(
            "SELECT label, wifi_ssid, timestamp FROM saved_locations WHERE wifi_ssid = ? ORDER BY id DESC",
            (wifi_ssid,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT label, wifi_ssid, timestamp FROM saved_locations ORDER BY id DESC"
        ).fetchall()
    conn.close()
    return [{"label": r[0], "wifi_ssid": r[1], "timestamp": r[2]} for r in rows]


def find_location(label: str) -> dict | None:
    """라벨로 장소 검색 (부분 일치)."""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT label, wifi_ssid, timestamp FROM saved_locations WHERE label LIKE ? ORDER BY id DESC LIMIT 1",
        (f"%{label}%",)
    ).fetchone()
    conn.close()
    return {"label": row[0], "wifi_ssid": row[1], "timestamp": row[2]} if row else None
