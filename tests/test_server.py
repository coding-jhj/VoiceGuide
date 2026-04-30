"""
VoiceGuide 서버 통합 테스트
===============================
실행 전 서버를 먼저 시작해야 합니다:
  uvicorn src.api.main:app --host 0.0.0.0 --port 8000

통합 테스트만 실행:
  pytest tests/test_server.py -v -m integration

서버 없이 실행하는 단위 테스트:
  pytest tests/ -v -m "not integration"
"""
import pytest
import io
import sys
import json
import requests
import numpy as np
from PIL import Image

BASE = "http://localhost:8000"
SESSION = "test-wifi"

# ── 더미 이미지 생성 ──────────────────────────────────────────────────────────
def make_dummy_image(width=640, height=480) -> bytes:
    """테스트용 랜덤 RGB 이미지 생성."""
    arr = np.random.randint(0, 255, (height, width, 3), dtype=np.uint8)
    img = Image.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


# ── 테스트 함수들 ─────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_health():
    """서버가 살아있는지 확인."""
    r = requests.get(f"{BASE}/")
    # FastAPI 기본 루트는 404지만 서버가 응답하면 OK
    assert r.status_code in (200, 404, 422), f"서버 응답 없음: {r.status_code}"
    print("✅ 서버 헬스체크 통과")


@pytest.mark.integration
def test_detect_obstacle():
    """장애물 모드 — 이미지 분석 응답 형식 확인."""
    img = make_dummy_image()
    r = requests.post(f"{BASE}/detect", files={"image": ("frame.jpg", img, "image/jpeg")},
        data={"mode": "장애물", "wifi_ssid": SESSION,
              "camera_orientation": "front", "query_text": "",
              "lat": "37.5665", "lng": "126.9780"})

    assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:200]}"
    body = r.json()
    assert "sentence"   in body, "sentence 필드 없음"
    assert "alert_mode" in body, "alert_mode 필드 없음"
    assert "objects"    in body, "objects 필드 없음"
    assert "hazards"    in body, "hazards 필드 없음"
    assert body["alert_mode"] in ("critical", "beep", "silent"), \
        f"잘못된 alert_mode: {body['alert_mode']}"
    print(f"✅ 장애물 모드: \"{body['sentence']}\" (alert={body['alert_mode']})")


@pytest.mark.integration
def test_detect_question():
    """질문 모드 — tracker 누적 상태 포함 응답 확인."""
    img = make_dummy_image()
    r = requests.post(f"{BASE}/detect", files={"image": ("frame.jpg", img, "image/jpeg")},
        data={"mode": "질문", "wifi_ssid": SESSION,
              "camera_orientation": "front", "query_text": ""})

    assert r.status_code == 200, f"HTTP {r.status_code}"
    body = r.json()
    assert "sentence" in body, "sentence 필드 없음"
    assert "tracked"  in body, "tracked 필드 없음 (tracker 상태 미포함)"
    print(f"✅ 질문 모드: \"{body['sentence']}\" (tracked={len(body['tracked'])}개)")


@pytest.mark.integration
def test_detect_find():
    """찾기 모드 — query_text에서 타깃 추출 확인."""
    img = make_dummy_image()
    r = requests.post(f"{BASE}/detect", files={"image": ("frame.jpg", img, "image/jpeg")},
        data={"mode": "찾기", "wifi_ssid": SESSION,
              "camera_orientation": "front", "query_text": "의자 찾아줘"})

    assert r.status_code == 200, f"HTTP {r.status_code}"
    body = r.json()
    assert "sentence" in body
    assert body["alert_mode"] == "critical", "찾기 모드는 항상 critical이어야 함"
    print(f"✅ 찾기 모드: \"{body['sentence']}\"")


