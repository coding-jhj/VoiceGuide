from src.nlg.templates import (
    CLOCK_ACTION, CLOCK_TO_DIRECTION, get_absolute_clock
)


def _josa(word: str, 받침있음: str, 받침없음: str) -> str:
    if not word:
        return 받침있음
    last = word[-1]
    if '가' <= last <= '힣':
        return 받침있음 if (ord(last) - 0xAC00) % 28 != 0 else 받침없음
    return 받침있음


def _i_ga(word: str) -> str:
    return _josa(word, "이", "가")


def _eul_reul(word: str) -> str:
    return _josa(word, "을", "를")


def _format_dist(dist_m: float) -> str:
    dist_m = max(0.1, min(dist_m, 10.0))
    if dist_m < 0.5:
        return "바로 코앞"
    if dist_m < 1.0:
        cm = round(dist_m * 100 / 10) * 10
        return f"약 {cm:.0f}cm"
    return f"약 {dist_m:.1f}m"


def _primary(obj: dict, abs_clock: str) -> str:
    dist_m    = obj.get("distance_m", 0.0)
    name      = obj["class_ko"]
    ig        = _i_ga(name)
    direction = CLOCK_TO_DIRECTION.get(abs_clock, abs_clock)
    dist_str  = _format_dist(dist_m)
    action    = CLOCK_ACTION.get(abs_clock, "조심하세요").rstrip(".")
    is_ground = obj.get("is_ground_level", False)

    # 바닥 장애물 (발에 걸릴 위험)
    if is_ground and dist_m < 2.0:
        if dist_m < 0.8:
            return f"조심! 발 아래 {name}. {action}."
        return f"조심! {direction} 바닥에 {name}{ig} 있어요. {action}."

    # 거리별 긴급도 — 짧을수록 더 짧고 강한 문장
    if dist_m < 0.5:
        # 초근접: 가장 짧고 강한 경고 (TTS 재생 시간 최소화)
        return f"위험! {direction} {name}!"

    if dist_m < 1.0:
        # 긴급: 행동 먼저
        return f"{action}! {direction}에 {name}{ig} 있어요. {dist_str}."

    if dist_m < 2.5:
        # 경고: 방향 + 거리 + 행동
        return (f"{direction}에 {name}{ig} 있어요. {dist_str}. {action}."
                if action else
                f"{direction}에 {name}{ig} 있어요. {dist_str}.")

    # 정보: 방향 + 거리
    return f"{direction}에 {name}{ig} 있어요. {dist_str}."


def _secondary(obj: dict, abs_clock: str) -> str:
    dist_m    = obj.get("distance_m", 0.0)
    name      = obj["class_ko"]
    direction = CLOCK_TO_DIRECTION.get(abs_clock, abs_clock)
    dist_str  = _format_dist(dist_m)
    action    = CLOCK_ACTION.get(abs_clock, "").rstrip(".")

    if dist_m < 1.5 and action:
        return f"{direction}에 {name}도 있어요. {dist_str}. {action}."
    return f"{direction}에 {name}도 있어요. {dist_str}."


def build_sentence(
    objects: list[dict],
    changes: list[str],
    camera_orientation: str = "front",
) -> str:
    if not objects:
        if changes:
            return changes[0]
        return "주변에 장애물이 없어요."

    parts = []
    for i, obj in enumerate(objects[:2]):
        abs_clock = get_absolute_clock(obj["direction"], camera_orientation)
        if i == 0:
            parts.append(_primary(obj, abs_clock))
        else:
            parts.append(_secondary(obj, abs_clock))

    result = " ".join(parts)
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
    계단·낙차·턱 등 바닥 위험을 최우선 안내.
    위험도가 높으면 장애물 정보 생략, 낮으면 뒤에 이어서 안내.
    """
    h_msg  = hazard.get("message", "앞에 위험이 있어요.")
    h_risk = hazard.get("risk", 0.5)

    if h_risk >= 0.7 or not objects:
        # 고위험: 계단 경고만 출력 (짧고 강하게)
        return h_msg

    # 중간 위험: 계단 경고 + 주요 장애물 1개 이어서 안내
    obj_sentence = build_sentence(objects[:1], [], camera_orientation)
    return f"{h_msg} 또한, {obj_sentence}"
