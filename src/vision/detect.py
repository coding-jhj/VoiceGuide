"""
VoiceGuide 객체 탐지 모듈 (2026-04-26)
=====================================
- COCO 80클래스 전체 커버 + 계단 파인튜닝(81번)
- 실내외 모든 위험 요소: 차량·동물·날카로운 물체·바닥 장애물 등
- 안전 경로 제안, 군중 경고, 위험 물체 특별 경고
- YOLO-World 옵션: 환경변수 YOLO_WORLD=1 로 활성화
"""
import math, os
from ultralytics import YOLO

# ── 모델 선택 ────────────────────────────────────────────────────────────────
_USE_YOLO_WORLD = os.environ.get("YOLO_WORLD", "0") == "1"

if _USE_YOLO_WORLD:
    # YOLO-World: 텍스트 프롬프트로 아무 물체나 탐지 (설치: pip install ultralytics)
    from ultralytics import YOLOWorld as _YOLOWorldCls
    _model = _YOLOWorldCls("yolov8x-worldv2.pt")
    # 한국 특화 + COCO 외 위험 클래스 추가
    _WORLD_CLASSES = [
        "person", "car", "motorcycle", "bus", "truck", "bicycle", "train",
        "traffic light", "fire hydrant", "stop sign", "parking meter",
        "dog", "cat", "horse", "cow", "bird", "sheep", "elephant", "bear",
        "electric scooter",   # 전동킥보드 — COCO 없음, 한국 최대 위험
        "bollard",            # 볼라드 — COCO 없음
        "construction cone",  # 공사 원뿔
        "manhole cover",      # 맨홀 뚜껑
        "escalator",          # 에스컬레이터
        "revolving door",     # 회전문
        "wet floor sign",     # 미끄럼 주의 표지
        "chair", "couch", "bed", "dining table", "toilet", "sink",
        "refrigerator", "potted plant", "bench",
        "backpack", "handbag", "suitcase", "umbrella",
        "knife", "scissors", "wine glass",
        "stairs", "curb", "step",
    ]
    _model.set_classes(_WORLD_CLASSES)
    print(f"[YOLO-World] 모델 로드: yolov8x-worldv2.pt ({len(_WORLD_CLASSES)}클래스)")
else:
    _src = "yolo11m_indoor.pt" if os.path.exists("yolo11m_indoor.pt") else "yolo11m.pt"
    _model = YOLO(_src)
    print(f"[YOLO] 모델 로드: {_src}")

model = _model

# ── 방향 구역 (9구역, 시계 방향) ─────────────────────────────────────────────
ZONE_BOUNDARIES = [
    (0.11, "8시"), (0.22, "9시"),  (0.33, "10시"),
    (0.44, "11시"),(0.56, "12시"), (0.67, "1시"),
    (0.78, "2시"), (0.89, "3시"),  (1.01, "4시"),
]

# ── 거리 분류 임계값 (bbox 면적 비율) ────────────────────────────────────────
DIST_VERY_NEAR = 0.25
DIST_NEAR      = 0.12
DIST_MID       = 0.04
DIST_FAR       = 0.01

# ── 기본 신뢰도 ─────────────────────────────────────────────────────────────
CONF_THRESHOLD = 0.50   # 야외 원거리 탐지 위해 낮게 유지

CLASS_MIN_CONF = {
    # 야외 차량: 멀리서도 일찍 잡아야 (안전 우선)
    "car": 0.38, "motorcycle": 0.38, "bus": 0.38, "truck": 0.38,
    "bicycle": 0.42, "train": 0.35,
    # 사람
    "person": 0.42,
    # 위험 동물
    "dog": 0.45, "horse": 0.45, "cow": 0.45,
    "bear": 0.40, "elephant": 0.40,
    # 교통 시설
    "traffic light": 0.42,
    # 실내 소형 (오탐 많아서 높게)
    "cell phone": 0.65, "remote": 0.65, "mouse": 0.65,
    "toothbrush": 0.70, "spoon": 0.70, "fork": 0.65,
}

