import pytest
from src.nlg.sentence import build_sentence, build_find_sentence, build_held_sentence


def test_empty_objects():
    # 물체가 없으면 "장애물 없음" 기본 문장을 반환해야 함
    result = build_sentence([], [])
    assert result == "주변에 장애물이 없어요."


def test_single_object():
    # 가까운 물체 1개가 있을 때 비어있지 않은 안내 문장을 반환해야 함
    objects = [{
        "class_ko": "의자",
        "direction": "12시",   # 정면
        "distance": "가까이",
        "distance_m": 1.5,
        "risk_score": 0.7,
        "is_ground_level": False,
    }]
    result = build_sentence(objects, [])
    assert isinstance(result, str)
    assert len(result) > 0


def test_with_changes():
    # changes 목록이 있으면 안내 문장 앞에 변화 메시지가 포함돼야 함
    objects = [{
        "class_ko": "의자",
        "direction": "12시",
        "distance": "보통",
        "distance_m": 3.0,
        "risk_score": 0.6,
        "is_ground_level": False,
    }]
    changes = ["가방이 1개 더 있어요"]   # 공간 기억에서 감지된 변화
    result = build_sentence(objects, changes)
    assert "가방이 1개 더 있어요" in result  # 변화 메시지가 문장에 포함되는지 확인


def test_max_two_sentences():
    # 물체가 3개여도 최대 2개 문장만 생성해야 함 (TTS 길이 제한)
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
    # 9방향 × 3거리 = 27가지 조합 모두 유효한 문자열을 반환해야 함
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
    """바닥 장애물도 위치 표현이 포함된 안내 문장을 반환해야 함.

    "가방"은 _CRITICAL_KO에 없는 일반 물체이므로 "위험!" 없이 일반 안내.
    바닥 장애물 강조는 routes.py의 slippery_warning / hazard 경로에서 처리됨.
    """
    obj = [{
        "class_ko": "가방",
        "direction": "12시",
        "distance": "가까이",
        "distance_m": 0.6,
        "risk_score": 0.9,
        "is_ground_level": True,
    }]
    result = build_sentence(obj, [])
    assert "가방" in result,   f"물체명 포함 확인 실패 → {result}"
    assert "바로" in result,   f"근거리 위치 표현 확인 실패 → {result}"
    assert "위험!" not in result, f"일반 물체에 '위험!' 붙으면 안 됨 → {result}"


# ── 신규 테스트: 2026-05 TTS 정책 개선 검증 ──────────────────────────────────

def test_everyday_object_no_critical():
    """생활 물체(키보드·마우스·TV 등)는 거리 무관하게 '위험!' 없어야 함.

    수정 전: SentenceBuilder.kt에서 areaRatio > 0.25이면 키보드도 "위험!" 붙었음.
    수정 후: _EVERYDAY_KO 세트가 is_critical 조건을 막아 일반 안내로 처리.
    """
    for name in ("키보드", "마우스", "TV", "책", "의자", "소파"):
        obj = [{
            "class_ko": name,
            "direction": "12시",
            "distance_m": 0.3,   # 매우 가까움
            "risk_score": 0.95,
            "is_ground_level": False,
        }]
        result = build_sentence(obj, [])
        assert "위험!" not in result, f"{name}: 생활 물체에 '위험!' 붙으면 안 됨 → {result}"


def test_vehicle_critical_uses_short_warning():
    """자동차 critical 문장은 서버/Android 공통의 짧은 긴급 경고 형식이어야 함.

    새 규칙: "위험! 바로 앞 자동차! 조심!"
    """
    obj = [{
        "class_ko": "자동차",
        "direction": "12시",
        "distance_m": 3.0,
        "is_vehicle": True,
        "risk_score": 1.0,
        "is_ground_level": False,
    }]
    result = build_sentence(obj, [])
    assert "위험!" in result,   f"자동차 critical에 '위험!' 없음 → {result}"
    assert "자동차" in result,  f"자동차 critical에 물체명 없음 → {result}"
    assert "조심!" in result,   f"자동차 critical에 짧은 경고 없음 → {result}"
    assert "미터" not in result, f"자동차 critical은 거리 수치 없이 짧게 안내해야 함 → {result}"
    assert "!" in result[-3:],  f"자동차 critical 문장이 느낌표로 끝나지 않음 → {result}"


