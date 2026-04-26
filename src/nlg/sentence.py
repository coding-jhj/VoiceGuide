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


def _un_neun(word: str) -> str:
    return _josa(word, "은", "는")


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

    if is_ground and dist_m < 2.0:
        if dist_m < 0.8:
            return f"조심! 바로 앞 바닥에 {name}{ig} 있어요. {action}."
        return f"조심! {direction} 바닥에 {name}{ig} 있어요. {action}."

    if dist_m < 0.5:
        return f"위험! {direction} {name}!"

    if dist_m < 1.0:
        return f"{direction}에 {name}{ig} 있어요. {dist_str}. {action}."

    if dist_m < 2.5:
        return (f"{direction}에 {name}{ig} 있어요. {dist_str}. {action}."
                if action else
                f"{direction}에 {name}{ig} 있어요. {dist_str}.")

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
    """계단·낙차·턱 등 바닥 위험을 최우선 안내."""
    h_msg  = hazard.get("message", "앞에 위험이 있어요.")
    h_risk = hazard.get("risk", 0.5)

    if h_risk >= 0.7 or not objects:
        return h_msg

    obj_sentence = build_sentence(objects[:1], [], camera_orientation)
    return f"{h_msg} 그리고 {obj_sentence}"


def build_find_sentence(
    target: str,
    objects: list[dict],
    camera_orientation: str = "front",
) -> str:
    """
    찾기 모드: 특정 물체를 찾는 맥락에서 안내.
    target이 비어있으면 일반 장애물 안내로 fallback.
    """
    if not target:
        return build_sentence(objects, [], camera_orientation)

    found = [o for o in objects if target in o.get("class_ko", "")]
    if found:
        obj = found[0]
        abs_clock = get_absolute_clock(obj["direction"], camera_orientation)
        direction = CLOCK_TO_DIRECTION.get(abs_clock, abs_clock)
        dist_str  = _format_dist(obj.get("distance_m", 0.0))
        un        = _un_neun(target)
        return f"{target}{un} {direction}에 있어요. {dist_str}."

    if objects:
        scene = build_sentence(objects[:1], [], camera_orientation)
        un = _un_neun(target)
        return f"{target}{un} 보이지 않아요. 카메라를 천천히 돌려보세요. {scene}"

    un = _un_neun(target)
    return f"{target}{un} 보이지 않아요. 카메라를 천천히 돌려보세요."


def build_navigation_sentence(
    label: str,
    action: str,           # "save" | "found_here" | "not_found" | "list"
    locations: list[dict] | None = None,
    wifi_ssid: str = "",
) -> str:
    """
    개인 네비게이팅 모드 안내 문장.

    action:
      "save"       - 장소 저장 완료
      "found_here" - 현재 위치가 저장된 장소와 일치
      "not_found"  - 해당 장소 미저장
      "list"       - 저장된 장소 목록 안내
      "deleted"    - 장소 삭제 완료
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
        names = [loc["label"] for loc in locations[:5]]
        joined = ", ".join(names)
        total  = len(locations)
        suffix = f" 외 {total - 5}곳" if total > 5 else ""
        return f"저장된 장소는 {joined}{suffix}이에요."

    return "안내를 처리하지 못했어요."