# ── 방향별 위험도 가중치 ─────────────────────────────────────────────────────
RISK_DIR = {
    "8시": 0.3, "9시": 0.5, "10시": 0.7, "11시": 0.9,
    "12시": 1.0,
    "1시": 0.9, "2시": 0.7, "3시": 0.5, "4시": 0.3,
    "6시": 0.4,
}

# ── 거리별 위험도 가중치 ─────────────────────────────────────────────────────
RISK_DIST = {
    "매우 가까이": 1.0, "가까이": 0.8, "보통": 0.5,
    "멀리": 0.2, "매우 멀리": 0.1,
}

# ── 클래스별 위험도 배수 ─────────────────────────────────────────────────────
# 이동 차량 = 생명 위협 / 동물 = 돌발 행동 / 날카로운 것 = 부상 위험
CLASS_RISK_MULTIPLIER = {
    # 이동 차량 (최고 위험)
    "car": 3.0, "motorcycle": 3.0, "bus": 3.5, "truck": 3.5,
    "train": 4.0, "bicycle": 2.0, "airplane": 1.5, "boat": 1.5,
    # 이동 물체
    "skateboard": 2.0, "sports ball": 1.3,
    # 위험 동물
    "elephant": 4.0, "bear": 4.0, "horse": 2.5, "zebra": 2.0,
    "giraffe": 2.0, "cow": 2.0, "sheep": 1.5,
    "dog": 1.8, "cat": 1.5, "bird": 1.2,
    # 날카로운 물체
    "knife": 2.5, "scissors": 2.0,
    "wine glass": 1.5,   # 깨지면 유리 파편
    "baseball bat": 1.5,
    # 도로/보도 시설물 (충돌)
    "fire hydrant": 1.2, "parking meter": 1.2,
    # 바닥 장애물 (걸림·미끄럼)
    "banana": 1.0,  # 껍질 미끄럼
}

# ── COCO80 전체 + 파인튜닝 클래스 매핑 ────────────────────────────────────────
TARGET_CLASSES = {
    # 사람
    "person":          "사람",

    # 이동 차량 (야외 — 최고 위험)
    "bicycle":         "자전거",
    "car":             "자동차",
    "motorcycle":      "오토바이",
    "airplane":        "비행기",
    "bus":             "버스",
    "train":           "기차",
    "truck":           "트럭",
    "boat":            "보트",

    # 교통 시설
    "traffic light":   "신호등",
    "fire hydrant":    "소화전",
    "stop sign":       "정지 표지판",
    "parking meter":   "주차 미터기",
    "bench":           "벤치",

    # 동물 (야외 — 돌발 위험)
    "bird":            "새",
    "cat":             "고양이",
    "dog":             "개",
    "horse":           "말",
    "sheep":           "양",
    "cow":             "소",
    "elephant":        "코끼리",
    "bear":            "곰",
    "zebra":           "얼룩말",
    "giraffe":         "기린",

    # 가방·소지품 (바닥 장애물)
    "backpack":        "배낭",
    "umbrella":        "우산",
    "handbag":         "핸드백",
    "tie":             "넥타이",
    "suitcase":        "여행가방",

    # 스포츠 용품 (이동·바닥 장애물)
    "frisbee":         "원반",
    "skis":            "스키",
    "snowboard":       "스노보드",
    "sports ball":     "공",
    "kite":            "연",
    "baseball bat":    "야구 방망이",
    "baseball glove":  "야구 글러브",
    "skateboard":      "스케이트보드",
    "surfboard":       "서프보드",
    "tennis racket":   "테니스 라켓",

    # 주방·날카로운 물체
    "bottle":          "병",
    "wine glass":      "유리잔",
    "cup":             "컵",
    "fork":            "포크",
    "knife":           "칼",
    "spoon":           "숟가락",
    "bowl":            "그릇",

    # 음식 (바닥에 있으면 미끄럼·걸림)
    "banana":          "바나나",
    "apple":           "사과",
    "sandwich":        "샌드위치",
    "orange":          "오렌지",
    "broccoli":        "브로콜리",
    "carrot":          "당근",
    "hot dog":         "핫도그",
    "pizza":           "피자",
    "donut":           "도넛",
    "cake":            "케이크",

    # 가구 (실내외)
    "chair":           "의자",
    "couch":           "소파",
    "potted plant":    "화분",
    "bed":             "침대",
    "dining table":    "테이블",
    "toilet":          "변기",
    "tv":              "TV",

    # 전자기기
    "laptop":          "노트북",
    "mouse":           "마우스",
    "remote":          "리모컨",
    "keyboard":        "키보드",
    "cell phone":      "휴대폰",

    # 가전
    "microwave":       "전자레인지",
    "oven":            "오븐",
    "toaster":         "토스터기",
    "sink":            "세면대",
    "refrigerator":    "냉장고",

    # 생활용품
    "book":            "책",
    "clock":           "시계",
    "vase":            "꽃병",
    "scissors":        "가위",
    "teddy bear":      "인형",
    "hair drier":      "드라이기",
    "toothbrush":      "칫솔",

    # 파인튜닝 추가 클래스
    "stairs":          "계단",
}

