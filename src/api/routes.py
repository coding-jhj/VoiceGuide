"""
VoiceGuide FastAPI 라우터
===========================
Android 앱과 Gradio 데모가 호출하는 API 엔드포인트를 정의합니다.

주요 엔드포인트:
  POST /detect           — 이미지 분석 (장애물/찾기/확인/저장/위치목록 5가지 모드)
  POST /locations/save   — 장소 저장
  GET  /locations        — 저장 장소 목록
  GET  /locations/find/{label} — 장소 검색
  DELETE /locations/{label}   — 장소 삭제
  POST /stt              — PC 마이크 음성 인식 (Gradio 데모용)

설계 원칙:
  - 모든 엔드포인트는 반드시 sentence 필드를 반환 → TTS로 바로 읽을 수 있음
  - 오류가 나도 음성 안내가 나오도록 전역 예외 핸들러 적용 (main.py)
  - 이미지가 필요 없는 모드(저장/위치목록)는 빠르게 처리하고 반환
"""

from datetime import datetime

from fastapi import APIRouter, UploadFile, Form
from src.depth.depth import detect_and_depth
from src.nlg.sentence import (
    build_sentence, build_hazard_sentence, build_find_sentence,
    build_navigation_sentence, _i_ga, _un_neun,
)
from src.api import db
from src.api.tracker import get_tracker
from src.voice.stt import extract_label

router = APIRouter()


def _space_changes(current: list[dict], previous: list[dict]) -> list[str]:
    """
    이번 프레임과 이전 스냅샷을 비교해서 달라진 물체를 찾는 함수.

    새로 생긴 물체: curr에 있고 prev에 없는 것 → "의자가 생겼어요"
    사라진 물체:   prev에 있고 curr에 없는 것 → "사람이 없어졌어요"

    공간 기억 기능의 핵심: 재방문 시 매번 같은 설명을 반복하지 않기 위함.
    WiFi SSID가 공간 ID 역할 → 같은 공간에 다시 왔을 때만 비교 가능.
    """
    prev_set = {o["class_ko"] for o in previous}  # 이전 방문 물체 집합
    curr_set = {o["class_ko"] for o in current}   # 현재 물체 집합

    changes = []
    for name in curr_set - prev_set:  # 새로 생긴 것
        changes.append(f"{name}{_i_ga(name)} 생겼어요")
    for name in prev_set - curr_set:  # 사라진 것
        changes.append(f"{name}{_i_ga(name)} 없어졌어요")
    return changes


