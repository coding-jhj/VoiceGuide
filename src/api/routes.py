from datetime import datetime

from fastapi import APIRouter, UploadFile, Form
from src.depth.depth import detect_and_depth
from src.nlg.sentence import (
    build_sentence, build_hazard_sentence, build_find_sentence,
    build_navigation_sentence, get_alert_mode,  # [추가] 경고 피로 방지를 위한 알림 모드 분류 함수
    _i_ga, _un_neun,
)
from src.api import db
from src.api.tracker import get_tracker
from src.voice.stt import extract_label

router = APIRouter()


def _space_changes(current: list[dict], previous: list[dict]) -> list[str]:
    prev_set = {o["class_ko"] for o in previous}
    curr_set = {o["class_ko"] for o in current}
    changes = []
    for name in curr_set - prev_set:
        changes.append(f"{name}{_i_ga(name)} 생겼어요")
    for name in prev_set - curr_set:
        changes.append(f"{name}{_i_ga(name)} 없어졌어요")
    return changes


@router.post("/detect")
async def detect(
    image:              UploadFile,
    wifi_ssid:          str = Form(""),
    camera_orientation: str = Form("front"),
    mode:               str = Form("장애물"),
    query_text:         str = Form(""),   # STT 원문 (찾기/저장 모드에서 타깃/라벨 추출)
):
    # ── 개인 네비게이팅: 저장 모드 ────────────────────────────────────────────
    if mode == "저장":
        label = extract_label(query_text) or f"위치_{datetime.now().strftime('%H%M')}"
        if not wifi_ssid:
            return {
                "sentence":     "WiFi에 연결되어 있지 않아 저장할 수 없어요.",
                "objects": [], "hazards": [], "changes": [], "depth_source": "none",
            }
        db.save_location(label, wifi_ssid)
        return {
            "sentence":     build_navigation_sentence(label, "save"),
            "objects": [], "hazards": [], "changes": [], "depth_source": "none",
        }

    # ── 개인 네비게이팅: 저장 목록 모드 ──────────────────────────────────────
    if mode == "위치목록":
        locations = db.get_locations(wifi_ssid)
        return {
            "sentence":    build_navigation_sentence("", "list", locations=locations),
            "locations":   locations,
            "objects": [], "hazards": [], "changes": [], "depth_source": "none",
        }

    # ── 이미지 분석 공통 흐름 ─────────────────────────────────────────────────
    image_bytes = await image.read()
    objects, hazards, scene = detect_and_depth(image_bytes)

    tracker = get_tracker(wifi_ssid or "__default__")
    objects, motion_changes = tracker.update(objects)

    previous = db.get_snapshot(wifi_ssid)
    space_changes = _space_changes(objects, previous) if previous else []
    db.save_snapshot(wifi_ssid, objects)

    all_changes = motion_changes + space_changes

    # ── 찾기 모드: 특정 물체를 타깃으로 탐색 ─────────────────────────────────
    if mode == "찾기":
        # query_text에서 찾을 물체 이름 추출
        target = _extract_find_target(query_text)
        sentence = build_find_sentence(target, objects, camera_orientation)
        return {
            "sentence":    sentence,
            # [추가] 찾기 모드는 사용자가 명시적으로 요청한 것이므로 항상 즉각 음성 안내
            "alert_mode":  "critical",
            "objects":     objects,
            "hazards":     hazards,
            "changes":     all_changes,
            "depth_source": objects[0].get("depth_source", "bbox") if objects else "bbox",
        }

    # ── 장애물 / 확인 모드 ───────────────────────────────────────────────────
    if hazards:
        top_hazard = max(hazards, key=lambda h: h.get("risk", 0))
        sentence   = build_hazard_sentence(top_hazard, objects, all_changes, camera_orientation)
        # [추가] hazard(계단·낙차 등)는 낙상 위험이 있으므로 항상 즉각 음성 경고로 고정.
        # objects[0]이 있더라도 is_hazard=True를 전달해 거리와 무관하게 critical 반환을 보장한다.
        alert_mode = get_alert_mode(objects[0], is_hazard=True) if objects else "critical"
    else:
        sentence   = build_sentence(objects, all_changes, camera_orientation=camera_orientation)
        # [추가] risk_score 1위 객체(objects[0])를 기준으로 알림 모드를 결정한다.
        # "silent"이면 프론트엔드는 TTS를 호출하지 않고, "beep"이면 비프음만 재생한다.
        alert_mode = get_alert_mode(objects[0]) if objects else "silent"

    # 안전 경로·군중·위험 물체 경고를 문장 뒤에 추가 (있을 때만)
    extras = [v for v in [
        scene.get("danger_warning"),
        scene.get("crowd_warning"),
        scene.get("safe_direction"),
    ] if v]
    if extras:
        sentence = sentence + " " + " ".join(extras)

    return {
        "sentence":      sentence,
        "alert_mode":    alert_mode,  # [추가] "critical" | "beep" | "silent" — 프론트엔드 TTS/비프 분기용
        "objects":       objects,
        "hazards":       hazards,
        "changes":       all_changes,
        "scene":         scene,
        "depth_source":  objects[0].get("depth_source", "bbox") if objects else "bbox",
    }


