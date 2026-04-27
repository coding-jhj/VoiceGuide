"""
VoiceGuide 데이터베이스 모듈
============================
SQLite를 사용해 두 가지 데이터를 저장합니다.

1. snapshots     — 공간 기억 (재방문 시 달라진 것만 안내하기 위해)
2. saved_locations — 개인 네비게이팅 (사용자가 이름 붙인 장소 저장)

SQLite를 쓰는 이유:
- 별도 서버/설치 없이 파일 하나로 동작 (voiceguide.db)
- 가벼운 데이터 양에 적합 (수백 개 스냅샷, 수십 개 장소)
- Python 내장 모듈이라 pip 설치 불필요
"""

import sqlite3
import json
from datetime import datetime

DB_PATH = "voiceguide.db"  # 서버 실행 디렉토리에 자동 생성됨


def init_db():
    """
    앱 시작 시 테이블이 없으면 생성. 이미 있으면 아무것도 안 함.
    src/api/main.py의 startup 이벤트에서 호출됨.
    """
    conn = sqlite3.connect(DB_PATH)

    # snapshots: WiFi SSID별로 "어떤 물체가 있었는지" 기록
    # → 재방문 시 이전 기록과 비교해서 새로 생긴 것/사라진 것만 안내
    conn.execute("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            space_id  TEXT NOT NULL,   -- WiFi SSID (공간 식별자)
            timestamp TEXT NOT NULL,   -- 저장 시각
            objects   TEXT NOT NULL    -- JSON 배열 (탐지된 물체 목록)
        )
    """)

    # saved_locations: "여기 저장해줘 편의점" → label="편의점", wifi_ssid=현재SSID
    # 나중에 "편의점 찾아줘" → 같은 WiFi에 있으면 "도착했어요!" 안내
    conn.execute("""
        CREATE TABLE IF NOT EXISTS saved_locations (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            label     TEXT NOT NULL,      -- 사용자가 붙인 이름 ("편의점", "화장실")
            wifi_ssid TEXT NOT NULL,      -- 저장 당시 WiFi SSID
            timestamp TEXT NOT NULL       -- 저장 시각
        )
    """)
    conn.commit()
    conn.close()


# ── 공간 스냅샷 (재방문 변화 감지용) ─────────────────────────────────────────

def get_snapshot(space_id: str) -> list[dict] | None:
    """
    가장 최근 스냅샷을 반환. 해당 공간의 기록이 없으면 None.

    space_id: WiFi SSID (공간 식별자)
    반환: 이전에 탐지된 물체 목록 [{class_ko, ...}, ...]
          처음 방문이면 None → routes.py에서 공간 기억 비교 스킵
    """
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        # ORDER BY id DESC → 가장 최근 저장된 것 1개만 가져옴
        "SELECT objects FROM snapshots WHERE space_id = ? ORDER BY id DESC LIMIT 1",
        (space_id,)
    ).fetchone()
    conn.close()
    # row[0]은 JSON 문자열 → python 객체로 변환
    return json.loads(row[0]) if row else None


def save_snapshot(space_id: str, objects: list[dict]):
    """
    현재 탐지 결과를 DB에 저장.
    매 요청마다 쌓임 → 오래된 스냅샷은 별도 정리 로직 없음 (용량 무시 가능 수준)
    """
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO snapshots (space_id, timestamp, objects) VALUES (?, ?, ?)",
        (
            space_id,
            datetime.now().isoformat(),
            # ensure_ascii=False: 한국어를 이스케이프 없이 저장 ("의자" 그대로)
            json.dumps(objects, ensure_ascii=False),
        )
    )
    conn.commit()
    conn.close()


# ── 개인 장소 저장 (개인 네비게이팅) ─────────────────────────────────────────

def save_location(label: str, wifi_ssid: str):
    """
    "여기 저장해줘 편의점" 처리.
    label: 사용자가 말한 장소 이름 ("편의점")
    wifi_ssid: 저장 당시 연결된 WiFi SSID → 나중에 같은 SSID면 "도착했어요!" 안내
    """
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO saved_locations (label, wifi_ssid, timestamp) VALUES (?, ?, ?)",
        (label, wifi_ssid, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def delete_location(label: str):
    """저장된 장소 삭제. label 정확 일치 기준."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM saved_locations WHERE label = ?", (label,))
    conn.commit()
    conn.close()


def get_locations(wifi_ssid: str = "") -> list[dict]:
    """
    저장된 장소 목록 반환.
    wifi_ssid 지정 시: 해당 SSID에 저장된 장소만 (현재 위치 근처)
    wifi_ssid 없을 시: 전체 목록
    """
    conn = sqlite3.connect(DB_PATH)
    if wifi_ssid:
        rows = conn.execute(
            "SELECT label, wifi_ssid, timestamp FROM saved_locations "
            "WHERE wifi_ssid = ? ORDER BY id DESC",
            (wifi_ssid,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT label, wifi_ssid, timestamp FROM saved_locations ORDER BY id DESC"
        ).fetchall()
    conn.close()
    return [{"label": r[0], "wifi_ssid": r[1], "timestamp": r[2]} for r in rows]


def find_location(label: str) -> dict | None:
    """
    라벨로 장소 검색 (부분 일치).
    "편의" 로 검색해도 "편의점" 히트.
    LIKE %label% = SQL의 부분 문자열 검색
    """
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT label, wifi_ssid, timestamp FROM saved_locations "
        "WHERE label LIKE ? ORDER BY id DESC LIMIT 1",
        (f"%{label}%",)  # % = 임의 문자열 와일드카드
    ).fetchone()
    conn.close()
    return {"label": row[0], "wifi_ssid": row[1], "timestamp": row[2]} if row else None
