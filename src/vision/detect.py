import math
from ultralytics import YOLO

model = YOLO("yolo11n.pt")

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

CALIB_RATIO  = 0.12
CALIB_DIST_M = 1.0

CONF_THRESHOLD = 0.25

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

TARGET_CLASSES = {
    "person":         "사람",
    "bicycle":        "자전거",
    "car":            "자동차",
    "motorcycle":     "오토바이",
    "airplane":       "비행기",
    "bus":            "버스",
    "train":          "기차",
    "truck":          "트럭",
    "boat":           "보트",
    "traffic light":  "신호등",
    "fire hydrant":   "소화전",
    "stop sign":      "정지 표지판",
    "parking meter":  "주차 미터기",
    "bench":          "벤치",
    "bird":           "새",
    "cat":            "고양이",
    "dog":            "개",
    "horse":          "말",
    "sheep":          "양",
    "cow":            "소",
    "elephant":       "코끼리",
    "bear":           "곰",
    "zebra":          "얼룩말",
    "giraffe":        "기린",
    "backpack":       "가방",
    "umbrella":       "우산",
    "handbag":        "가방",
    "tie":            "넥타이",
    "suitcase":       "여행가방",
    "frisbee":        "원반",
    "skis":           "스키",
    "snowboard":      "스노보드",
    "sports ball":    "공",
    "kite":           "연",
    "baseball bat":   "야구 방망이",
    "baseball glove": "야구 글러브",
    "skateboard":     "스케이트보드",
    "surfboard":      "서프보드",
    "tennis racket":  "테니스 라켓",
    "bottle":         "병",
    "wine glass":     "와인잔",
    "cup":            "컵",
    "fork":           "포크",
    "knife":          "칼",
    "spoon":          "숟가락",
    "bowl":           "그릇",
    "banana":         "바나나",
    "apple":          "사과",
    "sandwich":       "샌드위치",
    "orange":         "오렌지",
    "broccoli":       "브로콜리",
    "carrot":         "당근",
    "hot dog":        "핫도그",
    "pizza":          "피자",
    "donut":          "도넛",
    "cake":           "케이크",
    "chair":          "의자",
    "couch":          "소파",
    "potted plant":   "화분",
    "bed":            "침대",
    "dining table":   "테이블",
    "toilet":         "변기",
    "tv":             "TV",
    "laptop":         "노트북",
    "mouse":          "마우스",
    "remote":         "리모컨",
    "keyboard":       "키보드",
    "cell phone":     "휴대폰",
    "microwave":      "전자레인지",
    "oven":           "오븐",
    "toaster":        "토스터기",
    "sink":           "세면대",
    "refrigerator":   "냉장고",
    "book":           "책",
    "clock":          "시계",
    "vase":           "꽃병",
    "scissors":       "가위",
    "teddy bear":     "인형",
    "hair drier":     "드라이기",
    "toothbrush":     "칫솔",
}


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
        risk_score = round(RISK_DIR.get(direction, 0.5) * RISK_DIST[distance], 2)

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
