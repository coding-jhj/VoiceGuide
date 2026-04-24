import pytest
from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)


def test_detect_endpoint_exists():
    response = client.post("/detect", data={"wifi_ssid": "test_ssid"})
    # 이미지 없이 호출하면 422, 있으면 200
    assert response.status_code in (200, 422)


def test_detect_response_schema(sample_jpeg_bytes):
    response = client.post(
        "/detect",
        files={"image": ("test.jpg", sample_jpeg_bytes, "image/jpeg")},
        data={"wifi_ssid": "test_wifi"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "sentence" in body
    assert "objects" in body
    assert "changes" in body
    assert isinstance(body["sentence"], str)
    assert isinstance(body["objects"], list)
    assert isinstance(body["changes"], list)


def test_spaces_snapshot_endpoint():
    payload = {"space_id": "test_ssid", "objects": []}
    response = client.post("/spaces/snapshot", json=payload)
    assert response.status_code == 200
    assert response.json() == {"saved": True}
