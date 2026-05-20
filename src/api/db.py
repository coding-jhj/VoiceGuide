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
import queue
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone

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
            CREATE TABLE IF NOT EXISTS detection_events (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id     TEXT NOT NULL UNIQUE,
                request_id   TEXT,
                session_id   TEXT NOT NULL,
                device_id    TEXT,
                wifi_ssid    TEXT,
                mode         TEXT,
                timestamp    TEXT NOT NULL,
                lat          REAL,
                lng          REAL,
                objects_json TEXT NOT NULL,
                hazards_json TEXT NOT NULL,
                scene_json   TEXT NOT NULL,
                raw_json     TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS detections (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id        TEXT NOT NULL,
                session_id      TEXT NOT NULL,
                class_name      TEXT,
                class_ko        TEXT NOT NULL,
                confidence      REAL,
                bbox_x          REAL,
                bbox_y          REAL,
                bbox_w          REAL,
                bbox_h          REAL,
                direction       TEXT,
                distance_m      REAL,
                risk_score      REAL,
                timestamp       TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_detection_events_session_time
                ON detection_events (session_id, id DESC);
            CREATE INDEX IF NOT EXISTS idx_detections_session_time
                ON detections (session_id, id DESC);
            CREATE INDEX IF NOT EXISTS idx_detections_class
                ON detections (class_ko);
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
            CREATE TABLE IF NOT EXISTS gps_routes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                route_id    TEXT NOT NULL UNIQUE,
                session_id  TEXT NOT NULL,
                name        TEXT,
                started_at  TEXT NOT NULL,
                ended_at    TEXT NOT NULL,
                point_count INTEGER NOT NULL DEFAULT 0,
                points_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_gps_routes_session
                ON gps_routes (session_id, id DESC);
            CREATE TABLE IF NOT EXISTS recent_detections (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id   TEXT    NOT NULL,
                session_id  TEXT    NOT NULL,
                request_id  TEXT    NOT NULL DEFAULT '',
                class_ko    TEXT    NOT NULL,
                confidence  REAL    NOT NULL,
                cx          REAL    NOT NULL,
                cy          REAL    NOT NULL,
                w           REAL    NOT NULL,
                h           REAL    NOT NULL,
                zone        TEXT    NOT NULL DEFAULT '12시',
                dist_m      REAL    NOT NULL DEFAULT 0.0,
                is_vehicle  INTEGER NOT NULL DEFAULT 0,
                is_animal   INTEGER NOT NULL DEFAULT 0,
                mode        TEXT    NOT NULL DEFAULT '장애물',
                lat         REAL    NOT NULL DEFAULT 0.0,
                lng         REAL    NOT NULL DEFAULT 0.0,
                detected_at TEXT    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_recent_detections_session_time
                ON recent_detections (session_id, id DESC);
        """)


def _init_postgres():
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS detection_events (
                    id           BIGSERIAL PRIMARY KEY,
                    event_id     TEXT NOT NULL UNIQUE,
                    request_id   TEXT,
                    session_id   TEXT NOT NULL,
                    device_id    TEXT,
                    wifi_ssid    TEXT,
                    mode         TEXT,
                    timestamp    TIMESTAMPTZ NOT NULL,
                    lat          DOUBLE PRECISION,
                    lng          DOUBLE PRECISION,
                    objects_json JSONB NOT NULL,
                    hazards_json JSONB NOT NULL,
                    scene_json   JSONB NOT NULL,
                    raw_json     JSONB NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS detections (
                    id              BIGSERIAL PRIMARY KEY,
                    event_id        TEXT NOT NULL REFERENCES detection_events(event_id) ON DELETE CASCADE,
                    session_id      TEXT NOT NULL,
                    class_name      TEXT,
                    class_ko        TEXT NOT NULL,
                    confidence      DOUBLE PRECISION,
                    bbox_x          DOUBLE PRECISION,
                    bbox_y          DOUBLE PRECISION,
                    bbox_w          DOUBLE PRECISION,
                    bbox_h          DOUBLE PRECISION,
                    direction       TEXT,
                    distance_m      DOUBLE PRECISION,
                    risk_score      DOUBLE PRECISION,
                    timestamp       TIMESTAMPTZ NOT NULL
                )
            """)
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_detection_events_session_time "
                "ON detection_events (session_id, id DESC)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_detections_session_time "
                "ON detections (session_id, id DESC)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_detections_class "
                "ON detections (class_ko)"
            )
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
            cur.execute("""
                CREATE TABLE IF NOT EXISTS gps_routes (
                    id          BIGSERIAL PRIMARY KEY,
                    route_id    TEXT NOT NULL UNIQUE,
                    session_id  TEXT NOT NULL,
                    name        TEXT,
                    started_at  TEXT NOT NULL,
                    ended_at    TEXT NOT NULL,
                    point_count INTEGER NOT NULL DEFAULT 0,
                    points_json JSONB NOT NULL
                )
            """)
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_gps_routes_session "
                "ON gps_routes (session_id, id DESC)"
            )
            cur.execute("""
                CREATE TABLE IF NOT EXISTS recent_detections (
                    id          BIGSERIAL PRIMARY KEY,
                    device_id   TEXT             NOT NULL,
                    session_id  TEXT             NOT NULL,
                    request_id  TEXT             NOT NULL DEFAULT '',
                    class_ko    TEXT             NOT NULL,
                    confidence  DOUBLE PRECISION NOT NULL,
                    cx          DOUBLE PRECISION NOT NULL,
                    cy          DOUBLE PRECISION NOT NULL,
                    w           DOUBLE PRECISION NOT NULL,
                    h           DOUBLE PRECISION NOT NULL,
                    zone        TEXT             NOT NULL DEFAULT '12시',
                    dist_m      DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                    is_vehicle  BOOLEAN          NOT NULL DEFAULT FALSE,
                    is_animal   BOOLEAN          NOT NULL DEFAULT FALSE,
                    mode        TEXT             NOT NULL DEFAULT '장애물',
                    lat         DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                    lng         DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                    detected_at TEXT             NOT NULL
                )
            """)
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_recent_detections_session_time "
                "ON recent_detections (session_id, id DESC)"
            )


