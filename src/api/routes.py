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
from functools import lru_cache
from pathlib import Path

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

_ROOT_DIR = Path(__file__).resolve().parents[2]
_PEDESTRIAN_HOTSPOT_DIR = _ROOT_DIR / "datasets" / "pedestrian_hotspots"
_PEDESTRIAN_SUMMARY_PATH = _PEDESTRIAN_HOTSPOT_DIR / "pedestrian_hotspots_summary.json"
_PEDESTRIAN_CLUSTERS_PATH = _PEDESTRIAN_HOTSPOT_DIR / "pedestrian_hotspot_clusters.geojson"
_DISABLED_POPULATION_DIR = _ROOT_DIR / "datasets" / "disabled_population"
_DISABLED_POPULATION_SUMMARY_PATH = _DISABLED_POPULATION_DIR / "disabled_population_summary.json"
_DISABLED_POPULATION_REGIONS_PATH = _DISABLED_POPULATION_DIR / "disabled_population_visual_regions.json"
_DISABLED_POPULATION_TREND_PATH = _DISABLED_POPULATION_DIR / "disabled_population_visual_trend.json"
_DISABLED_POPULATION_BY_TYPE_PATH = _DISABLED_POPULATION_DIR / "disabled_population_by_type_latest.json"
_SIDO_ALIASES = {
    "서울": "서울특별시",
    "부산": "부산광역시",
    "대구": "대구광역시",
    "인천": "인천광역시",
    "광주": "광주광역시",
    "대전": "대전광역시",
    "울산": "울산광역시",
    "세종": "세종특별자치시",
    "경기": "경기도",
    "강원": "강원특별자치도",
    "충북": "충청북도",
    "충남": "충청남도",
    "전북": "전북특별자치도",
    "전남": "전라남도",
    "경북": "경상북도",
    "경남": "경상남도",
    "제주": "제주특별자치도",
}


@lru_cache(maxsize=8)
def _load_json_artifact(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _require_json_artifact(path: Path) -> dict:
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Pedestrian hotspot artifact not found: {path}",
        )
    return _load_json_artifact(str(path))


def _distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    import math

    radius = 6_371_000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _strip_district_suffix(value: str) -> str:
    return value.rstrip("0123456789").strip()


def _parse_hotspot_district(value: str) -> tuple[str, list[str]]:
    clean = _strip_district_suffix(str(value or ""))
    parts = clean.split()
    if not parts:
        return "", []
    sido = _SIDO_ALIASES.get(parts[0], parts[0])
    sigungu_candidates = []
    if len(parts) >= 3:
        sigungu_candidates.append(" ".join(parts[1:3]))
    if len(parts) >= 2:
        sigungu_candidates.append(parts[1])
    return sido, list(dict.fromkeys(sigungu_candidates))


def _find_disabled_region(sido: str, sigungu_candidates: list[str]) -> dict | None:
    if not sido:
        return None
    regions = _require_json_artifact(_DISABLED_POPULATION_REGIONS_PATH)
    sido_regions = [row for row in regions if row.get("sido") == sido]
    for candidate in sigungu_candidates:
        for row in sido_regions:
            if row.get("sigungu") == candidate:
                return row
    for candidate in sigungu_candidates:
        for row in sido_regions:
            name = str(row.get("sigungu", ""))
            if candidate and (candidate in name or name in candidate):
                return row
    return None

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
            "event_id":   payload.get("event_id"),
            "request_id": payload.get("request_id"),
            "sentence":   payload.get("sentence", ""),
            "alert_mode": payload.get("alert_mode", "silent"),
            "objects":    payload.get("objects", []),
            "hazards":    payload.get("hazards", []),
            "scene":      payload.get("scene", {}),
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


_ZONE_BOUNDARIES = [
    (0.11, "8시"), (0.22, "9시"), (0.33, "10시"),
    (0.44, "11시"), (0.56, "12시"), (0.67, "1시"),
    (0.78, "2시"), (0.89, "3시"), (1.01, "4시"),
]


