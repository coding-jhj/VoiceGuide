from src.nlg.templates import (
    CLOCK_ACTION, CLOCK_TO_DIRECTION, get_absolute_clock
)

# 차량 — 5m 이내부터 긴급, 이동하는 물체이므로 별도 처리
_VEHICLE_KO = {"자동차", "오토바이", "버스", "트럭", "기차", "자전거"}
# 동물 — 돌발 행동 위험
_ANIMAL_KO  = {"개", "말", "고양이"} # 주변에 고양이가 많이 보이는데 빠져있어서 추가


# [추가] 경고 피로(alert fatigue) 방지를 위한 알림 모드 분류 함수.
# 기존에는 모든 탐지 객체를 항상 TTS로 읽어줬기 때문에 사용자가 경고에 둔감해지는 문제가 있었다.
# 객체 종류와 거리 기준으로 critical / beep / silent 3단계로 분기해 불필요한 음성 안내를 줄인다.
def get_alert_mode(obj: dict, is_hazard: bool = False) -> str:
    """탐지 객체 하나의 알림 모드를 반환한다.

    Returns:
        "critical" — 즉각 TTS 음성 경고
        "beep"     — 비프음만, 음성 없음
        "silent"   — 무음 (사용자가 명시적으로 물어볼 때만 안내)
    """
    dist_m     = obj.get("distance_m", 99.0)
    is_vehicle = obj.get("is_vehicle", False)
    is_animal  = obj.get("is_animal",  False)

    # 계단·낙차 등 hazard는 항상 즉각 음성 — 낙상 위험이 크므로 거리와 무관하게 경고
    if is_hazard:
        return "critical"

    # 차량은 8m 이내부터 즉각 경고 — 이동 속도가 빠르므로 넉넉한 여유 거리가 필요
    if is_vehicle and dist_m < 8.0:
        return "critical"

    # 동물은 3m 이내 즉각 경고 — 돌발 행동으로 충돌 위험이 있음
    if is_animal and dist_m < 3.0:
        return "critical"

    # 0.5m 미만 코앞 장애물은 충돌 직전이므로 즉각 경고
    if dist_m < 0.5:
        return "critical"

    # 1m 이내 일반 장애물 — 위험하지만 즉각 음성 대신 비프음으로 경고 피로를 줄임
    if dist_m < 1.0:
        return "beep"

    # 그 외(1m 이상, 군중 등) — 무음 처리, 사용자가 명시적으로 요청할 때만 안내
    return "silent"


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
    dist_m = max(0.1, min(dist_m, 15.0))
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
    is_vehicle = obj.get("is_vehicle", name in _VEHICLE_KO)
    is_animal  = obj.get("is_animal",  name in _ANIMAL_KO)

    # ── 차량 (야외 이동 위협) ───────────────────────────────────────────
    if is_vehicle:
        if dist_m < 3.0:
            return f"위험! {direction}에 {name}{ig} 있어요! {dist_str}. 잠깐 {action}!"
        if dist_m < 8.0:
            return f"조심! {direction}에 {name}{ig} 접근 중이에요. {dist_str}. {action}."
        return f"{direction}에 {name}{ig} 있어요. {dist_str}."

    # ── 동물 (돌발 행동 위험) ───────────────────────────────────────────
    if is_animal:
        if dist_m < 3.0:
            return f"조심! {direction}에 {name}{ig} 있어요. {dist_str}. 천천히 {action}."
        return f"{direction}에 {name}{ig} 있어요. {dist_str}."

    # ── 바닥 장애물 (걸려 넘어짐) ─────────────────────────────────────
    if is_ground and dist_m < 2.0:
        if dist_m < 0.8:
            return f"조심! 바로 앞 바닥에 {name}{ig} 있어요. {action}."
        return f"조심! {direction} 바닥에 {name}{ig} 있어요. {action}."

    # ── 일반 장애물 거리별 긴박도 ─────────────────────────────────────
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
    is_vehicle = obj.get("is_vehicle", name in _VEHICLE_KO)

    # 위험순위가 2순위인 물체가 있어서 판별했을 시 action까지 넣으면
    # 문장도 길어지고 과다하게 정보가 들어가서 action은 빼고 거리와 물체만
    # 설명하게 변경했어요.
    if is_vehicle and dist_m < 8.0:
        return f"{direction}으로 {dist_str}에 {name}도 있어요!"
    if dist_m < 1.5 and action:
        return f"{direction}으로 {dist_str}에 {name}도 있어요."
    return f"{direction}으로 {dist_str}에 {name}도 있어요."


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
    """계단·낙차·턱 등 바닥 위험 최우선 안내."""
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
    """찾기 모드: 특정 물체를 찾는 맥락에서 안내."""
    if not target:
        return build_sentence(objects, [], camera_orientation)

    found = [o for o in objects if target in o.get("class_ko", "")]
    if found:
        obj = found[0]
        abs_clock = get_absolute_clock(obj["direction"], camera_orientation)
        direction = CLOCK_TO_DIRECTION.get(abs_clock, abs_clock)
        dist_str  = _format_dist(obj.get("distance_m", 0.0))
        un        = _un_neun(target)
        # 문장을 좀더 자연스럽게 나오도록 문맥 변경했어요.
        return f"{target}{un} {direction} {dist_str} 거리에 있어요."

    if objects:
        scene = build_sentence(objects[:1], [], camera_orientation)
        un = _un_neun(target)
        return f"{target}{un} 보이지 않아요. 카메라를 천천히 돌려보세요. {scene}"

    un = _un_neun(target)
    return f"{target}{un} 보이지 않아요. 카메라를 천천히 돌려보세요."


def build_navigation_sentence(
    label: str,
    action: str,
    locations: list[dict] | None = None,
    wifi_ssid: str = "",
) -> str:
    """개인 네비게이팅 모드 안내."""
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
        names  = [loc["label"] for loc in locations[:5]]
        joined = ", ".join(names)
        suffix = f" 외 {len(locations) - 5}곳" if len(locations) > 5 else ""
        return f"저장된 장소는 {joined}{suffix}이에요."
    return "안내를 처리하지 못했어요."
