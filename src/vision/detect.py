import math
from ultralytics import YOLO

model = YOLO("yolo11m.pt")

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

DIST_VERY_NEAR = 0.25
DIST_NEAR      = 0.12
DIST_MID       = 0.04
DIST_FAR       = 0.01

# 기본 신뢰도: 0.45 → 0.60으로 상향 (오탐 감소)
CONF_THRESHOLD = 0.60

# 작거나 오탐 많은 물체는 더 높은 신뢰도 요구
CLASS_MIN_CONF = {
    "bottle":     0.72,
    "cup":        0.72,
    "book":       0.70,
    "cell phone": 0.72,
    "keyboard":   0.70,
    "laptop":     0.65,
    "tv":         0.65,
    "handbag":    0.68,
    "backpack":   0.65,
    "cat":        0.68,
    "dog":        0.65,
    "umbrella":   0.68,
    "suitcase":   0.65,
}

RISK_DIR = {
    "8시":  0.3, "9시":  0.5, "10시": 0.7, "11시": 0.9,
    "12시": 1.0,
    "1시":  0.9, "2시":  0.7, "3시":  0.5, "4시":  0.3,
    "6시":  0.6,
}

RISK_DIST = {
    "매우 가까이": 1.0,
    "가까이":      0.8,
    "보통":        0.5,
    "멀리":        0.2,
    "매우 멀리":   0.1,
}

# 내비게이션에 실제로 필요한 클래스만 유지
# 제거: 음식류, 스포츠 용품, 희귀 동물, 작은 생활용품
TARGET_CLASSES = {
    # 사람 - 항상 최우선
    "person":        "사람",

    # 차량 - 야외 이동
    "bicycle":       "자전거",
    "car":           "자동차",
    "motorcycle":    "오토바이",
    "bus":           "버스",
    "train":         "기차",
    "truck":         "트럭",

    # 교통 시설
    "traffic light": "신호등",
    "fire hydrant":  "소화전",
    "stop sign":     "정지 표지판",

    # 바닥 위 동물 (걸려넘어질 수 있음)
    "dog":           "개",
    "cat":           "고양이",

    # 대형 가구 (충돌 위험)
    "bench":         "벤치",
    "chair":         "의자",
    "couch":         "소파",
    "bed":           "침대",
    "dining table":  "테이블",
    "toilet":        "변기",
    "sink":          "세면대",
    "refrigerator":  "냉장고",
    "potted plant":  "화분",

    # 바닥/공중 장애물
    "backpack":      "배낭",
    "umbrella":      "우산",
    "handbag":       "핸드백",
    "suitcase":      "여행가방",

    # 실내 맥락 파악용 (확인용)
    "tv":            "TV",
    "laptop":        "노트북",
    "cell phone":    "휴대폰",
    "bottle":        "병",
    "cup":           "컵",
    "book":          "책",
    "keyboard":      "키보드",
}

# 물체 실제 크기 기반 캘리브레이션 (area_ratio at 1m)
# 카메라 수직 FOV ~60°, 수평 FOV ~80° 기준 추정값
CLASS_CALIB_RATIO = {
    "person":        0.10,  # 평균 신장 170cm, 어깨 폭 45cm
    "car":           0.30,  # 폭 180cm
    "bus":           0.50,  # 폭 250cm
    "truck":         0.40,  # 폭 220cm
    "bicycle":       0.06,  # 폭 60cm
    "motorcycle":    0.08,  # 폭 80cm
    "bench":         0.15,  # 폭 150cm
    "chair":         0.06,  # 폭 50cm
    "couch":         0.20,  # 폭 180cm
    "bed":           0.28,  # 폭 150cm
    "dining table":  0.22,  # 폭 120cm
    "refrigerator":  0.12,  # 폭 60cm
    "suitcase":      0.06,  # 폭 40cm
    "dog":           0.05,
    "cat":           0.03,
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
        distance_m = min(distance_m, 10.0)

        # 바닥 장애물 감지: bbox 하단이 화면 65% 아래 = 발 아래 장애물(걸림 위험)
        y2_norm = y2 / h
        is_ground_level = y2_norm > 0.65

        # 바닥 장애물은 가까울수록 위험도 상향
        ground_multiplier = 1.4 if is_ground_level and distance in ("매우 가까이", "가까이", "보통") else 1.0
        risk_score = round(RISK_DIR.get(direction, 0.5) * RISK_DIST[distance] * ground_multiplier, 2)
        risk_score = min(risk_score, 1.0)

        detections.append({
            "class":           cls_name,
            "class_ko":        TARGET_CLASSES.get(cls_name, "알 수 없는 물체"),
            "bbox":            [x1, y1, x2, y2],
            "direction":       direction,
            "distance":        distance,
            "distance_m":      distance_m,
            "risk_score":      risk_score,
            "conf":            round(conf, 2),
            "is_ground_level": is_ground_level,
        })

    return sorted(detections, key=lambda x: x["risk_score"], reverse=True)[:3]
