"""
데모 시뮬레이션 — 상도푸르지오클라베뉴아파트 107동 → 서울시남부장애인종합복지관

경로 정보 (OSRM 보행자 경로):
  거리  : 약 1,282m
  소요  : 약 17분 (실제 보행 속도 기준)
  시뮬레이션: STEPS_PER_LEG=20, INTERVAL=1.0초 → 약 5분 소요

사용법:
    python tools/simulator_sangdo_welfare.py

대시보드에서 세션 ID 입력창에 'demo-sangdo-01' 을 입력하면
이동 경로와 탐지 내역이 실시간으로 표시됩니다.
"""

import sys
import time
import random
import requests
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── 설정 ────────────────────────────────────────────────────────────────────

SERVER_URL    = "https://voiceguide-1063164560758.asia-northeast3.run.app"
SESSION_ID    = "demo-sangdo-01"
API_KEY       = ""
INTERVAL      = 1.0      # 좌표 전송 간격(초)
STEPS_PER_LEG = 20       # 구간당 보간 점수  →  15구간×20×1초 ≈ 5분
DETECT_EVERY  = 4        # N번째 GPS 전송마다 탐지 데이터 전송
LOOP          = False

# ── 경로 좌표 (위도, 경도, 설명) ─────────────────────────────────────────────
# OSRM 보행자 경로: 상도푸르지오클라베뉴아파트 → 서울시남부장애인종합복지관
ROUTE = [
    (37.496867, 126.938432, "출발: 상도푸르지오클라베뉴아파트 107동 앞"),
    (37.496602, 126.937522, "단지 내 보행로"),
    (37.495908, 126.936440, "단지 출구 / 상도로 진입 전"),
    (37.495638, 126.935504, "상도로 횡단보도 대기"),
    (37.495499, 126.934472, "상도로 보도 이동"),
    (37.495335, 126.933896, "상도1동 주민센터 방면"),
    (37.495853, 126.932948, "신대방터널 입구 방면 골목"),
    (37.495578, 126.931901, "신대방동 주택가"),
    (37.495761, 126.931692, "여의대방로 방면 골목"),
    (37.496044, 126.931239, "여의대방로 교차로 진입"),
    (37.495952, 126.931092, "여의대방로 교차로"),
    (37.495837, 126.929943, "여의대방로20나길 방면"),
    (37.495960, 126.929424, "복지관 방면 골목길"),
    (37.496180, 126.928460, "음향신호기 횡단보도 대기 (경로 B)"),
    (37.496100, 126.927666, "횡단 후 복지관 방면"),
    (37.495096, 126.927424, "도착: 서울시남부장애인종합복지관"),
]

# ── 탐지 장면 정의 ───────────────────────────────────────────────────────────
# leg_idx(구간 번호) → 해당 구간에서 보낼 탐지 객체 목록

def _obj(class_ko, conf, x, y, w, h, depth):
    return {
        "class_ko":    class_ko,
        "confidence":  conf,
        "bbox":        [x, y, w, h],
        "depth_m":     depth,
        "is_vehicle":  class_ko in {"자동차", "오토바이", "버스", "트럭", "자전거"},
        "is_dangerous":class_ko in {"자동차", "오토바이", "버스", "트럭", "자전거", "계단"},
    }

