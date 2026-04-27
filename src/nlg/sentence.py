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
  build_hazard_sentence()  — 계단·낙차 최우선 안내
  build_find_sentence()    — 찾기 모드
  build_navigation_sentence() — 개인 네비게이팅
"""

from src.nlg.templates import (
    CLOCK_ACTION, CLOCK_TO_DIRECTION, get_absolute_clock
)

# 이동 차량: 같은 거리라도 정적 의자보다 훨씬 위험 → 8m 이내부터 긴급 경고
_VEHICLE_KO = {"자동차", "오토바이", "버스", "트럭", "기차", "자전거"}

# 동물: 돌발 행동 가능 → 일반 장애물보다 주의 어조
_ANIMAL_KO  = {"개", "말", "고양이"}


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
    dist_m     = obj.get("distance_m", 99.0)
    is_vehicle = obj.get("is_vehicle", False)
    is_animal  = obj.get("is_animal",  False)

    if is_hazard:                          # 계단·낙차 — 낙상 위험이므로 거리 무관 경고
        return "critical"
    if is_vehicle and dist_m < 8.0:        # 차량 — 이동 속도 때문에 여유 거리 넉넉히
        return "critical"
    if is_animal and dist_m < 3.0:         # 동물 — 돌발 행동 위험
        return "critical"
    if dist_m < 0.5:                       # 코앞 장애물 — 충돌 직전
        return "critical"
    if dist_m < 1.0:                       # 1m 이내 — 위험하지만 비프음으로 피로 줄임
        return "beep"
    return "silent"


# ── 한국어 조사 자동화 ────────────────────────────────────────────────────────

def _josa(word: str, 받침있음: str, 받침없음: str) -> str:
    """
    한국어 받침 유무에 따라 올바른 조사를 반환하는 핵심 함수.

    원리:
      한국어 유니코드 배치: 가(0xAC00) ~ 힣(0xD7A3)
      각 글자 = 초성(19) × 중성(21) × 종성(28) 조합
      (글자코드 - 0xAC00) % 28 == 0 이면 종성(받침) 없음

    예시:
      "의자": 마지막 글자 "자"(0xC790) → (51088-44032)%28 = 0 → 받침 없음 → "가"
      "책":   마지막 글자 "책"(0xCC45) → (52293-44032)%28 = 1 → 받침 있음 → "이"
      "소파": 마지막 글자 "파"(0xD30C) → (54028-44032)%28 = 0 → 받침 없음 → "가"
    """
    if not word:
        return 받침있음  # 빈 문자열이면 안전하게 받침 있는 쪽 반환
    last = word[-1]
    if '가' <= last <= '힣':  # 한글 범위 내인지 확인
        return 받침있음 if (ord(last) - 0xAC00) % 28 != 0 else 받침없음
    return 받침있음  # 영문/숫자/기타 → 받침 있는 쪽으로 fallback


def _i_ga(word: str) -> str:
    """주어 조사: "의자가", "책이" """
    return _josa(word, "이", "가")


def _eul_reul(word: str) -> str:
    """목적어 조사: "의자를", "책을" """
    return _josa(word, "을", "를")


def _un_neun(word: str) -> str:
    """보조사: "의자는", "책은" """
    return _josa(word, "은", "는")


# ── 거리 표현 ─────────────────────────────────────────────────────────────────

def _format_dist(dist_m: float) -> str:
    """
    거리(미터)를 상대 표현으로 변환.

    왜 수치("약 1.2미터")가 아닌 상대 표현("가까이")인가?
      카메라 단안으로 정확한 거리 측정은 불가능합니다.
      Depth V2도 상대적 깊이 추정이라 오차가 큽니다.
      "약 1.2미터"라고 말하면 신뢰도가 없는 수치를 마치 정확한 것처럼 전달하게 됩니다.
      → 사용자가 판단하기 쉬운 상대 표현이 더 안전하고 정직합니다.
    """
    dist_m = max(0.1, min(dist_m, 15.0))  # 유효 범위 클리핑
    if dist_m < 0.5:  return "바로 코앞"    # 즉각 위험 — 0.5m 미만
    if dist_m < 1.0:  return "매우 가까이"  # 주의 필요 — 1m 미만
    if dist_m < 2.5:  return "가까이"       # 경계 — 2.5m 미만
    if dist_m < 5.0:  return "조금 멀리"    # 정보성 — 5m 미만
    return "멀리"                            # 참고용 — 5m 이상


# ── 주요 물체 문장 생성 (위험도 1순위) ────────────────────────────────────────

def _primary(obj: dict, abs_clock: str) -> str:
    """
    가장 위험한 물체 1개에 대한 완전한 안내 문장 생성.

    우선순위:
      1. 차량 (이동 물체, 속도 위험)
      2. 동물 (돌발 행동 위험)
      3. 바닥 장애물 (걸림·넘어짐 위험)
      4. 일반 장애물 (거리별 긴박도 차등)

    abs_clock: 카메라 방향 보정이 완료된 실제 시계 방향
    """
    dist_m     = obj.get("distance_m", 0.0)
    name       = obj["class_ko"]
    ig         = _i_ga(name)
    direction  = CLOCK_TO_DIRECTION.get(abs_clock, abs_clock)
    dist_str   = _format_dist(dist_m)
    action     = CLOCK_ACTION.get(abs_clock, "조심하세요").rstrip(".")
    is_ground  = obj.get("is_ground_level", False)
    is_vehicle = obj.get("is_vehicle", name in _VEHICLE_KO)
    is_animal  = obj.get("is_animal",  name in _ANIMAL_KO)

    # ── 차량: 이동 중이므로 거리 기준이 다름 ────────────────────────────
    # 일반 장애물은 0.5m 기준이지만, 차량은 8m 이내부터 위험
    # 이유: 차량은 0.5m까지 기다리면 이미 늦음
    if is_vehicle:
        if dist_m < 3.0:
            return f"위험! {direction}에 {name}{ig} 있어요! {dist_str}. 즉시 {action}!"
        if dist_m < 8.0:
            # "접근 중"이라고 표현해서 이동 물체임을 강조
            return f"조심! {direction}에 {name}{ig}접근 중이에요. {dist_str}. {action}."
        return f"{direction}에 {name}{ig} 있어요. {dist_str}."

    # ── 동물: "천천히" 어조 — 급격한 움직임 자제 유도 ───────────────────
    if is_animal:
        if dist_m < 3.0:
            return f"조심! {direction}에 {name}{ig} 있어요. {dist_str}. 천천히 {action}."
        return f"{direction}에 {name}{ig} 있어요. {dist_str}."

    # ── 바닥 장애물: 발에 걸릴 수 있어서 2m 이내일 때만 특별 처리 ────────
    # is_ground: bbox 하단이 이미지 65% 아래이거나 _GROUND_CLASSES에 속함
    if is_ground and dist_m < 2.0:
        if dist_m < 0.8:
            return f"조심! 바로 앞 바닥에 {name}{ig} 있어요. {action}."
        return f"조심! {direction} 바닥에 {name}{ig} 있어요. {action}."

    # ── 일반 장애물: 거리별 4단계 긴박도 ────────────────────────────────
    # 0.5m 미만: 너무 가까워서 방향 설명할 시간 없음 → 초단문
    if dist_m < 0.5:
        return f"위험! {direction} {name}!"
    # 1m 미만: 짧게 + 행동
    if dist_m < 1.0:
        return f"{direction}에 {name}{ig} 있어요. {dist_str}. {action}."
    # 2.5m 미만: 방향 + 거리 + 행동
    if dist_m < 2.5:
        return (f"{direction}에 {name}{ig} 있어요. {dist_str}. {action}."
                if action else
                f"{direction}에 {name}{ig} 있어요. {dist_str}.")
    # 2.5m 이상: 정보성, 행동 안내 생략
    return f"{direction}에 {name}{ig} 있어요. {dist_str}."


# ── 보조 물체 문장 생성 (위험도 2순위) ────────────────────────────────────────

def _secondary(obj: dict, abs_clock: str) -> str:
    """
    두 번째 물체에 대한 간략한 안내 문장.
    "~도 있어요" 형태로 첫 번째 물체와 구분됩니다.

    _primary보다 짧게 — 두 문장 합쳐도 TTS가 너무 길지 않아야 함
    """
    dist_m     = obj.get("distance_m", 0.0)
    name       = obj["class_ko"]
    direction  = CLOCK_TO_DIRECTION.get(abs_clock, abs_clock)
    dist_str   = _format_dist(dist_m)
    action     = CLOCK_ACTION.get(abs_clock, "").rstrip(".")
    is_vehicle = obj.get("is_vehicle", name in _VEHICLE_KO)

    # 2순위 물체는 action까지 넣으면 정보 과다 → 방향+거리만 안내
    if is_vehicle and dist_m < 8.0:
        return f"{direction}으로 {dist_str}에 {name}도 있어요!"
    return f"{direction}으로 {dist_str}에 {name}도 있어요."


# ── 공개 함수들 ───────────────────────────────────────────────────────────────

def build_sentence(
    objects: list[dict],
    changes: list[str],
    camera_orientation: str = "front",
) -> str:
    """
    장애물/확인 모드의 메인 안내 문장 생성.

    Args:
        objects: detect_and_depth()가 반환한 탐지 물체 (위험도 순 정렬됨)
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


