import pytest
from src.vision.detect import detect_objects, TARGET_CLASSES


def test_target_classes_defined():
    assert "person" in TARGET_CLASSES
    assert "chair" in TARGET_CLASSES
    assert "dining table" in TARGET_CLASSES
    assert "backpack" in TARGET_CLASSES
    assert "suitcase" in TARGET_CLASSES
    assert "cell phone" in TARGET_CLASSES


def test_detect_objects_returns_list(sample_image_bytes):
    result = detect_objects(sample_image_bytes)
    assert isinstance(result, list)
    assert len(result) <= 2


def test_detect_objects_fields(sample_image_bytes):
    result = detect_objects(sample_image_bytes)
    for obj in result:
        assert "class" in obj
        assert "class_ko" in obj
        assert "bbox" in obj
        assert "direction" in obj
        assert "distance" in obj
        assert "risk_score" in obj
        assert obj["direction"] in ("left", "center", "right")
        assert obj["distance"] in ("가까이", "보통", "멀리")
        assert 0.0 <= obj["risk_score"] <= 1.0
