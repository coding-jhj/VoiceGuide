import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)


def test_detect_endpoint_exists():
    response = client.post("/detect", data={"wifi_ssid": "test_ssid"})
    assert response.status_code in (200, 422)


def test_detect_response_schema(sample_jpeg_bytes):
    response = client.post(
        "/detect",
        files={"image": ("test.jpg", sample_jpeg_bytes, "image/jpeg")},
        data={"wifi_ssid": "test_wifi"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "sentence"     in body
    assert "objects"      in body
    assert "hazards"      in body   # 바닥 위험 감지 필드 추가됨
    assert "changes"      in body
    assert "depth_source" in body
    assert isinstance(body["sentence"], str)
    assert isinstance(body["objects"],  list)
    assert isinstance(body["hazards"],  list)
    assert isinstance(body["changes"],  list)
    assert len(body["sentence"]) > 0


def test_spaces_snapshot_endpoint():
    payload = {"space_id": "test_ssid", "objects": []}
    response = client.post("/spaces/snapshot", json=payload)
    assert response.status_code == 200
    assert response.json() == {"saved": True}


def test_stt_endpoint_exists():
    """STT 엔드포인트가 존재하는지 확인 (마이크 없어도 응답 와야 함)."""
    response = client.post("/stt")
    assert response.status_code == 200
    body = response.json()
    assert "text"    in body
    assert "mode"    in body
    assert "success" in body