@router.post("/detect")
async def detect(
    image:              UploadFile,
    wifi_ssid:          str = Form(""),        # 공간 기억 + 장소 저장에 사용
    camera_orientation: str = Form("front"),   # 방향 보정: front/back/left/right
    mode:               str = Form("장애물"),  # STT가 결정한 모드
    query_text:         str = Form(""),        # STT 원문 (찾기/저장 모드에서 추출에 사용)
):
    """
    VoiceGuide 메인 분석 API.

    mode에 따라 처리 경로가 달라집니다:
      "저장"     → 이미지 불필요, 즉시 장소 저장 후 반환
      "위치목록" → 이미지 불필요, DB에서 장소 목록 반환
      나머지     → 이미지 분석 (YOLO + Depth V2 + 문장 생성)
    """

    # ── 저장 모드: 이미지 없이 즉시 처리 ────────────────────────────────────
    # "여기 저장해줘 편의점" → query_text에서 "편의점" 추출 → DB 저장
    if mode == "저장":
        label = extract_label(query_text) or f"위치_{datetime.now().strftime('%H%M')}"
        if not wifi_ssid:
            # WiFi 없으면 공간 ID를 알 수 없어 저장 불가
            return {
                "sentence":     "WiFi에 연결되어 있지 않아 저장할 수 없어요.",
                "objects": [], "hazards": [], "changes": [], "depth_source": "none",
            }
        db.save_location(label, wifi_ssid)
        return {
            "sentence":     build_navigation_sentence(label, "save"),
            "objects": [], "hazards": [], "changes": [], "depth_source": "none",
        }

    # ── 위치목록 모드: DB 조회 후 즉시 반환 ──────────────────────────────────
    if mode == "위치목록":
        locations = db.get_locations(wifi_ssid)  # wifi_ssid 있으면 해당 위치 장소만
        return {
            "sentence":    build_navigation_sentence("", "list", locations=locations),
            "locations":   locations,
            "objects": [], "hazards": [], "changes": [], "depth_source": "none",
        }

    # ── 이미지 분석 공통 흐름 (장애물/찾기/확인 모드) ────────────────────────
    image_bytes = await image.read()  # multipart form에서 이미지 바이트 추출

    # YOLO 탐지 + Depth V2 거리 추정 + 바닥 위험 감지
    # 내부적으로 이미지당 깊이 맵 1회만 추론해서 효율적으로 처리
    objects, hazards, scene = detect_and_depth(image_bytes)

    # EMA 추적기: 프레임 간 거리 흔들림 제거 + 접근 감지
    # wifi_ssid가 없으면 "__default__" 세션으로 처리
    tracker = get_tracker(wifi_ssid or "__default__")
    objects, motion_changes = tracker.update(objects)

    # 공간 기억: 이전 방문과 비교해서 달라진 것 감지
    previous = db.get_snapshot(wifi_ssid)
    space_changes = _space_changes(objects, previous) if previous else []
    db.save_snapshot(wifi_ssid, objects)  # 현재 상태를 다음 방문을 위해 저장

    all_changes = motion_changes + space_changes

    # ── 찾기 모드: 특정 물체를 타깃으로 탐색 ────────────────────────────────
    if mode == "찾기":
        target = _extract_find_target(query_text)  # "의자 찾아줘" → "의자"
        sentence = build_find_sentence(target, objects, camera_orientation)
        return {
            "sentence":    sentence,
            "objects":     objects,
            "hazards":     hazards,
            "changes":     all_changes,
            "depth_source": objects[0].get("depth_source", "bbox") if objects else "bbox",
        }

    # ── 장애물/확인 모드: 위험도 기반 문장 생성 ──────────────────────────────
    if hazards:
        # 계단·낙차·턱이 감지되면 최우선 안내 (YOLO 결과보다 우선)
        top_hazard = max(hazards, key=lambda h: h.get("risk", 0))
        sentence = build_hazard_sentence(top_hazard, objects, all_changes, camera_orientation)
    else:
        sentence = build_sentence(objects, all_changes, camera_orientation=camera_orientation)

    # 부가 경고 추가: 위험 물체·점자블록·군중·신호등·안전경로
    # 메인 문장 뒤에 붙임 (있을 때만)
    extras = [v for v in [
        scene.get("danger_warning"),        # 칼·가위 3m 이내 즉시 경고
        scene.get("tactile_block_warning"), # 점자 블록 위 장애물
        scene.get("crowd_warning"),         # 군중 밀집 경고
        scene.get("safe_direction"),        # 안전 경로 제안
        scene.get("traffic_light_msg"),     # 신호등 빨강/초록
    ] if v]
    if extras:
        sentence = sentence + " " + " ".join(extras)

    # alert_level: Android에서 음성(danger/warning) vs 비프음(info) 결정에 사용
    alert_level = objects[0].get("alert_level", "info") if objects else "info"
    # beep: True이면 Android가 TTS 대신 짧은 비프음만 냄
    # 조건: 위험도 낮은 물체만 있고, 계단·경고·신호등 등 추가 정보 없을 때
    beep = (alert_level == "info" and not hazards and not extras)

    return {
        "sentence":      sentence,
        "objects":       objects,
        "hazards":       hazards,
        "changes":       all_changes,
        "scene":         scene,
        "alert_level":   alert_level,
        "beep":          beep,
        "depth_source":  objects[0].get("depth_source", "bbox") if objects else "bbox",
    }


def _extract_find_target(text: str) -> str:
    """
    찾기 명령어에서 대상 물체 이름 추출.
    "의자 찾아줘" → "의자"
    "가방 어디있어" → "가방"

    명령 동사 패턴을 순서대로 제거하고 남은 것이 대상 물체.
    """
    verbs = ["찾아줘", "찾아", "어디있어", "어디 있어", "어디야",
             "어딘지", "어디에 있어", "어디에 있나", "있는지 알려줘"]
    label = text
    for v in verbs:
        label = label.replace(v, "")
    return label.strip()


# ── 장소 저장/조회 전용 엔드포인트 ───────────────────────────────────────────
# Android MainActivity에서 직접 호출 가능 (detect API 거치지 않고 빠르게 처리)

