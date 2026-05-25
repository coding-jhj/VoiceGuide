from __future__ import annotations

import argparse
import json
import math
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_SOURCE_DIR = Path(
    r"C:\Users\kjh\Downloads\서울시 보행자작동신호기 관련 정보"
)
DEFAULT_OUTPUT_DIR = Path("data/processed/voiceguide_scenario")

FINAL_ROUTE_A_CROSSWALK_ID = "06-0000016344"
FINAL_ROUTE_B_CROSSWALK_ID = "06-0000032157"
FINAL_ROUTE_DETOUR_M = 8
FINAL_ROUTE_ORIGIN = "보라매역"
FINAL_ROUTE_DESTINATION = "서울시남부장애인종합복지관"

CROSSWALK_FILE = "서울특별시 자치구 횡단보도 정보.csv"
TRAFFIC_SAFETY_FILE = "서울시 교통안전시설물 횡단보도 정보.csv"
WELFARE_FILE = "서울시 사회복지시설(장애인지역사회재활시설) 목록.csv"
AUDIO_SIGNAL_FILE = "서울시 음향신호기 관련 정보.csv"
PUSH_BUTTON_FILE = "서울시 보행자작동신호기 관련 정보.csv"
MOBILITY_CENTER_FILE = "전국교통약자이동지원센터정보표준데이터.csv"


def read_csv(path: Path) -> pd.DataFrame:
    for encoding in ("utf-8-sig", "cp949", "euc-kr", "utf-8"):
        try:
            return pd.read_csv(path, encoding=encoding, low_memory=False)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(path, low_memory=False)


def clean_text(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def yn_to_bool(value: Any) -> bool:
    return clean_text(value).upper() == "Y"


def yes_no(value: bool) -> str:
    return "Y" if value else "N"


def apply_final_tier_labels(scores: pd.Series) -> pd.Series:
    return pd.cut(
        scores,
        bins=[-1, 0, 3, 6, 99],
        labels=["insufficient", "basic", "recommended", "preferred"],
    ).astype(str)


def normalize_crosswalk_coordinates(df: pd.DataFrame) -> pd.DataFrame:
    # The source file labels are reversed in the downloaded sample:
    # "경도" contains latitude-like values and "위도" contains longitude-like values.
    first_lon_label = pd.to_numeric(df["경도"], errors="coerce")
    first_lat_label = pd.to_numeric(df["위도"], errors="coerce")
    likely_swapped = (
        first_lon_label.between(33, 39).mean() > 0.9
        and first_lat_label.between(124, 132).mean() > 0.9
    )
    if likely_swapped:
        df["latitude"] = first_lon_label
        df["longitude"] = first_lat_label
    else:
        df["latitude"] = first_lat_label
        df["longitude"] = first_lon_label
    df["coordinate_note"] = (
        "source_columns_swapped" if likely_swapped else "source_columns_as_labeled"
    )
    return df


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(a))


def build_crosswalks(source_dir: Path) -> pd.DataFrame:
    crosswalks = read_csv(source_dir / CROSSWALK_FILE)
    crosswalks = normalize_crosswalk_coordinates(crosswalks)
    crosswalks = crosswalks[crosswalks["시군구명"].eq("동작구")].copy()

    detail = read_csv(source_dir / TRAFFIC_SAFETY_FILE)
    detail = detail[
        [
            "횡단보도관리번호",
            "상태 (공통)",
            "횡단보도종류코드",
            "가로길이",
            "세로길이",
            "교차로코드",
            "X좌표",
            "Y좌표",
        ]
    ].copy()
    detail = detail.rename(
        columns={
            "상태 (공통)": "traffic_safety_state_code",
            "횡단보도종류코드": "traffic_safety_type_code",
            "가로길이": "crosswalk_width_m",
            "세로길이": "crosswalk_length_m",
            "교차로코드": "intersection_code",
            "X좌표": "projected_x",
            "Y좌표": "projected_y",
        }
    )
    detail["_detail_quality"] = detail.notna().sum(axis=1)
    detail = (
        detail.sort_values("_detail_quality", ascending=False)
        .drop_duplicates("횡단보도관리번호", keep="first")
        .drop(columns=["_detail_quality"])
    )

    df = crosswalks.merge(detail, on="횡단보도관리번호", how="left")
    df["has_pedestrian_light_bool"] = df["보행등유무"].map(yn_to_bool)
    df["has_audio_signal_bool"] = df["음향신호기설치여부"].map(yn_to_bool)
    df["has_push_button_bool"] = df["보행자작동신호기유무"].map(yn_to_bool)
    df["is_raised_crosswalk_bool"] = df["고원식횡단보도유무"].map(yn_to_bool)
    df["has_traffic_safety_detail_bool"] = df["traffic_safety_state_code"].notna()

    df["accessibility_score"] = (
        df["has_pedestrian_light_bool"].astype(int) * 2
        + df["has_audio_signal_bool"].astype(int) * 4
        + df["has_push_button_bool"].astype(int) * 3
        + df["is_raised_crosswalk_bool"].astype(int)
        + df["has_traffic_safety_detail_bool"].astype(int)
    )

    def reason(row: pd.Series) -> str:
        items: list[str] = []
        if row["has_audio_signal_bool"]:
            items.append("음향신호기")
        if row["has_push_button_bool"]:
            items.append("보행자작동신호기")
        if row["has_pedestrian_light_bool"]:
            items.append("보행등")
        if row["is_raised_crosswalk_bool"]:
            items.append("고원식횡단보도")
        if row["has_traffic_safety_detail_bool"]:
            items.append("교통안전시설 상세")
        return ", ".join(items) if items else "보행지원시설 정보 없음"

    df["support_evidence"] = df.apply(reason, axis=1)
    df["route_recommendation_tier"] = apply_final_tier_labels(
        df["accessibility_score"]
    )

    out = pd.DataFrame(
        {
            "crosswalk_id": df["횡단보도관리번호"].map(clean_text),
            "district": df["시군구명"].map(clean_text),
            "address": df["소재지지번주소"].map(clean_text),
            "crosswalk_type": df["횡단보도종류"].map(clean_text),
            "latitude": df["latitude"],
            "longitude": df["longitude"],
            "has_pedestrian_light": df["has_pedestrian_light_bool"].map(yes_no),
            "has_audio_signal": df["has_audio_signal_bool"].map(yes_no),
            "has_push_button": df["has_push_button_bool"].map(yes_no),
            "is_raised_crosswalk": df["is_raised_crosswalk_bool"].map(yes_no),
            "has_traffic_safety_detail": df["has_traffic_safety_detail_bool"].map(
                yes_no
            ),
            "accessibility_score": df["accessibility_score"],
            "route_recommendation_tier": df["route_recommendation_tier"],
            "support_evidence": df["support_evidence"],
            "crosswalk_width_m": df["crosswalk_width_m"],
            "crosswalk_length_m": df["crosswalk_length_m"],
            "traffic_safety_type_code": df["traffic_safety_type_code"],
            "traffic_safety_state_code": df["traffic_safety_state_code"],
            "intersection_code": df["intersection_code"],
            "data_reference_date": df["데이터기준일자"].map(clean_text),
            "coordinate_note": df["coordinate_note"].map(clean_text),
        }
    )
    return out.sort_values(
        ["accessibility_score", "address", "crosswalk_id"],
        ascending=[False, True, True],
    )


