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

import os
from datetime import datetime

from fastapi import APIRouter, Depends, UploadFile, Form, Header, HTTPException
from fastapi.responses import FileResponse

# ── API Key 인증 ────────────────────────────────────────────────────────────
# .env에 API_KEY=비밀값 설정 시 모든 /detect 요청에 Authorization: Bearer <키> 필요
# API_KEY 미설정 시 인증 없음 (로컬 개발 모드)
_API_KEY = os.getenv("API_KEY", "")

def _verify_api_key(authorization: str = Header(default="")) -> None:
    if not _API_KEY:
        return  # 키 미설정 = 개발 모드, 인증 건너뜀
    if authorization != f"Bearer {_API_KEY}":
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
from src.depth.depth import detect_and_depth
from src.nlg.sentence import (
    build_sentence, build_hazard_sentence, build_find_sentence,
    build_navigation_sentence, build_question_sentence, get_alert_mode, _i_ga, _un_neun,
)
from src.api import db
from src.api.tracker import get_tracker
from src.voice.stt import extract_label

router = APIRouter()

# ── 세션별 마지막 문장 캐시 (TTS 중복 방지) ────────────────────────────────────
# 같은 세션에서 동일 문장이 5초 이내에 반복되면 alert_mode를 "silent"로 내려보냄
# → Android에서 TTS를 새로 재생하지 않음 (UI 업데이트만)
# "critical" 수준 (차량·계단)은 항상 통과
import time as _time
_last_sentence: dict[str, tuple[str, float]] = {}  # session_id → (sentence, timestamp)
_DEDUP_SECS = 5.0   # 같은 문장 억제 시간

def _should_suppress(session_id: str, sentence: str, alert_mode: str) -> bool:
    """같은 문장이 최근 N초 내에 이미 전달됐으면 억제 여부 반환."""
    if alert_mode == "critical":  # 위험 경고는 항상 발화
        _last_sentence[session_id] = (sentence, _time.monotonic())
        return False
    prev_sentence, prev_ts = _last_sentence.get(session_id, ("", 0.0))
    if sentence == prev_sentence and (_time.monotonic() - prev_ts) < _DEDUP_SECS:
        return True  # 억제
    _last_sentence[session_id] = (sentence, _time.monotonic())
    return False


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


