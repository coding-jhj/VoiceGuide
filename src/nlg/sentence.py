"""
VoiceGuide 한국어 문장 생성 모듈
==================================
탐지된 물체 정보를 받아 시각장애인이 바로 이해할 수 있는
한국어 음성 안내 문장을 만듭니다.

설계 원칙:
  1. 짧고 명확하게 — TTS 재생 시간을 최소화해야 즉각 반응 가능
  2. 행동 중심 — "의자가 있어요" 가 아니라 "피해가세요" 까지 포함
  3. 긴박도 차등 — 가까울수록 짧고 강하게, 멀수록 부드럽게
  4. 물체 특성 반영 — 차량·동물은 이동 물체라 별도 처리
  5. 상대 표현 — 카메라로 정확한 거리 측정 불가, 수치 대신 "가까이" 등 사용

routes.py에서 호출되는 공개 함수:
  build_sentence()         — 장애물/확인 모드
  build_find_sentence()    — 찾기 모드
"""

from src.nlg.templates import (
    CLOCK_ACTION, CLOCK_TO_DIRECTION, get_absolute_clock
)
from src.config import policy as _policy


# ── 경고 피로(alert fatigue) 방지 ─────────────────────────────────────────────
# 매 프레임마다 TTS를 읽어주면 사용자가 경고에 둔감해지는 문제가 있었음.
# critical/beep/silent 3단계로 나눠 불필요한 음성 안내를 줄인다.

def get_alert_mode(obj: dict, is_hazard: bool = False) -> str:
    """탐지 객체 하나의 알림 모드 반환.

    Returns:
        "critical" — 즉각 TTS 음성 경고
        "beep"     — 비프음만, 음성 없음
        "silent"   — 무음 (사용자가 명시적으로 물어볼 때만 안내)
    """
    am = _policy.alert_thresholds()
    v_m = float(am["vehicle_critical_m"])
    a_m = float(am["animal_critical_m"])
    g_m = float(am["generic_critical_m"])
    b_m = float(am["beep_until_m"])

    dist_m     = obj.get("smoothed_distance_m", obj.get("distance_m", 99.0))
    is_vehicle = obj.get("is_vehicle", False)
    is_animal  = obj.get("is_animal",  False)

    if is_hazard:                          # 계단·낙차 — 낙상 위험이므로 거리 무관 경고
        return "critical"
    if is_vehicle and dist_m < v_m:
        return "critical"
    if is_animal and dist_m < a_m:
        return "critical"
    if dist_m < g_m:
        return "critical"
    if dist_m < b_m:
        return "beep"
    return "silent"


# ── 한국어 조사 자동화 ────────────────────────────────────────────────────────

# 영문 알파벳 발음 기준 받침 없는 글자 (B=비, C=씨, D=디, E=이, T=티, V=브이 등)
_ENG_NO_BATCHIM = set('BCDEGHIJKOPQTUVWYZbcdeghijkopqtuvwyz')

def _josa(word: str, 받침있음: str, 받침없음: str) -> str:
    """
    한국어 받침 유무에 따라 올바른 조사를 반환하는 핵심 함수.

    원리:
      한국어: (글자코드 - 0xAC00) % 28 == 0 이면 받침 없음
      영문자: 발음 기준 — B(비)/C(씨)/D(디)/T(티)/V(브이) 등은 받침 없음
                         F(에프)/L(엘)/M(엠)/N(엔)/S(에스)/X(엑스) 등은 받침 있음
    예시:
      "TV"  → 마지막 V → 받침없음 → "TV가"
      "PC"  → 마지막 C → 받침없음 → "PC가"
      "USB" → 마지막 B → 받침없음 → "USB가"
    """
    if not word:
        return 받침있음
    last = word[-1]
    if '가' <= last <= '힣':
        return 받침있음 if (ord(last) - 0xAC00) % 28 != 0 else 받침없음
    if last in _ENG_NO_BATCHIM:
        return 받침없음
    return 받침있음  # F, L, M, N, R, S, X 및 숫자 등 → 받침 있는 쪽


def _i_ga(word: str) -> str:
    """주어 조사: "의자가", "책이" """
    return _josa(word, "이", "가")


def _un_neun(word: str) -> str:
    """보조사: "의자는", "책은" """
    return _josa(word, "은", "는")


def _i_eyo(word: str) -> str:
    """술어 어미: '사과예요', '컵이에요'"""
    return _josa(word, "이에요", "예요")

# ── 거리 표현 ─────────────────────────────────────────────────────────────────

def _format_dist(dist_m: float) -> str:
    """
    거리(미터)를 "약 Xm" 형식으로 변환 — policy.json distance_format 수치를 따름.
    """
    df = _policy.distance_format()
    lo = float(df["clamp_min_m"])
    hi = float(df["clamp_max_m"])
    close_m = float(df["close_face_m"])
    half_until = float(df["half_meter_round_until_m"])
    suf = str(df["meter_suffix"])

    dist_m = max(lo, min(dist_m, hi))
    if dist_m < close_m:
        return "코앞"
    if dist_m < half_until:
        r = round(dist_m * 2) / 2          # 0.5m 단위
        r_str = f"{r:.1f}".rstrip("0").rstrip(".")
        return f"약 {r_str}{suf}"
    r = round(dist_m)
    return f"약 {r}{suf}"


