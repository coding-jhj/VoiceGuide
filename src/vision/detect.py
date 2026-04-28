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
from src.nlg.sentence import _i_ga

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
    # 야외 차량: 멀리서도 일찍 잡아야 (안전 우선) → 임계값 낮게
    "car": 0.35, "motorcycle": 0.35, "bus": 0.35, "truck": 0.35,
    "bicycle": 0.40, "train": 0.32,
    # 사람
    "person": 0.40,
    # 위험 동물
    "dog": 0.42, "horse": 0.42, "cow": 0.42,
    "bear": 0.38, "elephant": 0.38,
    # 교통 시설
    "traffic light": 0.40,
    # 날카로운 위험 물체 → 낮게 (부상 위험)
    "knife": 0.42, "scissors": 0.45,
    # 실내 소형 (오탐 많아서 높게)
    "cell phone": 0.65, "remote": 0.65, "mouse": 0.65,
    "toothbrush": 0.70, "spoon": 0.70, "fork": 0.65,
    # 계단: 키보드·에스컬레이터 등 계단형 패턴 오탐 방지
    "stairs": 0.72,
    # 실내 소형/오탐 잦은 클래스
    "tie": 0.75, "umbrella": 0.68, "handbag": 0.65,
    "wine glass": 0.70, "cup": 0.65, "bowl": 0.65,
}

