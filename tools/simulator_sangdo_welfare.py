"""
데모 시뮬레이션 — 성대로1가길 동광교회 → 서울시남부장애인종합복지관

경로 정보 (OSRM 보행자 경로 — 안전 우회 경로 B):
  거리  : 약 1,581m  (직선 최단 1,160m 대비 +421m)
  소요  : 약 20분 (실제 보행 속도 기준)
  특징  : 여의대방로 경유로 신대방동 사고다발 구간 완전 우회 + 음향신호기·보행자작동신호기 횡단보도(06-0000032157) 경유
  시뮬레이션: STEPS_PER_SEG=5, INTERVAL=1.0초 → 약 5분 50초 소요

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
STEPS_PER_SEG = 5        # OSRM 구간당 보간 점수  →  70구간×5×1초 ≈ 5분 50초
DETECT_EVERY  = 4        # N번째 GPS 전송마다 탐지 데이터 전송
LOOP          = False
ZONE_SIZE     = 8        # osrm_idx // ZONE_SIZE = zone_idx (9개 존, 71좌표 기준)

# ── OSRM 실제 보행 경로 (71개 좌표, 1,581m) ──────────────────────────────────
# 경로 B: 동광교회(성대로1가길) → 여의대방로 경유 → 신대방동 사고다발 완전 우회 → 음향신호기 횡단보도 → 복지관
# routing.openstreetmap.de/routed-foot 로 사전 계산된 실제 인도 경로
# HS2(신대방동 메디칼우리약국 부근) 최소 거리 156m 확보 — 경로 A(156m)와 동일 수준의 안전 우회
OSRM_COORDS = [
    (37.501727, 126.935007), (37.501583, 126.93445),  (37.501415, 126.934372),
    (37.501026, 126.934016), (37.500862, 126.934061), (37.500701, 126.934057),
    (37.500427, 126.93405),  (37.500263, 126.933991), (37.500177, 126.933973),
    (37.500155, 126.934014), (37.500107, 126.934048), (37.500098, 126.934208),
    (37.499767, 126.934291), (37.499285, 126.934411), (37.498977, 126.934498),
    (37.498968, 126.934503), (37.498865, 126.934549), (37.498775, 126.93459),
    (37.498499, 126.934881), (37.498324, 126.934916), (37.498324, 126.934882),
    (37.498296, 126.934826), (37.497977, 126.934554), (37.49795,  126.934503),
    (37.497353, 126.93381),  (37.497238, 126.933916), (37.497201, 126.933888),
    (37.49717,  126.933861), (37.496981, 126.933427), (37.497077, 126.933366),
    (37.497136, 126.933331), (37.497364, 126.933194), (37.497779, 126.932986),
    (37.4979,   126.93294),  (37.498073, 126.932898), (37.498151, 126.932879),
    (37.498288, 126.932845), (37.498199, 126.932461), (37.497981, 126.931604),
    (37.497929, 126.931398), (37.497837, 126.931149), (37.497795, 126.930917),
    (37.497758, 126.930734), (37.49791,  126.930684), (37.497884, 126.930514),
    (37.49783,  126.930171), (37.497775, 126.929659), (37.497746, 126.929619),
    (37.497561, 126.929247), (37.497503, 126.92905),  (37.497489, 126.929003),
    (37.497457, 126.928887), (37.497173, 126.928546), (37.497157, 126.928472),
    (37.497095, 126.928489), (37.496914, 126.928523), (37.49677,  126.928523),
    (37.496607, 126.928543), (37.496514, 126.92854),  (37.496351, 126.928517),
    (37.496248, 126.928483), (37.49618,  126.92846),  (37.496053, 126.928408),
    (37.495993, 126.928307), (37.4961,   126.927666), (37.495937, 126.92763),
    (37.495292, 126.927471), (37.495038, 126.92741),  (37.495034, 126.927409),
    (37.495038, 126.92741),  (37.495096, 126.927424),
]

# 9개 존(zone_idx 0~8) + 도착(zone 9) 라벨  (ZONE_SIZE=8, 71좌표 기준)
WAYPOINT_LABELS = [
    "출발: 성대로1가길 동광교회",              # zone 0 (osrm 0-7)
    "상도로 보도 — 여의대방로 방향",           # zone 1 (osrm 8-15)
    "여의대방로 진입 (사고다발 북쪽 우회)",    # zone 2 (osrm 16-23)
    "여의대방로 직진 구간",                   # zone 3 (osrm 24-31)
    "여의대방로 중간 — 사고다발 서쪽 통과",   # zone 4 (osrm 32-39)
    "신대방동 안전 구간 진입",                # zone 5 (osrm 40-47)
    "복지관 방면 이동",                       # zone 6 (osrm 48-55)
    "음향신호기 횡단보도 대기 (경로 B 선택)",  # zone 7 (osrm 56-63)
    "횡단 후 복지관 방면",                    # zone 8 (osrm 64-70)
    "도착: 서울시남부장애인종합복지관",         # 최종 도착
]

# ── 탐지 장면 정의 (zone_idx → 탐지 객체 목록) ──────────────────────────────

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
    0: None,  # 동광교회 출발 — 조용
    1: [      # 상도로 보도 — 보행자·자전거
        _obj("사람",   0.85, 0.40, 0.56, 0.16, 0.62, 3.0),
        _obj("자전거", 0.76, 0.62, 0.58, 0.20, 0.68, 4.5),
    ],
    2: [      # 여의대방로 진입 — 자동차·신호등 (사고다발 북쪽 우회 시작)
        _obj("신호등", 0.91, 0.50, 0.28, 0.05, 0.16, 9.0),
        _obj("자동차", 0.88, 0.55, 0.65, 0.36, 0.56, 7.5),
    ],
    3: [      # 여의대방로 직진 — 버스·자동차
        _obj("버스",   0.85, 0.70, 0.62, 0.30, 0.54, 10.0),
        _obj("자동차", 0.83, 0.40, 0.60, 0.35, 0.55, 6.0),
        _obj("사람",   0.77, 0.28, 0.55, 0.14, 0.60, 2.8),
    ],
    4: [      # 여의대방로 중간 — 사고다발 서쪽 통과 (오토바이 주의)
        _obj("오토바이", 0.87, 0.52, 0.60, 0.20, 0.54, 3.8),
        _obj("자동차",   0.83, 0.68, 0.62, 0.35, 0.52, 7.0),
        _obj("사람",     0.80, 0.30, 0.55, 0.15, 0.62, 2.5),
    ],
    5: [      # 신대방동 안전 구간 — 보행자 밀집
        _obj("사람", 0.86, 0.35, 0.58, 0.17, 0.65, 2.2),
        _obj("사람", 0.79, 0.60, 0.56, 0.15, 0.60, 3.5),
    ],
    6: [      # 복지관 방면 이동 — 사람·핸드백
        _obj("사람",   0.84, 0.45, 0.58, 0.18, 0.65, 2.0),
        _obj("핸드백", 0.71, 0.55, 0.68, 0.10, 0.38, 1.6),
    ],
    7: [      # 음향신호기 횡단보도 (06-0000032157) — 핵심 구간
        _obj("신호등", 0.97, 0.50, 0.25, 0.06, 0.20, 7.0),
        _obj("사람",   0.89, 0.38, 0.58, 0.17, 0.63, 2.5),
        _obj("사람",   0.83, 0.62, 0.57, 0.15, 0.61, 3.0),
    ],
    8: [      # 복지관 도착 — 휠체어·사람
        _obj("사람", 0.90, 0.40, 0.58, 0.20, 0.70, 1.8),
        _obj("사람", 0.85, 0.60, 0.57, 0.18, 0.68, 2.5),
    ],
}

# ── 유틸 ────────────────────────────────────────────────────────────────────

HEADERS = {"X-API-Key": API_KEY} if API_KEY else {}
_collected: list[dict] = []


def build_dense_route(osrm_coords, steps_per_seg, zone_size):
    """OSRM 좌표 사이를 보간해 밀집 경로 생성.

    OSRM 좌표는 실제 인도 위에 있으므로 짧은 구간 내 직선 보간은 건물 통과 없음.
    zone_idx = osrm_idx // zone_size 로 탐지 장면 매핑.
    """
    dense = []
    for osrm_idx in range(len(osrm_coords) - 1):
        lat1, lng1 = osrm_coords[osrm_idx]
        lat2, lng2 = osrm_coords[osrm_idx + 1]
        zone_idx = osrm_idx // zone_size
        is_wp    = (osrm_idx % zone_size == 0)
        label    = WAYPOINT_LABELS[zone_idx] if is_wp else ""
        for t in range(steps_per_seg):
            frac = t / steps_per_seg
            dense.append((
                lat1 + (lat2 - lat1) * frac,
                lng1 + (lng2 - lng1) * frac,
                label if t == 0 else "",
                zone_idx,
                is_wp and t == 0,
            ))
    lat, lng = osrm_coords[-1]
    dense.append((lat, lng, WAYPOINT_LABELS[-1], len(WAYPOINT_LABELS) - 1, True))
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
    name = f"동광교회-복지관 {datetime.now():%m/%d %H:%M}"
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
    dense     = build_dense_route(OSRM_COORDS, STEPS_PER_SEG, ZONE_SIZE)
    total_sec = len(dense) * INTERVAL

    print("\nVoiceGuide 데모 시뮬레이션")
    print(f"  구간     : 성대로1가길 동광교회 → 서울시남부장애인종합복지관")
    print(f"  경로     : 안전 우회 (신대방동 사고다발 회피 + 음향신호기 경유)")
    print(f"  서버     : {SERVER_URL}")
    print(f"  세션 ID  : {SESSION_ID}")
    print(f"  OSRM 좌표: {len(OSRM_COORDS)}개, 약 1,581m")
    print(f"  전송 좌표: {len(dense)}개  →  예상 {int(total_sec//60)}분 {int(total_sec%60)}초")
    print(f"  탐지     : {DETECT_EVERY}번째 포인트마다 전송")
    print(f"\n대시보드 세션 ID 입력창에 '{SESSION_ID}' 를 입력하세요.\n")

    for point_idx, (lat, lng, label, zone_idx, is_wp) in enumerate(dense):
        if not send_gps(lat, lng, label, silent=not is_wp):
            print("\n서버 오류로 시뮬레이션을 중단합니다.")
            save_route()
            sys.exit(1)

        if point_idx % DETECT_EVERY == 0:
            scene = WAYPOINT_SCENES.get(zone_idx)
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