def build_welfare_facilities(source_dir: Path) -> pd.DataFrame:
    welfare = read_csv(source_dir / WELFARE_FILE)
    welfare = welfare[welfare["시군구명"].eq("동작구")].copy()
    welfare["is_primary_destination_candidate"] = welfare[
        "시설종류명(시설유형)"
    ].fillna("").str.contains("장애인복지관|장애인생활이동지원센터", regex=True)

    return pd.DataFrame(
        {
            "facility_name": welfare["시설명"].map(clean_text),
            "facility_code": welfare["시설코드"].map(clean_text),
            "facility_type": welfare["시설종류명(시설유형)"].map(clean_text),
            "facility_detail_type": welfare["시설종류상세명(시설종류)"].map(
                clean_text
            ),
            "district": welfare["시군구명"].map(clean_text),
            "address": welfare["시설주소"].map(clean_text),
            "phone": welfare["전화번호"].map(clean_text),
            "is_primary_destination_candidate": welfare[
                "is_primary_destination_candidate"
            ].map(yes_no),
            "geocode_status": "address_only_needs_geocoding",
        }
    ).sort_values(["is_primary_destination_candidate", "facility_name"], ascending=[False, True])


def build_mobility_centers(source_dir: Path) -> pd.DataFrame:
    centers = read_csv(source_dir / MOBILITY_CENTER_FILE)
    text = centers.fillna("").astype(str).agg(" ".join, axis=1)
    serves_seoul = text.str.contains("서울", na=False)
    in_seoul = centers["소재지도로명주소"].fillna("").str.contains(
        "서울", na=False
    ) | centers["소재지지번주소"].fillna("").str.contains("서울", na=False)
    centers = centers[serves_seoul | in_seoul].copy()
    centers["serves_seoul"] = serves_seoul.loc[centers.index]
    centers["is_located_in_seoul"] = in_seoul.loc[centers.index]

    out = pd.DataFrame(
        {
            "center_name": centers["교통약자이동지원센터명"].map(clean_text),
            "road_address": centers["소재지도로명주소"].map(clean_text),
            "lot_address": centers["소재지지번주소"].map(clean_text),
            "latitude": pd.to_numeric(centers["위도"], errors="coerce"),
            "longitude": pd.to_numeric(centers["경도"], errors="coerce"),
            "reservation_phone": centers["예약접수전화번호"].map(clean_text),
            "app_service_name": centers["앱서비스명"].map(clean_text),
            "weekday_reservation_start": centers["평일예약접수운영시작시각"].map(
                clean_text
            ),
            "weekday_reservation_end": centers["평일예약접수운영종료시각"].map(
                clean_text
            ),
            "weekday_vehicle_start": centers["차량평일운행시작시각"].map(clean_text),
            "weekday_vehicle_end": centers["차량평일운행종료시각"].map(clean_text),
            "service_area_local": centers["차량관내운행지역"].map(clean_text),
            "service_area_outside": centers["차량관외운행지역"].map(clean_text),
            "target_users": centers["차량이용대상"].map(clean_text),
            "fare": centers["차량이용요금"].map(clean_text),
            "manager": centers["관리기관명"].map(clean_text),
            "manager_phone": centers["관리기관전화번호"].map(clean_text),
            "data_reference_date": centers["데이터기준일자"].map(clean_text),
            "serves_seoul": centers["serves_seoul"].map(yes_no),
            "is_located_in_seoul": centers["is_located_in_seoul"].map(yes_no),
        }
    )
    return out.sort_values(["is_located_in_seoul", "center_name"], ascending=[False, True])


