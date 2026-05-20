"""
VoiceGuide FastAPI 라우터
===========================
Android 앱이 호출하는 API 엔드포인트를 정의합니다.

주요 엔드포인트:
  POST /detect           — 온디바이스 탐지 결과 JSON 수신/배포/저장
  POST /locations/save   — 장소 저장
  GET  /locations        — 저장 장소 목록
  GET  /locations/find/{label} — 장소 검색
  DELETE /locations/{label}   — 장소 삭제

설계 원칙:
  - 모든 엔드포인트는 반드시 sentence 필드를 반환 → TTS로 바로 읽을 수 있음
  - 오류가 나도 음성 안내가 나오도록 전역 예외 핸들러 적용 (main.py)
  - 서버는 YOLO 추론이나 이미지 분석을 하지 않고, 앱이 보낸 JSON만 처리
"""

import os
import uuid
import hashlib
import json
import asyncio
from collections import defaultdict

from fastapi import APIRouter, Depends, Body, Form, Header, HTTPException, Response
from fastapi.responses import StreamingResponse

from src.api import locations as location_api

# ── API Key 인증 ────────────────────────────────────────────────────────────
_API_KEY = os.getenv("API_KEY", "")

def _verify_api_key(
    authorization: str = Header(default=""),
    x_api_key: str = Header(default=""),
) -> None:
    if not _API_KEY:
        return
    if authorization == f"Bearer {_API_KEY}" or x_api_key == _API_KEY:
        return
    raise HTTPException(status_code=401, detail="Invalid or missing API key")

from src.nlg.sentence import (
    build_sentence, build_find_sentence,
    build_question_sentence, build_held_sentence,
    get_alert_mode, _i_ga,
)
from src.api import db
from src.api import events
from src.api.detections import normalize_detection_objects, normalize_legacy_detections
from src.api.tracker import get_tracker

router = APIRouter()

@router.get("/api/policy")
async def get_voice_policy(
    response: Response,
    if_none_match: str = Header(default=None),
    x_app_client: str = Header(default=None)
):
    """SSOT 정책 JSON — Android 온디바이스 NLG와 동기화 (ETag 트래픽 최적화)"""
    # 하위 호환성 유지: 헤더가 없는 구버전은 통과, 이상한 값을 보내면 차단
    if x_app_client is not None and x_app_client != "voiceguide-android-v1":
        raise HTTPException(status_code=403, detail="Forbidden Client")

    from src.config.policy import get_policy
    policy_dict = get_policy()

    # ETag(데이터 지문) 캐싱 처리
    policy_str = json.dumps(policy_dict, sort_keys=True)
    etag = hashlib.md5(policy_str.encode("utf-8")).hexdigest()
    client_etag = if_none_match.strip('"') if if_none_match else None

    if client_etag == etag:
        return Response(status_code=304)

    response.headers["ETag"] = f'"{etag}"'
    return policy_dict

# ── 세션별 마지막 문장 캐시 (TTS 중복 방지) ────────────────────────────────────
import time as _time
_last_sentence: dict[str, tuple[str, float]] = {}
_DEDUP_SECS = 2.5
_SAVE_EVERY_N_FRAMES = max(1, int(os.getenv("DETECT_SAVE_EVERY_N_FRAMES", "5")))
_SNAPSHOT_MIN_INTERVAL_S = float(os.getenv("SNAPSHOT_MIN_INTERVAL_S", "1.0"))
_last_snapshot: dict[str, tuple[str, float]] = {}
_frame_counts: dict[str, int] = defaultdict(int)


def _object_signature(objects: list[dict]) -> str:
    parts = []
    for obj in objects[:8]:
        bbox = obj.get("bbox_norm_xywh") or [0, 0, 0, 0]
        area = round(float(bbox[2]) * float(bbox[3]), 3) if len(bbox) >= 4 else 0
        parts.append(f"{obj.get('class_ko')}:{obj.get('direction')}:{area}")
    return "|".join(parts)


