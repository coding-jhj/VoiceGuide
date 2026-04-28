"""
VoiceGuide DB 모듈
==================
DATABASE_URL 환경변수 유무에 따라 자동 전환:
  - 없음 → SQLite (로컬, 파일 기반)
  - 있음 → PostgreSQL / Supabase (외부, LTE 접속 가능)

설정 방법:
  로컬: .env에 DATABASE_URL 없으면 자동으로 SQLite 사용
  외부: .env에 DATABASE_URL=postgresql://... 추가 (Supabase 연결 문자열)
        서버_DB/SUPABASE_DB_CONNECT_GUIDE.md 참고
"""

import os
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime

# ── 모드 결정 ─────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL")  # Supabase: postgresql://user:pass@host/db
DB_PATH      = "voiceguide.db"            # SQLite 로컬 파일
_IS_POSTGRES = bool(DATABASE_URL)

_pool = None  # PostgreSQL 커넥션 풀 (Supabase 모드에서만)


def _get_pool():
    global _pool
    if _pool is None:
        from psycopg_pool import ConnectionPool
        from psycopg.rows import dict_row
        _pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=5, open=True,
                               kwargs={"row_factory": dict_row})
    return _pool


@contextmanager
def _conn():
    """SQLite / PostgreSQL 구분 없이 사용하는 커넥션 컨텍스트."""
    if _IS_POSTGRES:
        with _get_pool().connection() as conn:
            yield conn
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


# ── DB 초기화 ─────────────────────────────────────────────────────────────────

def init_db():
    """앱 시작 시 테이블 생성. 이미 있으면 무시."""
    if _IS_POSTGRES:
        _init_postgres()
    else:
        _init_sqlite()
    mode = "PostgreSQL/Supabase" if _IS_POSTGRES else "SQLite"
    print(f"[DB] 초기화 완료 ({mode})")


def _init_sqlite():
    with _conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                space_id  TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                objects   TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS saved_locations (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                label     TEXT NOT NULL,
                wifi_ssid TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS gps_history (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                lat        REAL NOT NULL,
                lng        REAL NOT NULL,
                timestamp  TEXT NOT NULL
            );
        """)


def _init_postgres():
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS snapshots (
                    id        BIGSERIAL PRIMARY KEY,
                    space_id  TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    objects   TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS saved_locations (
                    id        BIGSERIAL PRIMARY KEY,
                    label     TEXT NOT NULL,
                    wifi_ssid TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS gps_history (
                    id         BIGSERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    lat        DOUBLE PRECISION NOT NULL,
                    lng        DOUBLE PRECISION NOT NULL,
                    timestamp  TEXT NOT NULL
                )
            """)


# ── 공간 스냅샷 ───────────────────────────────────────────────────────────────

def get_snapshot(space_id: str) -> list[dict] | None:
    with _conn() as conn:
        if _IS_POSTGRES:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT objects FROM snapshots WHERE space_id = %s "
                    "ORDER BY id DESC LIMIT 1", (space_id,))
                row = cur.fetchone()
            return json.loads(row["objects"]) if row else None
        else:
            row = conn.execute(
                "SELECT objects FROM snapshots WHERE space_id = ? "
                "ORDER BY id DESC LIMIT 1", (space_id,)).fetchone()
            return json.loads(row[0]) if row else None


def save_snapshot(space_id: str, objects: list[dict]):
    ts  = datetime.now().isoformat()
    obj = json.dumps(objects, ensure_ascii=False)
    with _conn() as conn:
        if _IS_POSTGRES:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO snapshots (space_id, timestamp, objects) "
                    "VALUES (%s, %s, %s)", (space_id, ts, obj))
        else:
            conn.execute(
                "INSERT INTO snapshots (space_id, timestamp, objects) "
                "VALUES (?, ?, ?)", (space_id, ts, obj))


# ── 개인 장소 저장 ────────────────────────────────────────────────────────────

def save_location(label: str, wifi_ssid: str):
    ts = datetime.now().isoformat()
    with _conn() as conn:
        if _IS_POSTGRES:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO saved_locations (label, wifi_ssid, timestamp) "
                    "VALUES (%s, %s, %s)", (label, wifi_ssid, ts))
        else:
            conn.execute(
                "INSERT INTO saved_locations (label, wifi_ssid, timestamp) "
                "VALUES (?, ?, ?)", (label, wifi_ssid, ts))


def delete_location(label: str):
    with _conn() as conn:
        if _IS_POSTGRES:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM saved_locations WHERE label = %s", (label,))
        else:
            conn.execute(
                "DELETE FROM saved_locations WHERE label = ?", (label,))