def build_projected_signal_table(source_dir: Path, filename: str, kind: str) -> pd.DataFrame:
    df = read_csv(source_dir / filename)
    id_col = "음향신호관리번호" if kind == "audio_signal" else "보행자작동신호기 관리번호"
    return pd.DataFrame(
        {
            "facility_kind": kind,
            "facility_id": df[id_col].map(clean_text),
            "pole_id": df["지주관리번호"].map(clean_text),
            "direction_degrees": pd.to_numeric(df["방향 (공통)"], errors="coerce"),
            "install_date": df["설치일"].map(clean_text),
            "replace_date": df["교체일"].map(clean_text),
            "projected_x": pd.to_numeric(df["X좌표"], errors="coerce"),
            "projected_y": pd.to_numeric(df["Y좌표"], errors="coerce"),
            "state_code": df["상태 (공통)"].map(clean_text),
            "display_code": df["표출구분 (공통)"].map(clean_text),
            "work_code": df["작업구분 (공통)"].map(clean_text),
            "source_coordinate_system": "seoul_projected_xy_unconverted",
        }
    )


def crosswalks_to_geojson(crosswalks: pd.DataFrame) -> dict[str, Any]:
    features = []
    for row in crosswalks.dropna(subset=["latitude", "longitude"]).to_dict("records"):
        props = {
            key: value
            for key, value in row.items()
            if key not in {"latitude", "longitude"}
            and not (isinstance(value, float) and math.isnan(value))
        }
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [row["longitude"], row["latitude"]],
                },
                "properties": props,
            }
        )
    return {"type": "FeatureCollection", "features": features}


def public_crosswalk_fields(row: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "crosswalk_id",
        "address",
        "latitude",
        "longitude",
        "accessibility_score",
        "support_evidence",
        "route_recommendation_tier",
        "has_pedestrian_light",
        "has_audio_signal",
        "has_push_button",
        "is_raised_crosswalk",
        "has_traffic_safety_detail",
    ]
    return {key: row.get(key) for key in keys if key in row}


def present_support_items(row: dict[str, Any]) -> list[str]:
    checks = [
        ("has_audio_signal", "음향신호기"),
        ("has_push_button", "보행자작동신호기"),
        ("has_pedestrian_light", "보행등"),
        ("is_raised_crosswalk", "고원식횡단보도"),
        ("has_traffic_safety_detail", "교통안전시설 상세"),
    ]
    return [label for key, label in checks if row.get(key) == "Y"]


def missing_support_items(row: dict[str, Any]) -> list[str]:
    checks = [
        ("has_pedestrian_light", "보행등 없음"),
        ("has_audio_signal", "음향신호기 없음"),
        ("has_push_button", "보행자작동신호기 없음"),
    ]
    return [label for key, label in checks if row.get(key) != "Y"]


def build_final_pair_if_available(crosswalks: pd.DataFrame) -> dict[str, Any]:
    rows = crosswalks.set_index("crosswalk_id", drop=False)
    if not {FINAL_ROUTE_A_CROSSWALK_ID, FINAL_ROUTE_B_CROSSWALK_ID}.issubset(
        rows.index
    ):
        return {}

    a = rows.loc[FINAL_ROUTE_A_CROSSWALK_ID].to_dict()
    b = rows.loc[FINAL_ROUTE_B_CROSSWALK_ID].to_dict()
    point_distance = haversine_m(
        float(a["latitude"]),
        float(a["longitude"]),
        float(b["latitude"]),
        float(b["longitude"]),
    )
    b_support = present_support_items(b)
    b_support_text = ", ".join(b_support) if b_support else "보행지원시설"
    selection_reason = (
        f"최단 후보보다 약 {FINAL_ROUTE_DETOUR_M}m 더 이동하지만, "
        f"{b_support_text} 정보가 있는 횡단보도로 안내합니다."
    )
    return {
        "scenario_note": (
            f"{FINAL_ROUTE_ORIGIN}에서 {FINAL_ROUTE_DESTINATION}으로 이동하는 "
            "발표용 A/B 비교입니다. detour_m은 경로 설명용 값이고, "
            "crosswalk_point_distance_m은 두 횡단보도 포인트 간 직선거리입니다."
        ),
        "origin": FINAL_ROUTE_ORIGIN,
        "destination": FINAL_ROUTE_DESTINATION,
        "estimated_route_detour_m": FINAL_ROUTE_DETOUR_M,
        "estimated_crosswalk_point_distance_m": round(point_distance),
        "shortest_route_crosswalk_a": public_crosswalk_fields(a),
        "safer_route_crosswalk_b": public_crosswalk_fields(b),
        "selection_reason": selection_reason,
        "tts_example": selection_reason,
    }