# ── 항상 최우선 안내 클래스 (botvoting 없이 즉시 통과) ────────────────────────
ALWAYS_CRITICAL = {
    "car", "motorcycle", "bus", "truck", "train",  # 이동 차량
    "bicycle",                                      # 자전거 (전동킥보드 대체)
    "stairs",                                       # 계단 (낙상)
    "knife", "scissors",                            # 날카로운 위험
    "bear", "elephant",                             # 위험 동물 대형
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


def _detect_color(img, x1: int, y1: int, x2: int, y2: int) -> str:
    """
    물체 중심부를 잘라서 HSV 색공간으로 색상을 분류합니다.

    왜 BGR이 아닌 HSV인가?
      BGR(파란/초록/빨간 채널 혼합)은 색상 판별에 부적합합니다.
      HSV = Hue(색조) / Saturation(채도) / Value(명도)
      → H값 하나로 색상 분류 가능, 조명 밝기 변화에 덜 민감

    HSV H값 범위 (OpenCV 기준 0~180):
      빨강: 0~15 또는 165~180 (원형이라 양쪽에 있음)
      주황: 15~30, 노랑: 30~45, 초록: 45~75
      파랑: 75~130, 보라: 130~165
    """
    import cv2
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    # 물체 중심의 작은 정사각형 영역만 분석 (배경 제외)
    r = max(5, min((x2 - x1) // 4, (y2 - y1) // 4))
    crop = img[max(0, cy - r):cy + r, max(0, cx - r):cx + r]
    if crop.size == 0:
        return "알 수 없음"
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    h_val = float(hsv[:, :, 0].mean())  # 색조 평균
    s_val = float(hsv[:, :, 1].mean())  # 채도 평균 (낮으면 무채색)
    v_val = float(hsv[:, :, 2].mean())  # 명도 평균
    # 채도가 낮으면 무채색 계열 (흰/회/검)
    if s_val < 40:
        if v_val > 180: return "흰색"
        if v_val > 80:  return "회색"
        return "검은색"
    # 채도 있으면 H값으로 색상 분류
    if h_val < 15 or h_val >= 165: return "빨간색"
    if h_val < 30:  return "주황색"
    if h_val < 45:  return "노란색"
    if h_val < 75:  return "초록색"
    if h_val < 130: return "파란색"
    if h_val < 165: return "보라색"
    return "알 수 없음"


def _detect_traffic_light_color(img, x1: int, y1: int, x2: int, y2: int) -> str:
    """
    신호등 bbox에서 빨간불/초록불을 구별합니다.

    신호등 구조 (수직형 기준):
      위쪽 1/3 → 빨간불 위치
      아래쪽 1/3 → 초록불 위치

    판별 방법:
      - 해당 영역을 HSV로 변환
      - 빨강 마스크: H=0~15 or 165~180, S>=100, V>=100
      - 초록 마스크: H=40~85, S>=100, V>=100
      - 해당 색 픽셀이 전체의 5% 이상이면 그 색으로 판정
      - 5% 미만이면 "unknown" (야간, 가림막 등)
    """
    import cv2
    crop = img[y1:y2, x1:x2]
    if crop.size == 0 or crop.shape[0] < 6:
        return "unknown"
    h = crop.shape[0]
    top    = crop[:h // 3]       # 위쪽 1/3 (빨간불 영역)
    bottom = crop[h * 2 // 3:]   # 아래쪽 1/3 (초록불 영역)
    hsv_top = cv2.cvtColor(top,    cv2.COLOR_BGR2HSV)
    hsv_bot = cv2.cvtColor(bottom, cv2.COLOR_BGR2HSV)
    # 빨강은 HSV H값이 0근처와 180근처 두 곳에 걸쳐 있음 → OR 결합
    red_mask = (
        cv2.inRange(hsv_top, (0, 100, 100),   (15, 255, 255)) |
        cv2.inRange(hsv_top, (165, 100, 100), (180, 255, 255))
    )
    green_mask = cv2.inRange(hsv_bot, (40, 100, 100), (85, 255, 255))
    # mean()/255: 마스크 픽셀 비율 (0.0~1.0), 5% 이상이면 해당 색으로 판정
    if green_mask.mean() / 255 > 0.05:
        return "green"
    if red_mask.mean() / 255 > 0.05:
        return "red"
    return "unknown"


def detect_objects(image_bytes: bytes) -> tuple[list[dict], dict]:
    """
    YOLO로 물체를 탐지하고 방향·거리·위험도·색상·신호등 상태를 계산합니다.

    처리 순서:
      1. 이미지 디코딩 + 좌우 flip (mirror 보정)
      2. YOLO 추론 → 모든 bbox 추출
      3. 각 bbox마다: 방향 구역, 면적 기반 거리, 위험도 점수, 경고 레벨 계산
      4. 신호등이면 색상 감지, 모든 물체에 색상 감지 실행
      5. 점자 블록 경로 위 장애물 확인
      6. scene_analysis: 안전경로·군중·위험물체·신호등 전체 분석
      7. 위험도 상위 3개만 반환

    Returns:
      top3_objects: 위험도 높은 물체 최대 3개
      scene: 안전경로·군중경고·위험물체경고·신호등·점자블록 경고
    """
    import numpy as np
    import cv2

    # 이미지 바이트 → numpy 배열 → OpenCV 이미지
    nparr = np.frombuffer(image_bytes, np.uint8)
    img   = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    img   = cv2.flip(img, 1)   # 좌우 반전: 카메라 mirror 현상 보정 (오른쪽↔왼쪽 교정)
    h, w  = img.shape[:2]      # 이미지 높이, 너비

    # YOLO 추론: conf=CONF_THRESHOLD 미만 박스는 자동 필터링
    results    = model(img, conf=CONF_THRESHOLD)[0]
    all_detections = []

    for box in results.boxes:
        cls_name = model.names[int(box.cls)]  # 영어 클래스명 (예: "chair")

        # TARGET_CLASSES에 없는 클래스는 무시 (COCO 중 보행 무관한 것들)
        if cls_name not in TARGET_CLASSES:
            continue

        # 클래스별 최소 신뢰도 적용 (소형 물체는 높게, 차량은 낮게)
        conf = float(box.conf[0])
        if conf < CLASS_MIN_CONF.get(cls_name, CONF_THRESHOLD):
            continue

        # bbox 좌표: xyxy 포맷 (왼쪽상단x, 왼쪽상단y, 오른쪽하단x, 오른쪽하단y)
        x1, y1, x2, y2 = map(int, box.xyxy[0])

        # 방향 판단: bbox 중심의 x좌표를 이미지 너비로 정규화 (0~1)
        # → ZONE_BOUNDARIES와 비교해서 8시~4시 중 어느 구역인지 결정
        cx_norm = ((x1 + x2) / 2) / w
        direction = "4시"  # 기본값: 오른쪽 끝
        for boundary, label in ZONE_BOUNDARIES:
            if cx_norm <= boundary:
                direction = label
                break

        # 거리 판단: bbox가 이미지에서 차지하는 면적 비율
        # 크게 보일수록(면적 클수록) 가까이 있는 것
        area_ratio = ((x2 - x1) * (y2 - y1)) / (w * h)
        if area_ratio > DIST_VERY_NEAR:   distance = "매우 가까이"  # 25% 이상
        elif area_ratio > DIST_NEAR:      distance = "가까이"        # 12% 이상
        elif area_ratio > DIST_MID:       distance = "보통"          # 4% 이상
        elif area_ratio > DIST_FAR:       distance = "멀리"          # 1% 이상
        else:                             distance = "매우 멀리"     # 1% 미만

        # 미터 단위 거리 추정: 물체 실제 크기(calib)와 면적 비율로 역산
        # 공식: dist = sqrt(calib / area_ratio)
        # 예) 의자(calib=0.06) 면적 6% → sqrt(0.06/0.06) = 1.0m
        # depth.py의 Depth V2가 더 정확하므로, 여기서는 초기 추정값만 계산
        calib      = CLASS_CALIB_RATIO.get(cls_name, _DEFAULT_CALIB)
        distance_m = round(math.sqrt(calib / area_ratio), 1) if area_ratio > 0 else 15.0
        distance_m = min(distance_m, 20.0)  # 최대 20m로 cap

        # 바닥 장애물 판별: bbox 하단이 이미지 65% 아래에 있거나 바닥 클래스이면
        # → 발에 걸릴 가능성이 높은 물체 (가중치 1.4배)
        y2_norm    = y2 / h
        is_ground  = y2_norm > 0.65 or cls_name in _GROUND_CLASSES
        is_vehicle = cls_name in {"car","motorcycle","bus","truck","train","bicycle","airplane","boat"}
        is_animal  = cls_name in {"dog","cat","horse","cow","sheep","bird","elephant","bear","zebra","giraffe"}
        is_dangerous = cls_name in {"knife","scissors","wine glass","baseball bat"}
        is_bus     = cls_name == "bus"

        # 위험도 점수 계산:
        # risk = 방향가중치 × 거리가중치 × 바닥가중치 × 클래스배수
        ground_mult = 1.4 if is_ground and distance in ("매우 가까이","가까이","보통") else 1.0
        class_mult  = CLASS_RISK_MULTIPLIER.get(cls_name, 1.0)
        risk_score  = round(
            RISK_DIR.get(direction, 0.5) * RISK_DIST[distance] * ground_mult * class_mult, 2
        )
        risk_score = min(risk_score, 1.0)  # 1.0 초과 방지

        # 색상 감지
        color = _detect_color(img, x1, y1, x2, y2)

        # 신호등 색상 감지
        traffic_light_state = None
        if cls_name == "traffic light":
            traffic_light_state = _detect_traffic_light_color(img, x1, y1, x2, y2)

        # 버스 번호 인식 (bbox 상단 영역 OCR 준비용 crop 좌표 저장)
        bus_crop = [x1, y1, x2, min(y1 + (y2-y1)//3, y2)] if is_bus else None

        all_detections.append({
            "class":                cls_name,
            "class_ko":             TARGET_CLASSES[cls_name],
            "bbox":                 [x1, y1, x2, y2],
            "direction":            direction,
            "distance":             distance,
            "distance_m":           distance_m,
            "risk_score":           risk_score,
            "conf":                 round(conf, 2),
            "is_ground_level":      is_ground,
            "is_vehicle":           is_vehicle,
            "is_animal":            is_animal,
            "is_dangerous":         is_dangerous,
            "color":                color,
            "traffic_light_state":  traffic_light_state,
            "bus_crop":             bus_crop,
        })

    scene = _compute_scene_analysis(all_detections)

    # 점자 블록 위 장애물 경고: 바닥에 있는 물체가 이미지 하단 중앙 경로에 있을 때
    _check_tactile_block_obstruction(all_detections, scene, w, h)

    top3  = sorted(all_detections, key=lambda x: x["risk_score"], reverse=True)[:3]
    return top3, scene


def _check_tactile_block_obstruction(detections: list[dict], scene: dict, w: int, h: int):
    """점자 블록 보행 경로(이미지 하단 중앙 30%) 위 장애물 감지."""
    # 경로 영역: 하단 35% 높이, 좌우 중앙 40% 너비
    path_x1 = w * 0.30
    path_x2 = w * 0.70
    path_y1 = h * 0.65

    _TACTILE_BLOCKERS = {
        "자전거", "오토바이", "스케이트보드", "유모차",
        "배낭", "여행가방", "우산", "화분", "벤치",
    }

    for det in detections:
        if not det.get("is_ground_level"):
            continue
        x1, y1, x2, y2 = det["bbox"]
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        if path_x1 <= cx <= path_x2 and cy >= path_y1:
            name = det["class_ko"]
            if name in _TACTILE_BLOCKERS:
                scene["tactile_block_warning"] = f"보행 경로에 {name}{_i_ga(name)} 있어요. 우회하세요."
            else:
                scene.setdefault("tactile_block_warning",
                                 f"보행 경로에 장애물이 있어요. 조심하세요.")
            break


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

    # 신호등 상태 안내
    traffic_light_msg = None
    for det in detections:
        if det.get("class") == "traffic light":
            state = det.get("traffic_light_state")
            if state == "green":
                traffic_light_msg = "신호등이 초록불이에요. 건너도 돼요."
            elif state == "red":
                traffic_light_msg = "신호등이 빨간불이에요. 멈추세요."
            break

    return {
        "safe_direction":    safe_dir,
        "crowd_warning":     crowd_msg,
        "danger_warning":    danger_msg,
        "person_count":      person_cnt,
        "traffic_light_msg": traffic_light_msg,
    }