def get_locations(wifi_ssid: str = "") -> list[dict]:
    with _conn() as conn:
        if _IS_POSTGRES:
            with conn.cursor() as cur:
                if wifi_ssid:
                    cur.execute(
                        "SELECT label, wifi_ssid, timestamp FROM saved_locations "
                        "WHERE wifi_ssid = %s ORDER BY id DESC", (wifi_ssid,))
                else:
                    cur.execute(
                        "SELECT label, wifi_ssid, timestamp FROM saved_locations "
                        "ORDER BY id DESC")
                rows = cur.fetchall()
            return [{"label": r["label"], "wifi_ssid": r["wifi_ssid"],
                     "timestamp": r["timestamp"]} for r in rows]
        else:
            if wifi_ssid:
                rows = conn.execute(
                    "SELECT label, wifi_ssid, timestamp FROM saved_locations "
                    "WHERE wifi_ssid = ? ORDER BY id DESC", (wifi_ssid,)).fetchall()
            else:
                rows = conn.execute(
                    "SELECT label, wifi_ssid, timestamp FROM saved_locations "
                    "ORDER BY id DESC").fetchall()
            return [{"label": r[0], "wifi_ssid": r[1], "timestamp": r[2]}
                    for r in rows]


def find_location(label: str) -> dict | None:
    with _conn() as conn:
        if _IS_POSTGRES:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT label, wifi_ssid, timestamp FROM saved_locations "
                    "WHERE label LIKE %s ORDER BY id DESC LIMIT 1",
                    (f"%{label}%",))
                row = cur.fetchone()
            return {"label": row["label"], "wifi_ssid": row["wifi_ssid"],
                    "timestamp": row["timestamp"]} if row else None
        else:
            row = conn.execute(
                "SELECT label, wifi_ssid, timestamp FROM saved_locations "
                "WHERE label LIKE ? ORDER BY id DESC LIMIT 1",
                (f"%{label}%",)).fetchone()
            return {"label": row[0], "wifi_ssid": row[1],
                    "timestamp": row[2]} if row else None


# ── GPS 위치 이력 ─────────────────────────────────────────────────────────────

def save_gps(session_id: str, lat: float, lng: float):
    ts = datetime.now().isoformat()
    with _conn() as conn:
        if _IS_POSTGRES:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO gps_history (session_id, lat, lng, timestamp) "
                    "VALUES (%s, %s, %s, %s)", (session_id, lat, lng, ts))
                cur.execute(
                    "DELETE FROM gps_history WHERE session_id = %s AND id NOT IN "
                    "(SELECT id FROM gps_history WHERE session_id = %s "
                    " ORDER BY id DESC LIMIT 200)",
                    (session_id, session_id))
        else:
            conn.execute(
                "INSERT INTO gps_history (session_id, lat, lng, timestamp) "
                "VALUES (?, ?, ?, ?)", (session_id, lat, lng, ts))
            conn.execute(
                "DELETE FROM gps_history WHERE session_id = ? AND id NOT IN "
                "(SELECT id FROM gps_history WHERE session_id = ? "
                " ORDER BY id DESC LIMIT 200)",
                (session_id, session_id))


def get_last_gps(session_id: str) -> dict | None:
    with _conn() as conn:
        if _IS_POSTGRES:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT lat, lng, timestamp FROM gps_history "
                    "WHERE session_id = %s ORDER BY id DESC LIMIT 1",
                    (session_id,))
                row = cur.fetchone()
            return {"lat": row["lat"], "lng": row["lng"],
                    "timestamp": row["timestamp"]} if row else None
        else:
            row = conn.execute(
                "SELECT lat, lng, timestamp FROM gps_history "
                "WHERE session_id = ? ORDER BY id DESC LIMIT 1",
                (session_id,)).fetchone()
            return {"lat": row[0], "lng": row[1],
                    "timestamp": row[2]} if row else None


def get_gps_track(session_id: str, limit: int = 100) -> list[dict]:
    with _conn() as conn:
        if _IS_POSTGRES:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT lat, lng, timestamp FROM gps_history "
                    "WHERE session_id = %s ORDER BY id DESC LIMIT %s",
                    (session_id, limit))
                rows = cur.fetchall()
            result = [{"lat": r["lat"], "lng": r["lng"],
                       "timestamp": r["timestamp"]} for r in rows]
        else:
            rows = conn.execute(
                "SELECT lat, lng, timestamp FROM gps_history "
                "WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, limit)).fetchall()
            result = [{"lat": r[0], "lng": r[1], "timestamp": r[2]}
                      for r in rows]
    return list(reversed(result))  # 시간순 오름차순 반환
