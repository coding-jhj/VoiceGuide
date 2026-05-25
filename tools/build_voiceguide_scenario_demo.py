from __future__ import annotations

import math
from pathlib import Path

import pandas as pd


ROOT = Path(r"C:\VoiceGuide\VoiceGuide")
PROCESSED = ROOT / "data" / "processed" / "voiceguide"
OUT = PROCESSED / "07_scenario_demo"


START = {
    "point_id": "start_boramae_station",
    "point_type": "start",
    "name": "보라매역",
    "address_or_note": "동작구 지하철역 출발지 데모 좌표",
    "lat": 37.499872,
    "lon": 126.920428,
    "source": "demo_assumption_near_boramae_station",
}

DEST = {
    "point_id": "dest_south_disability_welfare_center",
    "point_type": "destination",
    "name": "서울시남부장애인종합복지관",
    "facility_id": "C0455",
    "address_or_note": "서울특별시 동작구 여의대방로20나길 40 (신대방동)",
    "lat": 37.495100,
    "lon": 126.927450,
    "source": "demo_geocoded_from_nearby_crosswalk_cluster",
}


ROUTE_A_CROSSWALK_ID = "06-0000016344"
ROUTE_B_CROSSWALK_ID = "06-0000032157"


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def save_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def build() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    crosswalks = pd.read_csv(
        PROCESSED / "03_pedestrian_support" / "crosswalks_with_support_score_dongjak.csv",
        encoding="utf-8-sig",
    )
    welfare = pd.read_csv(
        PROCESSED / "01_destination" / "welfare_facilities_dongjak.csv",
        encoding="utf-8-sig",
    )

    selected = crosswalks[
        crosswalks["crosswalk_id"].isin([ROUTE_A_CROSSWALK_ID, ROUTE_B_CROSSWALK_ID])
    ].copy()
    if len(selected) != 2:
        missing = {ROUTE_A_CROSSWALK_ID, ROUTE_B_CROSSWALK_ID} - set(selected["crosswalk_id"])
        raise RuntimeError(f"Missing selected crosswalks: {missing}")

    route_labels = {
        ROUTE_A_CROSSWALK_ID: {
            "route_id": "A",
            "route_name": "최단 후보 경로",
            "route_role": "shortest_candidate",
            "selected": False,
        },
        ROUTE_B_CROSSWALK_ID: {
            "route_id": "B",
            "route_name": "설명 가능한 안전 경로",
            "route_role": "safe_explainable_route",
            "selected": True,
        },
    }

    route_rows = []
    for _, row in selected.iterrows():
        route = route_labels[row["crosswalk_id"]]
        start_to_crosswalk = haversine_m(START["lat"], START["lon"], row["lat"], row["lon"])
        crosswalk_to_dest = haversine_m(row["lat"], row["lon"], DEST["lat"], DEST["lon"])
        proxy_distance = start_to_crosswalk + crosswalk_to_dest
        route_rows.append(
            {
                **route,
                "start_name": START["name"],
                "destination_name": DEST["name"],
                "destination_facility_id": DEST["facility_id"],
                "main_crosswalk_id": row["crosswalk_id"],
                "main_crosswalk_address": row["address"],
                "main_crosswalk_lat": row["lat"],
                "main_crosswalk_lon": row["lon"],
                "approx_distance_m": round(proxy_distance),
                "start_to_crosswalk_m": round(start_to_crosswalk),
                "crosswalk_to_destination_m": round(crosswalk_to_dest),
                "has_pedestrian_signal": bool(row["has_pedestrian_signal"]),
                "has_audio_signal": bool(row["has_audio_signal"]),
                "has_pedestrian_button": bool(row["has_pedestrian_button"]),
                "support_score": int(row["support_score"]),
                "route_priority": row["route_priority"],
                "safety_evidence": evidence(row),
            }
        )

    routes = pd.DataFrame(route_rows).sort_values("route_id")
    route_a_dist = int(routes.loc[routes["route_id"].eq("A"), "approx_distance_m"].iloc[0])
    route_b_dist = int(routes.loc[routes["route_id"].eq("B"), "approx_distance_m"].iloc[0])
    detour_m = route_b_dist - route_a_dist

    routes["distance_delta_vs_shortest_m"] = routes["approx_distance_m"] - route_a_dist
    routes["reason_summary"] = routes.apply(
        lambda r: (
            "최단 후보지만 보행등, 음향신호기, 보행자작동신호기 정보가 없어 선택하지 않음"
            if r["route_id"] == "A"
            else f"약 {max(detour_m, 0)}m 더 이동하지만 보행등, 음향신호기, 보행자작동신호기 근거가 있어 선택"
        ),
        axis=1,
    )

    guide_lines = pd.DataFrame(
        [
            {
                "sequence": 1,
                "event": "route_selected",
                "tts_text": (
                    f"최단 후보보다 약 {max(detour_m, 0)}미터 더 이동하지만, "
                    "보행등과 음향신호기, 보행자작동신호기 정보가 있는 횡단보도로 안내합니다."
                ),
                "vibration": "short",
            },
            {
                "sequence": 2,
                "event": "crosswalk_approach",
                "tts_text": "전방에 보행지원시설 정보가 있는 횡단보도가 있습니다. 신호 안내를 확인하며 건너세요.",
                "vibration": "medium",
            },
            {
                "sequence": 3,
                "event": "realtime_detection",
                "tts_text": "이동 중 전방 장애물은 카메라로 계속 확인합니다.",
                "vibration": "none",
            },
        ]
    )

    points = pd.DataFrame(
        [
            START,
            DEST,
            *[
                {
                    "point_id": f"crosswalk_{r.route_id}",
                    "point_type": "crosswalk",
                    "name": f"{r.route_name} 대표 횡단보도",
                    "address_or_note": r.main_crosswalk_address,
                    "lat": r.main_crosswalk_lat,
                    "lon": r.main_crosswalk_lon,
                    "source": "processed_crosswalk_support_score",
                    "route_id": r.route_id,
                    "support_score": r.support_score,
                    "selected": r.selected,
                }
                for r in routes.itertuples(index=False)
            ],
        ]
    )

    dest_facility = welfare[welfare["facility_id"].eq(DEST["facility_id"])].copy()
    dest_facility["demo_lat"] = DEST["lat"]
    dest_facility["demo_lon"] = DEST["lon"]
    dest_facility["geocoding_status"] = "demo_coordinate_assigned"
    dest_facility["geocoding_note"] = "정식 지도 API 지오코딩 전까지 데모 좌표로 사용"

    save_csv(routes, OUT / "scenario_route_comparison.csv")
    save_csv(selected, OUT / "scenario_selected_crosswalks_raw.csv")
    save_csv(points, OUT / "scenario_map_points.csv")
    save_csv(guide_lines, OUT / "scenario_tts_guidance.csv")
    save_csv(dest_facility, OUT / "scenario_destination_facility.csv")

    readme = OUT / "README.md"
    readme.write_text(
        "\n".join(
            [
                "# VoiceGuide 시나리오 데모 데이터",
                "",
                "## 고정 시나리오",
                "",
                "- 출발지: 보라매역",
                "- 목적지: 서울시남부장애인종합복지관",
                "- 비교: 최단 후보 경로 A vs 설명 가능한 안전 경로 B",
                "",
                "## 중요한 해석",
                "",
                "- 이 결과는 도로 네트워크 경로 API를 쓰지 않고, 출발지-대표 횡단보도-목적지 직선거리 합으로 만든 데모용 비교입니다.",
                "- 원래 초안의 `90m 더 이동` 문구는 이 공공데이터만으로는 그대로 검증되지 않았습니다.",
                f"- 현재 데이터 기준 B는 A보다 약 {max(detour_m, 0)}m 더 이동하는 것으로 계산됩니다.",
                "- 발표에서 숫자를 정확히 말하려면 지도 경로 API를 붙여 실제 보행거리로 다시 계산해야 합니다.",
                "",
                "## 파일",
                "",
                "- `scenario_route_comparison.csv`: 발표 표와 경로 선택 로직에 바로 쓰는 핵심 파일",
                "- `scenario_map_points.csv`: 지도 마커용 출발지, 목적지, 횡단보도 A/B",
                "- `scenario_tts_guidance.csv`: 사용자에게 말할 안내 문장",
                "- `scenario_destination_facility.csv`: 목적지 복지관 1개",
                "- `scenario_selected_crosswalks_raw.csv`: 선택된 횡단보도 원본 정제 컬럼",
                "",
            ]
        ),
        encoding="utf-8",
    )

    print("scenario_root", OUT)
    print(routes.to_string(index=False))


def evidence(row: pd.Series) -> str:
    flags = []
    if bool(row["has_pedestrian_signal"]):
        flags.append("보행등")
    if bool(row["has_audio_signal"]):
        flags.append("음향신호기")
    if bool(row["has_pedestrian_button"]):
        flags.append("보행자작동신호기")
    if not flags:
        return "보행지원시설 확인 정보 없음"
    return ", ".join(flags) + " 정보 있음"


if __name__ == "__main__":
    build()
