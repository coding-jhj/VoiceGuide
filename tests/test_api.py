import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"  # Windows OpenMP 라이브러리 충돌 방지
import tempfile
from pathlib import Path

_TEST_DB_DIR = tempfile.TemporaryDirectory(prefix="voiceguide-api-test-")
os.environ["VOICEGUIDE_DB_PATH"] = str(Path(_TEST_DB_DIR.name) / "voiceguide_test.db")

from fastapi.testclient import TestClient
from src.api.main import app
from src.api import db
from src.api import routes
import uuid

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


def test_scenario_data_summary_endpoint():
    response = client.get("/scenario-data/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["counts"]["dongjak_crosswalks"] == 1025
    assert body["counts"]["route_recommendation_tiers"]["preferred"] == 54
    assert body["demo_pair"]["shortest_route_crosswalk_a"]["main_crosswalk_id"] == "06-0000016344"
    assert body["demo_pair"]["safer_route_crosswalk_b"]["main_crosswalk_id"] == "06-0000032157"


def test_scenario_data_crosswalk_geojson_endpoint():
    response = client.get("/scenario-data/crosswalks.geojson")

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) == 1025


def test_dashboard_loads_scenario_data_api():
    response = client.get("/dashboard")

    assert response.status_code == 200
    assert "/scenario-data/summary" in response.text
    assert "loadScenarioData()" in response.text


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


def test_detect_preserves_android_risk_and_vibration_pattern():
    payload = {
        "event_id": "evt-client-judgement-1",
        "request_id": "req-client-judgement-1",
        "device_id": "client_judgement_device",
        "wifi_ssid": "client_judgement_wifi",
        "mode": "obstacle",
        "camera_orientation": "front",
        "objects": [
            {
                "class_ko": "box",
                "confidence": 0.88,
                "bbox_norm_xywh": [0.35, 0.40, 0.18, 0.20],
                "distance_m": 1.2,
                "risk_score": 0.92,
                "vibration_pattern": "DOUBLE",
            }
        ],
    }

    response = client.post("/detect", json=payload)

    assert response.status_code == 200
    obj = response.json()["objects"][0]
    assert obj["risk_score"] == 0.92
    assert obj["vibration_pattern"] == "DOUBLE"
    assert obj["depth_source"] == "on_device_bbox"


def test_detect_json_uses_same_on_device_depth_source_name():
    payload = {
        "device_id": "detect_json_depth_device",
        "wifi_ssid": "detect_json_depth_wifi",
        "request_id": "req-detect-json-depth",
        "mode": "obstacle",
        "camera_orientation": "front",
        "detections": [
            {
                "class_ko": "box",
                "confidence": 0.88,
                "cx": 0.5,
                "cy": 0.5,
                "w": 0.18,
                "h": 0.20,
                "zone": "12시",
                "dist_m": 1.2,
                "risk_score": 0.83,
                "vibration_pattern": "URGENT",
            }
        ],
    }

    response = client.post("/detect_json", json=payload)

    assert response.status_code == 200
    obj = response.json()["objects"][0]
    assert obj["depth_source"] == "on_device_bbox"
    assert obj["risk_score"] == 0.83
    assert obj["vibration_pattern"] == "URGENT"


def test_detect_does_not_smooth_android_risk_across_frames():
    session = "client_risk_stream"
    first = {
        "event_id": "evt-client-risk-stream-1",
        "request_id": "req-client-risk-stream-1",
        "device_id": session,
        "wifi_ssid": session,
        "mode": "obstacle",
        "objects": [
            {
                "class_ko": "box",
                "confidence": 0.90,
                "bbox_norm_xywh": [0.40, 0.40, 0.20, 0.20],
                "distance_m": 2.0,
                "risk_score": 0.10,
                "vibration_pattern": "NONE",
            }
        ],
    }
    second = {
        **first,
        "event_id": "evt-client-risk-stream-2",
        "request_id": "req-client-risk-stream-2",
        "objects": [
            {
                **first["objects"][0],
                "risk_score": 0.90,
                "vibration_pattern": "URGENT",
            }
        ],
    }

    assert client.post("/detect", json=first).status_code == 200
    response = client.post("/detect", json=second)

    assert response.status_code == 200
    obj = response.json()["objects"][0]
    assert obj["risk_score"] == 0.90
    assert obj["vibration_pattern"] == "URGENT"


