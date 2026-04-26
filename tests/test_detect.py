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
    # COCO80 전체 포함 확인
    assert "car"          in TARGET_CLASSES
    assert "dog"          in TARGET_CLASSES
    assert "knife"        in TARGET_CLASSES
    assert "banana"       in TARGET_CLASSES
    assert len(TARGET_CLASSES) >= 81   # COCO80 + 계단


def test_detect_objects_returns_tuple(sample_image_bytes):
    result, scene = detect_objects(sample_image_bytes)
    assert isinstance(result, list)
    assert isinstance(scene, dict)
    assert len(result) <= 3


def test_scene_analysis_keys(sample_image_bytes):
    _, scene = detect_objects(sample_image_bytes)
    assert "safe_direction" in scene
    assert "crowd_warning"  in scene
    assert "danger_warning" in scene
    assert "person_count"   in scene


def test_detect_objects_fields(sample_image_bytes):
    result, _ = detect_objects(sample_image_bytes)
    for obj in result:
        assert "class"           in obj
        assert "class_ko"        in obj
        assert "bbox"            in obj
        assert "direction"       in obj
        assert "distance"        in obj
        assert "distance_m"      in obj
        assert "risk_score"      in obj
        assert "is_ground_level" in obj
        assert "is_vehicle"      in obj
        assert "is_animal"       in obj
        assert "is_dangerous"    in obj
        assert obj["direction"]  in VALID_DIRECTIONS
        assert obj["distance"]   in VALID_DISTANCES
        assert 0.0 <= obj["risk_score"] <= 1.0
        assert obj["distance_m"] >= 0.1
        assert isinstance(obj["is_ground_level"], bool)