def _should_persist_frame(session_id: str, objects: list[dict], mode: str) -> bool:
    _frame_counts[session_id] += 1
    if mode in {"질문", "찾기", "들고있는것"}:
        return True
    if _frame_counts[session_id] % _SAVE_EVERY_N_FRAMES == 0:
        return True
    signature = _object_signature(objects)
    prev_signature, prev_ts = _last_snapshot.get(session_id, ("", 0.0))
    return signature != prev_signature and (_time.monotonic() - prev_ts) >= _SNAPSHOT_MIN_INTERVAL_S


def _mark_persisted(session_id: str, objects: list[dict]) -> None:
    _last_snapshot[session_id] = (_object_signature(objects), _time.monotonic())


async def _publish_dashboard_event(session_id: str, payload: dict, gps: dict | None = None, track: list[dict] | None = None) -> None:
    await events.publish(session_id, {
        "session_id": session_id,
        "objects": payload.get("objects", []),
        "gps": gps,
        "track": track or [],
        "latest_event": {
            "event_id": payload.get("event_id"),
            "request_id": payload.get("request_id"),
            "objects": payload.get("objects", []),
            "hazards": payload.get("hazards", []),
            "scene": payload.get("scene", {}),
        },
    })

def _normalize_session_id(wifi_ssid: str = "", device_id: str = "") -> str:
    """기기별 대시보드 세션 ID 정규화."""
    preferred = device_id or wifi_ssid
    value = (preferred or "").strip().strip('"')
    if not value or value.lower() in {"<unknown ssid>", "unknown ssid", "0x"}:
        # 버그 수정: 익명 유저 간 세션 꼬임 방지 (일회용 UUID 부여)
        return f"anonymous_{uuid.uuid4().hex[:8]}"
    return value

def _with_perf(payload: dict, t0: float, request_id: str, detect_ms: int = 0, tracker_ms: int = 0) -> dict:
    process_ms = int((_time.monotonic() - t0) * 1000)
    nlg_ms = max(0, process_ms - detect_ms - tracker_ms)
    payload.update({
        "request_id": request_id,
        "process_ms": process_ms,
        "perf": {
            "detect_ms": detect_ms,
            "tracker_ms": tracker_ms,
            "nlg_ms": nlg_ms,
            "total_ms": process_ms,
        },
    })
    return payload

def _should_suppress(session_id: str, sentence: str, alert_mode: str) -> bool:
    if alert_mode == "critical":
        _last_sentence[session_id] = (sentence, _time.monotonic())
        return False
    prev_sentence, prev_ts = _last_sentence.get(session_id, ("", 0.0))
    if sentence == prev_sentence and (_time.monotonic() - prev_ts) < _DEDUP_SECS:
        return True
    _last_sentence[session_id] = (sentence, _time.monotonic())
    return False

def _space_changes(current: list[dict], previous: list[dict]) -> list[str]:
    prev_set = {o["class_ko"] for o in previous}
    curr_set = {o["class_ko"] for o in current}
    changes = []
    for name in curr_set - prev_set:
        changes.append(f"{name}{_i_ga(name)} 생겼어요")
    for name in prev_set - curr_set:
        changes.append(f"{name}{_i_ga(name)} 없어졌어요")
    return changes


