import uuid

from src.api.detections import normalize_detection_objects
from src.config.policy import init_policy


def test_server_bbox_distance_fallback_uses_class_specific_calibration():
    init_policy()
    bbox = [0.4, 0.4, 0.2, 0.2]
    objects = normalize_detection_objects(
        [
            {
                "class_ko": "사람",
                "confidence": 0.9,
                "bbox_norm_xywh": bbox,
                "track_id": f"person-{uuid.uuid4().hex}",
            },
            {
                "class_ko": "버스",
                "confidence": 0.9,
                "bbox_norm_xywh": bbox,
                "track_id": f"bus-{uuid.uuid4().hex}",
            },
        ]
    )

    by_class = {obj["class_ko"]: obj["distance_m"] for obj in objects}
    assert by_class["버스"] > by_class["사람"]