# ── 공간 스냅샷 ───────────────────────────────────────────────────────────────

def get_snapshot(space_id: str, max_age_s: float | None = None) -> list[dict] | None:
    cutoff = None
    if max_age_s is not None:
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=max_age_s)).isoformat()
    with _conn() as conn:
        if _IS_POSTGRES:
            with conn.cursor() as cur:
                if cutoff:
                    cur.execute(
                        "SELECT objects FROM snapshots WHERE space_id = %s "
                        "AND timestamp > %s ORDER BY id DESC LIMIT 1", (space_id, cutoff))
                else:
                    cur.execute(
                        "SELECT objects FROM snapshots WHERE space_id = %s "
                        "ORDER BY id DESC LIMIT 1", (space_id,))
                row = cur.fetchone()
            return json.loads(row["objects"]) if row else None
        else:
            if cutoff:
                row = conn.execute(
                    "SELECT objects FROM snapshots WHERE space_id = ? "
                    "AND timestamp > ? ORDER BY id DESC LIMIT 1", (space_id, cutoff)).fetchone()
            else:
                row = conn.execute(
                    "SELECT objects FROM snapshots WHERE space_id = ? "
                    "ORDER BY id DESC LIMIT 1", (space_id,)).fetchone()
            return json.loads(row[0]) if row else None


_SNAPSHOT_KEEP = 20  # 공간별 스냅샷 최대 보관 수 (이 이상이면 오래된 것부터 삭제)
_EVENT_KEEP = 200
_EVENT_QUEUE_MAX = int(os.getenv("DETECTION_EVENT_QUEUE_MAX", "512"))
_EVENT_BATCH_SIZE = int(os.getenv("DETECTION_EVENT_BATCH_SIZE", "24"))
_EVENT_FLUSH_INTERVAL_S = float(os.getenv("DETECTION_EVENT_FLUSH_INTERVAL_S", "0.25"))
_event_queue: queue.Queue[dict | None] = queue.Queue(maxsize=_EVENT_QUEUE_MAX)
_writer_stop = threading.Event()
_writer_thread: threading.Thread | None = None
_dropped_event_count = 0