def build_fallback_pair(crosswalks: pd.DataFrame) -> dict[str, Any]:
    no_support = (
        crosswalks["has_pedestrian_light"].eq("N")
        & crosswalks["has_audio_signal"].eq("N")
        & crosswalks["has_push_button"].eq("N")
    )
    low = crosswalks[no_support]
    high = crosswalks[
        crosswalks["has_audio_signal"].eq("Y")
        & crosswalks["accessibility_score"].ge(6)
    ]
    best: tuple[float, dict[str, Any], dict[str, Any]] | None = None
    max_distance = 160
    fallback_best: tuple[float, dict[str, Any], dict[str, Any], float] | None = None
    for a in low.to_dict("records"):
        for b in high.to_dict("records"):
            if any(pd.isna(a[k]) or pd.isna(b[k]) for k in ("latitude", "longitude")):
                continue
            dist = haversine_m(
                float(a["latitude"]),
                float(a["longitude"]),
                float(b["latitude"]),
                float(b["longitude"]),
            )
            if 40 <= dist <= 300:
                fallback_rank = abs(dist - 90)
                if fallback_best is None or fallback_rank < fallback_best[0]:
                    fallback_best = (fallback_rank, a, b, dist)
            if not 40 <= dist <= max_distance:
                continue
            target_penalty = abs(dist - 90)
            score_gap_bonus = float(b["accessibility_score"] - a["accessibility_score"])
            rank = target_penalty - score_gap_bonus * 3
            if best is None or rank < best[0]:
                best = (rank, a, b)
    if best is None:
        if fallback_best is None:
            return {}
        _, a, b, distance = fallback_best
    else:
        _, a, b = best
        distance = haversine_m(
            float(a["latitude"]),
            float(a["longitude"]),
            float(b["latitude"]),
            float(b["longitude"]),
        )

    return {
        "scenario_note": (
            "A is a nearby low-information crosswalk; B is a nearby supported "
            "crosswalk. The distance is straight-line distance between crosswalk "
            "points, not a routed walking detour."
        ),
        "estimated_crosswalk_point_distance_m": round(distance),
        "shortest_route_crosswalk_a": public_crosswalk_fields(a),
        "safer_route_crosswalk_b": public_crosswalk_fields(b),
        "tts_example": (
            f"최단 경로보다 약 {round(distance / 10) * 10}m 더 이동하지만, "
            "음향신호기와 보행지원시설 정보가 있는 횡단보도로 안내합니다."
        ),
    }


def pick_demo_pair(crosswalks: pd.DataFrame) -> dict[str, Any]:
    return build_final_pair_if_available(crosswalks) or build_fallback_pair(crosswalks)


def build_final_route_comparison(demo_pair: dict[str, Any]) -> pd.DataFrame:
    if not demo_pair:
        return pd.DataFrame()

    a = demo_pair["shortest_route_crosswalk_a"]
    b = demo_pair["safer_route_crosswalk_b"]
    rows = [
        ("A", "최단 후보", "N", a),
        ("B", "설명 가능한 안전 경로", "Y", b),
    ]
    return pd.DataFrame(
        [
            {
                "route": route,
                "role": role,
                "selected": selected,
                "crosswalk_id": row.get("crosswalk_id"),
                "address": row.get("address"),
                "latitude": row.get("latitude"),
                "longitude": row.get("longitude"),
                "accessibility_score": row.get("accessibility_score"),
                "route_recommendation_tier": row.get("route_recommendation_tier"),
                "support_evidence": row.get("support_evidence"),
                "missing_support": ", ".join(missing_support_items(row)),
                "estimated_route_detour_m": demo_pair.get("estimated_route_detour_m"),
                "selection_reason": demo_pair.get("selection_reason")
                if selected == "Y"
                else "",
            }
            for route, role, selected, row in rows
        ]
    )


def build_final_tts_guidance(demo_pair: dict[str, Any]) -> pd.DataFrame:
    if not demo_pair:
        return pd.DataFrame()
    return pd.DataFrame(
        [
            {
                "guidance_id": "safe_route_reason",
                "situation": "최단 후보보다 보행지원 근거가 많은 횡단보도를 선택할 때",
                "text": demo_pair["tts_example"],
                "source_fields": "demo_crosswalk_pair.selection_reason",
            }
        ]
    )


def write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def write_text(path: Path, text: str) -> None:
    path.write_text(text.strip() + "\n", encoding="utf-8")


