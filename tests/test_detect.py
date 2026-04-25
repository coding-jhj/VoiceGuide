import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

from src.vision.detect import detect_objects, TARGET_CLASSES

VALID_DIRECTIONS = {"8시", "9시", "10시", "11시", "12시", "1시", "2시", "3시", "4시"}
VALID_DISTANCES  = {"매우 가까이", "가까이", "보통", "멀리", "매우 멀리"}


def test_target_classes_defined():
    assert "person"       in TARGET_CLASSES
    assert "chair"        in TARGET_CLASSES
    assert "dining table" in TARGET_CLASSES
    assert "backpack"     in TARGET_CLASSES
    assert "suitcase"     in TARGET_CLASSES
    assert "cell phone"   in TARGET_CLASSES
    assert "stairs"       in TARGET_CLASSES   # 파인튜닝 추가 클래스


def test_detect_objects_returns_list(sample_image_bytes):
    result = detect_objects(sample_image_bytes)
    assert isinstance(result, list)
    assert len(result) <= 3   # 상위 3개 반환


def test_detect_objects_fields(sample_image_bytes):
    result = detect_objects(sample_image_bytes)
    for obj in result:
        assert "class"           in obj
        assert "class_ko"        in obj
        assert "bbox"            in obj
        assert "direction"       in obj
        assert "distance"        in obj
        assert "distance_m"      in obj
        assert "risk_score"      in obj
        assert "is_ground_level" in obj
        assert "depth_source"    not in obj   # detect_objects는 depth_source 없음
        assert obj["direction"] in VALID_DIRECTIONS
        assert obj["distance"]  in VALID_DISTANCES
        assert 0.0 <= obj["risk_score"] <= 1.0
        assert obj["distance_m"] >= 0.1
        assert isinstance(obj["is_ground_level"], bool)
