from fastapi import APIRouter, UploadFile, Form
from src.depth.depth import detect_and_depth
from src.nlg.sentence import build_sentence, _i_ga
from src.api import db
from src.api.tracker import get_tracker

router = APIRouter()


def _space_changes(current: list[dict], previous: list[dict]) -> list[str]:
    """공간 스냅샷 비교: 새로 등장한 물체 안내."""
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
    image: UploadFile,
    wifi_ssid:          str = Form(""),
    camera_orientation: str = Form("front"),
):
    image_bytes = await image.read()

    # 1. YOLO + Depth 탐지
    objects = detect_and_depth(image_bytes)

    # 2. 프레임 간 추적 (jitter 제거 + 접근/소멸 감지)
    tracker = get_tracker(wifi_ssid or "__default__")
    objects, motion_changes = tracker.update(objects)

    # 3. 공간 기억 비교 (방 재방문 시 변화)
    previous = db.get_snapshot(wifi_ssid)
    space_changes = _space_changes(objects, previous) if previous else []
    db.save_snapshot(wifi_ssid, objects)

    # 이동 중 감지된 변화를 우선, 공간 변화는 보조
    all_changes = motion_changes + space_changes

    # 4. 문장 생성
    sentence = build_sentence(objects, all_changes, camera_orientation=camera_orientation)

    return {
        "sentence":    sentence,
        "objects":     objects,
        "changes":     all_changes,
        "depth_source": objects[0].get("depth_source", "bbox") if objects else "bbox",
    }


@router.post("/spaces/snapshot")
async def save_space_snapshot(body: dict):
    space_id = body.get("space_id", "")
    objects  = body.get("objects", [])
    db.save_snapshot(space_id, objects)
    return {"saved": True}


@router.post("/stt")
async def stt_listen():
    """PC 마이크로 음성 인식 후 모드 분류 (Gradio 데모용)."""
    try:
        from src.voice.stt import listen_and_classify
        text, mode = listen_and_classify()
        return {"text": text, "mode": mode, "success": bool(text)}
    except Exception as e:
        return {"text": "", "mode": "unknown", "success": False, "error": str(e)}