@router.post("/detect", dependencies=[Depends(_verify_api_key)])
async def detect(
    payload: dict = Body(...),
):
    _t0 = _time.monotonic()
    wifi_ssid = str(payload.get("wifi_ssid", ""))
    device_id = str(payload.get("device_id", ""))
    camera_orientation = str(payload.get("camera_orientation", "front"))
    mode = str(payload.get("mode", "장애물"))
    query_text = str(payload.get("query_text", ""))
    lat = float(payload.get("lat") or 0.0)
    lng = float(payload.get("lng") or 0.0)
    request_id = str(payload.get("request_id") or "")
    request_id = request_id or f"srv-{int(_t0 * 1000)}"
    event_id = str(payload.get("event_id") or request_id or uuid.uuid4().hex)
    session_id = _normalize_session_id(wifi_ssid, device_id)

    if lat != 0.0 or lng != 0.0:
        db.save_gps(session_id, lat, lng)

    objects = normalize_detection_objects(payload.get("objects", []))
    current_objects = list(objects)
    hazards = payload.get("hazards", [])
    if not isinstance(hazards, list):
        hazards = []
    scene = payload.get("scene", {})
    if not isinstance(scene, dict):
        scene = {}
    _detect_ms = int(payload.get("client_perf", {}).get("infer_ms", 0) or 0)

    _t_tracker = _time.monotonic()
    tracker = get_tracker(session_id)
    objects, motion_changes = tracker.update(objects)
    nlg_objects = current_objects if mode in {"찾기", "질문", "들고있는것"} and current_objects else objects
    _tracker_ms = int((_time.monotonic() - _t_tracker) * 1000)

    should_persist = _should_persist_frame(session_id, objects, mode)
    previous = db.get_snapshot(session_id) if should_persist else None
    space_changes = _space_changes(objects, previous) if previous and objects else []
    if objects and should_persist:
        db.save_snapshot(session_id, objects)
        _mark_persisted(session_id, objects)

    all_changes = motion_changes + space_changes
    db_enqueued = False
    if should_persist and objects:
        db_enqueued = db.enqueue_detection_event(
            event_id=event_id,
            request_id=request_id,
            session_id=session_id,
            device_id=device_id,
            wifi_ssid=wifi_ssid,
            mode=mode,
            objects=objects,
            hazards=hazards,
            scene=scene,
            raw_payload=payload,
            lat=lat if lat != 0.0 or lng != 0.0 else None,
            lng=lng if lat != 0.0 or lng != 0.0 else None,
        )

    if mode == "들고있는것":
        sentence = build_held_sentence(nlg_objects)
        response_payload = _with_perf({
            "mode": mode, "event_id": event_id, "session_id": session_id,
            "sentence": sentence, "alert_mode": "critical",
            "objects": nlg_objects, "hazards": hazards, "changes": motion_changes,
            "db_queued": db_enqueued,
            "depth_source": nlg_objects[0].get("depth_source", "bbox") if nlg_objects else "bbox",
        }, _t0, request_id, _detect_ms, _tracker_ms)
        await _publish_dashboard_event(session_id, response_payload, db.get_last_gps(session_id), db.get_gps_track(session_id, limit=100))
        return response_payload

    if mode == "질문":
        tracked = tracker.get_current_state(max_age_s=3.0)
        sentence = build_question_sentence(nlg_objects, hazards, scene, tracked, camera_orientation)
        alert_mode = get_alert_mode(nlg_objects[0], is_hazard=bool(hazards)) if nlg_objects else ("critical" if hazards else "silent")
        response_payload = _with_perf({
            "mode": mode, "event_id": event_id, "session_id": session_id,
            "sentence": sentence, "alert_mode": alert_mode,
            "objects": nlg_objects, "hazards": hazards, "changes": motion_changes,
            "scene": scene, "tracked": tracked,
            "db_queued": db_enqueued,
            "depth_source": nlg_objects[0].get("depth_source", "bbox") if nlg_objects else "bbox",
        }, _t0, request_id, _detect_ms, _tracker_ms)
        await _publish_dashboard_event(session_id, response_payload, db.get_last_gps(session_id), db.get_gps_track(session_id, limit=100))
        return response_payload

    if mode == "찾기":
        target = _extract_find_target(query_text)
        sentence = build_find_sentence(target, nlg_objects, camera_orientation)
        response_payload = _with_perf({
            "mode": mode, "event_id": event_id, "session_id": session_id,
            "sentence": sentence, "alert_mode": "critical",
            "objects": nlg_objects, "hazards": hazards, "changes": all_changes,
            "db_queued": db_enqueued,
            "depth_source": nlg_objects[0].get("depth_source", "bbox") if nlg_objects else "bbox",
        }, _t0, request_id, _detect_ms, _tracker_ms)
        await _publish_dashboard_event(session_id, response_payload, db.get_last_gps(session_id), db.get_gps_track(session_id, limit=100))
        return response_payload

    sentence = build_sentence(objects, all_changes, camera_orientation=camera_orientation)
    alert_mode = get_alert_mode(objects[0]) if objects else "silent"

    extras = [v for v in [
        scene.get("danger_warning"), scene.get("slippery_warning"),
        scene.get("tactile_block_warning"), scene.get("crowd_warning"),
        scene.get("safe_direction"), scene.get("traffic_light_msg"),
    ] if v]
    if extras:
        sentence = sentence + " " + " ".join(extras)

    if _should_suppress(session_id, sentence, alert_mode):
        alert_mode = "silent"

    response_payload = _with_perf({
        "mode": mode, "event_id": event_id, "session_id": session_id,
        "sentence": sentence, "alert_mode": alert_mode,
        "objects": objects, "hazards": hazards, "changes": all_changes, "scene": scene,
        "db_queued": db_enqueued,
        "depth_source": objects[0].get("depth_source", "bbox") if objects else "bbox",
    }, _t0, request_id, _detect_ms, _tracker_ms)
    await _publish_dashboard_event(session_id, response_payload, db.get_last_gps(session_id), db.get_gps_track(session_id, limit=100))
    return response_payload