def write_final_readme(path: Path, summary: dict[str, Any]) -> None:
    counts = summary["counts"]
    demo_pair = summary["demo_pair"]
    write_text(
        path,
        f"""
# VoiceGuide Scenario Data

`final_data_usage.html`의 설명 흐름에 맞춰 공공데이터 전처리 결과를 발표/앱 데모용 최종 패키지로 묶은 산출물입니다.

## Main files

- `final_route_comparison.csv`
  - 보라매역 → 서울시남부장애인종합복지관 시나리오의 A/B 횡단보도 비교표입니다.
  - A는 최단 후보, B는 설명 가능한 안전 경로 후보입니다.
- `final_crosswalk_accessibility.csv`
  - 동작구 횡단보도 {counts["dongjak_crosswalks"]:,}건의 보행지원시설 점수표입니다.
  - 등급은 `preferred`, `recommended`, `basic`, `insufficient`로 정리합니다.
- `final_crosswalk_accessibility.geojson`
  - 지도 레이어에 바로 올릴 수 있는 횡단보도 포인트 GeoJSON입니다.
- `final_scenario_dataset.json`
  - 목적지 후보, 추천 횡단보도, A/B 비교, TTS 문장, 이동지원센터 fallback을 한 번에 읽는 JSON입니다.
- `final_tts_guidance.csv`
  - 사용자에게 들려줄 안전 경로 선택 이유 문장입니다.
- `final_data_usage.html`
  - 팀 공유/발표 설명용 HTML입니다.

기존 호환용 파일명(`dongjak_crosswalk_accessibility.csv`, `dongjak_crosswalk_accessibility.geojson`, `voiceguide_scenario_dataset.json`, `voiceguide_scenario_data_usage.html`)도 함께 생성합니다.

## Demo pair

- A: `{demo_pair["shortest_route_crosswalk_a"]["crosswalk_id"]}` · {demo_pair["shortest_route_crosswalk_a"]["address"]} · {demo_pair["shortest_route_crosswalk_a"]["accessibility_score"]}점
- B: `{demo_pair["safer_route_crosswalk_b"]["crosswalk_id"]}` · {demo_pair["safer_route_crosswalk_b"]["address"]} · {demo_pair["safer_route_crosswalk_b"]["accessibility_score"]}점
- 안내 문장: {demo_pair["tts_example"]}

`estimated_route_detour_m`은 발표 시나리오 설명용 값입니다. 실제 보행거리 검증은 지도 경로 API 또는 보행 네트워크 계산이 별도로 필요합니다.

## Rebuild

```powershell
python tools\\preprocess_voiceguide_scenario_data.py
```
""",
    )