def _extract_find_target(text: str) -> str:
    """
    "의자 찾아줘" → "의자" 처럼 찾기 명령에서 대상 물체 추출.
    명령 동사를 제거하고 남은 명사를 반환.
    """
    verbs = ["찾아줘", "찾아", "어디있어", "어디 있어", "어디야",
             "어딘지", "어디에 있어", "어디에 있나", "있는지 알려줘"]
    label = text
    for v in verbs:
        label = label.replace(v, "")
    return label.strip()


# ── 장소 저장/조회 전용 엔드포인트 (Android 직접 호출용) ──────────────────────

@router.post("/locations/save")
async def save_location_endpoint(
    wifi_ssid: str = Form(""),
    label:     str = Form(""),
):
    if not label:
        return {"success": False, "sentence": "장소 이름을 말씀해 주세요."}
    if not wifi_ssid:
        return {"success": False, "sentence": "WiFi에 연결되어 있지 않아 저장할 수 없어요."}
    db.save_location(label, wifi_ssid)
    return {"success": True, "sentence": build_navigation_sentence(label, "save")}


@router.get("/locations")
async def list_locations(wifi_ssid: str = ""):
    locations = db.get_locations(wifi_ssid)
    return {
        "locations": locations,
        "sentence":  build_navigation_sentence("", "list", locations=locations),
    }


@router.get("/locations/find/{label}")
async def find_location_endpoint(label: str, wifi_ssid: str = ""):
    loc = db.find_location(label)
    if not loc:
        return {
            "found":    False,
            "sentence": build_navigation_sentence(label, "not_found"),
        }
    nearby = (wifi_ssid == loc["wifi_ssid"]) if wifi_ssid else False
    action = "found_here" if nearby else "list"
    return {
        "found":    True,
        "nearby":   nearby,
        "location": loc,
        "sentence": build_navigation_sentence(loc["label"], "found_here") if nearby
                    else f"{loc['label']}{_un_neun(loc['label'])} 다른 WiFi 위치에 저장되어 있어요.",
    }


@router.delete("/locations/{label}")
async def delete_location_endpoint(label: str):
    loc = db.find_location(label)
    if not loc:
        return {"success": False, "sentence": f"{label}은 저장되어 있지 않아요."}
    db.delete_location(loc["label"])
    return {"success": True, "sentence": build_navigation_sentence(loc["label"], "deleted")}


# ── 공간 스냅샷 수동 저장 ─────────────────────────────────────────────────────

@router.post("/spaces/snapshot")
async def save_space_snapshot(body: dict):
    space_id = body.get("space_id", "")
    objects  = body.get("objects", [])
    db.save_snapshot(space_id, objects)
    return {"saved": True}


# ── STT (Gradio 데모용 PC 마이크) ─────────────────────────────────────────────

@router.post("/stt")
async def stt_listen():
    try:
        from src.voice.stt import listen_and_classify
        text, mode = listen_and_classify()
        return {"text": text, "mode": mode, "success": bool(text)}
    except Exception as e:
        return {"text": "", "mode": "unknown", "success": False, "error": str(e)}
