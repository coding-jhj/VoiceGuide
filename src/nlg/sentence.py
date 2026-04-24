from src.nlg.templates import (
    CLOCK_ACTION, DISTANCE_KO, get_absolute_clock
)

_ACTION_DISTANCES = {"매우 가까이", "가까이"}
_URGENCY_MARK     = {"매우 가까이": "!", "가까이": "."}


def _primary(obj: dict, abs_clock: str) -> str:
    """위험도 1순위 문장 — 긴박도에 따라 구조가 달라짐

    매우 가까이 → 행동 먼저, 세부 정보 나중
        "멈추세요! 의자가 12시 방향 약 0.6m에 있어요."
    가까이      → 위치 먼저, 행동 나중
        "의자가 10시 방향 약 1.2m에 있어요. 오른쪽으로 비켜보세요."
    보통 이하   → 정보만
        "의자가 10시 방향 약 2.5m에 있어요."
    """
    distance = obj["distance"]
    dist_m   = obj.get("distance_m", 0.0)
    name     = obj["class_ko"]
    action   = CLOCK_ACTION.get(abs_clock, "")

    if distance == "매우 가까이":
        return f"{action} {name}가 {abs_clock} 방향 약 {dist_m:.1f}m에 있어요."
    elif distance == "가까이":
        return f"{name}가 {abs_clock} 방향 약 {dist_m:.1f}m에 있어요. {action}".strip()
    else:
        dist_ko = DISTANCE_KO.get(distance, distance)
        return f"{name}가 {abs_clock} 방향 약 {dist_m:.1f}m {dist_ko}에 있어요."


def _secondary(obj: dict, abs_clock: str) -> str:
    """위험도 2순위: 방향·수치만 짧게"""
    dist_m = obj.get("distance_m", 0.0)
    return f"{obj['class_ko']}도 {abs_clock} 방향 약 {dist_m:.1f}m에 있어요."


def build_sentence(
    objects: list[dict],
    changes: list[str],
    camera_orientation: str = "front",
) -> str:
    """
    objects는 detect_and_depth()가 risk_score 내림차순으로 전달
    → 가장 위험한 것부터 안내
    """
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