def test_find_target_not_found_no_nameerror():
    """찾는 물체가 없을 때 NameError 없이 정상 반환해야 함.

    수정 전: ig 변수가 if found 블록 안에서만 정의 → objects 비어있으면 NameError.
    수정 후: ig·un을 블록 밖에서 미리 계산 → 항상 안전.
    """
    # 빈 objects — 찾는 물체 없음
    result = build_find_sentence("의자", [], "front")
    assert "의자가" in result,       f"받침 없는 조사 '가' 확인 실패 → {result}"
    assert "없어요" in result,       f"'없어요' 포함 확인 실패 → {result}"

    result2 = build_find_sentence("책", [], "front")
    assert "책이" in result2,        f"받침 있는 조사 '이' 확인 실패 → {result2}"


def test_find_target_found_format():
    """찾기 성공 시 '물체는 방향 거리에 있어요.' 형식이어야 함.

    Kotlin buildFind() 포맷과 동일: "{target}{un} {dir} {distStr}에 있어요."
    수정 전 Kotlin: "${target}${un} ${dir}에 있어요. $distStr." (거리 분리)
    수정 후 Kotlin: "${target}${un} ${dir} ${distStr}에 있어요."
    """
    obj = [{
        "class_ko": "의자",
        "direction": "12시",
        "distance_m": 2.0,
        "is_ground_level": False,
    }]
    result = build_find_sentence("의자", obj, "front")
    assert result.startswith("의자는"), f"'의자는'으로 시작해야 함 → {result}"
    assert "에 있어요" in result,      f"'에 있어요' 형식 확인 실패 → {result}"
    assert "미터" in result,           f"거리 표현 포함 확인 실패 → {result}"


def test_max_two_objects_policy():
    """물체 3개 입력 시 문장이 최대 2문장이어야 함 (TTS 길이 제한).

    수정 전 Kotlin: detections.take(3) — 3문장 생성.
    수정 후 Kotlin: detections.take(2) — Python objects[:2] 와 일치.
    Python은 원래부터 objects[:2] 이므로 이 테스트로 Python 정책도 함께 검증.
    """
    objects = [
        {"class_ko": "의자",   "direction": "11시", "distance_m": 1.0, "risk_score": 0.8, "is_ground_level": False},
        {"class_ko": "사람",   "direction": "12시", "distance_m": 2.5, "risk_score": 0.6, "is_ground_level": False},
        {"class_ko": "테이블", "direction": "1시",  "distance_m": 4.0, "risk_score": 0.3, "is_ground_level": False},
    ]
    result = build_sentence(objects, [])
    # 3번째 물체("테이블")가 결과에 포함되지 않아야 함
    assert "테이블" not in result, f"3번째 물체가 문장에 포함됨 → {result}"


def test_held_sentence_answers_nearest_object():
    """물건 확인 모드는 위험도보다 손/바로 앞에 가까운 물체를 우선 답해야 함."""
    objects = [
        {"class_ko": "의자", "direction": "12시", "distance_m": 2.4, "risk_score": 0.7},
        {"class_ko": "컵", "direction": "12시", "distance_m": 0.6, "risk_score": 0.2},
    ]
    result = build_held_sentence(objects)
    assert result == "손에 들고 있는 건 컵이에요."


def test_held_sentence_empty_scene():
    result = build_held_sentence([])
    assert result == "손에 든 물건이나 바로 앞에 뭔가 없어 보여요."