def build_hazard_sentence(
    hazard: dict,
    objects: list[dict],
    changes: list[str],
    camera_orientation: str = "front",
) -> str:
    """
    계단·낙차·턱 등 바닥 위험을 최우선으로 안내.

    hazard.risk >= 0.7이면 다른 물체 안내 없이 위험만 말함.
    이유: 계단 앞에서 "의자도 있어요"까지 들을 시간이 없음.

    Args:
        hazard: detect_floor_hazards()가 반환한 hazard dict
        objects: YOLO 탐지 물체 (위험도 보조 참고용)
    """
    h_msg  = hazard.get("message", "앞에 위험이 있어요.")
    h_risk = hazard.get("risk", 0.5)

    # 고위험(0.7+) 또는 주변 물체 없으면 계단 경고만
    if h_risk >= 0.7 or not objects:
        return h_msg

    # 저위험 계단 + 주변 물체 있으면 둘 다 안내
    obj_sentence = build_sentence(objects[:1], [], camera_orientation)
    return f"{h_msg} 그리고 {obj_sentence}"


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

    found = [o for o in objects if target in o.get("class_ko", "")]
    if found:
        obj       = found[0]
        abs_clock = get_absolute_clock(obj["direction"], camera_orientation)
        direction = CLOCK_TO_DIRECTION.get(abs_clock, abs_clock)
        dist_str  = _format_dist(obj.get("distance_m", 0.0))
        un        = _un_neun(target)
        return f"{target}{un} {direction} {dist_str} 거리에 있어요."

    # 못 찾음 — 주변 물체라도 안내해서 사용자가 방향 감각을 잃지 않게
    un = _un_neun(target)
    if objects:
        scene = build_sentence(objects[:1], [], camera_orientation)
        return f"{target}{un} 보이지 않아요. 카메라를 천천히 돌려보세요. {scene}"

    return f"{target}{un} 보이지 않아요. 카메라를 천천히 돌려보세요."