def _extract_find_target(text: str) -> str:
    """
    찾기 명령어에서 대상 물체 이름 추출.
    "의자 찾아줘" → "의자", "이거 뭐야" → "" (확인 의도 → 빈 target)

    명령 동사/확인 패턴을 순서대로 제거하고 남은 것이 대상 물체.
    """
    verbs = [
        "찾아줘", "찾아", "어디있어", "어디 있어", "어디야",
        "어딘지", "어디에 있어", "어디에 있나", "있는지 알려줘",
        "뭔지 알려줘", "뭐야", "뭐지", "뭔지", "뭔데", "이거", "이게", "이건",
    ]
    label = text
    for v in sorted(verbs, key=len, reverse=True):  # 긴 패턴부터 제거 (부분 겹침 방지)
        label = label.replace(v, "")
    return label.strip()

@router.post("/detect_json", dependencies=[Depends(_verify_api_key)])
async def detect_from_json(body: dict):
    """
    온디바이스 추론 결과 JSON 수신 엔드포인트 (새 아키텍처).

    폰이 YOLO 추론 후 탐지 결과를 JSON으로 전송 → 서버는 이미지 처리 없이
    tracker 업데이트 + DB 저장 + NLG 문장 생성만 수행.

    요청 형식:
    {
        "device_id": "abc123",
        "session_id": "abc123",
        "wifi_ssid": "MyWifi",
        "request_id": "and-...",
        "mode": "장애물",
        "camera_orientation": "front",
        "lat": 0.0, "lng": 0.0,
        "detections": [
            {"class_ko":"의자","confidence":0.9,"cx":0.5,"cy":0.6,
             "w":0.15,"h":0.20,"zone":"12시","dist_m":1.47,
             "is_vehicle":false,"is_animal":false}
        ]
    }
    """
    _t0 = _time.monotonic()
    device_id  = body.get("device_id", "")
    wifi_ssid  = body.get("wifi_ssid", "")
    request_id = body.get("request_id", f"srv-{int(_t0*1000)}")
    mode       = body.get("mode", "장애물")
    lat        = float(body.get("lat", 0.0))
    lng        = float(body.get("lng", 0.0))
    camera_orientation = body.get("camera_orientation", "front")
    raw_detections: list[dict] = body.get("detections", [])

    session_id = _normalize_session_id(wifi_ssid, device_id)

    if lat != 0.0 or lng != 0.0:
        db.save_gps(session_id, lat, lng)

    # 폰 포맷 → 서버 내부 포맷으로 변환
    objects = normalize_legacy_detections(raw_detections)

    # tracker 업데이트 (EMA 평활화 + 접근 감지)
    _t_tracker = _time.monotonic()
    tracker = get_tracker(session_id)
    objects, motion_changes = tracker.update(objects)
    _tracker_ms = int((_time.monotonic() - _t_tracker) * 1000)

    # DB 저장 (fire & store)
    db.save_detections(device_id, session_id, request_id,
                       raw_detections, mode, lat, lng)

    # 스냅샷 저장 (대시보드 호환)
    if objects:
        db.save_snapshot(session_id, objects)

    # NLG 문장 생성
    hazards: list[str] = []
    if mode == "찾기":
        target = body.get("query_text", "")
        sentence = build_find_sentence(target, objects, camera_orientation)
        alert_mode = "critical"
    else:
        previous = db.get_snapshot(session_id)
        space_changes = _space_changes(objects, previous) if previous and objects else []
        all_changes = motion_changes + space_changes
        sentence  = build_sentence(objects, all_changes, camera_orientation=camera_orientation)
        alert_mode = get_alert_mode(objects[0]) if objects else "silent"
        if _should_suppress(session_id, sentence, alert_mode):
            alert_mode = "silent"

    return _with_perf({
        "mode": mode, "sentence": sentence, "alert_mode": alert_mode,
        "objects": objects, "changes": motion_changes,
    }, _t0, request_id, 0, _tracker_ms)