def start_event_writer() -> None:
    """Start the background writer used by /detect to avoid request-thread DB stalls."""
    global _writer_thread
    if _writer_thread and _writer_thread.is_alive():
        return
    _writer_stop.clear()
    _writer_thread = threading.Thread(target=_event_writer_loop, name="vg-db-writer", daemon=True)
    _writer_thread.start()


def stop_event_writer(timeout_s: float = 3.0) -> None:
    _writer_stop.set()
    try:
        _event_queue.put_nowait(None)
    except queue.Full:
        pass
    if _writer_thread and _writer_thread.is_alive():
        _writer_thread.join(timeout=timeout_s)


def get_event_writer_stats() -> dict:
    return {
        "queued": _event_queue.qsize(),
        "dropped": _dropped_event_count,
        "running": bool(_writer_thread and _writer_thread.is_alive()),
    }


def enqueue_detection_event(**kwargs) -> bool:
    global _dropped_event_count
    try:
        _event_queue.put_nowait(kwargs)
        return True
    except queue.Full:
        _dropped_event_count += 1
        return False


def _event_writer_loop() -> None:
    while not _writer_stop.is_set():
        batch = []
        try:
            first = _event_queue.get(timeout=_EVENT_FLUSH_INTERVAL_S)
        except queue.Empty:
            continue
        if first is None:
            break
        batch.append(first)

        deadline = time.monotonic() + _EVENT_FLUSH_INTERVAL_S
        while len(batch) < _EVENT_BATCH_SIZE and time.monotonic() < deadline:
            try:
                item = _event_queue.get_nowait()
            except queue.Empty:
                break
            if item is None:
                _writer_stop.set()
                break
            batch.append(item)

        for item in batch:
            try:
                save_detection_event(**item)
            except Exception as e:
                print(f"[DB] detection event async save failed: {e}")
            finally:
                _event_queue.task_done()

    while True:
        try:
            item = _event_queue.get_nowait()
        except queue.Empty:
            break
        if item is not None:
            try:
                save_detection_event(**item)
            except Exception as e:
                print(f"[DB] detection event final flush failed: {e}")
        _event_queue.task_done()


def save_detection_event(
    *,
    event_id: str,
    request_id: str,
    session_id: str,
    device_id: str,
    wifi_ssid: str,
    mode: str,
    objects: list[dict],
    hazards: list[dict],
    scene: dict,
    raw_payload: dict,
    lat: float | None = None,
    lng: float | None = None,
) -> None:
    """온디바이스 탐지 결과 이벤트와 개별 객체 행을 함께 저장한다."""
    ts = datetime.now().isoformat()
    objects_json = json.dumps(objects, ensure_ascii=False)
    hazards_json = json.dumps(hazards, ensure_ascii=False)
    scene_json = json.dumps(scene, ensure_ascii=False)
    raw_json = json.dumps(raw_payload, ensure_ascii=False)

    with _conn() as conn:
        if _IS_POSTGRES:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO detection_events "
                    "(event_id, request_id, session_id, device_id, wifi_ssid, mode, timestamp, "
                    " lat, lng, objects_json, hazards_json, scene_json, raw_json) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb) "
                    "ON CONFLICT (event_id) DO NOTHING",
                    (event_id, request_id, session_id, device_id, wifi_ssid, mode, ts,
                     lat, lng, objects_json, hazards_json, scene_json, raw_json),
                )
                cur.execute("DELETE FROM detections WHERE event_id = %s", (event_id,))
                _insert_detection_rows(cur, event_id, session_id, objects, ts, postgres=True)
                cur.execute(
                    "DELETE FROM detection_events WHERE session_id = %s AND id NOT IN "
                    "(SELECT id FROM detection_events WHERE session_id = %s ORDER BY id DESC LIMIT %s)",
                    (session_id, session_id, _EVENT_KEEP),
                )
        else:
            conn.execute(
                "INSERT OR IGNORE INTO detection_events "
                "(event_id, request_id, session_id, device_id, wifi_ssid, mode, timestamp, "
                " lat, lng, objects_json, hazards_json, scene_json, raw_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (event_id, request_id, session_id, device_id, wifi_ssid, mode, ts,
                 lat, lng, objects_json, hazards_json, scene_json, raw_json),
            )
            conn.execute("DELETE FROM detections WHERE event_id = ?", (event_id,))
            _insert_detection_rows(conn, event_id, session_id, objects, ts, postgres=False)
            conn.execute(
                "DELETE FROM detection_events WHERE session_id = ? AND id NOT IN "
                "(SELECT id FROM detection_events WHERE session_id = ? ORDER BY id DESC LIMIT ?)",
                (session_id, session_id, _EVENT_KEEP),
            )