WAYPOINT_SCENES: dict[int, list[dict] | None] = {
    0:  None,  # 아파트 앞 — 탐지 없음
    1:  [      # 단지 내 — 보행자·자전거
        _obj("사람",    0.88, 0.48, 0.55, 0.18, 0.65, 3.2),
        _obj("자전거",  0.76, 0.62, 0.58, 0.22, 0.70, 4.8),
    ],
    2:  [      # 단지 출구 — 자동차 통행
        _obj("자동차",  0.91, 0.50, 0.60, 0.40, 0.55, 5.5),
        _obj("사람",    0.80, 0.28, 0.52, 0.15, 0.60, 2.8),
    ],
    3:  [      # 상도로 횡단보도 — 신호등·버스
        _obj("신호등",  0.93, 0.50, 0.30, 0.06, 0.18, 6.0),
        _obj("버스",    0.87, 0.55, 0.62, 0.35, 0.60, 7.2),
    ],
    4:  [      # 상도로 보도 — 사람들
        _obj("사람",    0.85, 0.35, 0.58, 0.16, 0.60, 2.5),
        _obj("사람",    0.79, 0.65, 0.56, 0.14, 0.58, 3.8),
    ],
    5:  None,  # 주민센터 방면 — 조용한 구간
    6:  [      # 신대방터널 입구 방면 — 오토바이 주의
        _obj("오토바이",0.83, 0.52, 0.60, 0.20, 0.55, 4.0),
        _obj("사람",    0.77, 0.30, 0.55, 0.15, 0.62, 3.0),
    ],
    7:  [      # 신대방동 주택가 — 배달 오토바이·사람
        _obj("오토바이",0.89, 0.50, 0.58, 0.18, 0.52, 3.5),
        _obj("배낭",    0.72, 0.45, 0.65, 0.12, 0.40, 1.5),
    ],
    8:  None,  # 여의대방로 방면 골목 — 조용한 구간
    9:  [      # 여의대방로 교차로 진입 — 신호등·자동차
        _obj("신호등",  0.95, 0.50, 0.28, 0.05, 0.16, 8.0),
        _obj("자동차",  0.90, 0.55, 0.65, 0.38, 0.58, 6.5),
        _obj("버스",    0.84, 0.70, 0.62, 0.30, 0.55, 9.0),
    ],
    10: [      # 여의대방로 교차로 — 자전거·사람
        _obj("자전거",  0.81, 0.42, 0.58, 0.20, 0.65, 3.2),
        _obj("사람",    0.86, 0.58, 0.55, 0.16, 0.62, 2.8),
    ],
    11: None,  # 여의대방로20나길 진입 — 조용
    12: [      # 음향신호기 횡단보도 (경로 B: 06-0000032157) — 핵심 구간
        _obj("신호등",  0.97, 0.50, 0.25, 0.06, 0.20, 7.0),
        _obj("사람",    0.88, 0.38, 0.58, 0.17, 0.63, 2.5),
        _obj("사람",    0.82, 0.62, 0.57, 0.15, 0.60, 3.2),
    ],
    13: [      # 횡단 후 — 사람·핸드백
        _obj("사람",    0.84, 0.45, 0.58, 0.18, 0.65, 2.2),
        _obj("핸드백",  0.70, 0.52, 0.68, 0.10, 0.35, 1.8),
    ],
    14: [      # 복지관 방면 — 휠체어·사람
        _obj("사람",    0.90, 0.40, 0.58, 0.20, 0.70, 1.8),
        _obj("사람",    0.85, 0.60, 0.57, 0.18, 0.68, 2.5),
    ],
}

# ── 유틸 ────────────────────────────────────────────────────────────────────

HEADERS = {"X-API-Key": API_KEY} if API_KEY else {}
_collected: list[dict] = []


def interpolate_route(route, steps):
    dense = []
    for i in range(len(route) - 1):
        lat1, lng1, label = route[i]
        lat2, lng2, _     = route[i + 1]
        for t in range(steps):
            frac = t / steps
            dense.append((
                lat1 + (lat2 - lat1) * frac,
                lng1 + (lng2 - lng1) * frac,
                label if t == 0 else "",
                i,
                t == 0,
            ))
    lat, lng, label = route[-1]
    dense.append((lat, lng, label, len(route) - 1, True))
    return dense