@router.post("/question", dependencies=[Depends(_verify_api_key)])
async def answer_question(body: dict):
    """
    질문 응답 전용 엔드포인트 (이미지 전송 없음).

    폰이 "앞에 뭐 있어?" 같은 질문을 하면, 서버에 누적된 tracker 상태
    (최근 /detect_json으로 쌓인 데이터)를 꺼내 요약 문장을 반환.
    """
    _t0 = _time.monotonic()
    device_id  = body.get("device_id", "")
    wifi_ssid  = body.get("wifi_ssid", "")
    request_id = body.get("request_id", f"srv-q-{int(_t0*1000)}")
    camera_orientation = body.get("camera_orientation", "front")

    session_id = _normalize_session_id(wifi_ssid, device_id)
    tracker    = get_tracker(session_id)

    # tracker에 누적된 최근 3초 상태 조회
    tracked = tracker.get_current_state(max_age_s=3.0)

    # tracker가 비어 있으면 DB에서 복원 시도 (서버 재시작 후 첫 질문 등)
    if not tracked:
        recent = db.get_recent_detections(session_id, max_age_s=3.0)
        tracked = [
            {
                "class":      r["class_ko"], "class_ko": r["class_ko"],
                "distance_m": r["dist_m"],   "direction": r["zone"],
                "is_vehicle": bool(r["is_vehicle"]),
                "is_animal":  bool(r["is_animal"]),
                "depth_source": "db",
            }
            for r in recent
        ]

    sentence = build_question_sentence([], [], {}, tracked, camera_orientation)
    alert_mode = get_alert_mode(tracked[0], is_hazard=False) if tracked else "silent"

    # 질문 응답 후 3초간 periodic silent 처리 (폰 측 suppressPeriodicUntil 호환)
    _last_sentence[session_id] = (sentence, _time.monotonic())

    return _with_perf({
        "mode": "질문", "sentence": sentence, "alert_mode": alert_mode,
        "tracked": tracked,
    }, _t0, request_id)


@router.post("/gps", dependencies=[Depends(_verify_api_key)])
async def save_gps_ping(
    wifi_ssid: str = Form(""), device_id: str = Form(""),
    lat: float = Form(0.0), lng: float = Form(0.0), request_id: str = Form("")
):
    session_id = _normalize_session_id(wifi_ssid, device_id)
    if lat == 0.0 and lng == 0.0:
        return {"saved": False, "session_id": session_id, "reason": "empty_location"}
    db.save_gps(session_id, lat, lng)
    gps = db.get_last_gps(session_id)
    track = db.get_gps_track(session_id, limit=100)
    await events.publish(session_id, {
        "session_id": session_id,
        "objects": [],
        "gps": gps,
        "track": track,
    })
    return {"saved": True, "session_id": session_id, "lat": lat, "lng": lng}


