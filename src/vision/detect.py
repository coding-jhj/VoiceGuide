import math
from ultralytics import YOLO

model = YOLO("yolo11n.pt")

# ── 튜닝 파라미터 ──────────────────────────────────────────────────────────
# [방향] 이미지 너비를 9구역으로 분할 (각 ~11%)
# ZONE_BOUNDARIES: (x 상한값, 시계 방향) — 왼쪽 끝(8시) → 오른쪽 끝(4시)
#
#  |--8시--|--9시--|--10시--|--11시--|--12시--|--1시--|--2시--|--3시--|--4시--|
#  0     0.11   0.22    0.33    0.44    0.56   0.67   0.78   0.89    1.0
#
#  경계값을 조정하면 특정 구역의 감도를 높이거나 낮출 수 있음
ZONE_BOUNDARIES = [
    (0.11, "8시"),
    (0.22, "9시"),
    (0.33, "10시"),
    (0.44, "11시"),
    (0.56, "12시"),
    (0.67, "1시"),
    (0.78, "2시"),
    (0.89, "3시"),
    (1.01, "4시"),   # 1.01: 나머지 전부 포함
]

# [거리] bbox 면적 ÷ 전체 이미지 면적 비율
#
#  bbox 비율   대략적인 실거리     distance 레이블
#  ─────────   ────────────────   ───────────────
#  > 0.25      ~0.5 m 이내        매우 가까이
#  > 0.12      ~1.0 m 이내        가까이
#  > 0.04      ~2.0 m 이내        보통
#  > 0.01      ~4.0 m 이내        멀리
#   ≤ 0.01     ~4.0 m 초과        매우 멀리
#
DIST_VERY_NEAR = 0.25
DIST_NEAR      = 0.12
DIST_MID       = 0.04
DIST_FAR       = 0.01

# [거리 추정] bbox 비율 → 미터 환산 보정값
# 보정 방법: 실제 1m 거리 물체를 찍어 bbox 비율 측정 → CALIB_RATIO 에 입력
CALIB_RATIO  = 0.12
CALIB_DIST_M = 1.0

# [YOLO] confidence 임계값 (낮출수록 더 많이 탐지, 오탐 증가 / 권장: 0.10~0.40)
CONF_THRESHOLD = 0.15

# [위험도] 방향별 가중치 — 12시(정면)가 가장 위험, 가장자리(8·4시)는 낮게
RISK_DIR = {
    "8시":  0.3,
    "9시":  0.5,
    "10시": 0.7,
    "11시": 0.9,
    "12시": 1.0,
    "1시":  0.9,
    "2시":  0.7,
    "3시":  0.5,
    "4시":  0.3,
    "6시":  0.6,   # 뒤쪽 (카메라 회전 후 절대 방향)
}

# [위험도] 거리별 가중치
RISK_DIST = {
    "매우 가까이": 1.0,
    "가까이":      0.8,
    "보통":        0.5,
    "멀리":        0.2,
    "매우 멀리":   0.1,
}
# ────────────────────────────────────────────────────────────────────────────

TARGET_CLASSES = {
    "person":       "사람",
    "chair":        "의자",
    "dining table": "테이블",
    "backpack":     "가방",
    "suitcase":     "가방",
    "cell phone":   "휴대폰",
}


def detect_objects(image_bytes: bytes) -> list[dict]:
    """
    YOLO11n으로 이미지에서 TARGET_CLASSES 탐지
    Returns: [{class, class_ko, bbox, direction, distance, distance_m, risk_score}, ...]
    """
    import numpy as np
    import cv2

    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    h, w = img.shape[:2]

    results = model(img, conf=CONF_THRESHOLD)[0]
    detections = []

    for box in results.boxes:
        cls_name = model.names[int(box.cls)]
        if cls_name not in TARGET_CLASSES:
            continue

        x1, y1, x2, y2 = map(int, box.xyxy[0])
        cx_norm = ((x1 + x2) / 2) / w

        direction = "4시"
        for boundary, label in ZONE_BOUNDARIES:
            if cx_norm <= boundary:
                direction = label
                break

        area_ratio = ((x2 - x1) * (y2 - y1)) / (w * h)
        if area_ratio > DIST_VERY_NEAR:
            distance = "매우 가까이"
        elif area_ratio > DIST_NEAR:
            distance = "가까이"
        elif area_ratio > DIST_MID:
            distance = "보통"
        elif area_ratio > DIST_FAR:
            distance = "멀리"
        else:
            distance = "매우 멀리"

        distance_m = round(CALIB_DIST_M * math.sqrt(CALIB_RATIO / area_ratio), 1) if area_ratio > 0 else 99.9

        risk_score = round(
            RISK_DIR.get(direction, 0.5) * RISK_DIST[distance], 2
        )

        detections.append({
            "class":      cls_name,
            "class_ko":   TARGET_CLASSES[cls_name],
            "bbox":       [x1, y1, x2, y2],
            "direction":  direction,
            "distance":   distance,
            "distance_m": distance_m,
            "risk_score": risk_score,
        })

    return sorted(detections, key=lambda x: x["risk_score"], reverse=True)[:2]
