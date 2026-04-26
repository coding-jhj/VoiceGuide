import math
from ultralytics import YOLO

import os
_MODEL_FILE = "yolo11m_indoor.pt" if os.path.exists("yolo11m_indoor.pt") else "yolo11m.pt"
model = YOLO(_MODEL_FILE)
print(f"[YOLO] 모델 로드: {_MODEL_FILE}")

# ── 방향 구역 (bbox 중심 x 정규화 → 9구역) ──────────────────────────────
ZONE_BOUNDARIES = [
    (0.11, "8시"),
    (0.22, "9시"),
    (0.33, "10시"),
    (0.44, "11시"),
    (0.56, "12시"),
    (0.67, "1시"),
    (0.78, "2시"),
    (0.89, "3시"),
    (1.01, "4시"),
]

# ── 거리 분류 임계값 (bbox 면적 비율) ────────────────────────────────────
DIST_VERY_NEAR = 0.25
DIST_NEAR      = 0.12
DIST_MID       = 0.04
DIST_FAR       = 0.01

# ── 기본 신뢰도 임계값 ───────────────────────────────────────────────────
CONF_THRESHOLD = 0.55   # 야외 원거리 탐지를 위해 0.60 → 0.55

CLASS_MIN_CONF = {
    # 실내 소형 물체 (오탐 많음)
    "bottle":     0.68,
    "cup":        0.68,
    "book":       0.65,
    "cell phone": 0.68,
    "keyboard":   0.65,
    "laptop":     0.60,
    "tv":         0.60,
    "handbag":    0.63,
    "backpack":   0.60,
    "cat":        0.63,
    "umbrella":   0.63,
    "suitcase":   0.60,
    # 야외 차량: 낮은 신뢰도에서도 감지 (안전 우선)
    "car":         0.40,
    "motorcycle":  0.40,
    "bus":         0.40,
    "truck":       0.40,
    "bicycle":     0.45,
    "person":      0.45,
    "traffic light": 0.45,
    "dog":         0.50,
}

# ── 방향별 위험도 가중치 ─────────────────────────────────────────────────
RISK_DIR = {
    "8시":  0.3, "9시":  0.5, "10시": 0.7, "11시": 0.9,
    "12시": 1.0,
    "1시":  0.9, "2시":  0.7, "3시":  0.5, "4시":  0.3,
    "6시":  0.4,
}

# ── 거리별 위험도 가중치 ─────────────────────────────────────────────────
RISK_DIST = {
    "매우 가까이": 1.0,
    "가까이":      0.8,
    "보통":        0.5,
    "멀리":        0.2,
    "매우 멀리":   0.1,
}

# ── 위험 카테고리별 배수 ─────────────────────────────────────────────────
# 이동 차량은 정적 장애물보다 훨씬 위험 → 위험도 배수 적용
VEHICLE_CLASSES = {"car", "motorcycle", "bus", "truck", "train"}
ANIMAL_CLASSES  = {"dog", "horse", "cat"}   # 개/말은 돌발 행동 위험

# 클래스별 위험도 배수 (기본 1.0 = 일반 장애물)
CLASS_RISK_MULTIPLIER = {
    # 야외 이동 차량 — 생명 위협 수준
    "car":        3.0,
    "motorcycle": 3.0,
    "bus":        3.5,
    "truck":      3.5,
    "train":      4.0,
    # 자전거 — 충돌 위험
    "bicycle":    2.0,
    # 동물 — 돌발 행동
    "dog":        1.8,
    "horse":      2.5,
    # 교통 시설 — 정보용
    "traffic light": 0.8,
    "stop sign":     0.6,
    "fire hydrant":  1.0,
}