@router.post("/gps/route/save", dependencies=[Depends(_verify_api_key)])
async def save_gps_route(body: dict = Body(...)):
    device_id = str(body.get("device_id", ""))
    wifi_ssid = str(body.get("wifi_ssid", ""))
    name = body.get("name")
    session_id = _normalize_session_id(wifi_ssid, device_id)
    route_id = db.save_gps_route(session_id, name=name)
    if not route_id:
        return {"saved": False, "reason": "no_gps_data"}
    routes = db.get_gps_routes(session_id, limit=1)
    meta = routes[0] if routes else {}
    # 경로 저장 완료 → 대시보드에 live track 초기화 신호 전송
    await events.publish(session_id, {
        "session_id": session_id,
        "objects": [],
        "gps": None,
        "track": [],
        "route_saved": True,
    })
    return {"saved": True, "route_id": route_id,
            "point_count": meta.get("point_count", 0),
            "started_at": meta.get("started_at"), "ended_at": meta.get("ended_at")}


@router.get("/routes/{session_id}", dependencies=[Depends(_verify_api_key)])
async def list_gps_routes(session_id: str):
    req_session_id = _normalize_session_id(session_id)
    routes = db.get_gps_routes(req_session_id, limit=20)
    return {"session_id": req_session_id, "routes": routes}


@router.get("/routes/{session_id}/{route_id}", dependencies=[Depends(_verify_api_key)])
async def get_gps_route(session_id: str, route_id: str):
    req_session_id = _normalize_session_id(session_id)
    routes = db.get_gps_routes(req_session_id, limit=20)
    meta = next((r for r in routes if r["route_id"] == route_id), None)
    points = db.get_gps_route_points(route_id)
    return {"route_id": route_id, "meta": meta, "points": points}

@router.get("/status/{session_id}", dependencies=[Depends(_verify_api_key)])
async def get_session_status(session_id: str):
    req_session_id = _normalize_session_id(device_id=session_id)
    gps = db.get_last_gps(req_session_id)
    tracker = get_tracker(req_session_id)
    current = tracker.get_current_state(max_age_s=5.0)
    if not current: current = db.get_snapshot(req_session_id, max_age_s=8.0) or []
    latest = db.get_latest_detection_event(req_session_id)
    return {
        "session_id": req_session_id,
        "objects": current,
        "gps": gps,
        "track": db.get_gps_track(req_session_id, limit=100),
        "latest_event": latest,
    }

@router.get("/events/{session_id}", dependencies=[Depends(_verify_api_key)])
async def stream_session_events(session_id: str):
    req_session_id = _normalize_session_id(device_id=session_id)

    async def event_stream():
        initial = await get_session_status(req_session_id)
        yield "event: status\n"
        yield f"data: {json.dumps(initial, ensure_ascii=False)}\n\n"
        async with events.subscribe(req_session_id) as queue:
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15)
                    yield "event: status\n"
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

@router.get("/sessions", dependencies=[Depends(_verify_api_key)])
async def list_sessions():
    return {"sessions": db.get_recent_sessions()}

@router.post("/locations/save", dependencies=[Depends(_verify_api_key)])
async def save_location(body: dict | None = Body(default=None)):
    body = body or {}
    label, scope = location_api.location_from_body(body, _normalize_session_id)
    if not label:
        raise HTTPException(status_code=400, detail="label is required")
    db.save_location(label, scope)
    location = {"label": label, "wifi_ssid": scope, "timestamp": ""}
    saved = db.get_locations(scope)
    if saved:
        location = saved[0]
    return location_api.save_payload(label, scope, location)

@router.get("/locations", dependencies=[Depends(_verify_api_key)])
async def list_locations(wifi_ssid: str = "", device_id: str = "", session_id: str = ""):
    scope = location_api.resolve_location_scope(
        _normalize_session_id,
        wifi_ssid=wifi_ssid,
        device_id=device_id,
        session_id=session_id,
    )
    return location_api.list_payload(db.get_locations(scope))

