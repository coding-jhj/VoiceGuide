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
    return f"약 {dist_m:.1f}미터"


def _primary(obj: dict, abs_clock: str) -> str:
    distance  = obj["distance"]
    dist_m    = obj.get("distance_m", 0.0)
    name      = obj["class_ko"]
    ig        = _i_ga(name)
    direction = CLOCK_TO_DIRECTION.get(abs_clock, abs_clock)
    dist_str  = _format_dist(dist_m)
    action    = CLOCK_ACTION.get(abs_clock, "").rstrip(".")

    if distance == "매우 가까이":
        return f"{action}! {direction}에 {name}{ig} 있어요. {dist_str} 거리예요."
    elif distance == "가까이":
        return f"{direction}에 {name}{ig} 있어요. {dist_str} 거리예요. {action}." if action else \
               f"{direction}에 {name}{ig} 있어요. {dist_str} 거리예요."
    else:
        return f"{direction}에 {name}{ig} 있어요. {dist_str}예요."


def _secondary(obj: dict, abs_clock: str) -> str:
    dist_m    = obj.get("distance_m", 0.0)
    name      = obj["class_ko"]
    direction = CLOCK_TO_DIRECTION.get(abs_clock, abs_clock)
    dist_str  = _format_dist(dist_m)
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