@router.post("/ocr/bus")
async def ocr_bus(
    image:     UploadFile,
    bus_crop:  str = Form(""),   # JSON 배열 문자열 "[x1,y1,x2,y2]" 또는 빈 문자열
):
    """
    버스 번호 OCR — ML Kit(Android)이 실패했을 때 서버 EasyOCR로 재시도.

    Android에서 호출 순서:
      1. ML Kit OCR 시도 → 숫자 없으면
      2. 이 엔드포인트 호출 (이미지 + bus_crop 좌표 전송)
      3. EasyOCR + 이미지 전처리로 재시도
      4. 결과 TTS로 읽어줌
    """
    import json
    from src.ocr.bus_ocr import recognize_bus_number

    image_bytes = await image.read()

    # bus_crop: Android에서 JSON 문자열로 전달 "[x1,y1,x2,y2]"
    crop = None
    if bus_crop:
        try:
            crop = json.loads(bus_crop)
        except Exception:
            crop = None

    bus_number = recognize_bus_number(image_bytes, crop)

    if bus_number:
        return {"success": True,  "bus_number": bus_number,
                "sentence": f"{bus_number}번 버스예요."}
    return {"success": False, "bus_number": None,
            "sentence": "버스 번호를 읽지 못했어요. 번호판에 더 가까이 대보세요."}


@router.post("/locations/save")
async def save_location_endpoint(
    wifi_ssid: str = Form(""),
    label:     str = Form(""),
):
    """장소 저장. Android에서 이미지 없이 직접 호출."""
    if not label:
        return {"success": False, "sentence": "장소 이름을 말씀해 주세요."}
    if not wifi_ssid:
        return {"success": False, "sentence": "WiFi에 연결되어 있지 않아 저장할 수 없어요."}
    db.save_location(label, wifi_ssid)
    return {"success": True, "sentence": build_navigation_sentence(label, "save")}


@router.get("/locations")
async def list_locations(wifi_ssid: str = ""):
    """저장 장소 목록 반환. wifi_ssid 지정 시 해당 WiFi 위치 장소만."""
    locations = db.get_locations(wifi_ssid)
    return {
        "locations": locations,
        "sentence":  build_navigation_sentence("", "list", locations=locations),
    }


@router.get("/locations/find/{label}")
async def find_location_endpoint(label: str, wifi_ssid: str = ""):
    """
    라벨로 장소 검색. 현재 WiFi와 일치 여부도 확인.
    nearby=True이면 "도착했어요!", False이면 "다른 WiFi에 있어요."
    """
    loc = db.find_location(label)
    if not loc:
        return {"found": False, "sentence": build_navigation_sentence(label, "not_found")}
    nearby = (wifi_ssid == loc["wifi_ssid"]) if wifi_ssid else False
    return {
        "found":    True,
        "nearby":   nearby,
        "location": loc,
        "sentence": build_navigation_sentence(loc["label"], "found_here") if nearby
                    else f"{loc['label']}{_un_neun(loc['label'])} 다른 WiFi 위치에 저장되어 있어요.",
    }


@router.delete("/locations/{label}")
async def delete_location_endpoint(label: str):
    """저장 장소 삭제."""
    loc = db.find_location(label)
    if not loc:
        return {"success": False, "sentence": f"{label}은 저장되어 있지 않아요."}
    db.delete_location(loc["label"])
    return {"success": True, "sentence": build_navigation_sentence(loc["label"], "deleted")}


@router.post("/spaces/snapshot")
async def save_space_snapshot(body: dict):
    """공간 스냅샷 수동 저장 (테스트·디버깅용)."""
    space_id = body.get("space_id", "")
    objects  = body.get("objects", [])
    db.save_snapshot(space_id, objects)
    return {"saved": True}


@router.post("/stt")
async def stt_listen():
    """
    PC 마이크로 음성 인식 — Gradio 데모 전용.
    Android 앱은 SpeechRecognizer 내장 API를 직접 사용하므로 이 엔드포인트 호출 안 함.
    """
    try:
        from src.voice.stt import listen_and_classify
        text, mode = listen_and_classify()
        return {"text": text, "mode": mode, "success": bool(text)}
    except Exception as e:
        return {"text": "", "mode": "unknown", "success": False, "error": str(e)}