def _direction(abs_clock: str) -> str:
    return "정면" if abs_clock == "12시" else CLOCK_TO_DIRECTION.get(abs_clock, abs_clock)


def _loc(abs_clock: str, dist_m: float) -> str:
    direction = _direction(abs_clock)
    dist_str = _format_dist(dist_m)
    if abs_clock == "12시" and (dist_str == "코앞" or dist_m <= 0.75):
        return "바로 앞"
    if dist_str == "코앞":
        return f"{direction} 코앞"
    return f"{direction} {dist_str}"


def _guide_distance(obj: dict) -> float:
    return obj.get("smoothed_distance_m", obj.get("distance_m", 0.0))


# ── 주요 물체 문장 생성 (위험도 1순위) ────────────────────────────────────────

def _primary(obj: dict, abs_clock: str) -> str:
    """가장 위험한 물체 1개에 대한 안내 문장 생성.

    색상 체계와 동일한 기준으로 문장 형식 결정:
      빨강(critical) → "위험! 방향 거리에 물체가 있어요! 액션!"
      노랑(caution) → "방향 거리에 물체가 있어요. 액션"
      초록(info) → "방향 거리에 물체가 있어요."

    생활 물체(everyday_ko)는 아무리 가까워도 긴급 표현 금지 — policy.json과 동기화.
    """
    vehicle_ko = _policy.class_set("vehicle_ko")
    animal_ko = _policy.class_set("animal_ko")
    critical_ko = _policy.class_set("critical_ko")
    everyday_ko = _policy.class_set("everyday_ko")
    animal_m = float(_policy.alert_thresholds()["animal_critical_m"])

    dist_m     = _guide_distance(obj)
    name       = obj["class_ko"]
    ig         = _i_ga(name)
    direction  = _direction(abs_clock)
    loc_str    = _loc(abs_clock, dist_m)
    is_vehicle = obj.get("is_vehicle", name in vehicle_ko)
    is_animal  = obj.get("is_animal",  name in animal_ko)
    is_hazard  = obj.get("is_hazard", False)
    action     = CLOCK_ACTION.get(abs_clock, "조심하세요").rstrip(".")

    # 생활 물체는 거리·크기 무관하게 긴급 표현 금지 (이중 방어)
    is_critical = (
        (name in critical_ko or is_vehicle or (is_animal and dist_m < animal_m) or is_hazard)
        and name not in everyday_ko
    )

    if is_critical:
        return f"위험! {direction} {name}. 조심! 멈추세요!"

    # 생활 물체: 액션 없이 위치만 안내
    if name in everyday_ko:
        return f"{loc_str}에 {name}{ig} 있어요."

    return f"{loc_str}에 {name}{ig} 있어요. {action}"


# ── 보조 물체 문장 생성 (위험도 2순위) ────────────────────────────────────────

def _secondary(obj: dict, abs_clock: str) -> str:
    """
    두 번째 물체에 대한 간략한 안내 문장.
    "~도 있어요" 형태로 첫 번째 물체와 구분됩니다.

    _primary보다 짧게 — 두 문장 합쳐도 TTS가 너무 길지 않아야 함
    """
    dist_m     = _guide_distance(obj)
    name       = obj["class_ko"]
    loc_str    = _loc(abs_clock, dist_m)
    vehicle_ko = _policy.class_set("vehicle_ko")
    v_m = float(_policy.alert_thresholds()["vehicle_critical_m"])
    is_vehicle = obj.get("is_vehicle", name in vehicle_ko)

    if is_vehicle and dist_m < v_m:
        return f"{loc_str}에 {name}도 있어요!"
    return f"{loc_str}에 {name}도 있어요."


# ── 공개 함수들 ───────────────────────────────────────────────────────────────

def build_sentence(
    objects: list[dict],
    changes: list[str],
    camera_orientation: str = "front",
) -> str:
    """
    장애물/확인 모드의 메인 안내 문장 생성.

    Args:
        objects: Android 온디바이스 YOLO 결과를 서버에서 정규화한 탐지 물체
        changes: tracker가 감지한 변화 메시지 ["가방이 가까워지고 있어요"]
        camera_orientation: 폰 방향 (front/back/left/right)

    Returns:
        TTS로 바로 읽을 수 있는 한국어 문장
    """
    if not objects:
        # 물체 없어도 변화(공간 기억 차이)가 있으면 그걸 먼저 안내
        if changes:
            return changes[0]
        return "주변에 장애물이 없어요."

    parts = []
    for i, obj in enumerate(objects[:2]):  # 최대 2개만 안내 (더 많으면 혼란)
        # 카메라 방향 보정: 이미지 기준 방향 → 실제 방향
        abs_clock = get_absolute_clock(obj["direction"], camera_orientation)
        if i == 0:
            parts.append(_primary(obj, abs_clock))    # 첫 번째: 완전한 안내
        else:
            parts.append(_secondary(obj, abs_clock))  # 두 번째: "~도 있어요"

    result = " ".join(parts)
    # 공간 변화(새로 생긴/사라진 물체)가 있으면 맨 앞에 붙임
    if changes:
        return f"{changes[0]} {result}".strip()
    return result