# ── 실내외 모든 위험 클래스 ──────────────────────────────────────────────
TARGET_CLASSES = {
    # 사람
    "person":        "사람",

    # 이동 차량 (야외 — 최고 위험)
    "car":           "자동차",
    "motorcycle":    "오토바이",
    "bus":           "버스",
    "truck":         "트럭",
    "train":         "기차",
    "bicycle":       "자전거",

    # 교통 시설
    "traffic light": "신호등",
    "fire hydrant":  "소화전",
    "stop sign":     "정지 표지판",

    # 동물 (야외 — 돌발 위험)
    "dog":           "개",
    "cat":           "고양이",
    "horse":         "말",

    # 대형 가구·구조물 (실내외)
    "bench":         "벤치",
    "chair":         "의자",
    "couch":         "소파",
    "bed":           "침대",
    "dining table":  "테이블",
    "toilet":        "변기",
    "sink":          "세면대",
    "refrigerator":  "냉장고",
    "potted plant":  "화분",

    # 바닥 장애물 (실내외)
    "backpack":      "배낭",
    "umbrella":      "우산",
    "handbag":       "핸드백",
    "suitcase":      "여행가방",

    # 실내 확인용
    "tv":            "TV",
    "laptop":        "노트북",
    "cell phone":    "휴대폰",
    "bottle":        "병",
    "cup":           "컵",
    "book":          "책",
    "keyboard":      "키보드",

    # 파인튜닝 추가
    "stairs":        "계단",
}

# ── 물체 실제 크기 기반 거리 캘리브레이션 ────────────────────────────────
# (area_ratio at 1m 기준 — 카메라 FOV ~80° 기준)
CLASS_CALIB_RATIO = {
    "person":        0.10,   # 신장 170cm
    "car":           0.35,   # 폭 180cm + 높이 150cm
    "bus":           0.60,   # 폭 250cm + 높이 280cm
    "truck":         0.50,   # 폭 220cm + 높이 280cm
    "motorcycle":    0.08,   # 폭 80cm
    "bicycle":       0.06,   # 폭 60cm
    "dog":           0.04,   # 중형견 기준
    "horse":         0.20,
    "bench":         0.15,
    "chair":         0.06,
    "couch":         0.20,
    "bed":           0.28,
    "dining table":  0.22,
    "refrigerator":  0.12,
    "suitcase":      0.06,
    "cat":           0.02,
    "traffic light": 0.05,
    "fire hydrant":  0.03,
}
_DEFAULT_CALIB_RATIO = 0.08


def detect_objects(image_bytes: bytes) -> list[dict]:
    import numpy as np
    import cv2

    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    h, w = img.shape[:2]

    results = model(img, conf=CONF_THRESHOLD)[0]
    detections = []

    for box in results.boxes:
        cls_name = model.names[int(box.cls)]

        # TARGET_CLASSES에 없는 클래스 무시
        if cls_name not in TARGET_CLASSES:
            continue

        # 클래스별 최소 신뢰도 체크
        conf = float(box.conf[0])
        if conf < CLASS_MIN_CONF.get(cls_name, CONF_THRESHOLD):
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

        calib = CLASS_CALIB_RATIO.get(cls_name, _DEFAULT_CALIB_RATIO)
        distance_m = round(math.sqrt(calib / area_ratio), 1) if area_ratio > 0 else 10.0
        distance_m = min(distance_m, 15.0)   # 야외 탐지 거리 15m로 확장

        # 바닥 장애물 감지 (발 아래 장애물)
        y2_norm = y2 / h
        is_ground_level = y2_norm > 0.65 or cls_name in ("stairs", "fire hydrant",
                                                           "dog", "cat", "backpack",
                                                           "suitcase", "handbag")

        # 위험도 계산
        ground_mult  = 1.4 if is_ground_level and distance in ("매우 가까이", "가까이", "보통") else 1.0
        class_mult   = CLASS_RISK_MULTIPLIER.get(cls_name, 1.0)
        base_risk    = RISK_DIR.get(direction, 0.5) * RISK_DIST[distance]
        risk_score   = round(base_risk * ground_mult * class_mult, 2)
        risk_score   = min(risk_score, 1.0)

        detections.append({
            "class":           cls_name,
            "class_ko":        TARGET_CLASSES[cls_name],
            "bbox":            [x1, y1, x2, y2],
            "direction":       direction,
            "distance":        distance,
            "distance_m":      distance_m,
            "risk_score":      risk_score,
            "conf":            round(conf, 2),
            "is_ground_level": is_ground_level,
            "is_vehicle":      cls_name in VEHICLE_CLASSES,
            "is_animal":       cls_name in ANIMAL_CLASSES,
        })

    # 위험도 내림차순, 최대 3개 반환
    return sorted(detections, key=lambda x: x["risk_score"], reverse=True)[:3]