# ── 물체 실제 크기 기반 거리 캘리브레이션 ────────────────────────────────────
CLASS_CALIB_RATIO = {
    "person": 0.10, "car": 0.35, "bus": 0.60, "truck": 0.50,
    "motorcycle": 0.08, "bicycle": 0.06, "airplane": 1.50,
    "train": 1.00, "boat": 0.40,
    "dog": 0.04, "horse": 0.20, "cow": 0.18, "elephant": 0.80,
    "bear": 0.25, "sheep": 0.06, "giraffe": 0.30, "zebra": 0.15,
    "bird": 0.01, "cat": 0.02,
    "bench": 0.15, "chair": 0.06, "couch": 0.20,
    "bed": 0.28, "dining table": 0.22, "refrigerator": 0.12,
    "suitcase": 0.06, "backpack": 0.04,
    "traffic light": 0.05, "fire hydrant": 0.03, "parking meter": 0.02,
    "skateboard": 0.02, "surfboard": 0.08, "skis": 0.06,
    "sports ball": 0.02, "baseball bat": 0.02,
    "knife": 0.005, "scissors": 0.005, "wine glass": 0.005,
    "bottle": 0.005, "vase": 0.008,
}
_DEFAULT_CALIB = 0.06


# ── 바닥 장애물 판별 ─────────────────────────────────────────────────────────
_GROUND_CLASSES = {
    "stairs", "fire hydrant", "parking meter",
    "dog", "cat", "bird", "backpack", "suitcase", "handbag",
    "frisbee", "sports ball", "skateboard",
    "knife", "scissors", "bottle", "wine glass",
    "banana", "apple", "orange", "pizza", "donut",
    "teddy bear", "toothbrush",
}