@router.get("/locations/find/{label}", dependencies=[Depends(_verify_api_key)])
async def find_location(label: str, wifi_ssid: str = "", device_id: str = "", session_id: str = ""):
    scope = location_api.resolve_location_scope(
        _normalize_session_id,
        wifi_ssid=wifi_ssid,
        device_id=device_id,
        session_id=session_id,
    )
    location = location_api.find_in_locations(label, db.get_locations(scope)) if scope else db.find_location(label)
    if not location:
        raise HTTPException(status_code=404, detail=location_api.missing_payload(label))
    return location_api.found_payload(label, location)

@router.delete("/locations/{label}", dependencies=[Depends(_verify_api_key)])
async def delete_location(label: str, wifi_ssid: str = "", device_id: str = "", session_id: str = ""):
    scope = location_api.resolve_location_scope(
        _normalize_session_id,
        wifi_ssid=wifi_ssid,
        device_id=device_id,
        session_id=session_id,
    )
    deleted = db.delete_location(label, scope) > 0
    if not deleted:
        raise HTTPException(status_code=404, detail=location_api.delete_payload(label, False))
    return location_api.delete_payload(label, True)

@router.get("/team-locations", dependencies=[Depends(_verify_api_key)])
async def get_team_locations():
    from datetime import datetime, timedelta
    cutoff = (datetime.now() - timedelta(minutes=30)).isoformat()
    locations = []
    for s in db.get_recent_sessions(limit=20):
        gps = db.get_last_gps(s)
        if gps and gps.get("timestamp", "") >= cutoff:
            locations.append({"session_id": s, "lat": gps["lat"], "lng": gps["lng"]})
    return {"locations": locations}

@router.get("/history/{session_id}", dependencies=[Depends(_verify_api_key)])
async def get_detection_history(session_id: str):
    """최근 24시간 탐지 이벤트 내역 조회 — 대시보드 하단 패널 전용.

    [왜 이 엔드포인트가 필요한가]
    대시보드의 '실시간 현황'은 현재 순간만 보여준다.
    이 엔드포인트는 "오늘 하루 동안 어떤 물체가 몇 번 탐지됐는지"
    누적 이력을 제공해 장기적인 패턴 파악에 활용한다.

    [앱 성능에 영향 없는 이유]
    - 호출자: 브라우저(대시보드)가 30초마다 1회 호출
    - 앱의 /detect는 초당 수회 호출 → 완전히 다른 경로
    - DB 조회는 SELECT만 수행, 앱의 쓰기 작업에 영향 없음

    반환:
        session_id   : 조회한 세션 ID
        period_hours : 조회 기간 (24시간 고정)
        summary      : 위험/주의/안전 건수 집계
        events       : 탐지 이벤트 목록 (최신순, 최대 50건)
    """
    req_session_id = _normalize_session_id(device_id=session_id)
    # DB에서 24시간 내역 조회 (SQLite·PostgreSQL 공통 인터페이스)
    result = db.get_history_24h(req_session_id, limit=50)
    return {
        "session_id":   req_session_id,
        "period_hours": 24,
        "summary":      result["summary"],
        "events":       result["events"],
    }


@router.get("/dashboard", dependencies=[Depends(_verify_api_key)])
async def dashboard():
    from fastapi.responses import HTMLResponse
    tpl_path = os.path.join(os.path.dirname(__file__), "../../templates/dashboard.html")
    if os.path.exists(tpl_path):
        with open(tpl_path, encoding="utf-8") as f: return HTMLResponse(f.read())
    return HTMLResponse("<h1>dashboard.html not found</h1>", status_code=404)

@router.post("/spaces/snapshot", dependencies=[Depends(_verify_api_key)])
async def save_space_snapshot(body: dict):
    db.save_snapshot(body.get("space_id", ""), body.get("objects", []))
    return {"saved": True}