def write_final_data_usage_html(path: Path, summary: dict[str, Any]) -> None:
    counts = summary["counts"]
    tiers = counts["route_recommendation_tiers"]
    pair = summary["demo_pair"]
    a = pair["shortest_route_crosswalk_a"]
    b = pair["safer_route_crosswalk_b"]
    a_missing = missing_support_items(a)
    b_support = present_support_items(b)
    b_support_html = "".join(f"<div>{item} 정보 있음</div>" for item in b_support)
    a_missing_html = "".join(f"<div>{item}</div>" for item in a_missing)
    write_text(
        path,
        f"""
<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>VoiceGuide 데이터 통합 결과</title>
<style>
  :root {{
    --bg:#eef3f8; --paper:#fff; --ink:#142033; --muted:#5c6c80;
    --line:#d8e1ec; --blue:#2563eb; --teal:#0a8a76; --green:#16824c;
    --red:#c23b3b; --amber:#a76300; --shadow:0 12px 32px rgba(20,32,51,.09);
  }}
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ background:var(--bg); color:var(--ink); font-family:"Segoe UI","Noto Sans KR",Arial,sans-serif; line-height:1.65; word-break:keep-all; }}
  .page {{ max-width:1160px; margin:0 auto; padding:36px 20px 68px; }}
  .hero,.panel,.route,.file,.source {{ border:1px solid var(--line); background:var(--paper); box-shadow:var(--shadow); }}
  .hero {{ display:grid; grid-template-columns:1.05fr .95fr; gap:26px; align-items:center; padding:38px; border-radius:22px; }}
  .eyebrow {{ color:var(--teal); font-size:12px; font-weight:900; letter-spacing:.08em; text-transform:uppercase; }}
  h1 {{ margin-top:12px; font-size:clamp(30px,4.4vw,50px); line-height:1.15; }}
  h2 {{ font-size:24px; }} h3 {{ font-size:18px; }} p {{ color:var(--muted); }}
  .lead {{ margin-top:18px; font-size:18px; }}
  .hero-answer,.tts {{ margin-top:24px; padding:18px 20px; border-radius:14px; background:#edf9f3; color:#105235; font-weight:900; }}
  .result-board,.three,.scenario,.file-grid {{ display:grid; gap:14px; }}
  .result-board,.scenario {{ grid-template-columns:1fr 1fr; }}
  .three,.file-grid {{ grid-template-columns:repeat(3,1fr); }}
  .result-card,.source,.file,.step {{ padding:18px; border:1px solid var(--line); border-radius:14px; background:#fbfcfe; }}
  .result-card strong {{ display:block; font-size:28px; }}
  section {{ margin-top:28px; }}
  .section-head {{ display:flex; align-items:center; gap:10px; margin-bottom:14px; }}
  .badge,.num {{ width:30px; height:30px; display:inline-flex; align-items:center; justify-content:center; border-radius:50%; background:var(--ink); color:#fff; font-weight:900; }}
  .tag,.pill {{ display:inline-flex; padding:4px 10px; border-radius:999px; color:#fff; font-size:12px; font-weight:900; }}
  .blue {{ background:var(--blue); }} .green {{ background:var(--green); }} .amber {{ background:var(--amber); }}
  .panel {{ padding:26px; border-radius:16px; }}
  .pipeline {{ display:grid; grid-template-columns:repeat(5,1fr); gap:10px; }}
  .step {{ min-height:170px; }}
  .route {{ padding:22px; border-radius:16px; min-height:260px; }}
  .route.a {{ background:#fff1f1; border-color:#efcaca; }} .route.b {{ background:#edf9f3; border-color:#bae2c8; }}
  .route-title {{ display:flex; justify-content:space-between; gap:12px; margin-bottom:14px; }}
  .pill {{ background:#fff; color:var(--muted); }}
  .score {{ margin:18px 0 12px; }} .score-label {{ display:flex; justify-content:space-between; font-weight:900; }}
  .track,.bar {{ height:13px; border-radius:999px; background:#e5ebf2; overflow:hidden; }}
  .track span,.bar span {{ display:block; height:100%; border-radius:999px; }}
  .track.a span {{ width:{min(float(a["accessibility_score"]) / 8 * 100, 100):.1f}%; background:var(--red); }}
  .track.b span {{ width:{min(float(b["accessibility_score"]) / 8 * 100, 100):.1f}%; background:var(--green); }}
  .evidence {{ display:grid; gap:8px; margin-top:14px; }}
  .evidence div {{ padding:10px 12px; border-radius:10px; background:rgba(255,255,255,.7); color:var(--muted); border:1px solid rgba(216,225,236,.78); }}
  .tier {{ display:grid; grid-template-columns:130px 1fr 80px; gap:12px; align-items:center; margin-top:10px; }}
  .preferred {{ width:{tiers["preferred"] / counts["dongjak_crosswalks"] * 100:.1f}%; background:var(--green); }}
  .recommended {{ width:{tiers["recommended"] / counts["dongjak_crosswalks"] * 100:.1f}%; background:var(--teal); }}
  .basic {{ width:{tiers["basic"] / counts["dongjak_crosswalks"] * 100:.1f}%; background:var(--amber); }}
  .insufficient {{ width:{tiers["insufficient"] / counts["dongjak_crosswalks"] * 100:.1f}%; background:var(--red); }}
  .warning {{ padding:18px 20px; border-radius:14px; border:1px solid #edce90; border-left:6px solid var(--amber); background:#fff7e8; color:#654200; font-weight:800; }}
  code {{ padding:4px 8px; border-radius:7px; background:#edf2f7; }}
  footer {{ margin-top:28px; text-align:center; color:var(--muted); font-size:13px; }}
  @media (max-width:920px) {{ .hero,.result-board,.three,.scenario,.pipeline,.file-grid {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>
<main class="page">
  <header class="hero">
    <div>
      <span class="eyebrow">VoiceGuide Data Merge</span>
      <h1>좋은 것만 뽑아<br>시나리오용 최종 데이터로 합쳤다</h1>
      <p class="lead">내 전처리 결과와 팀원 ZIP 2개를 비교해서, 발표와 앱 데모에 바로 쓰기 좋은 형태로 다시 묶었다.</p>
      <div class="hero-answer">한 줄 결론: 우리 전처리를 기준본으로 두고, 팀원 자료의 GeoJSON·추천등급·화면 구성 장점을 흡수했다.</div>
    </div>
    <div class="result-board">
      <div class="result-card"><strong>기준본</strong><span>내 전처리 결과<br>A/B 시나리오까지 연결</span></div>
      <div class="result-card"><strong>채택</strong><span>GeoJSON, 추천등급, 근거 문구</span></div>
      <div class="result-card"><strong>제외</strong><span>90m 예시<br>우리 시나리오와 직접 연결되지 않음</span></div>
      <div class="result-card"><strong>완성</strong><span>CSV, GeoJSON, JSON, TTS, HTML</span></div>
    </div>
  </header>

  <section>
    <div class="section-head"><span class="badge">1</span><h2>세 자료를 이렇게 비교했다</h2></div>
    <div class="three">
      <div class="source"><span class="tag blue">내 전처리</span><h3>기준본으로 사용</h3><p>시나리오에 직접 연결된 데이터가 있어서 최종본의 뼈대로 삼았다.</p></div>
      <div class="source"><span class="tag green">voiceguide_scenario.zip</span><h3>구조를 가져옴</h3><p>지도와 발표 설명에 바로 쓰기 좋은 데이터 표현이 있었다.</p></div>
      <div class="source"><span class="tag amber">voiceguide전처리.zip</span><h3>화면 구성을 참고</h3><p>데모 HTML의 흐름과 카드형 대시보드 구성이 보기 좋았다.</p></div>
    </div>
  </section>

  <section>
    <div class="section-head"><span class="badge">3</span><h2>전처리는 이런 흐름으로 완성했다</h2></div>
    <div class="panel"><div class="pipeline">
      <div class="step"><div class="num">1</div><strong>역할별 분리</strong><span>복지시설, 횡단보도, 음향신호기, 버튼, 이동지원센터로 나눴다.</span></div>
      <div class="step"><div class="num">2</div><strong>좌표 보정</strong><span>위도/경도 컬럼이 뒤집힌 문제를 바로잡았다.</span></div>
      <div class="step"><div class="num">3</div><strong>시설 매칭</strong><span>원천의 보행지원시설 플래그와 교통안전시설 상세를 횡단보도 기준으로 묶었다.</span></div>
      <div class="step"><div class="num">4</div><strong>점수화</strong><span>보행등, 음향신호기, 버튼, 교통안전시설 근거를 점수로 바꿨다.</span></div>
      <div class="step"><div class="num">5</div><strong>최종 패키징</strong><span>CSV, GeoJSON, JSON, TTS, HTML로 다시 묶었다.</span></div>
    </div></div>
  </section>

  <section>
    <div class="section-head"><span class="badge">4</span><h2>시나리오에서는 이렇게 쓰인다</h2></div>
    <div class="scenario">
      <div class="route a"><div class="route-title"><h3>A 경로: 최단 후보</h3><span class="pill">탈락</span></div>
        <p>대표 횡단보도 <strong>{a["crosswalk_id"]}</strong><br>{a["address"]}</p>
        <div class="score"><div class="score-label"><span>접근성 점수</span><span>{a["accessibility_score"]}점</span></div><div class="track a"><span></span></div></div>
        <div class="evidence">{a_missing_html}</div>
      </div>
      <div class="route b"><div class="route-title"><h3>B 경로: 설명 가능한 안전 경로</h3><span class="pill">선택</span></div>
        <p>대표 횡단보도 <strong>{b["crosswalk_id"]}</strong><br>{b["address"]}</p>
        <div class="score"><div class="score-label"><span>접근성 점수</span><span>{b["accessibility_score"]}점</span></div><div class="track b"><span></span></div></div>
        <div class="evidence">{b_support_html}</div>
      </div>
    </div>
    <div class="tts">사용자 안내문: “{pair["tts_example"]}”</div>
  </section>

  <section>
    <div class="section-head"><span class="badge">5</span><h2>동작구 횡단보도 전체는 이렇게 등급화했다</h2></div>
    <div class="panel">
      <div class="tier"><strong>preferred</strong><div class="bar"><span class="preferred"></span></div><span>{tiers["preferred"]}건</span></div>
      <div class="tier"><strong>recommended</strong><div class="bar"><span class="recommended"></span></div><span>{tiers["recommended"]}건</span></div>
      <div class="tier"><strong>basic</strong><div class="bar"><span class="basic"></span></div><span>{tiers["basic"]}건</span></div>
      <div class="tier"><strong>insufficient</strong><div class="bar"><span class="insufficient"></span></div><span>{tiers["insufficient"]}건</span></div>
    </div>
  </section>

  <section>
    <div class="section-head"><span class="badge">6</span><h2>최종 파일은 이렇게 쓰면 된다</h2></div>
    <div class="file-grid">
      <div class="file"><code>final_route_comparison.csv</code><strong>발표 핵심 표</strong><p>A/B 경로 비교와 B 선택 이유를 보여준다.</p></div>
      <div class="file"><code>final_crosswalk_accessibility.csv</code><strong>횡단보도 점수표</strong><p>동작구 횡단보도 {counts["dongjak_crosswalks"]:,}건의 보행지원시설 점수를 담았다.</p></div>
      <div class="file"><code>final_crosswalk_accessibility.geojson</code><strong>지도 표시용</strong><p>대시보드 지도 레이어에 바로 올릴 수 있다.</p></div>
      <div class="file"><code>final_scenario_dataset.json</code><strong>앱 연결용</strong><p>목적지, 추천 횡단보도, A/B 비교, TTS를 한 번에 읽는다.</p></div>
      <div class="file"><code>final_tts_guidance.csv</code><strong>안내 문장</strong><p>사용자에게 들려줄 문장을 따로 정리했다.</p></div>
      <div class="file"><code>final_data_usage.html</code><strong>설명 자료</strong><p>팀원이나 교수님에게 전처리 결과를 설명할 때 쓴다.</p></div>
    </div>
  </section>

  <section>
    <div class="section-head"><span class="badge">!</span><h2>여기까지만 말해야 정확하다</h2></div>
    <div class="warning">지금 완료된 것은 “데이터 전처리 + 시나리오용 통합 데이터셋”이다. 실제 지도 API로 최단 보행거리와 우회거리를 검증한 단계는 아직 아니다.</div>
  </section>

  <footer>VoiceGuide · 데이터 통합 결과 · {datetime.now().date().isoformat()}</footer>
</main>
</body>
</html>
""",
    )