def test_detect_preserves_android_distance_and_exposes_smoothed_distance():
    session = f"client_distance_stream_{uuid.uuid4().hex}"
    first = {
        "event_id": f"evt-{session}-1",
        "request_id": f"req-{session}-1",
        "device_id": session,
        "wifi_ssid": session,
        "mode": "obstacle",
        "objects": [
            {
                "class_ko": "box",
                "confidence": 0.90,
                "bbox_norm_xywh": [0.40, 0.40, 0.20, 0.20],
                "distance_m": 4.0,
                "risk_score": 0.10,
                "vibration_pattern": "NONE",
            }
        ],
    }
    second = {
        **first,
        "event_id": f"evt-{session}-2",
        "request_id": f"req-{session}-2",
        "objects": [
            {
                **first["objects"][0],
                "distance_m": 1.0,
                "risk_score": 0.90,
                "vibration_pattern": "URGENT",
            }
        ],
    }

    assert client.post("/detect", json=first).status_code == 200
    response = client.post("/detect", json=second)

    assert response.status_code == 200
    obj = response.json()["objects"][0]
    assert obj["distance_m"] == 1.0
    assert obj["smoothed_distance_m"] == 2.3


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


def test_detect_json_persists_normalized_bbox_distance_and_direction():
    session = f"detect_json_normalized_{uuid.uuid4().hex}"
    payload = {
        "device_id": session,
        "wifi_ssid": session,
        "request_id": f"req-{session}",
        "mode": "장애물",
        "camera_orientation": "front",
        "detections": [
            {
                "class_ko": "상자",
                "confidence": 0.77,
                "bbox_norm_xywh": [0.25, 0.30, 0.40, 0.20],
                "direction": "10시",
                "distance_m": 2.6,
                "is_vehicle": False,
                "is_animal": False,
            }
        ],
    }

    response = client.post("/detect_json", json=payload)

    assert response.status_code == 200
    recent = db.get_recent_detections(session, max_age_s=60)
    assert recent
    assert recent[0]["class_ko"] == "상자"
    assert recent[0]["zone"] == "10시"
    assert recent[0]["dist_m"] == 2.6
    assert recent[0]["cx"] == 0.45
    assert recent[0]["cy"] == 0.40
    assert recent[0]["w"] == 0.40
    assert recent[0]["h"] == 0.20


def test_spaces_snapshot_endpoint():
    # 공간 스냅샷 수동 저장 엔드포인트 — 디버깅/테스트 전용
    payload = {"space_id": "test_ssid", "objects": []}
    response = client.post("/spaces/snapshot", json=payload)
    assert response.status_code == 200
    assert response.json() == {"saved": True}


def test_locations_route_saves_and_lists_by_session():
    session = f"test_locations_{uuid.uuid4().hex}"
    label = "테스트 출입구"

    save = client.post(
        "/locations/save",
        json={"label": label, "wifi_ssid": session},
    )
    assert save.status_code == 200
    assert save.json()["saved"] is True
    assert save.json()["location"]["label"] == label
    assert "sentence" in save.json()

    listed = client.get("/locations", params={"wifi_ssid": session})
    assert listed.status_code == 200
    body = listed.json()
    assert "sentence" in body
    assert body["locations"][0]["label"] == label
    assert body["locations"][0]["wifi_ssid"] == session


def test_locations_route_finds_and_deletes_by_session():
    session = f"test_locations_{uuid.uuid4().hex}"
    label = "테스트 엘리베이터"
    client.post("/locations/save", json={"label": label, "wifi_ssid": session})

    found = client.get(f"/locations/find/{label}", params={"wifi_ssid": session})
    assert found.status_code == 200
    assert found.json()["found"] is True
    assert found.json()["location"]["label"] == label

    deleted = client.delete(f"/locations/{label}", params={"wifi_ssid": session})
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True

    missing = client.get(f"/locations/find/{label}", params={"wifi_ssid": session})
    assert missing.status_code == 404


def test_protected_status_requires_api_key(monkeypatch):
    # API_KEY 설정 시 X-API-Key 헤더 없이 접근하면 401 반환, 헤더 포함 시 200 반환
    monkeypatch.setattr(routes, "_API_KEY", "test-secret")
    response = client.get("/status/test_ssid")
    assert response.status_code == 401  # 인증 없이 거부

    ok = client.get("/status/test_ssid", headers={"X-API-Key": "test-secret"})
    assert ok.status_code == 200  # 올바른 키로 통과