def send_gps(lat, lng, label, silent=False):
    try:
        resp = requests.post(
            f"{SERVER_URL}/gps",
            data={"device_id": SESSION_ID, "lat": lat, "lng": lng},
            headers=HEADERS,
            timeout=5,
        )
        ok = resp.status_code == 200
        if not silent:
            status = "✅" if ok else f"❌ {resp.status_code}"
            print(f"  {status}  {label}  ({lat:.6f}, {lng:.6f})")
        if ok:
            _collected.append({"lat": lat, "lng": lng})
        return ok
    except requests.exceptions.ConnectionError:
        print(f"  ❌ 서버 연결 실패 — {SERVER_URL} 확인")
        return False
    except Exception as e:
        print(f"  ❌ 오류: {e}")
        return False


def send_detect(lat, lng, objects):
    if not objects:
        return
    # 신뢰도 약간 랜덤화 (매 전송마다 동일값 방지)
    jittered = []
    for o in objects:
        oj = dict(o)
        oj["confidence"] = round(min(0.99, o["confidence"] + random.uniform(-0.05, 0.05)), 2)
        oj["depth_m"]    = round(max(0.5, o["depth_m"]    + random.uniform(-0.3, 0.3)), 1)
        jittered.append(oj)
    try:
        resp = requests.post(
            f"{SERVER_URL}/detect",
            json={
                "device_id": SESSION_ID,
                "mode":      "장애물",
                "lat":       lat,
                "lng":       lng,
                "objects":   jittered,
            },
            headers=HEADERS,
            timeout=5,
        )
        names  = ", ".join(o["class_ko"] for o in jittered[:3])
        extra  = f" 외 {len(jittered)-3}개" if len(jittered) > 3 else ""
        status = "✅" if resp.status_code == 200 else f"❌ {resp.status_code}"
        print(f"    └─ 탐지 {status}: {names}{extra}")
    except Exception as e:
        print(f"    └─ 탐지 전송 실패: {e}")


def save_route():
    if not _collected:
        return
    name = f"상도-복지관 {datetime.now():%m/%d %H:%M}"
    try:
        resp = requests.post(
            f"{SERVER_URL}/gps/route/save",
            json={"device_id": SESSION_ID, "name": name},
            headers=HEADERS,
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("saved"):
                print(f"\n경로 저장 완료 — '{name}' ({data.get('point_count', 0)}개 포인트)")
            else:
                print(f"\n경로 저장 건너뜀: {data.get('reason', '')}")
        else:
            print(f"\n경로 저장 실패 ({resp.status_code})")
    except Exception as e:
        print(f"\n경로 저장 오류: {e}")


# ── 메인 실행 ────────────────────────────────────────────────────────────────

def run():
    dense     = interpolate_route(ROUTE, STEPS_PER_LEG)
    total_sec = len(dense) * INTERVAL

    print("\nVoiceGuide 데모 시뮬레이션")
    print(f"  구간     : 상도푸르지오클라베뉴아파트 107동 → 서울시남부장애인종합복지관")
    print(f"  서버     : {SERVER_URL}")
    print(f"  세션 ID  : {SESSION_ID}")
    print(f"  경로     : {len(ROUTE)}개 웨이포인트, 약 1,282m")
    print(f"  좌표     : {len(dense)}개  →  예상 {int(total_sec//60)}분 {int(total_sec%60)}초")
    print(f"  탐지     : {DETECT_EVERY}번째 포인트마다 전송")
    print(f"\n대시보드 세션 ID 입력창에 '{SESSION_ID}' 를 입력하세요.\n")

    for point_idx, (lat, lng, label, leg_idx, is_wp) in enumerate(dense):
        if not send_gps(lat, lng, label, silent=not is_wp):
            print("\n서버 오류로 시뮬레이션을 중단합니다.")
            save_route()
            sys.exit(1)

        if point_idx % DETECT_EVERY == 0:
            scene = WAYPOINT_SCENES.get(leg_idx)
            if scene:
                send_detect(lat, lng, scene)

        time.sleep(INTERVAL)

    print(f"\n시뮬레이션 완료 — {len(dense)}개 포인트 전송.")


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\n\n사용자가 중단했습니다.")
    finally:
        save_route()
