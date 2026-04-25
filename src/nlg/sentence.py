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


def _format_dist(dist_m: float) -> str:
    if dist_m < 1.0:
        cm = max(10, round(dist_m * 100 / 10) * 10)
        return f"약 {cm:.0f}센티미터"
    return f"약 {min(dist_m, 10.0):.1f}미터"


def _primary(obj: dict, abs_clock: str) -> str:
    dist_m     = obj.get("distance_m", 0.0)
    name       = obj["class_ko"]
    ig         = _i_ga(name)
    direction  = CLOCK_TO_DIRECTION.get(abs_clock, abs_clock)
    dist_str   = _format_dist(dist_m)
    action     = CLOCK_ACTION.get(abs_clock, "").rstrip(".")
    is_ground  = obj.get("is_ground_level", False)

    # 바닥 장애물 (발에 걸릴 위험): 방향보다 "발 아래" 강조
    if is_ground and dist_m < 1.5:
        loc = "발 아래" if dist_m < 0.8 else direction
        act = action if action else "조심하세요"
        return f"조심! {loc}에 {name}{ig} 있어요. {act}."

    # 거리 기반 긴급도 (area_ratio 라벨 대신 distance_m 직접 사용)
    if dist_m < 1.0:
        return f"{action}! {direction}에 {name}{ig} 있어요. {dist_str} 거리예요."
    elif dist_m < 2.5:
        return f"{direction}에 {name}{ig} 있어요. {dist_str} 거리예요. {action}." if action else \
               f"{direction}에 {name}{ig} 있어요. {dist_str} 거리예요."
    else:
        return f"{direction}에 {name}{ig} 있어요. {dist_str}예요."


def _secondary(obj: dict, abs_clock: str) -> str:
    dist_m    = obj.get("distance_m", 0.0)
    name      = obj["class_ko"]
    direction = CLOCK_TO_DIRECTION.get(abs_clock, abs_clock)
    dist_str  = _format_dist(dist_m)
    action    = CLOCK_ACTION.get(abs_clock, "").rstrip(".")

    # 두 번째 장애물도 가까우면 회피 행동 포함
    if dist_m < 1.5 and action:
        return f"{direction}에 {name}도 있어요. {dist_str}예요. {action}."
    return f"{direction}에 {name}도 있어요. {dist_str}예요."


def build_sentence(
    objects: list[dict],
    changes: list[str],
    camera_orientation: str = "front",
) -> str:
    if not objects:
        return "주변에 장애물이 없어요."

    parts = []
    for i, obj in enumerate(objects[:2]):
        abs_clock = get_absolute_clock(obj["direction"], camera_orientation)
        if i == 0:
            parts.append(_primary(obj, abs_clock))
        else:
            parts.append(_secondary(obj, abs_clock))

    result = " ".join(parts)
    change_text = " ".join(changes[:1]) if changes else ""
    return f"{result} {change_text}".strip()