def _insert_detection_rows(cur, event_id: str, session_id: str, objects: list[dict], ts: str, postgres: bool) -> None:
    rows = []
    for obj in objects:
        bbox = obj.get("bbox_norm_xywh") or [None, None, None, None]
        rows.append((
            event_id,
            session_id,
            obj.get("class", ""),
            obj.get("class_ko", ""),
            obj.get("confidence"),
            bbox[0] if len(bbox) > 0 else None,
            bbox[1] if len(bbox) > 1 else None,
            bbox[2] if len(bbox) > 2 else None,
            bbox[3] if len(bbox) > 3 else None,
            obj.get("direction"),
            obj.get("distance_m"),
            obj.get("risk_score"),
            ts,
        ))
    if not rows:
        return

    if postgres:
        cur.executemany(
            "INSERT INTO detections "
            "(event_id, session_id, class_name, class_ko, confidence, bbox_x, bbox_y, bbox_w, bbox_h, "
            " direction, distance_m, risk_score, timestamp) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            rows,
        )
    else:
        cur.executemany(
            "INSERT INTO detections "
            "(event_id, session_id, class_name, class_ko, confidence, bbox_x, bbox_y, bbox_w, bbox_h, "
            " direction, distance_m, risk_score, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )


def get_latest_detection_event(session_id: str) -> dict | None:
    with _conn() as conn:
        if _IS_POSTGRES:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT event_id, request_id, timestamp, objects_json, hazards_json, scene_json "
                    "FROM detection_events WHERE session_id = %s ORDER BY id DESC LIMIT 1",
                    (session_id,),
                )
                row = cur.fetchone()
            if not row:
                return None
            return {
                "event_id": row["event_id"],
                "request_id": row["request_id"],
                "timestamp": str(row["timestamp"]),
                "objects": row["objects_json"],
                "hazards": row["hazards_json"],
                "scene": row["scene_json"],
            }
        row = conn.execute(
            "SELECT event_id, request_id, timestamp, objects_json, hazards_json, scene_json "
            "FROM detection_events WHERE session_id = ? ORDER BY id DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "event_id": row[0],
            "request_id": row[1],
            "timestamp": row[2],
            "objects": json.loads(row[3]),
            "hazards": json.loads(row[4]),
            "scene": json.loads(row[5]),
        }


def save_snapshot(space_id: str, objects: list[dict]):
    ts  = datetime.now().isoformat()          # ISO 8601 형식 타임스탬프
    obj = json.dumps(objects, ensure_ascii=False)  # 한국어 유지하여 JSON 직렬화
    with _conn() as conn:
        if _IS_POSTGRES:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO snapshots (space_id, timestamp, objects) "
                    "VALUES (%s, %s, %s)", (space_id, ts, obj))
                # 공간별 최근 N개만 유지 (DB 무한 증가 방지)
                cur.execute(
                    "DELETE FROM snapshots WHERE space_id = %s AND id NOT IN "
                    "(SELECT id FROM snapshots WHERE space_id = %s "
                    " ORDER BY id DESC LIMIT %s)",
                    (space_id, space_id, _SNAPSHOT_KEEP))
        else:
            conn.execute(
                "INSERT INTO snapshots (space_id, timestamp, objects) "
                "VALUES (?, ?, ?)", (space_id, ts, obj))
            # 공간별 최근 N개만 유지 (DB 무한 증가 방지)
            conn.execute(
                "DELETE FROM snapshots WHERE space_id = ? AND id NOT IN "
                "(SELECT id FROM snapshots WHERE space_id = ? "
                " ORDER BY id DESC LIMIT ?)",
                (space_id, space_id, _SNAPSHOT_KEEP))


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