def build_find_sentence(
    target: str,
    objects: list[dict],
    camera_orientation: str = "front",
) -> str:
    """
    찾기 모드: "의자 찾아줘" → 의자 위치 안내.

    target이 비어있으면 일반 장애물 안내로 fallback.
    찾는 물체가 없으면 "보이지 않아요 + 카메라 돌려보세요" 안내.

    부분 일치 검색: "가방"으로 검색 시 "핸드백"도 매칭 (contains 사용)
    """
    if not target:
        return build_sentence(objects, [], camera_orientation)

    # ig·un을 if 블록 바깥에서 미리 계산
    # 수정 전: ig가 found 블록 안에서만 정의되어 물체를 못 찾으면 NameError 크래시
    # 수정 후: 항상 정의되므로 found 유무와 무관하게 안전하게 사용 가능
    ig = _i_ga(target)
    un = _un_neun(target)

    found = [o for o in objects if target in o.get("class_ko", "")]
    if found:
        obj       = found[0]
        abs_clock = get_absolute_clock(obj["direction"], camera_orientation)
        loc_str = _loc(abs_clock, obj.get("distance_m", 0.0))
        return f"{target}{un} {loc_str}에 있어요."

    return f"{target}{ig} 없어요. 다른 곳을 보여주세요."


def build_question_sentence(
    objects: list[dict],
    hazards: list[dict],
    scene: dict,
    tracked_state: list[dict],
    camera_orientation: str = "front",
) -> str:
    """
    사용자가 직접 질문했을 때 포괄적 현재 상황 안내.

    "지금 뭐가 있어?", "앞에 뭐 있어?" 같은 질문에 응답.
    현재 프레임 탐지 결과 + tracker에 누적된 최근 상태를 모두 활용.

    Args:
        objects:       현재 프레임 YOLO 탐지 결과
        hazards:       현재 프레임 바닥 위험 감지 결과
        scene:         신호등·군중·위험물 등 장면 정보
        tracked_state: tracker.get_current_state() — 최근 3초 누적 정보
        camera_orientation: 폰 방향
    """
    parts = []

   # 1. 위험물 긴급 경고
    if scene.get("danger_warning"):
        parts.append(scene["danger_warning"])

    # 2. 현재 프레임 탐지 물체 (가장 신선한 정보)
    if objects:
        for i, obj in enumerate(objects[:2]):
            abs_clock = get_absolute_clock(obj["direction"], camera_orientation)
            parts.append(_primary(obj, abs_clock) if i == 0 else _secondary(obj, abs_clock))
    elif tracked_state:
        # 현재 프레임에 탐지 없으면 최근 tracker 상태로 대답
        for i, obj in enumerate(tracked_state[:2]):
            abs_clock = get_absolute_clock(obj.get("direction", "12시"), camera_orientation)
            name = obj["class_ko"]
            loc_str = _loc(abs_clock, obj["distance_m"])
            ig = _i_ga(name)
            if i == 0:
                parts.append(f"최근에 {loc_str}에서 {name}{ig} 보였어요.")
            else:
                parts.append(f"{loc_str}에 {name}도 있었어요.")

    # 3. 신호등 정보
    if scene.get("traffic_light_msg"):
        parts.append(scene["traffic_light_msg"])

    # 4. 안전 경로
    if scene.get("safe_direction"):
        parts.append(scene["safe_direction"])

    if not parts:
        return "현재 주변에 장애물이 없어 안전해 보여요."

    return " ".join(parts)

def build_held_sentence(objects: list[dict]) -> str:
    """손에 들고 있거나 바로 가까이 있는 물건 안내 (held_sentence_m 구간)."""
    if not objects:
        return "손에 든 물건이나 바로 앞에 뭔가 없어 보여요."

    hs = _policy.held_thresholds_m()
    h1 = float(hs["in_hand_max_m"])
    h2 = float(hs["immediate_front_max_m"])
    h3 = float(hs["near_max_m"])

    closest = min(objects, key=lambda o: o.get("distance_m", 99.0))
    dist_m = closest.get("distance_m", 99.0)
    name = closest["class_ko"]
    ig = _i_ga(name)
    ie = _i_eyo(name)

    if dist_m < h1:
        return f"손에 들고 있는 건 {name}{ie}."
    if dist_m < h2:
        return f"바로 앞에 {name}{ig} 있어요."
    if dist_m < h3:
        return f"가까이에 {name}{ig} 있어요."
    return "손에 든 물건이나 바로 앞에 뭔가 없어 보여요."
