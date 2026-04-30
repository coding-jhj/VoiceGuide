"""
VoiceGuide server/client link probe.

This sends a dummy image to /detect, then checks /status and /dashboard.
Use it to prove that the server, tracker/DB state, and dashboard endpoint are
connected before debugging the Android client.

Examples:
  python tools/probe_server_link.py --base https://voiceguide-135456731041.asia-northeast3.run.app
  python tools/probe_server_link.py --base http://127.0.0.1:8000 --image data/test_images/chair/chair_000.jpg
"""

from __future__ import annotations

import argparse
import io
import json
import time
from pathlib import Path

import requests
from PIL import Image, ImageDraw


def make_dummy_image() -> bytes:
    """Create a deterministic JPEG with simple shapes for transport testing."""
    img = Image.new("RGB", (640, 480), (235, 238, 242))
    draw = ImageDraw.Draw(img)
    draw.rectangle((250, 160, 390, 420), fill=(90, 120, 190), outline=(20, 40, 90), width=4)
    draw.rectangle((285, 90, 355, 160), fill=(210, 170, 120), outline=(80, 50, 20), width=3)
    draw.line((0, 430, 640, 430), fill=(80, 80, 80), width=4)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def load_image(path: str | None) -> bytes:
    if not path:
        return make_dummy_image()
    return Path(path).read_bytes()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, help="Server base URL, e.g. https://...run.app")
    parser.add_argument("--image", help="Optional local image path. If omitted, a dummy image is generated.")
    parser.add_argument("--session", default="probe-client", help="wifi_ssid/session_id used for /status")
    parser.add_argument("--mode", default="장애물", help="Mode sent to /detect")
    parser.add_argument("--lat", default="37.5665")
    parser.add_argument("--lng", default="126.9780")
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    base = args.base.rstrip("/")
    request_id = f"probe-{int(time.time() * 1000)}"
    image_bytes = load_image(args.image)

    print(f"[probe] base={base}")
    print(f"[probe] request_id={request_id} session={args.session} image_bytes={len(image_bytes)}")

    health = requests.get(f"{base}/health", timeout=args.timeout)
    print(f"[health] HTTP {health.status_code}: {health.text[:300]}")
    health.raise_for_status()

    t0 = time.perf_counter()
    detect = requests.post(
        f"{base}/detect",
        files={"image": ("probe.jpg", image_bytes, "image/jpeg")},
        data={
            "mode": args.mode,
            "wifi_ssid": args.session,
            "camera_orientation": "front",
            "query_text": "",
            "lat": args.lat,
            "lng": args.lng,
            "request_id": request_id,
        },
        timeout=args.timeout,
    )
    round_trip_ms = int((time.perf_counter() - t0) * 1000)
    print(f"[detect] HTTP {detect.status_code} round_trip_ms={round_trip_ms}")
    detect.raise_for_status()
    body = detect.json()
    print(json.dumps({
        "request_id": body.get("request_id"),
        "sentence": body.get("sentence"),
        "alert_mode": body.get("alert_mode"),
        "objects": len(body.get("objects", [])),
        "hazards": len(body.get("hazards", [])),
        "process_ms": body.get("process_ms"),
        "perf": body.get("perf"),
    }, ensure_ascii=False, indent=2))

    if body.get("request_id") != request_id:
        raise SystemExit(f"request_id mismatch: sent={request_id}, got={body.get('request_id')}")

    status = requests.get(f"{base}/status/{args.session}", timeout=args.timeout)
    print(f"[status] HTTP {status.status_code}")
    status.raise_for_status()
    status_body = status.json()
    print(json.dumps({
        "session_id": status_body.get("session_id"),
        "objects": len(status_body.get("objects", [])),
        "gps": status_body.get("gps"),
        "track_points": len(status_body.get("track", [])),
    }, ensure_ascii=False, indent=2))

    dashboard = requests.get(f"{base}/dashboard", timeout=args.timeout)
    print(f"[dashboard] HTTP {dashboard.status_code} contains VoiceGuide={'VoiceGuide' in dashboard.text}")
    dashboard.raise_for_status()

    print("[probe] OK: /detect, /status, and /dashboard are reachable and correlated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