def delete_location(label: str, wifi_ssid: str = "") -> int:
    with _conn() as conn:
        if _IS_POSTGRES:
            with conn.cursor() as cur:
                if wifi_ssid:
                    cur.execute(
                        "DELETE FROM saved_locations WHERE label = %s AND wifi_ssid = %s",
                        (label, wifi_ssid),
                    )
                else:
                    cur.execute(
                        "DELETE FROM saved_locations WHERE label = %s", (label,))
                return cur.rowcount
        else:
            if wifi_ssid:
                cur = conn.execute(
                    "DELETE FROM saved_locations WHERE label = ? AND wifi_ssid = ?",
                    (label, wifi_ssid),
                )
            else:
                cur = conn.execute(
                    "DELETE FROM saved_locations WHERE label = ?", (label,))
            return cur.rowcount


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


def get_recent_sessions(limit: int = 10) -> list[str]:
    """GPS 데이터가 있는 최근 세션 ID 목록 반환 (대시보드 세션 선택용)."""
    with _conn() as conn:
        if _IS_POSTGRES:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT session_id FROM gps_history "
                    "GROUP BY session_id "
                    "ORDER BY MAX(id) DESC LIMIT %s", (limit,))
                rows = cur.fetchall()
            return [r["session_id"] for r in rows]
        else:
            rows = conn.execute(
                "SELECT session_id FROM gps_history "
                "GROUP BY session_id "
                "ORDER BY MAX(id) DESC LIMIT ?", (limit,)).fetchall()
            return [r[0] for r in rows]


def get_latest_session() -> str | None:
    """가장 최근 GPS를 보낸 세션 ID 반환."""
    sessions = get_recent_sessions(limit=1)
    return sessions[0] if sessions else None


# ── 온디바이스 탐지 결과 저장 ─────────────────────────────────────────────────

_DETECTIONS_KEEP = 500  # 세션별 최대 보관 수

def save_detections(
    device_id: str,
    session_id: str,
    request_id: str,
    detections: list[dict],
    mode: str = "장애물",
    lat: float = 0.0,
    lng: float = 0.0,
) -> None:
    """폰에서 온 탐지 결과 리스트를 DB에 저장."""
    if not detections:
        return
    ts = datetime.now().isoformat()
    with _conn() as conn:
        if _IS_POSTGRES:
            rows = [
                (device_id, session_id, request_id,
                 d.get("class_ko", ""), d.get("confidence", 0.0),
                 d.get("cx", 0.0), d.get("cy", 0.0),
                 d.get("w", 0.0),  d.get("h", 0.0),
                 d.get("zone", "12시"), d.get("dist_m", 0.0),
                 d.get("is_vehicle", False), d.get("is_animal", False),
                 mode, lat, lng, ts)
                for d in detections
            ]
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO recent_detections "
                    "(device_id, session_id, request_id, class_ko, confidence, "
                    " cx, cy, w, h, zone, dist_m, is_vehicle, is_animal, "
                    " mode, lat, lng, detected_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    rows,
                )
                cur.execute(
                    "DELETE FROM recent_detections WHERE session_id = %s AND id NOT IN "
                    "(SELECT id FROM recent_detections WHERE session_id = %s "
                    " ORDER BY id DESC LIMIT %s)",
                    (session_id, session_id, _DETECTIONS_KEEP),
                )
        else:
            rows = [
                (device_id, session_id, request_id,
                 d.get("class_ko", ""), d.get("confidence", 0.0),
                 d.get("cx", 0.0), d.get("cy", 0.0),
                 d.get("w", 0.0),  d.get("h", 0.0),
                 d.get("zone", "12시"), d.get("dist_m", 0.0),
                 int(d.get("is_vehicle", False)), int(d.get("is_animal", False)),
                 mode, lat, lng, ts)
                for d in detections
            ]
            conn.executemany(
                "INSERT INTO recent_detections "
                "(device_id, session_id, request_id, class_ko, confidence, "
                " cx, cy, w, h, zone, dist_m, is_vehicle, is_animal, "
                " mode, lat, lng, detected_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                rows,
            )
            conn.execute(
                "DELETE FROM recent_detections WHERE session_id = ? AND id NOT IN "
                "(SELECT id FROM recent_detections WHERE session_id = ? "
                " ORDER BY id DESC LIMIT ?)",
                (session_id, session_id, _DETECTIONS_KEEP),
            )


