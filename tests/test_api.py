import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"  # Windows OpenMP 라이브러리 충돌 방지

from fastapi.testclient import TestClient
from src.api.main import app
from src.api import db
from src.api import routes

db.init_db()

# TestClient: uvicorn 서버 없이 FastAPI 앱을 직접 테스트 (httpx 기반)
client = TestClient(app)


def test_policy_endpoint():
    r = client.get("/api/policy")
    assert r.status_code == 200
    body = r.json()
    assert body.get("version", 0) >= 1
    assert "classes" in body
    assert "vehicle_ko" in body["classes"]


def test_root_redirects_to_dashboard():
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/dashboard"


def test_detect_endpoint_exists():
    # /detect는 온디바이스 탐지 결과 JSON을 받는다.
    response = client.post("/detect", json={"device_id": "test_device", "objects": []})
    assert response.status_code == 200


def test_detect_response_schema():
    # 정상 탐지 JSON 전송 시 응답 필드 구조가 Android 앱 기대 스키마와 일치하는지 확인
    payload = {
        "event_id": "evt-test-1",
        "request_id": "req-test-1",
        "device_id": "test_device",
        "wifi_ssid": "test_wifi",
        "mode": "장애물",
        "camera_orientation": "front",
        "objects": [
            {
                "class_ko": "의자",
                "confidence": 0.91,
                "bbox_norm_xywh": [0.4, 0.45, 0.2, 0.25],
            }
        ],
        "client_perf": {"infer_ms": 12},
    }
    response = client.post(
        "/detect",
        json=payload,
    )
    assert response.status_code == 200
    body = response.json()
    assert "sentence"     in body   # TTS로 바로 읽을 한국어 문장
    assert "objects"      in body   # YOLO 탐지 물체 목록
    assert "hazards"      in body   # 바닥 위험 감지 필드 추가됨
    assert "changes"      in body   # 공간 기억 변화 목록
    assert "depth_source" in body   # on-device bbox 기반 거리 추정 방법
    assert "event_id"     in body
    assert "session_id"   in body
    assert isinstance(body["sentence"], str)
    assert isinstance(body["objects"],  list)
    assert isinstance(body["hazards"],  list)
    assert isinstance(body["changes"],  list)
    assert len(body["sentence"]) > 0  # 빈 문장 반환 금지
    assert body["objects"][0]["depth_source"] == "on_device_bbox"