def _direction_from_bbox(obj: dict) -> str:
    if obj.get("direction"):
        return str(obj["direction"])
    bbox = obj.get("bbox_norm_xywh") or []
    if len(bbox) >= 4:
        cx = float(bbox[0]) + float(bbox[2]) / 2
    else:
        cx = float(obj.get("cx", 0.5))
    for boundary, label in _ZONE_BOUNDARIES:
        if cx < boundary:
            return label
    return "4시"


def _distance_from_bbox(obj: dict) -> float:
    if obj.get("distance_m") is not None:
        return round(float(obj["distance_m"]), 1)
    bbox = obj.get("bbox_norm_xywh") or []
    if len(bbox) >= 4:
        area = max(0.0001, float(bbox[2]) * float(bbox[3]))
    else:
        area = max(0.0001, float(obj.get("w", 0.1)) * float(obj.get("h", 0.1)))
    try:
        from src.config.policy import get_policy
        calib = float(get_policy().get("on_device", {}).get("bbox_calib_area", 0.12))
    except Exception:
        calib = 0.12
    return round(min(15.0, max(0.1, (calib / area) ** 0.5)), 1)


def _risk_from_object(obj: dict, critical_ko: set, caution_ko: set, everyday_ko: set,
                      animal_ko: set, thresholds: dict) -> float:
    """VoiceGuide 정책 카테고리 기반 위험도 점수(0~1) 계산."""
    if obj.get("risk_score") is not None:
        return float(obj["risk_score"])
    name = obj.get("class_ko", "")
    dist = float(obj.get("distance_m", 99.0))
    # critical_ko (차량·위험물체·계단) → 항상 위험
    if name in critical_ko:
        return 0.85
    # 동물 → 거리 임계치 기반
    if name in animal_ko:
        animal_m = float(thresholds.get("animal_critical_m", 3.0))
        return 0.85 if dist < animal_m else 0.35
    # caution_ko → 주의
    if name in caution_ko:
        return 0.55
    # everyday_ko → 안전
    if name in everyday_ko:
        return 0.15
    # 그 외(사람 등) → 거리·bbox 면적 기반
    bbox = obj.get("bbox_norm_xywh") or [0, 0, 0.1, 0.1]
    area = float(bbox[2]) * float(bbox[3]) if len(bbox) >= 4 else 0.01
    distance_score = max(0.0, min(1.0, (7.0 - dist) / 7.0))
    area_score = max(0.0, min(1.0, area / 0.12))
    return round(max(distance_score, area_score), 2)