def detect_objects(image_bytes: bytes) -> tuple[list[dict], dict]:
    """
    반환: (top3_objects, scene_analysis)
    scene_analysis = {
        "safe_direction": str | None,   # 안전 경로 제안
        "crowd_warning":  str | None,   # 군중 경고
        "danger_warning": str | None,   # 위험 물체 경고
        "person_count":   int,
    }
    """
    import numpy as np
    import cv2

    nparr = np.frombuffer(image_bytes, np.uint8)
    img   = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    h, w  = img.shape[:2]

    results    = model(img, conf=CONF_THRESHOLD)[0]
    all_detections = []

    for box in results.boxes:
        cls_name = model.names[int(box.cls)]
        if cls_name not in TARGET_CLASSES:
            continue

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
        if area_ratio > DIST_VERY_NEAR:   distance = "매우 가까이"
        elif area_ratio > DIST_NEAR:      distance = "가까이"
        elif area_ratio > DIST_MID:       distance = "보통"
        elif area_ratio > DIST_FAR:       distance = "멀리"
        else:                             distance = "매우 멀리"

        calib      = CLASS_CALIB_RATIO.get(cls_name, _DEFAULT_CALIB)
        distance_m = round(math.sqrt(calib / area_ratio), 1) if area_ratio > 0 else 15.0
        distance_m = min(distance_m, 20.0)

        y2_norm        = y2 / h
        is_ground      = y2_norm > 0.65 or cls_name in _GROUND_CLASSES
        is_vehicle     = cls_name in {"car","motorcycle","bus","truck","train","bicycle","airplane","boat"}
        is_animal      = cls_name in {"dog","cat","horse","cow","sheep","bird","elephant","bear","zebra","giraffe"}
        is_dangerous   = cls_name in {"knife","scissors","wine glass","baseball bat"}

        ground_mult    = 1.4 if is_ground and distance in ("매우 가까이","가까이","보통") else 1.0
        class_mult     = CLASS_RISK_MULTIPLIER.get(cls_name, 1.0)
        risk_score     = round(
            RISK_DIR.get(direction, 0.5) * RISK_DIST[distance] * ground_mult * class_mult, 2
        )
        risk_score = min(risk_score, 1.0)

        all_detections.append({
            "class":           cls_name,
            "class_ko":        TARGET_CLASSES[cls_name],
            "bbox":            [x1, y1, x2, y2],
            "direction":       direction,
            "distance":        distance,
            "distance_m":      distance_m,
            "risk_score":      risk_score,
            "conf":            round(conf, 2),
            "is_ground_level": is_ground,
            "is_vehicle":      is_vehicle,
            "is_animal":       is_animal,
            "is_dangerous":    is_dangerous,
        })

    scene = _compute_scene_analysis(all_detections)
    top3  = sorted(all_detections, key=lambda x: x["risk_score"], reverse=True)[:3]
    return top3, scene


def _compute_scene_analysis(detections: list[dict]) -> dict:
    """전체 탐지 결과 → 안전 경로·군중·위험 물체 분석."""
    from src.nlg.templates import CLOCK_TO_DIRECTION

    all_zones  = ["8시","9시","10시","11시","12시","1시","2시","3시","4시"]
    zone_risk  = {z: 0.0 for z in all_zones}
    person_cnt = 0
    danger_msg = None

    for det in detections:
        d = det.get("direction", "12시")
        if d in zone_risk:
            zone_risk[d] += det.get("risk_score", 0)
        if det.get("class") == "person":
            person_cnt += 1
        if det.get("is_dangerous") and det.get("distance_m", 99) < 3.0:
            danger_msg = f"위험! 근처에 {det['class_ko']}이 있어요! 조심하세요."

    # 안전 경로: 정면 위험 있고 더 안전한 방향이 있을 때만 제안
    safe_dir = None
    front_risk = zone_risk.get("12시", 0)
    if front_risk > 0.3:
        safest = min(all_zones, key=lambda z: zone_risk[z])
        if zone_risk[safest] < front_risk * 0.4:
            direction = CLOCK_TO_DIRECTION.get(safest, safest)
            safe_dir  = f"{direction} 방향이 가장 안전해요."

    # 군중 경고
    crowd_msg = None
    if person_cnt >= 5:
        crowd_msg = "매우 혼잡해요. 멈추고 안내원을 찾아보세요."
    elif person_cnt >= 3:
        crowd_msg = "사람이 많아요. 천천히 이동하세요."

    return {
        "safe_direction": safe_dir,
        "crowd_warning":  crowd_msg,
        "danger_warning": danger_msg,
        "person_count":   person_cnt,
    }