@router.post("/detect", dependencies=[Depends(_verify_api_key)])
async def detect(
    image:              UploadFile,
    wifi_ssid:          str   = Form(""),        # 공간 기억 + 장소 저장에 사용
    camera_orientation: str   = Form("front"),   # 방향 보정: front/back/left/right
    mode:               str   = Form("장애물"),  # STT가 결정한 모드
    query_text:         str   = Form(""),        # STT 원문 (찾기/저장 모드에서 추출에 사용)
    lat:                float = Form(0.0),       # GPS 위도 (대시보드 지도용)
    lng:                float = Form(0.0),       # GPS 경도 (대시보드 지도용)
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

    # ── 이미지 분석 공통 흐름 (장애물/찾기/확인/질문 모드) ───────────────────
    image_bytes = await image.read()  # multipart form에서 이미지 바이트 추출

    # FPS 측정: 서버 처리 시간 기록 시작
    _t0 = _time.monotonic()

    # GPS 위치 기록 (대시보드 지도 표시용) — 좌표가 있을 때만 저장
    if lat != 0.0 or lng != 0.0:
        db.save_gps(wifi_ssid or "__default__", lat, lng)

    # YOLO 탐지 + Depth V2 거리 추정 + 바닥 위험 감지
    _t_detect = _time.monotonic()
    objects, hazards, scene = detect_and_depth(image_bytes)
    _detect_ms = int((_time.monotonic() - _t_detect) * 1000)

    # EMA 추적기: 프레임 간 거리 흔들림 제거 + 접근 감지
    _t_tracker = _time.monotonic()
    tracker = get_tracker(wifi_ssid or "__default__")
    objects, motion_changes = tracker.update(objects)
    _tracker_ms = int((_time.monotonic() - _t_tracker) * 1000)

    # 공간 기억: 이전 방문과 비교해서 달라진 것 감지
    previous = db.get_snapshot(wifi_ssid)
    space_changes = _space_changes(objects, previous) if previous else []
    db.save_snapshot(wifi_ssid, objects)  # 현재 상태를 다음 방문을 위해 저장

    all_changes = motion_changes + space_changes

    # ── 질문 모드: 사용자가 직접 "지금 뭐가 있어?" 물었을 때 즉시 응답 ──────
    # 핵심 버그 수정: 기존엔 질문해도 periodic capture를 기다렸음.
    # 이제 tracker에 누적된 최근 상태 + 현재 프레임을 합쳐 즉시 응답.
    if mode == "질문":
        tracked = tracker.get_current_state(max_age_s=3.0)
        sentence = build_question_sentence(objects, hazards, scene, tracked, camera_orientation)
        alert_mode = get_alert_mode(objects[0], is_hazard=bool(hazards)) if objects else (
            "critical" if hazards else "silent"
        )
        return {
            "sentence":    sentence,
            "alert_mode":  alert_mode,
            "objects":     objects,
            "hazards":     hazards,
            "changes":     motion_changes,
            "scene":       scene,
            "tracked":     tracked,
            "depth_source": objects[0].get("depth_source", "bbox") if objects else "bbox",
        }

    # ── 식사 도우미 모드: 식기·음식 위치 집중 안내 ──────────────────────────
    if mode == "식사":
        sentence = _build_meal_sentence(objects)
        return {
            "sentence":    sentence,
            "objects":     objects,
            "hazards":     [],
            "changes":     [],
            "alert_mode":  "silent",
            "depth_source": objects[0].get("depth_source","bbox") if objects else "bbox",
        }

    # ── 찾기 모드: 특정 물체를 타깃으로 탐색 ────────────────────────────────
    if mode == "찾기":
        target = _extract_find_target(query_text)  # "의자 찾아줘" → "의자"
        sentence = build_find_sentence(target, objects, camera_orientation)
        return {
            "sentence":    sentence,
            "alert_mode":  "critical",  # 사용자가 명시적으로 요청한 것 → 항상 즉각 안내
            "objects":     objects,
            "hazards":     hazards,
            "changes":     all_changes,
            "depth_source": objects[0].get("depth_source", "bbox") if objects else "bbox",
        }

    # ── 장애물/확인 모드: 위험도 기반 문장 생성 ──────────────────────────────
    if hazards:
        # 계단·낙차·턱이 감지되면 최우선 안내 (YOLO 결과보다 우선)
        top_hazard = max(hazards, key=lambda h: h.get("risk", 0))
        sentence   = build_hazard_sentence(top_hazard, objects, all_changes, camera_orientation)
        alert_mode = get_alert_mode(objects[0], is_hazard=True) if objects else "critical"
    else:
        sentence   = build_sentence(objects, all_changes, camera_orientation=camera_orientation)
        # risk_score 1위 객체 기준으로 알림 모드 결정
        # "silent"이면 프론트엔드는 TTS 호출 안 함, "beep"이면 비프음만 재생
        alert_mode = get_alert_mode(objects[0]) if objects else "silent"

    # 부가 경고 추가: 위험 물체·점자블록·군중·신호등·안전경로
    # 메인 문장 뒤에 붙임 (있을 때만)
    extras = [v for v in [
        scene.get("danger_warning"),        # 칼·가위 3m 이내 즉시 경고
        scene.get("slippery_warning"),      # 바닥 음식류 미끄럼 위험
        scene.get("tactile_block_warning"), # 점자 블록 위 장애물
        scene.get("crowd_warning"),         # 군중 밀집 경고
        scene.get("safe_direction"),        # 안전 경로 제안
        scene.get("traffic_light_msg"),     # 신호등 빨강/초록
    ] if v]
    if extras:
        sentence = sentence + " " + " ".join(extras)

    # 같은 문장이 5초 이내에 이미 전달됐으면 alert_mode를 "silent"로 낮춤 (TTS 겹침 방지)
    sid = wifi_ssid or "__default__"
    if _should_suppress(sid, sentence, alert_mode):
        alert_mode = "silent"

    # 전체 서버 처리 시간 + 단계별 분석 로그
    process_ms = int((_time.monotonic() - _t0) * 1000)
    _nlg_ms = process_ms - _detect_ms - _tracker_ms
    print(f"[PERF] detect={_detect_ms}ms | tracker={_tracker_ms}ms | nlg+rest={_nlg_ms}ms | TOTAL={process_ms}ms | objs={len(objects)}")

    return {
        "sentence":      sentence,
        "alert_mode":    alert_mode,
        "objects":       objects,
        "hazards":       hazards,
        "changes":       all_changes,
        "scene":         scene,
        "depth_source":  objects[0].get("depth_source", "bbox") if objects else "bbox",
        "process_ms":    process_ms,  # 서버 처리 시간 ms — Android FPS 표시용
    }


_MEAL_CLASSES = {
    "포크", "칼", "숟가락", "그릇", "컵", "병", "유리잔",
    "바나나", "사과", "오렌지", "샌드위치", "피자", "도넛",
    "케이크", "핫도그", "브로콜리", "당근",
}
_MEAL_DIRECTIONS = {
    "바로 앞": "바로 앞에",
    "왼쪽 앞": "왼쪽 앞에",
    "오른쪽 앞": "오른쪽 앞에",
    "왼쪽": "왼쪽에",
    "오른쪽": "오른쪽에",
}


def _build_meal_sentence(objects: list[dict]) -> str:
    """식사 모드 전용 문장 — 식기·음식 위치를 친근하게 안내."""
    from src.nlg.templates import CLOCK_TO_DIRECTION
    from src.nlg.sentence import _i_ga, _format_dist
    meal_items = [o for o in objects if o.get("class_ko") in _MEAL_CLASSES]
    if not meal_items:
        return "식기나 음식이 보이지 않아요. 카메라를 식탁 쪽으로 향해 주세요."
    parts = []
    for obj in meal_items[:3]:
        name = obj.get("class_ko", "")
        if not name:
            continue
        direction = CLOCK_TO_DIRECTION.get(obj.get("direction", "12시"), "앞")
        dist = obj.get("distance_m", 1.0)
        ig = _i_ga(name)
        loc = _MEAL_DIRECTIONS.get(direction, f"{direction}에")
        if dist < 0.8:
            parts.append(f"{loc} {name}{ig} 있어요. 손 뻗으면 닿아요.")
        else:
            parts.append(f"{loc} {name}{ig} 있어요.")
    return " ".join(parts) if parts else "식기나 음식이 보이지 않아요."


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

@router.post("/tts")
async def tts_endpoint(text: str = Form("")):
    """ElevenLabs / gTTS — 텍스트를 음성 파일(MP3)로 변환해 Android 앱에 반환.
    API 키 없으면 gTTS로 자동 폴백."""
    from src.voice.tts import _cache_path, _generate
    from fastapi.responses import JSONResponse
    import os
    if not text:
        return JSONResponse({"error": "text is empty"}, status_code=400)
    path = _cache_path(text)
    if not os.path.exists(path):
        if not _generate(text, path):
            return JSONResponse({"error": "TTS generation failed"}, status_code=500)
    return FileResponse(path, media_type="audio/mpeg")


@router.post("/vision/clothing")
async def vision_clothing(
    image: UploadFile,
    type:  str = Form("matching"),   # "matching" or "pattern"
):
    """옷 매칭·패턴 분석 — GPT-4o Vision 활용."""
    from src.vision.gpt_vision import analyze_clothing
    if type not in ("matching", "pattern"):
        type = "matching"   # 잘못된 값이면 기본값으로 fallback
    image_bytes = await image.read()
    sentence = analyze_clothing(image_bytes, type)
    return {"sentence": sentence}


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


@router.get("/status/{session_id}")
async def get_session_status(session_id: str):
    """
    세션(WiFi SSID)의 현재 추적 상태 반환 — 대시보드 폴링용.
    최근 3초 이내에 탐지된 물체 목록과 마지막 GPS 좌표를 반환.
    """
    tracker = get_tracker(session_id)
    current = tracker.get_current_state(max_age_s=3.0)
    gps     = db.get_last_gps(session_id)
    track   = db.get_gps_track(session_id, limit=100)
    return {
        "session_id": session_id,
        "objects":    current,
        "gps":        gps,
        "track":      track,
    }


@router.get("/dashboard")
async def dashboard():
    """대시보드 HTML 페이지 반환."""
    from fastapi.responses import HTMLResponse
    import os
    tpl_path = os.path.join(os.path.dirname(__file__), "../../templates/dashboard.html")
    if os.path.exists(tpl_path):
        with open(tpl_path, encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>dashboard.html not found</h1>", status_code=404)


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