def get_recent_detections(session_id: str, max_age_s: float = 3.0) -> list[dict]:
    """최근 N초 이내 탐지 결과 반환 — 질문 응답 및 tracker 복원용."""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=max_age_s)).isoformat()
    with _conn() as conn:
        if _IS_POSTGRES:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT class_ko, confidence, cx, cy, w, h, zone, dist_m, "
                    "       is_vehicle, is_animal, detected_at "
                    "FROM recent_detections WHERE session_id = %s AND detected_at > %s "
                    "ORDER BY id DESC LIMIT 100",
                    (session_id, cutoff),
                )
                rows = cur.fetchall()
            return [dict(r) for r in rows]
        else:
            rows = conn.execute(
                "SELECT class_ko, confidence, cx, cy, w, h, zone, dist_m, "
                "       is_vehicle, is_animal, detected_at "
                "FROM recent_detections WHERE session_id = ? AND detected_at > ? "
                "ORDER BY id DESC LIMIT 100",
                (session_id, cutoff),
            ).fetchall()
            keys = ["class_ko","confidence","cx","cy","w","h",
                    "zone","dist_m","is_vehicle","is_animal","detected_at"]
            return [dict(zip(keys, r)) for r in rows]


def get_history_24h(session_id: str, limit: int = 50) -> dict:
    """최근 24시간 탐지 이벤트 내역과 위험도별 요약 통계를 반환한다.

    [왜 이 함수가 필요한가]
    대시보드 하단 패널에서 "오늘 이 기기가 어떤 물체를 얼마나 탐지했는지"를
    보여주기 위해 추가. 앱의 실시간 탐지 흐름(/detect)과 완전히 별개로 동작하며
    브라우저(대시보드)가 30초마다 한 번 호출한다.

    [위험도 분류 기준]
    risk_score 0.7 이상 → critical(위험)
    risk_score 0.4 이상 → beep(주의)
    그 미만             → safe(안전)
    이벤트 위험도 = 해당 이벤트 내 물체들 중 가장 높은 위험도

    반환 형식:
        {
            "events":  [{"event_id", "timestamp", "objects"(최대3개), "risk"}, ...],
            "summary": {"total", "critical", "beep", "safe"}
        }
    """
    def _risk_level(risk_score: float) -> str:
        if risk_score >= 0.7:
            return "critical"
        if risk_score >= 0.4:
            return "beep"
        return "safe"

    def _event_risk(objects: list) -> str:
        # 이벤트에 포함된 물체가 없으면 안전으로 처리
        if not objects:
            return "safe"
        levels = [_risk_level(float(o.get("risk_score", 0))) for o in objects]
        if "critical" in levels:
            return "critical"
        if "beep" in levels:
            return "beep"
        return "safe"

    events = []
    with _conn() as conn:
        if _IS_POSTGRES:
            with conn.cursor() as cur:
                # PostgreSQL: INTERVAL 문법으로 24시간 전 시점 계산
                cur.execute(
                    "SELECT event_id, timestamp, objects_json "
                    "FROM detection_events "
                    "WHERE session_id = %s "
                    "  AND timestamp >= NOW() - INTERVAL '24 hours' "
                    "ORDER BY id DESC LIMIT %s",
                    (session_id, limit)
                )
                rows = cur.fetchall()
            for row in rows:
                # psycopg3 + dict_row: JSONB 컬럼은 이미 Python list로 파싱됨
                objs = row["objects_json"] if isinstance(row["objects_json"], list) \
                       else json.loads(row["objects_json"] or "[]")
                events.append({
                    "event_id":  row["event_id"],
                    "timestamp": str(row["timestamp"]),
                    "objects":   objs[:3],       # 대시보드 표시용 상위 3개만
                    "risk":      _event_risk(objs),
                })
        else:
            # SQLite: Python으로 24시간 전 시점을 계산해 ISO 문자열 비교
            from datetime import timedelta
            cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
            rows = conn.execute(
                "SELECT event_id, timestamp, objects_json "
                "FROM detection_events "
                "WHERE session_id = ? AND timestamp >= ? "
                "ORDER BY id DESC LIMIT ?",
                (session_id, cutoff, limit)
            ).fetchall()
            for row in rows:
                objs = json.loads(row[2] or "[]")
                events.append({
                    "event_id":  row[0],
                    "timestamp": row[1],
                    "objects":   objs[:3],
                    "risk":      _event_risk(objs),
                })

    # 위험도별 건수 집계
    summary = {"total": len(events), "critical": 0, "beep": 0, "safe": 0}
    for e in events:
        summary[e["risk"]] += 1

    return {"events": events, "summary": summary}


