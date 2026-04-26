import pytest
from src.nlg.sentence import build_sentence


def test_empty_objects():
    result = build_sentence([], [])
    assert result == "주변에 장애물이 없어요."


def test_single_object():
    objects = [{
        "class_ko": "의자",
        "direction": "12시",
        "distance": "가까이",
        "distance_m": 1.5,
        "risk_score": 0.7,
        "is_ground_level": False,
    }]
    result = build_sentence(objects, [])
    assert isinstance(result, str)
    assert len(result) > 0


def test_with_changes():
    objects = [{
        "class_ko": "의자",
        "direction": "12시",
        "distance": "보통",
        "distance_m": 3.0,
        "risk_score": 0.6,
        "is_ground_level": False,
    }]
    changes = ["가방이 1개 더 있어요"]
    result = build_sentence(objects, changes)
    assert "가방이 1개 더 있어요" in result


def test_max_two_sentences():
    objects = [
        {"class_ko": "의자",   "direction": "11시", "distance": "가까이", "distance_m": 1.2, "risk_score": 0.7, "is_ground_level": False},
        {"class_ko": "사람",   "direction": "12시", "distance": "보통",   "distance_m": 3.0, "risk_score": 0.6, "is_ground_level": False},
        {"class_ko": "테이블", "direction": "1시",  "distance": "멀리",   "distance_m": 5.0, "risk_score": 0.3, "is_ground_level": False},
    ]
    result = build_sentence(objects, [])
    assert isinstance(result, str)
    # 최대 2개 객체만 안내
    assert result.count("있어요") <= 2


def test_all_clock_directions():
    """실제 ZONE_BOUNDARIES 가 생성하는 시계 방향 값들로 테스트"""
    directions = ["8시", "9시", "10시", "11시", "12시", "1시", "2시", "3시", "4시"]
    distances  = [("가까이", 1.5), ("보통", 3.0), ("멀리", 5.0)]
    for d in directions:
        for dist_label, dist_m in distances:
            obj = [{
                "class_ko": "의자",
                "direction": d,
                "distance": dist_label,
                "distance_m": dist_m,
                "risk_score": 0.5,
                "is_ground_level": False,
            }]
            result = build_sentence(obj, [])
            assert isinstance(result, str)
            assert len(result) > 0


def test_ground_level_warning():
    """바닥 장애물은 가까울 때 '조심' 문구가 포함돼야 함"""
    obj = [{
        "class_ko": "가방",
        "direction": "12시",
        "distance": "가까이",
        "distance_m": 0.6,
        "risk_score": 0.9,
        "is_ground_level": True,
    }]
    result = build_sentence(obj, [])
    assert "조심" in result
