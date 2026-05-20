"""Saved location response helpers for the FastAPI router."""

from collections.abc import Callable


NormalizeSessionId = Callable[..., str]


def _text(value: object) -> str:
    return str(value or "").strip()


def resolve_location_scope(
    normalize_session_id: NormalizeSessionId,
    *,
    wifi_ssid: str = "",
    device_id: str = "",
    session_id: str = "",
) -> str:
    """Return the stable DB scope used by the saved_locations.wifi_ssid column."""
    if _text(session_id):
        return normalize_session_id(device_id=_text(session_id))
    if _text(wifi_ssid) or _text(device_id):
        return normalize_session_id(wifi_ssid=_text(wifi_ssid), device_id=_text(device_id))
    return ""


def location_from_body(body: dict, normalize_session_id: NormalizeSessionId) -> tuple[str, str]:
    label = _text(body.get("label") or body.get("name") or body.get("query_text"))
    scope = resolve_location_scope(
        normalize_session_id,
        wifi_ssid=_text(body.get("wifi_ssid")),
        device_id=_text(body.get("device_id")),
        session_id=_text(body.get("session_id")),
    )
    return label, scope


def list_payload(locations: list[dict]) -> dict:
    count = len(locations)
    sentence = "저장된 장소가 없어요." if count == 0 else f"저장된 장소가 {count}개 있어요."
    return {"locations": locations, "sentence": sentence}


def save_payload(label: str, scope: str, location: dict) -> dict:
    return {
        "saved": True,
        "location": location,
        "sentence": f"{label}을 저장했어요.",
        "wifi_ssid": scope,
    }


def find_in_locations(label: str, locations: list[dict]) -> dict | None:
    needle = _text(label)
    if not needle:
        return None
    return next((loc for loc in locations if needle in _text(loc.get("label"))), None)


def found_payload(label: str, location: dict) -> dict:
    return {
        "found": True,
        "location": location,
        "sentence": f"{location['label']}을 찾았어요.",
    }


def missing_payload(label: str) -> dict:
    return {
        "found": False,
        "location": None,
        "sentence": f"{label}을 찾지 못했어요.",
    }


def delete_payload(label: str, deleted: bool) -> dict:
    sentence = f"{label}을 삭제했어요." if deleted else f"{label}을 찾지 못했어요."
    return {"deleted": deleted, "sentence": sentence}