def test_detect_json_persists_recent_detections():
    payload = {
        "device_id": "test_detect_json_device",
        "wifi_ssid": "test_detect_json_wifi",
        "request_id": "req-detect-json-1",
        "mode": "장애물",
        "camera_orientation": "front",
        "lat": 37.5665,
        "lng": 126.9780,
        "detections": [
            {
                "class_ko": "의자",
                "confidence": 0.91,
                "cx": 0.5,
                "cy": 0.55,
                "w": 0.2,
                "h": 0.25,
                "zone": "12시",
                "dist_m": 1.5,
            }
        ],
    }
    response = client.post("/detect_json", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["sentence"]
    assert body["objects"][0]["class_ko"] == "의자"

    from src.api.routes import _normalize_session_id
    expected_session = _normalize_session_id(wifi_ssid="test_detect_json_wifi", device_id="test_detect_json_device")
    recent = db.get_recent_detections(expected_session, max_age_s=60)
    assert recent
    assert recent[0]["class_ko"] == "의자"


def test_detect_json_held_mode_uses_item_confirmation_sentence():
    payload = {
        "device_id": "held_mode_device",
        "wifi_ssid": "held_mode_wifi",
        "request_id": "req-held-mode-1",
        "mode": "들고있는것",
        "camera_orientation": "front",
        "detections": [
            {
                "class_ko": "의자",
                "confidence": 0.86,
                "cx": 0.45,
                "cy": 0.55,
                "w": 0.20,
                "h": 0.25,
                "zone": "12시",
                "dist_m": 2.2,
            },
            {
                "class_ko": "컵",
                "confidence": 0.88,
                "cx": 0.50,
                "cy": 0.58,
                "w": 0.35,
                "h": 0.40,
                "zone": "12시",
                "dist_m": 0.6,
            },
        ],
    }
    response = client.post("/detect_json", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "들고있는것"
    assert body["alert_mode"] == "critical"
    assert body["sentence"] == "손에 들고 있는 건 컵이에요."


def test_spaces_snapshot_endpoint():
    # 공간 스냅샷 수동 저장 엔드포인트 — 디버깅/테스트 전용
    payload = {"space_id": "test_ssid", "objects": []}
    response = client.post("/spaces/snapshot", json=payload)
    assert response.status_code == 200
    assert response.json() == {"saved": True}


def test_status_includes_risk_score_after_detect():
    """대시보드 실시간 위험도: /detect 후 tracker 상태에 risk_score(0~1)가 포함되는지."""
    payload = {
        "device_id": "dash_risk_dev",
        "wifi_ssid": "dash_risk_wifi",
        "mode": "장애물",
        "camera_orientation": "front",
        "objects": [
            {
                "class_ko": "사람",
                "confidence": 0.9,
                "bbox_norm_xywh": [0.25, 0.25, 0.4, 0.45],
            },
            {
                "class_ko": "의자",
                "confidence": 0.85,
                "bbox_norm_xywh": [0.6, 0.55, 0.08, 0.1],
            },
        ],
    }
    dr = client.post("/detect", json=payload)
    assert dr.status_code == 200
    session_id = dr.json()["session_id"]
    sr = client.get(f"/status/{session_id}")
    assert sr.status_code == 200
    objects = sr.json().get("objects") or []
    assert len(objects) >= 1
    for o in objects:
        assert "risk_score" in o
        rs = float(o["risk_score"])
        assert 0.0 <= rs <= 1.0
    ranked = sorted(objects, key=lambda x: float(x.get("risk_score", 0)), reverse=True)
    assert ranked[0]["class_ko"] == "사람"


def test_dashboard_summary_groups_recent_events_by_session():
    payload = {
        "device_id": "summary_device",
        "wifi_ssid": "summary_wifi",
        "mode": "장애물",
        "camera_orientation": "front",
        "objects": [
            {
                "class_ko": "자동차",
                "confidence": 0.92,
                "bbox_norm_xywh": [0.45, 0.45, 0.4, 0.45],
            }
        ],
    }
    dr = client.post("/detect", json=payload)
    assert dr.status_code == 200
    session_id = dr.json()["session_id"]

    # /detect 저장은 background writer queue를 사용하므로 테스트에서 writer를 켜고 대기한다.
    db.start_event_writer()
    db._event_queue.join()

    sr = client.get("/dashboard/summary")
    assert sr.status_code == 200
    body = sr.json()
    assert body["summary"]["total"] >= 1

    sessions = {s["session_id"]: s for s in body["sessions"]}
    assert session_id in sessions
    assert sessions[session_id]["total"] >= 1
    assert sessions[session_id]["critical"] >= 1
    assert sessions[session_id]["top_objects"][0]["class_ko"] == "자동차"


def test_protected_status_requires_api_key(monkeypatch):
    # API_KEY 설정 시 X-API-Key 헤더 없이 접근하면 401 반환, 헤더 포함 시 200 반환
    monkeypatch.setattr(routes, "_API_KEY", "test-secret")
    response = client.get("/status/test_ssid")
    assert response.status_code == 401  # 인증 없이 거부

    ok = client.get("/status/test_ssid", headers={"X-API-Key": "test-secret"})
    assert ok.status_code == 200  # 올바른 키로 통과


# ── /locations 엔드포인트 테스트 ──────────────────────────────────────────────
def test_locations_save_and_list():
    """장소 저장 후 목록 조회 — sentence 필드 포함 확인."""
    # 저장
    r = client.post("/locations/save", json={"label": "테스트카페", "wifi_ssid": "CafeWifi"})
    assert r.status_code == 200
    body = r.json()
    assert body["saved"] is True
    assert "sentence" in body
    assert "테스트카페" in body["sentence"]

    # 목록 조회
    r2 = client.get("/locations")
    assert r2.status_code == 200
    locs = r2.json()
    assert "locations" in locs
    assert "sentence" in locs
    labels = [loc["label"] for loc in locs["locations"]]
    assert "테스트카페" in labels


def test_locations_find():
    """장소 검색 — 부분 일치 확인."""
    client.post("/locations/save", json={"label": "집앞편의점", "wifi_ssid": "ConvWifi"})
    r = client.get("/locations/find/편의점")
    assert r.status_code == 200
    body = r.json()
    assert body["found"] is True
    assert "sentence" in body


def test_locations_save_empty_label():
    """빈 label 저장 시 saved=False 반환."""
    r = client.post("/locations/save", json={"label": "", "wifi_ssid": "SomeWifi"})
    assert r.status_code == 200
    assert r.json()["saved"] is False


def test_locations_delete():
    """장소 삭제 — deleted=True 반환."""
    client.post("/locations/save", json={"label": "삭제테스트", "wifi_ssid": "DelWifi"})
    r = client.delete("/locations/삭제테스트")
    assert r.status_code == 200
    assert r.json()["deleted"] is True
