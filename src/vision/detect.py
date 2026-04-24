from ultralytics import YOLO

model = YOLO("yolo11n.pt")

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
    YOLO11n으로 이미지에서 5종 물체 탐지
    Returns: [{class, class_ko, bbox, direction, distance, risk_score}, ...]
    """
    import numpy as np
    import cv2

    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    h, w = img.shape[:2]

    results = model(img)[0]
    detections = []

    for box in results.boxes:
        cls_name = model.names[int(box.cls)]
        if cls_name not in TARGET_CLASSES:
            continue

        x1, y1, x2, y2 = map(int, box.xyxy[0])
        cx = (x1 + x2) / 2

        if cx < w * 0.33:
            direction = "left"
        elif cx < w * 0.66:
            direction = "center"
        else:
            direction = "right"

        area_ratio = ((x2 - x1) * (y2 - y1)) / (w * h)
        if area_ratio > 0.15:
            distance = "가까이"
        elif area_ratio > 0.05:
            distance = "보통"
        else:
            distance = "멀리"

        dir_score  = {"center": 1.0, "left": 0.7, "right": 0.7}[direction]
        dist_score = {"가까이": 1.0, "보통": 0.6, "멀리": 0.3}[distance]
        risk_score = round(dir_score * dist_score, 2)

        detections.append({
            "class":      cls_name,
            "class_ko":   TARGET_CLASSES[cls_name],
            "bbox":       [x1, y1, x2, y2],
            "direction":  direction,
            "distance":   distance,
            "risk_score": risk_score,
        })

    return sorted(detections, key=lambda x: x["risk_score"], reverse=True)[:2]