def write_zip(zip_path: Path, files: list[Path], base_dir: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in files:
            if file_path.exists():
                archive.write(file_path, arcname=file_path.relative_to(base_dir))


def preprocess(source_dir: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    crosswalks = build_crosswalks(source_dir)
    welfare = build_welfare_facilities(source_dir)
    mobility = build_mobility_centers(source_dir)
    audio_signals = build_projected_signal_table(
        source_dir, AUDIO_SIGNAL_FILE, "audio_signal"
    )
    push_buttons = build_projected_signal_table(
        source_dir, PUSH_BUTTON_FILE, "pedestrian_push_button"
    )
    demo_pair = pick_demo_pair(crosswalks)
    route_comparison = build_final_route_comparison(demo_pair)
    tts_guidance = build_final_tts_guidance(demo_pair)

    crosswalk_csv = output_dir / "dongjak_crosswalk_accessibility.csv"
    welfare_csv = output_dir / "dongjak_welfare_facilities.csv"
    mobility_csv = output_dir / "seoul_service_mobility_centers.csv"
    audio_csv = output_dir / "seoul_audio_signals_projected.csv"
    push_csv = output_dir / "seoul_pedestrian_push_buttons_projected.csv"
    geojson_path = output_dir / "dongjak_crosswalk_accessibility.geojson"
    dataset_json = output_dir / "voiceguide_scenario_dataset.json"
    usage_html = output_dir / "voiceguide_scenario_data_usage.html"
    final_route_csv = output_dir / "final_route_comparison.csv"
    final_crosswalk_csv = output_dir / "final_crosswalk_accessibility.csv"
    final_geojson_path = output_dir / "final_crosswalk_accessibility.geojson"
    final_dataset_json = output_dir / "final_scenario_dataset.json"
    final_tts_csv = output_dir / "final_tts_guidance.csv"
    final_usage_html = output_dir / "final_data_usage.html"
    summary_json = output_dir / "preprocess_summary.json"

    crosswalks.to_csv(crosswalk_csv, index=False, encoding="utf-8-sig")
    crosswalks.to_csv(final_crosswalk_csv, index=False, encoding="utf-8-sig")
    welfare.to_csv(welfare_csv, index=False, encoding="utf-8-sig")
    mobility.to_csv(mobility_csv, index=False, encoding="utf-8-sig")
    audio_signals.to_csv(audio_csv, index=False, encoding="utf-8-sig")
    push_buttons.to_csv(push_csv, index=False, encoding="utf-8-sig")
    route_comparison.to_csv(final_route_csv, index=False, encoding="utf-8-sig")
    tts_guidance.to_csv(final_tts_csv, index=False, encoding="utf-8-sig")
    write_json(geojson_path, crosswalks_to_geojson(crosswalks))
    write_json(final_geojson_path, crosswalks_to_geojson(crosswalks))

    preferred_crosswalks = crosswalks[
        crosswalks["route_recommendation_tier"].eq("preferred")
    ].head(50)
    primary_destinations = welfare[
        welfare["is_primary_destination_candidate"].eq("Y")
    ]
    seoul_located_mobility = mobility[mobility["is_located_in_seoul"].eq("Y")]

    dataset = {
        "metadata": {
            "name": "VoiceGuide scenario-ready public data",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "focus_area": "서울특별시 동작구",
            "scenario": {
                "origin": FINAL_ROUTE_ORIGIN,
                "destination": FINAL_ROUTE_DESTINATION,
                "estimated_route_detour_m": FINAL_ROUTE_DETOUR_M,
            },
            "source_dir": str(source_dir),
            "coordinate_notes": [
                "Crosswalk source columns named 경도/위도 were normalized to latitude/longitude.",
                "Audio signal and pedestrian push-button source files expose projected X/Y only, so they are exported separately without WGS84 conversion.",
                "Welfare facility source has addresses but no coordinates; geocoding is required before map markers can be shown.",
            ],
        },
        "destination_candidates": primary_destinations.to_dict("records"),
        "preferred_crosswalk_candidates": preferred_crosswalks.to_dict("records"),
        "demo_crosswalk_pair": demo_pair,
        "mobility_fallback_centers": seoul_located_mobility.to_dict("records"),
        "files": {
            "route_comparison_csv": str(final_route_csv),
            "crosswalk_csv": str(final_crosswalk_csv),
            "crosswalk_geojson": str(final_geojson_path),
            "scenario_dataset_json": str(final_dataset_json),
            "tts_guidance_csv": str(final_tts_csv),
            "data_usage_html": str(final_usage_html),
            "welfare_csv": str(welfare_csv),
            "mobility_csv": str(mobility_csv),
            "audio_signals_projected_csv": str(audio_csv),
            "pedestrian_push_buttons_projected_csv": str(push_csv),
        },
    }
    write_json(dataset_json, dataset)
    write_json(final_dataset_json, dataset)

    tier_counts = {
        tier: int(crosswalks["route_recommendation_tier"].eq(tier).sum())
        for tier in ("preferred", "recommended", "basic", "insufficient")
    }

    summary = {
        "output_dir": str(output_dir),
        "counts": {
            "dongjak_crosswalks": int(len(crosswalks)),
            "route_recommendation_tiers": tier_counts,
            "preferred_crosswalks_score_7_plus": tier_counts["preferred"],
            "crosswalks_with_audio_signal": int(
                crosswalks["has_audio_signal"].eq("Y").sum()
            ),
            "crosswalks_with_push_button": int(
                crosswalks["has_push_button"].eq("Y").sum()
            ),
            "dongjak_welfare_facilities": int(len(welfare)),
            "primary_destination_candidates": int(
                welfare["is_primary_destination_candidate"].eq("Y").sum()
            ),
            "mobility_centers_serving_seoul": int(len(mobility)),
            "mobility_centers_located_in_seoul": int(
                mobility["is_located_in_seoul"].eq("Y").sum()
            ),
            "audio_signal_projected_rows": int(len(audio_signals)),
            "pedestrian_push_button_projected_rows": int(len(push_buttons)),
        },
        "demo_pair": demo_pair,
        "files": dataset["files"] | {
            "legacy_crosswalk_csv": str(crosswalk_csv),
            "legacy_crosswalk_geojson": str(geojson_path),
            "legacy_scenario_dataset_json": str(dataset_json),
            "legacy_data_usage_html": str(usage_html),
            "summary_json": str(summary_json),
        },
    }
    write_json(summary_json, summary)
    write_final_data_usage_html(final_usage_html, summary)
    write_final_data_usage_html(usage_html, summary)
    write_final_readme(output_dir / "README.md", summary)
    write_zip(
        output_dir.with_suffix(".zip"),
        [
            final_route_csv,
            final_crosswalk_csv,
            final_geojson_path,
            final_dataset_json,
            final_tts_csv,
            final_usage_html,
            output_dir / "README.md",
            summary_json,
        ],
        output_dir,
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preprocess public data for the VoiceGuide scenario demo."
    )
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    summary = preprocess(args.source_dir, args.output_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
