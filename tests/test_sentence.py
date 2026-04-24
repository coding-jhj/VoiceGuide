import pytest
from src.nlg.sentence import build_sentence


def test_empty_objects():
    result = build_sentence([], [])
    assert result == "주변에 장애물이 없어요."


def test_single_object():
    objects = [{"class_ko": "의자", "direction": "left", "distance": "가까이", "risk_score": 0.7}]
    result = build_sentence(objects, [])
    assert isinstance(result, str)
    assert len(result) > 0


def test_with_changes():
    objects = [{"class_ko": "의자", "direction": "center", "distance": "보통", "risk_score": 0.6}]
    changes = ["가방이 1개 더 있어요"]
    result = build_sentence(objects, changes)
    assert "가방이 1개 더 있어요" in result


def test_max_two_sentences():
    objects = [
        {"class_ko": "의자", "direction": "left",   "distance": "가까이", "risk_score": 0.7},
        {"class_ko": "사람", "direction": "center", "distance": "보통",   "risk_score": 0.6},
        {"class_ko": "테이블", "direction": "right", "distance": "멀리",  "risk_score": 0.3},
    ]
    result = build_sentence(objects, [])
    assert isinstance(result, str)


def test_all_directions_distances():
    directions = ["left", "center", "right"]
    distances  = ["가까이", "보통", "멀리"]
    for d in directions:
        for dist in distances:
            obj = [{"class_ko": "의자", "direction": d, "distance": dist, "risk_score": 0.5}]
            result = build_sentence(obj, [])
            assert isinstance(result, str)
            assert len(result) > 0