def _normalize_objects(raw_objects: list[dict]) -> list[dict]:
    from src.config.policy import get_policy, alert_thresholds
    classes = get_policy().get("classes", {})
    vehicle_ko  = set(classes.get("vehicle_ko", []))
    animal_ko   = set(classes.get("animal_ko", []))
    critical_ko = set(classes.get("critical_ko", []))
    caution_ko  = set(classes.get("caution_ko", []))
    everyday_ko = set(classes.get("everyday_ko", []))
    thresholds  = alert_thresholds()

    objects = []
    for raw in raw_objects:
        if not isinstance(raw, dict):
            continue
        class_ko = str(raw.get("class_ko") or raw.get("classKo") or raw.get("label") or "").strip()
        if not class_ko:
            continue
        bbox = raw.get("bbox_norm_xywh")
        if not bbox:
            cx = float(raw.get("cx", 0.5))
            cy = float(raw.get("cy", 0.5))
            w = float(raw.get("w", 0.1))
            h = float(raw.get("h", 0.1))
            bbox = [round(cx - w / 2, 6), round(cy - h / 2, 6), round(w, 6), round(h, 6)]
        bbox = [round(float(v), 6) for v in bbox[:4]]
        obj = {
            "class": str(raw.get("class") or raw.get("class_name") or class_ko),
            "class_ko": class_ko,
            "confidence": round(float(raw.get("confidence", 0.0)), 4),
            "bbox_norm_xywh": bbox,
            "direction": _direction_from_bbox({**raw, "bbox_norm_xywh": bbox}),
            "depth_source": str(raw.get("depth_source", "on_device_bbox")),
            "is_vehicle": bool(raw.get("is_vehicle", class_ko in vehicle_ko)),
            "is_animal": bool(raw.get("is_animal", class_ko in animal_ko)),
            "is_dangerous": bool(raw.get("is_dangerous", class_ko in critical_ko)),
        }
        obj["distance_m"] = _distance_from_bbox({**raw, "bbox_norm_xywh": bbox})
        obj["risk_score"] = _risk_from_object(obj, critical_ko, caution_ko, everyday_ko, animal_ko, thresholds)
        objects.append(obj)
    return sorted(objects, key=lambda x: x.get("risk_score", 0), reverse=True)[:8]


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
    client_perf = payload.get("client_perf") or {}
    _detect_ms = int(client_perf.get("infer_ms", 0) or 0)

    _t_tracker = _time.monotonic()
    tracker = get_tracker(session_id)
    objects, motion_changes = tracker.update(objects)
    # voting 필터가 모두 걸러낸 경우 pre-tracker 원본을 DB 히스토리 저장에 사용
    _save_objs = objects or current_objects
    nlg_objects = current_objects if mode in {"찾기", "질문", "들고있는것"} and current_objects else objects
    _tracker_ms = int((_time.monotonic() - _t_tracker) * 1000)

    should_persist = _should_persist_frame(session_id, _save_objs, mode)
    previous = db.get_snapshot(session_id) if should_persist else None
    space_changes = _space_changes(objects, previous) if previous and objects else []
    if objects and should_persist:
        db.save_snapshot(session_id, objects)
        _mark_persisted(session_id, objects)
    elif should_persist and _save_objs:
        # tracker가 모두 필터링한 경우에도 시그니처 업데이트 → 중복 저장 방지
        _mark_persisted(session_id, _save_objs)

    all_changes = motion_changes + space_changes
    db_enqueued = False
    if should_persist and _save_objs:
        db_enqueued = db.enqueue_detection_event(
            event_id=event_id,
            request_id=request_id,
            session_id=session_id,
            device_id=device_id,
            wifi_ssid=wifi_ssid,
            mode=mode,
            objects=_save_objs,
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
    if should_persist and _save_objs:
        db.save_performance_metric(
            session_id=session_id, device_id=device_id, event_id=event_id,
            client_perf=client_perf,
            server_perf=response_payload.get("perf", {}),
            object_count=len(_save_objs),
        )
        db.save_alert_decision(
            event_id=event_id, session_id=session_id,
            alert_mode=alert_mode, objects=objects,
            spoken_sentence=sentence,
        )
    await _publish_dashboard_event(session_id, response_payload, db.get_last_gps(session_id), db.get_gps_track(session_id, limit=100))
    return response_payload

def _extract_find_target(text: str) -> str:
    verbs = ["찾아줘", "찾아", "어디있어", "어디 있어", "어디야", "어딘지", "어디에 있어", "어디에 있나", "있는지 알려줘"]
    label = text
    for v in verbs: label = label.replace(v, "")
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
    if mode == "들고있는것":
        sentence = build_held_sentence(objects)
        alert_mode = "critical"
    elif mode == "찾기":
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
    _cur_objs = get_tracker(session_id).get_current_state(max_age_s=8.0) or []
    await events.publish(session_id, {
        "session_id": session_id,
        "objects": _cur_objs,
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
        return {
            "saved": False,
            "sentence": "저장할 장소 이름이 없어요.",
            "label": label,
            "wifi_ssid": scope,
        }
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
    locations = []
    for s in db.get_recent_sessions(limit=20):
        gps = db.get_last_gps(s)
        if gps and gps.get("lat") and gps.get("lng"):
            locations.append({"session_id": s, "lat": gps["lat"], "lng": gps["lng"]})
    return {"locations": locations}

@router.get("/dashboard/summary", dependencies=[Depends(_verify_api_key)])
async def get_dashboard_summary():
    """전체 단말 기준 최근 24시간 탐지 통계.

    대시보드가 선택 세션뿐 아니라 모든 단말의 총 탐지 건수와 세션별 요약을
    보여주도록 제공한다. 데모 영상에서 클라이언트 화면과 대시보드의 세션이
    서로 매칭되는지 설명할 때 사용한다.
    """
    return db.get_dashboard_summary_24h(limit=500)

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


@router.get("/heatmap/{session_id}", dependencies=[Depends(_verify_api_key)])
async def get_heatmap(session_id: str, hours: int = 24):
    """위험 구간 히트맵 데이터 조회 — 대시보드 지도 오버레이 전용.

    detection_events의 GPS 좌표 + risk_score를 집계해 히트맵 포인트 목록을 반환한다.
    반환된 intensity(0~1)를 Leaflet.heat가 색상 강도로 표현한다.
    """
    req_session_id = _normalize_session_id(device_id=session_id)
    points = db.get_heatmap_data(req_session_id, hours=hours)
    return {"session_id": req_session_id, "hours": hours, "points": points}


@router.get("/pedestrian-hotspots/summary", dependencies=[Depends(_verify_api_key)])
async def get_pedestrian_hotspot_summary():
    """Dashboard summary for preprocessed pedestrian accident hotspots."""
    return _require_json_artifact(_PEDESTRIAN_SUMMARY_PATH)


@router.get("/pedestrian-hotspots/clusters", dependencies=[Depends(_verify_api_key)])
async def get_pedestrian_hotspot_clusters(risk_level: str = "high", limit: int = 300):
    """Return clustered pedestrian accident hotspots as GeoJSON.

    The dashboard uses clustered points instead of the full polygon dataset by
    default so the map stays responsive while still showing repeated danger
    areas. Pass risk_level=all to include every cluster.
    """
    limit = max(1, min(limit, 2000))
    wanted = {item.strip() for item in risk_level.split(",") if item.strip()}
    include_all = not wanted or "all" in wanted
    geojson = _require_json_artifact(_PEDESTRIAN_CLUSTERS_PATH)
    features = geojson.get("features", [])
    if not include_all:
        features = [
            feature for feature in features
            if feature.get("properties", {}).get("risk_level") in wanted
        ]
    features = sorted(
        features,
        key=lambda feature: feature.get("properties", {}).get("max_risk_score", 0),
        reverse=True,
    )[:limit]
    return {
        "type": "FeatureCollection",
        "features": features,
        "count": len(features),
        "risk_level": risk_level,
    }


@router.get("/pedestrian-hotspots/nearby", dependencies=[Depends(_verify_api_key)])
async def get_nearby_pedestrian_hotspots(
    lat: float,
    lng: float,
    radius_m: float = 300.0,
    limit: int = 10,
):
    """Return nearby pedestrian accident hotspot clusters for GPS-based warnings."""
    radius_m = max(10.0, min(radius_m, 2000.0))
    limit = max(1, min(limit, 50))
    geojson = _require_json_artifact(_PEDESTRIAN_CLUSTERS_PATH)
    nearby = []
    for feature in geojson.get("features", []):
        props = dict(feature.get("properties", {}))
        center_lat = float(props.get("center_lat", feature["geometry"]["coordinates"][1]))
        center_lng = float(props.get("center_lng", feature["geometry"]["coordinates"][0]))
        distance = _distance_m(lat, lng, center_lat, center_lng)
        if distance <= radius_m:
            props["distance_m"] = round(distance, 1)
            nearby.append({**feature, "properties": props})
    nearby.sort(
        key=lambda feature: (
            feature["properties"]["distance_m"],
            -float(feature["properties"].get("max_risk_score", 0)),
        )
    )
    return {
        "type": "FeatureCollection",
        "features": nearby[:limit],
        "count": len(nearby[:limit]),
        "radius_m": radius_m,
    }


@router.get("/disabled-population/summary", dependencies=[Depends(_verify_api_key)])
async def get_disabled_population_summary():
    """Latest registered disabled population summary for dashboard context."""
    return _require_json_artifact(_DISABLED_POPULATION_SUMMARY_PATH)


@router.get("/disabled-population/regions", dependencies=[Depends(_verify_api_key)])
async def get_disabled_population_regions(limit: int = 20, sido: str = ""):
    """Return latest visual disability counts by administrative region."""
    limit = max(1, min(limit, 300))
    regions = _require_json_artifact(_DISABLED_POPULATION_REGIONS_PATH)
    if sido:
        regions = [row for row in regions if row.get("sido") == sido]
    return {
        "regions": regions[:limit],
        "count": len(regions[:limit]),
        "limit": limit,
        "sido": sido,
    }


@router.get("/disabled-population/nearby", dependencies=[Depends(_verify_api_key)])
async def get_nearby_disabled_population_context(
    lat: float,
    lng: float,
    radius_m: float = 3000.0,
):
    """Return visual disability context for the city/district nearest the current GPS."""
    radius_m = max(100.0, min(radius_m, 10000.0))
    summary = _require_json_artifact(_DISABLED_POPULATION_SUMMARY_PATH)
    geojson = _require_json_artifact(_PEDESTRIAN_CLUSTERS_PATH)

    nearest: tuple[float, dict] | None = None
    for feature in geojson.get("features", []):
        props = dict(feature.get("properties", {}))
        center_lat = float(props.get("center_lat", feature["geometry"]["coordinates"][1]))
        center_lng = float(props.get("center_lng", feature["geometry"]["coordinates"][0]))
        distance = _distance_m(lat, lng, center_lat, center_lng)
        if distance > radius_m:
            continue
        if nearest is None or distance < nearest[0]:
            nearest = (distance, props)

    region = None
    matched_hotspot = None
    if nearest is not None:
        distance, props = nearest
        district = props.get("representative_district") or props.get("representative_place_name") or ""
        sido, sigungu_candidates = _parse_hotspot_district(str(district))
        region = _find_disabled_region(sido, sigungu_candidates)
        matched_hotspot = {
            "cluster_id": props.get("cluster_id"),
            "display_name": props.get("display_name"),
            "district": district,
            "distance_m": round(distance, 1),
        }

    return {
        "summary": summary,
        "region": region,
        "matched_hotspot": matched_hotspot,
        "scope": "region" if region else "national",
        "radius_m": radius_m,
    }


@router.get("/disabled-population/trend", dependencies=[Depends(_verify_api_key)])
async def get_disabled_population_trend():
    """Return monthly visual disability trend data."""
    return {"trend": _require_json_artifact(_DISABLED_POPULATION_TREND_PATH)}


@router.get("/disabled-population/types", dependencies=[Depends(_verify_api_key)])
async def get_disabled_population_types():
    """Return latest registered disabled population by disability type."""
    return {"types": _require_json_artifact(_DISABLED_POPULATION_BY_TYPE_PATH)}


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

# ── 장소 저장 / 조회 / 검색 / 삭제 ──────────────────────────────────────────
# Android 앱이 SharedPreferences 외에 서버에도 장소를 동기화할 수 있도록 제공.
# db.py에 save_location / get_locations / find_location / delete_location 완비.
@router.post("/locations/save", dependencies=[Depends(_verify_api_key)])
async def save_location(body: dict):
    """장소 저장: {"label": "집", "wifi_ssid": "HomeWifi"}"""
    label    = (body.get("label") or "").strip()
    wifi_ssid = (body.get("wifi_ssid") or "").strip()
    if not label:
        return {
            "saved": False,
            "sentence": "저장할 장소 이름이 없어요.",
            "label": label,
        }
    db.save_location(label, wifi_ssid)
    ig = _i_ga(label)
    return {
        "saved": True,
        "sentence": f"{label}{ig} 저장됐어요.",
        "label": label,
        "wifi_ssid": wifi_ssid,
    }

@router.get("/locations", dependencies=[Depends(_verify_api_key)])
async def list_locations(wifi_ssid: str = ""):
    """저장된 장소 목록 조회. wifi_ssid 파라미터로 필터링 가능."""
    locations = db.get_locations(wifi_ssid=wifi_ssid)
    if not locations:
        sentence = "저장된 장소가 없어요."
    else:
        names = ", ".join(loc["label"] for loc in locations[:5])
        suffix = f" 외 {len(locations) - 5}곳" if len(locations) > 5 else ""
        sentence = f"저장된 장소는 {names}{suffix} 이에요."
    return {"locations": locations, "sentence": sentence}

@router.get("/locations/find/{label}", dependencies=[Depends(_verify_api_key)])
async def find_location(label: str):
    """장소 검색: label 부분 일치 검색."""
    result = db.find_location(label)
    if result:
        ig = _i_ga(label)
        return {
            "found": True,
            "location": result,
            "sentence": f"{label}{ig} 저장돼 있어요.",
        }
    ig = _i_ga(label)
    return {
        "found": False,
        "location": None,
        "sentence": f"{label}{ig} 저장된 장소에 없어요.",
    }

@router.delete("/locations/{label}", dependencies=[Depends(_verify_api_key)])
async def delete_location(label: str):
    """저장된 장소 삭제."""
    db.delete_location(label)
    from src.nlg.sentence import _i_ga as _ig
    return {
        "deleted": True,
        "sentence": f"{label}을(를) 삭제했어요.",
        "label": label,
    }


# ── 장소 저장 / 조회 / 검색 / 삭제 ──────────────────────────────────────────
# Android 앱이 SharedPreferences 외에 서버에도 장소를 동기화할 수 있도록 제공.
# db.py에 save_location / get_locations / find_location / delete_location 완비.
@router.post("/locations/save", dependencies=[Depends(_verify_api_key)])
async def save_location_endpoint(body: dict):
    """장소 저장: {"label": "집", "wifi_ssid": "HomeWifi"}"""
    label     = (body.get("label") or "").strip()
    wifi_ssid = (body.get("wifi_ssid") or "").strip()
    if not label:
        return {
            "saved": False,
            "sentence": "저장할 장소 이름이 없어요.",
            "label": label,
        }
    db.save_location(label, wifi_ssid)
    ig = _i_ga(label)
    return {
        "saved": True,
        "sentence": f"{label}{ig} 저장됐어요.",
        "label": label,
        "wifi_ssid": wifi_ssid,
    }

@router.get("/locations", dependencies=[Depends(_verify_api_key)])
async def list_locations_endpoint(wifi_ssid: str = ""):
    """저장된 장소 목록 조회. wifi_ssid 파라미터로 필터링 가능."""
    locations = db.get_locations(wifi_ssid=wifi_ssid)
    if not locations:
        sentence = "저장된 장소가 없어요."
    else:
        names = ", ".join(loc["label"] for loc in locations[:5])
        suffix = f" 외 {len(locations) - 5}곳" if len(locations) > 5 else ""
        sentence = f"저장된 장소는 {names}{suffix} 이에요."
    return {"locations": locations, "sentence": sentence}

@router.get("/locations/find/{label}", dependencies=[Depends(_verify_api_key)])
async def find_location_endpoint(label: str):
    """장소 검색: label 부분 일치 검색."""
    result = db.find_location(label)
    if result:
        ig = _i_ga(label)
        return {
            "found": True,
            "location": result,
            "sentence": f"{label}{ig} 저장돼 있어요.",
        }
    ig = _i_ga(label)
    return {
        "found": False,
        "location": None,
        "sentence": f"{label}{ig} 저장된 장소에 없어요.",
    }

@router.delete("/locations/{label}", dependencies=[Depends(_verify_api_key)])
async def delete_location_endpoint(label: str):
    """저장된 장소 삭제."""
    db.delete_location(label)
    eul_reul = "을" if (ord(label[-1]) - 0xAC00) % 28 != 0 else "를"
    return {
        "deleted": True,
        "sentence": f"{label}{eul_reul} 삭제했어요.",
        "label": label,
    }