def build_navigation_sentence(
    label: str,
    action: str,
    locations: list[dict] | None = None,
    wifi_ssid: str = "",
) -> str:
    """
    개인 네비게이팅 모드의 안내 문장.

    action 종류:
      "save"       → "편의점을 저장했어요."
      "found_here" → "편의점이 저장된 위치예요! 도착했어요."
      "not_found"  → "편의점은 저장된 장소에 없어요."
      "deleted"    → "편의점을 삭제했어요."
      "list"       → "저장된 장소는 편의점, 화장실이에요."

    locations: DB에서 조회한 장소 목록 (list 액션에서만 사용)
    최대 5개만 읽어줌 — TTS가 너무 길어지는 것 방지
    """
    if action == "save":
        label_str = label or "이 장소"
        return f"{label_str}{_eul_reul(label_str)} 저장했어요."
    if action == "found_here":
        return f"{label}{_i_ga(label)} 저장된 위치예요! 도착했어요."
    if action == "not_found":
        return f"{label}{_un_neun(label)} 저장된 장소에 없어요. 먼저 그 곳에서 저장해 주세요."
    if action == "deleted":
        return f"{label}{_eul_reul(label)} 삭제했어요."
    if action == "list":
        if not locations:
            return "저장된 장소가 없어요. 가고 싶은 곳에서 '여기 저장해줘'라고 말해보세요."
        names  = [loc["label"] for loc in locations[:5]]  # 최대 5개
        joined = ", ".join(names)
        # 5개 초과이면 "외 N곳" 추가
        suffix = f" 외 {len(locations) - 5}곳" if len(locations) > 5 else ""
        return f"저장된 장소는 {joined}{suffix}이에요."
    return "안내를 처리하지 못했어요."
