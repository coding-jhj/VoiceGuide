"""Detection payload normalization for server-side storage and dashboard use.

Android is the authority for real-time safety judgement. This module preserves
client-provided distance, risk, and vibration fields, and only computes fallback
display values when the client omits them.
"""

from src.config.policy import get_policy


_ZONE_BOUNDARIES = [
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


def _class_sets() -> tuple[set[str], set[str], set[str]]:
    classes = get_policy().get("classes", {})
    return (
        set(classes.get("vehicle_ko", [])),
        set(classes.get("animal_ko", [])),
        set(classes.get("critical_ko", [])),
    )


def _float_value(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _bbox_from_raw(raw: dict) -> list[float]:
    bbox = raw.get("bbox_norm_xywh")
    if bbox and len(bbox) >= 4:
        return [round(_float_value(v), 6) for v in bbox[:4]]

    cx = _float_value(raw.get("cx"), 0.5)
    cy = _float_value(raw.get("cy"), 0.5)
    w = _float_value(raw.get("w"), 0.1)
    h = _float_value(raw.get("h"), 0.1)
    return [
        round(cx - w / 2, 6),
        round(cy - h / 2, 6),
        round(w, 6),
        round(h, 6),
    ]


def _direction_from_bbox(raw: dict, bbox: list[float]) -> str:
    direction = raw.get("direction") or raw.get("zone")
    if direction:
        return str(direction)

    cx = bbox[0] + bbox[2] / 2 if len(bbox) >= 4 else _float_value(raw.get("cx"), 0.5)
    for boundary, label in _ZONE_BOUNDARIES:
        if cx < boundary:
            return label
    return "4시"


def _distance_from_bbox(raw: dict, bbox: list[float]) -> float:
    if raw.get("distance_m") is not None:
        return round(_float_value(raw.get("distance_m"), 99.0), 1)
    if raw.get("dist_m") is not None:
        return round(_float_value(raw.get("dist_m"), 99.0), 1)

    area = max(0.0001, bbox[2] * bbox[3]) if len(bbox) >= 4 else 0.01
    try:
        calib = float(get_policy().get("on_device", {}).get("bbox_calib_area", 0.12))
    except Exception:
        calib = 0.12
    return round(min(15.0, max(0.1, (calib / area) ** 0.5)), 1)


def _risk_from_object(raw: dict, bbox: list[float], distance_m: float) -> float:
    if raw.get("risk_score") is not None:
        return round(_float_value(raw.get("risk_score"), 0.0), 2)

    area = bbox[2] * bbox[3] if len(bbox) >= 4 else 0.01
    distance_score = max(0.0, min(1.0, (7.0 - distance_m) / 7.0))
    area_score = max(0.0, min(1.0, area / 0.12))
    return round(max(distance_score, area_score), 2)


def _vibration_pattern(raw: dict, risk_score: float, is_vehicle: bool) -> str:
    pattern = raw.get("vibration_pattern")
    if pattern:
        return str(pattern)
    if is_vehicle and risk_score >= 0.55:
        return "URGENT"
    if risk_score >= 0.75:
        return "URGENT"
    if risk_score >= 0.55:
        return "DOUBLE"
    if risk_score >= 0.35:
        return "SHORT"
    return "NONE"


def normalize_detection_objects(raw_objects: list[dict]) -> list[dict]:
    """Normalize current /detect objects into the server detection shape."""
    vehicle_ko, animal_ko, critical_ko = _class_sets()
    objects = []

    for raw in raw_objects:
        if not isinstance(raw, dict):
            continue

        class_ko = str(raw.get("class_ko") or raw.get("classKo") or raw.get("label") or "").strip()
        if not class_ko:
            continue

        bbox = _bbox_from_raw(raw)
        is_vehicle = bool(raw.get("is_vehicle", class_ko in vehicle_ko))
        is_animal = bool(raw.get("is_animal", class_ko in animal_ko))
        distance_m = _distance_from_bbox(raw, bbox)
        risk_score = _risk_from_object(raw, bbox, distance_m)

        obj = {
            "class": str(raw.get("class") or raw.get("class_name") or class_ko),
            "class_ko": class_ko,
            "confidence": round(_float_value(raw.get("confidence"), 0.0), 4),
            "bbox_norm_xywh": bbox,
            "direction": _direction_from_bbox(raw, bbox),
            "depth_source": str(raw.get("depth_source", "on_device_bbox")),
            "is_vehicle": is_vehicle,
            "is_animal": is_animal,
            "is_dangerous": bool(raw.get("is_dangerous", class_ko in critical_ko)),
            "distance_m": distance_m,
            "risk_score": risk_score,
            "vibration_pattern": _vibration_pattern(raw, risk_score, is_vehicle),
        }
        if raw.get("track_id") not in (None, ""):
            obj["track_id"] = raw.get("track_id")
        objects.append(obj)

    return sorted(objects, key=lambda x: x.get("risk_score", 0.0), reverse=True)[:8]


def normalize_legacy_detections(raw_detections: list[dict]) -> list[dict]:
    """Normalize /detect_json detections into the same shape as /detect."""
    compatible = []
    for raw in raw_detections:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        if "bbox_norm_xywh" not in item:
            cx = _float_value(item.get("cx"), 0.5)
            cy = _float_value(item.get("cy"), 0.5)
            w = _float_value(item.get("w"), 0.1)
            h = _float_value(item.get("h"), 0.1)
            item["bbox_norm_xywh"] = [
                round(cx - w / 2, 6),
                round(cy - h / 2, 6),
                round(w, 6),
                round(h, 6),
            ]
        item["direction"] = item.get("direction") or item.get("zone", "12시")
        item["distance_m"] = item.get("distance_m", item.get("dist_m"))
        item["depth_source"] = item.get("depth_source", "on_device_bbox")
        compatible.append(item)
    return normalize_detection_objects(compatible)
