from fastapi import APIRouter, UploadFile, Form
from src.depth.depth import detect_and_depth
from src.nlg.sentence import build_sentence
from src.api import db

router = APIRouter()


def detect_space_change(current: list[dict], previous: list[dict]) -> list[str]:
    changes = []
    prev_classes = [o["class_ko"] for o in previous]
    curr_classes = [o["class_ko"] for o in current]

    for cls in curr_classes:
        if cls not in prev_classes:
            changes.append(f"{cls}이 1개 더 있어요")

    return changes


@router.post("/detect")
async def detect(
    image: UploadFile,
    wifi_ssid: str = Form(""),
    camera_orientation: str = Form("front"),
):
    image_bytes = await image.read()

    objects = detect_and_depth(image_bytes)

    previous = db.get_snapshot(wifi_ssid)
    changes = detect_space_change(objects, previous) if previous else []

    db.save_snapshot(wifi_ssid, objects)

    sentence = build_sentence(objects, changes, camera_orientation=camera_orientation)

    return {"sentence": sentence, "objects": objects, "changes": changes}


@router.post("/spaces/snapshot")
async def save_space_snapshot(body: dict):
    space_id = body.get("space_id", "")
    objects = body.get("objects", [])
    db.save_snapshot(space_id, objects)
    return {"saved": True}