@pytest.mark.integration
def test_detect_save():
    """저장 모드 — 이미지 없이 WiFi 기반 장소 저장."""
    img = make_dummy_image()
    r = requests.post(f"{BASE}/detect", files={"image": ("frame.jpg", img, "image/jpeg")},
        data={"mode": "저장", "wifi_ssid": SESSION, "query_text": "여기 저장해줘 테스트편의점"})

    assert r.status_code == 200, f"HTTP {r.status_code}"
    body = r.json()
    assert "sentence" in body
    print(f"✅ 저장 모드: \"{body['sentence']}\"")


@pytest.mark.integration
def test_status_endpoint():
    """GET /status/{session_id} — tracker 상태 + GPS 반환 확인."""
    r = requests.get(f"{BASE}/status/{SESSION}")
    assert r.status_code == 200, f"HTTP {r.status_code}"
    body = r.json()
    assert "session_id" in body
    assert "objects"    in body
    assert "gps"        in body
    assert "track"      in body
    assert body["session_id"] == SESSION
    print(f"✅ /status: objects={len(body['objects'])}개, "
          f"gps={'있음' if body['gps'] else '없음'}, "
          f"track={len(body['track'])}포인트")


@pytest.mark.integration
def test_locations():
    """GET /locations — 저장 장소 목록 반환 확인."""
    r = requests.get(f"{BASE}/locations", params={"wifi_ssid": SESSION})
    assert r.status_code == 200, f"HTTP {r.status_code}"
    body = r.json()
    assert "locations" in body
    assert "sentence"  in body
    print(f"✅ /locations: {len(body['locations'])}개 장소")


@pytest.mark.integration
def test_gps_stored():
    """/detect에서 GPS 전송 후 /status에서 확인."""
    img = make_dummy_image()
    lat, lng = 37.5665, 126.9780
    requests.post(f"{BASE}/detect", files={"image": ("frame.jpg", img, "image/jpeg")},
        data={"mode": "장애물", "wifi_ssid": SESSION, "lat": str(lat), "lng": str(lng)})

    r = requests.get(f"{BASE}/status/{SESSION}")
    body = r.json()

    if body["gps"]:
        assert abs(body["gps"]["lat"] - lat) < 0.0001, "GPS 위도 불일치"
        assert abs(body["gps"]["lng"] - lng) < 0.0001, "GPS 경도 불일치"
        print(f"✅ GPS 저장/조회: ({body['gps']['lat']}, {body['gps']['lng']})")
    else:
        print("⚠️  GPS 없음 (앱에서 GPS 좌표를 전송해야 함)")


@pytest.mark.integration
def test_dashboard():
    """GET /dashboard — HTML 페이지 반환 확인."""
    r = requests.get(f"{BASE}/dashboard")
    assert r.status_code == 200, f"HTTP {r.status_code}"
    assert "VoiceGuide" in r.text, "대시보드 HTML에 VoiceGuide 없음"
    print("✅ /dashboard: HTML 정상 반환")


# ── 메인 실행 ─────────────────────────────────────────────────────────────────

TESTS = [
    test_health,
    test_detect_obstacle,
    test_detect_question,
    test_detect_find,
    test_detect_save,
    test_status_endpoint,
    test_locations,
    test_gps_stored,
    test_dashboard,
]

if __name__ == "__main__":
    print(f"\n{'='*55}")
    print(f"  VoiceGuide 서버 테스트  |  {BASE}")
    print(f"{'='*55}\n")

    passed = failed = 0
    for fn in TESTS:
        try:
            fn()
            passed += 1
        except AssertionError as e:
            print(f"❌ {fn.__name__}: {e}")
            failed += 1
        except requests.exceptions.ConnectionError:
            print(f"⚠️  서버에 연결할 수 없습니다. 먼저 서버를 실행하세요:")
            print(f"   uvicorn src.api.main:app --host 0.0.0.0 --port 8000")
            sys.exit(1)

    print(f"\n{'='*55}")
    print(f"  결과: {passed}개 통과 / {failed}개 실패")
    print(f"{'='*55}\n")
    sys.exit(0 if failed == 0 else 1)
