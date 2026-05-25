import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"  # Windows OpenMP 라이브러리 충돌 방지

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


def test_address_like_session_ids_are_not_kept_or_listed():
    private_address = "서울특별시 동작구 상도로 12"
    response = client.post("/detect", json={"device_id": private_address, "objects": []})
    assert response.status_code == 200
    assert response.json()["session_id"] == "__default__"

    sessions = client.get("/sessions")
    assert sessions.status_code == 200
    assert private_address not in sessions.json()["sessions"]

    summary = client.get("/dashboard/summary")
    assert summary.status_code == 200
    assert private_address not in [s["session_id"] for s in summary.json()["sessions"]]


def test_voiceguide_final_dashboard_endpoints():
    summary = client.get("/voiceguide-final/summary")
    assert summary.status_code == 200
    body = summary.json()
    assert body["selected_route"]["route_id"] == "B"
    assert body["selected_route"]["facilities"]["installed"]["audio_signal"] is True
    assert body["tier_counts"]["preferred"] > 0
    assert body["improvement_candidates"]

    geo = client.get("/voiceguide-final/crosswalks.geojson", params={"limit": 5})
    assert geo.status_code == 200
    geo_body = geo.json()
    assert geo_body["type"] == "FeatureCollection"
    assert geo_body["count"] == 5
    props = geo_body["features"][0]["properties"]
    assert "address" not in props
    assert "installed" in props


def test_pedestrian_hotspot_dashboard_endpoints():
    summary = client.get("/pedestrian-hotspots/summary")
    assert summary.status_code == 200
    summary_body = summary.json()
    assert summary_body["record_count"] == 1984
    assert summary_body["risk_level_counts"]["high"] > 0

    clusters = client.get("/pedestrian-hotspots/clusters", params={"risk_level": "high", "limit": 5})
    assert clusters.status_code == 200
    clusters_body = clusters.json()
    assert clusters_body["type"] == "FeatureCollection"
    assert clusters_body["count"] == 5
    first = clusters_body["features"][0]
    assert first["geometry"]["type"] == "Point"
    assert first["properties"]["risk_level"] == "high"
    assert first["properties"]["max_risk_score"] >= clusters_body["features"][-1]["properties"]["max_risk_score"]

    nearby = client.get(
        "/pedestrian-hotspots/nearby",
        params={"lat": 37.612888751869, "lng": 127.030288014848, "radius_m": 300},
    )
    assert nearby.status_code == 200
    nearby_body = nearby.json()
    assert nearby_body["count"] >= 1
    assert nearby_body["features"][0]["properties"]["distance_m"] <= 300


def test_disabled_population_dashboard_endpoints():
    summary = client.get("/disabled-population/summary")
    assert summary.status_code == 200
    summary_body = summary.json()
    assert summary_body["month"]["latest"] == "202604"
    assert summary_body["latest"]["visual_disabled"] == 245198
    assert summary_body["latest"]["visual_by_degree"]["심한 장애"] == 43918

    regions = client.get("/disabled-population/regions", params={"limit": 3})
    assert regions.status_code == 200
    regions_body = regions.json()
    assert regions_body["count"] == 3
    assert regions_body["regions"][0]["visual_disabled"] >= regions_body["regions"][-1]["visual_disabled"]

    nearby = client.get(
        "/disabled-population/nearby",
        params={"lat": 37.612888751869, "lng": 127.030288014848, "radius_m": 3000},
    )
    assert nearby.status_code == 200
    nearby_body = nearby.json()
    assert nearby_body["scope"] == "region"
    assert nearby_body["region"]["sido"] == "서울특별시"
    assert nearby_body["region"]["sigungu"] == "강북구"
    assert nearby_body["region"]["visual_disabled"] == 1852
    assert nearby_body["matched_hotspot"]["distance_m"] <= 3000

    trend = client.get("/disabled-population/trend")
    assert trend.status_code == 200
    trend_body = trend.json()
    assert len(trend_body["trend"]) == 64
    assert trend_body["trend"][-1]["month"] == "202604"


def test_disabled_gender_degree_dashboard_endpoints():
    summary = client.get("/disabled-gender-degree/summary")
    assert summary.status_code == 200
    summary_body = summary.json()
    assert summary_body["month"]["latest"] == "202604"
    assert summary_body["latest"]["total_disabled"] == 2624025
    assert summary_body["latest"]["by_gender"]["남자"] == 1523612
    assert summary_body["latest"]["by_gender"]["여자"] == 1100413
    assert summary_body["latest"]["by_degree"]["심한 장애"] == 961628
    assert summary_body["latest"]["by_degree"]["심하지 않은 장애"] == 1662397

    regions = client.get("/disabled-gender-degree/regions", params={"limit": 3})
    assert regions.status_code == 200
    regions_body = regions.json()
    assert regions_body["count"] == 3
    assert regions_body["regions"][0]["total_disabled"] >= regions_body["regions"][-1]["total_disabled"]

    nearby = client.get(
        "/disabled-gender-degree/nearby",
        params={"lat": 37.612888751869, "lng": 127.030288014848, "radius_m": 3000},
    )
    assert nearby.status_code == 200
    nearby_body = nearby.json()
    assert nearby_body["scope"] == "region"
    assert nearby_body["region"]["sido"] == "서울특별시"
    assert nearby_body["region"]["sigungu"] == "강북구"
    assert nearby_body["region"]["total_disabled"] == 16567
    assert nearby_body["region"]["male"] == 9291
    assert nearby_body["region"]["female"] == 7276

    trend = client.get("/disabled-gender-degree/trend")
    assert trend.status_code == 200
    trend_body = trend.json()
    assert len(trend_body["trend"]) == 4
    assert trend_body["trend"][-1]["month"] == "202604"


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