def save_gps_route(session_id: str, name: str | None = None) -> str | None:
    """gps_history의 현재 좌표를 하나의 완성 경로로 저장하고 gps_history를 초기화.
    저장된 좌표가 없으면 None 반환, 그 외에는 route_id 반환.
    """
    import uuid as _uuid
    points = get_gps_track(session_id, limit=500)
    if not points:
        return None

    route_id = _uuid.uuid4().hex
    started_at = points[0]["timestamp"]
    ended_at   = points[-1]["timestamp"]
    points_json = json.dumps(points, ensure_ascii=False)

    with _conn() as conn:
        if _IS_POSTGRES:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO gps_routes "
                    "(route_id, session_id, name, started_at, ended_at, point_count, points_json) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)",
                    (route_id, session_id, name, started_at, ended_at, len(points), points_json),
                )
                cur.execute(
                    "DELETE FROM gps_history WHERE session_id = %s", (session_id,)
                )
        else:
            conn.execute(
                "INSERT OR IGNORE INTO gps_routes "
                "(route_id, session_id, name, started_at, ended_at, point_count, points_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (route_id, session_id, name, started_at, ended_at, len(points), points_json),
            )
            conn.execute(
                "DELETE FROM gps_history WHERE session_id = ?", (session_id,)
            )
    return route_id


def get_gps_routes(session_id: str, limit: int = 20) -> list[dict]:
    """세션의 저장된 경로 목록 반환 (메타데이터만, 좌표 제외)."""
    with _conn() as conn:
        if _IS_POSTGRES:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT route_id, name, started_at, ended_at, point_count "
                    "FROM gps_routes WHERE session_id = %s ORDER BY id DESC LIMIT %s",
                    (session_id, limit),
                )
                rows = cur.fetchall()
            return [{"route_id": r["route_id"], "name": r["name"],
                     "started_at": str(r["started_at"]), "ended_at": str(r["ended_at"]),
                     "point_count": r["point_count"]} for r in rows]
        else:
            rows = conn.execute(
                "SELECT route_id, name, started_at, ended_at, point_count "
                "FROM gps_routes WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
            return [{"route_id": r[0], "name": r[1], "started_at": r[2],
                     "ended_at": r[3], "point_count": r[4]} for r in rows]


def get_gps_route_points(route_id: str) -> list[dict]:
    """특정 경로의 좌표 목록 반환."""
    with _conn() as conn:
        if _IS_POSTGRES:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT points_json FROM gps_routes WHERE route_id = %s", (route_id,)
                )
                row = cur.fetchone()
            if not row:
                return []
            pts = row["points_json"]
            return pts if isinstance(pts, list) else json.loads(pts)
        else:
            row = conn.execute(
                "SELECT points_json FROM gps_routes WHERE route_id = ?", (route_id,)
            ).fetchone()
            return json.loads(row[0]) if row else []


def get_gps_track(session_id: str, limit: int = 100) -> list[dict]:
    """대시보드 지도에 표시할 이동 경로 포인트 목록 반환."""
    with _conn() as conn:
        if _IS_POSTGRES:
            with conn.cursor() as cur:
                # DESC로 최신 100개 조회 후 reversed()로 시간순 정렬
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
    return list(reversed(result))  # 시간순 오름차순 반환 (지도 경로 그리기 위해)
