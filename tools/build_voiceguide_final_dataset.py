from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd


ROOT = Path(r"C:\VoiceGuide\VoiceGuide")
PROCESSED = ROOT / "data" / "processed" / "voiceguide"
DEFAULT_OUT = ROOT / "data" / "processed" / "voiceguide_final"


def yn(value) -> str:
    if isinstance(value, bool):
        return "Y" if value else "N"
    text = "" if pd.isna(value) else str(value).strip().upper()
    return "Y" if text in {"Y", "YES", "TRUE", "1", "있음", "설치", "O"} else "N"


def truthy(value) -> bool:
    return yn(value) == "Y"


def accessibility_score(row: dict | pd.Series) -> int:
    return (
        (1 if truthy(row.get("has_pedestrian_light")) else 0)
        + (3 if truthy(row.get("has_audio_signal")) else 0)
        + (2 if truthy(row.get("has_push_button")) else 0)
        + (1 if truthy(row.get("is_raised_crosswalk")) else 0)
        + (1 if truthy(row.get("has_traffic_safety_detail")) else 0)
    )


def route_tier(score: int) -> str:
    if score >= 6:
        return "preferred"
    if score >= 3:
        return "recommended"
    if score >= 1:
        return "basic"
    return "insufficient"


def support_evidence(row: dict | pd.Series) -> str:
    parts = []
    if truthy(row.get("has_pedestrian_light")):
        parts.append("보행등")
    if truthy(row.get("has_audio_signal")):
        parts.append("음향신호기")
    if truthy(row.get("has_push_button")):
        parts.append("보행자작동신호기")
    if truthy(row.get("is_raised_crosswalk")):
        parts.append("고원식횡단보도")
    if truthy(row.get("has_traffic_safety_detail")):
        parts.append("교통안전시설 상세")
    return ", ".join(parts) if parts else "보행지원시설 확인 정보 없음"


def save_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig")


def build_crosswalk_accessibility() -> pd.DataFrame:
    ours = read_csv(PROCESSED / "03_pedestrian_support" / "crosswalks_with_support_score_dongjak.csv")

    traffic_detail_path = PROCESSED / "99_reference" / "tgis_2021_crosswalk_shape_centroids.csv"
    traffic_ids: set[str] = set()
    if traffic_detail_path.exists():
        traffic = read_csv(traffic_detail_path)
        if "MGRNU" in traffic.columns:
            traffic_ids = set(traffic["MGRNU"].dropna().astype(str).str.strip())

    final = pd.DataFrame(
        {
            "crosswalk_id": ours["crosswalk_id"].astype(str),
            "district": ours["gu"],
            "address": ours["address"],
            "crosswalk_type": ours["crosswalk_type"],
            "latitude": ours["lat"],
            "longitude": ours["lon"],
            "has_pedestrian_light": ours["has_pedestrian_signal"].map(yn),
            "has_audio_signal": ours["has_audio_signal"].map(yn),
            "has_push_button": ours["has_pedestrian_button"].map(yn),
            "is_raised_crosswalk": ours["is_elevated_crosswalk"].map(yn),
            "has_traffic_safety_detail": ours["crosswalk_id"].astype(str).isin(traffic_ids).map(yn),
            "nearest_audio_signal_id": ours.get("nearest_audio_signal_id", ""),
            "nearest_audio_signal_distance_m": ours.get("nearest_audio_signal_distance_m", ""),
            "nearest_push_button_id": ours.get("nearest_pedestrian_button_id", ""),
            "nearest_push_button_distance_m": ours.get("nearest_pedestrian_button_distance_m", ""),
            "data_reference_date": ours["reference_date"],
            "coordinate_note": "source_columns_swapped_and_normalized",
        }
    )
    final["accessibility_score"] = final.apply(accessibility_score, axis=1)
    final["route_recommendation_tier"] = final["accessibility_score"].map(route_tier)
    final["support_evidence"] = final.apply(support_evidence, axis=1)

    column_order = [
        "crosswalk_id",
        "district",
        "address",
        "crosswalk_type",
        "latitude",
        "longitude",
        "has_pedestrian_light",
        "has_audio_signal",
        "has_push_button",
        "is_raised_crosswalk",
        "has_traffic_safety_detail",
        "accessibility_score",
        "route_recommendation_tier",
        "support_evidence",
        "nearest_audio_signal_id",
        "nearest_audio_signal_distance_m",
        "nearest_push_button_id",
        "nearest_push_button_distance_m",
        "data_reference_date",
        "coordinate_note",
    ]
    return final[column_order].sort_values(
        ["accessibility_score", "crosswalk_id"], ascending=[False, True]
    )


def geojson_from_crosswalks(crosswalks: pd.DataFrame) -> dict:
    features = []
    for row in crosswalks.itertuples(index=False):
        props = row._asdict()
        lon = props.pop("longitude")
        lat = props.pop("latitude")
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]},
                "properties": props,
            }
        )
    return {"type": "FeatureCollection", "features": features}


def build_route_comparison(crosswalks: pd.DataFrame) -> pd.DataFrame:
    routes = read_csv(PROCESSED / "07_scenario_demo" / "scenario_route_comparison.csv")
    enriched = routes.merge(
        crosswalks[
            [
                "crosswalk_id",
                "accessibility_score",
                "route_recommendation_tier",
                "support_evidence",
                "has_traffic_safety_detail",
            ]
        ],
        left_on="main_crosswalk_id",
        right_on="crosswalk_id",
        how="left",
    ).drop(columns=["crosswalk_id"])

    enriched["final_selection_reason"] = enriched.apply(
        lambda row: (
            "최단 후보지만 보행지원시설 근거가 부족해 선택하지 않음"
            if row["route_id"] == "A"
            else "보행등, 음향신호기, 보행자작동신호기 등 설명 가능한 근거가 있어 선택"
        ),
        axis=1,
    )
    return enriched


def build_destination_candidates() -> pd.DataFrame:
    welfare = read_csv(PROCESSED / "01_destination" / "welfare_facilities_dongjak.csv")
    candidates = welfare[welfare["is_welfare_center"].map(truthy)].copy()
    if len(candidates) < 4:
        candidates = pd.concat([candidates, welfare[~welfare.index.isin(candidates.index)]])
    candidates = candidates.head(4).copy()
    candidates["geocode_status"] = "address_only_needs_geocoding"
    return candidates


def build_mobility_fallback() -> pd.DataFrame:
    mobility = read_csv(PROCESSED / "06_mobility_support" / "mobility_support_centers_seoul_capital_area.csv")
    seoul = mobility[
        mobility["road_address"].fillna("").str.contains("서울")
        | mobility["inside_area"].fillna("").str.contains("서울")
        | mobility["outside_area"].fillna("").str.contains("서울")
    ].copy()
    if seoul.empty:
        seoul = mobility.copy()
    return seoul.head(5)


def records(df: pd.DataFrame) -> list[dict]:
    return json.loads(df.where(pd.notna(df), "").to_json(orient="records", force_ascii=False))


def build_scenario_json(
    crosswalks: pd.DataFrame,
    route_comparison: pd.DataFrame,
    destinations: pd.DataFrame,
    mobility: pd.DataFrame,
) -> dict:
    tts = read_csv(PROCESSED / "07_scenario_demo" / "scenario_tts_guidance.csv")
    preferred = crosswalks[crosswalks["route_recommendation_tier"].eq("preferred")].head(50)

    route_a = route_comparison[route_comparison["route_id"].eq("A")].iloc[0].to_dict()
    route_b = route_comparison[route_comparison["route_id"].eq("B")].iloc[0].to_dict()

    return {
        "metadata": {
            "name": "VoiceGuide final scenario-ready dataset",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "focus_area": "서울특별시 동작구",
            "scenario": "보라매역에서 서울시남부장애인종합복지관까지 이동",
            "distance_note": "지도 경로 API 미연동 상태이므로 거리는 대표 횡단보도 경유 직선거리 합 기반 데모값입니다.",
        },
        "destination_candidates": records(destinations),
        "preferred_crosswalk_candidates": records(preferred),
        "demo_crosswalk_pair": {
            "shortest_route_crosswalk_a": route_a,
            "safer_route_crosswalk_b": route_b,
            "selection_rule": "거리 차이가 작고 B의 보행지원시설 근거가 더 많으면 B를 선택",
        },
        "tts_guidance": records(tts),
        "mobility_fallback_centers": records(mobility),
        "files": {
            "crosswalk_csv": "final_crosswalk_accessibility.csv",
            "crosswalk_geojson": "final_crosswalk_accessibility.geojson",
            "route_comparison_csv": "final_route_comparison.csv",
            "tts_csv": "final_tts_guidance.csv",
            "usage_html": "final_data_usage.html",
        },
    }


def write_usage_html(output_dir: Path, crosswalks: pd.DataFrame, route_comparison: pd.DataFrame) -> None:
    preferred_count = int(crosswalks["route_recommendation_tier"].eq("preferred").sum())
    recommended_count = int(crosswalks["route_recommendation_tier"].eq("recommended").sum())
    basic_count = int(crosswalks["route_recommendation_tier"].eq("basic").sum())
    insufficient_count = int(crosswalks["route_recommendation_tier"].eq("insufficient").sum())
    route_a = route_comparison[route_comparison["route_id"].eq("A")].iloc[0]
    route_b = route_comparison[route_comparison["route_id"].eq("B")].iloc[0]
    route_a_score = int(route_a["accessibility_score"])
    route_b_score = int(route_b["accessibility_score"])
    route_a_width = max(route_a_score * 12, 8)
    route_b_width = max(route_b_score * 12, 8)
    html = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>VoiceGuide 최종 전처리 통합 리포트</title>
  <style>
    :root {{
      --bg: #f5f7fb;
      --paper: #ffffff;
      --ink: #18212f;
      --muted: #5f6b7a;
      --line: #dce3ec;
      --navy: #18324a;
      --blue: #2457d6;
      --teal: #0b7f7a;
      --green: #26734d;
      --amber: #9a6200;
      --red: #b23b3b;
      --violet: #6a4fb3;
      --shadow: 0 16px 34px rgba(24, 33, 47, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans KR", Arial, sans-serif;
      line-height: 1.65;
      word-break: keep-all;
    }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 42px 22px 72px; }}
    header {{
      min-height: 430px;
      display: grid;
      grid-template-columns: minmax(0, 1.05fr) minmax(340px, 0.95fr);
      gap: 30px;
      align-items: center;
      padding: 34px;
      background:
        linear-gradient(rgba(255,255,255,0.92), rgba(255,255,255,0.92)),
        url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='900' height='520' viewBox='0 0 900 520'%3E%3Crect width='900' height='520' fill='%23eef4ff'/%3E%3Cg fill='none' stroke='%23b9c7dd' stroke-width='3'%3E%3Cpath d='M0 85h900M0 190h900M0 310h900M0 430h900M120 0v520M270 0v520M450 0v520M640 0v520M810 0v520'/%3E%3Cpath d='M50 470 C210 300 350 260 510 120 S770 60 900 25' stroke='%232457d6' stroke-width='8'/%3E%3Cpath d='M60 500 C230 350 410 325 580 210 S740 150 875 95' stroke='%230b7f7a' stroke-width='8'/%3E%3C/g%3E%3Cg fill='%23ffffff' stroke='%2318324a' stroke-width='5'%3E%3Ccircle cx='82' cy='452' r='18'/%3E%3Ccircle cx='590' cy='205' r='18'/%3E%3Ccircle cx='842' cy='112' r='18'/%3E%3C/g%3E%3C/svg%3E");
      background-size: cover;
      border: 1px solid var(--line);
      border-radius: 18px;
      box-shadow: var(--shadow);
      overflow: hidden;
    }}
    .eyebrow {{ margin: 0 0 10px; color: var(--teal); font-size: 14px; font-weight: 900; }}
    h1 {{ margin: 0; color: var(--navy); font-size: clamp(32px, 4.4vw, 54px); line-height: 1.1; letter-spacing: -0.02em; }}
    .lead {{ max-width: 760px; margin: 18px 0 0; color: var(--muted); font-size: 18px; }}
    section {{
      margin-top: 26px;
      padding: 26px;
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 14px;
      box-shadow: 0 8px 22px rgba(24, 33, 47, 0.045);
      animation: rise 0.65s ease both;
    }}
    h2 {{ margin: 0 0 14px; color: var(--navy); font-size: 24px; line-height: 1.3; }}
    h3 {{ margin: 0 0 8px; color: var(--ink); font-size: 18px; }}
    p {{ margin: 0; color: var(--muted); }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 14px; overflow: hidden; border-radius: 10px; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 13px 14px; text-align: left; vertical-align: top; }}
    th {{ background: #edf2f7; color: var(--navy); font-size: 14px; white-space: nowrap; }}
    tr:last-child td {{ border-bottom: 0; }}
    code {{ background: #eef1f5; padding: 2px 5px; border-radius: 5px; color: #273448; }}
    .hero-panel {{
      padding: 22px;
      border: 1px solid rgba(36, 87, 214, 0.22);
      background: rgba(255, 255, 255, 0.82);
      border-radius: 14px;
      backdrop-filter: blur(6px);
    }}
    .metric-grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-top: 18px; }}
    .metric {{
      padding: 16px;
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 10px;
    }}
    .metric strong {{ display: block; color: var(--navy); font-size: 26px; line-height: 1.1; }}
    .metric span {{ color: var(--muted); font-size: 13px; }}
    .grid-3 {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }}
    .card {{ padding: 18px; background: #fff; border: 1px solid var(--line); border-radius: 10px; }}
    .tag {{ display: inline-block; margin-bottom: 10px; padding: 4px 10px; border-radius: 999px; color: #fff; font-size: 12px; font-weight: 900; }}
    .blue {{ background: var(--blue); }}
    .teal {{ background: var(--teal); }}
    .green {{ background: var(--green); }}
    .amber {{ background: var(--amber); }}
    .violet {{ background: var(--violet); }}
    .red {{ background: var(--red); }}
    .route-wrap {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
    .route-card {{ position: relative; padding: 20px; border: 1px solid var(--line); border-radius: 12px; overflow: hidden; background: #fff; }}
    .route-card.selected {{ border-color: rgba(38, 115, 77, 0.45); background: #f1faf5; }}
    .score-line {{ height: 10px; margin: 14px 0 8px; background: #e7ecf3; border-radius: 999px; overflow: hidden; }}
    .score-line span {{ display: block; height: 100%; border-radius: inherit; animation: fill 1.1s ease both; }}
    .score-a {{ width: {route_a_width}%; background: var(--amber); }}
    .score-b {{ width: {route_b_width}%; background: var(--green); }}
    .route-stage {{
      position: relative;
      min-height: 210px;
      margin-top: 16px;
      padding: 22px;
      background: #f8fafc;
      border: 1px solid var(--line);
      border-radius: 12px;
      overflow: hidden;
    }}
    .route-line {{
      position: absolute;
      left: 10%;
      right: 10%;
      top: 50%;
      height: 5px;
      background: #c9d3e1;
      border-radius: 999px;
    }}
    .route-line.safe {{
      top: 64%;
      background: var(--green);
      transform-origin: left;
      animation: draw 1.4s ease both;
    }}
    .route-line.short {{
      top: 38%;
      background: var(--amber);
      transform-origin: left;
      animation: draw 1.1s ease both;
    }}
    .pin {{
      position: absolute;
      width: 18px;
      height: 18px;
      border-radius: 50%;
      background: #fff;
      border: 4px solid var(--navy);
      z-index: 2;
    }}
    .pin.start {{ left: 9%; top: 47%; }}
    .pin.a {{ left: 46%; top: 33%; border-color: var(--amber); }}
    .pin.b {{ left: 58%; top: 59%; border-color: var(--green); animation: pulse 1.6s ease-in-out infinite; }}
    .pin.dest {{ right: 9%; top: 47%; border-color: var(--blue); }}
    .legend {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 14px; color: var(--muted); font-size: 14px; }}
    .dot {{ width: 10px; height: 10px; display: inline-block; border-radius: 50%; margin-right: 6px; }}
    .timeline {{ display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; margin-top: 14px; }}
    .step {{ padding: 16px; border: 1px solid var(--line); border-radius: 10px; background: #fff; }}
    .step-num {{ width: 28px; height: 28px; display: inline-grid; place-items: center; margin-bottom: 8px; border-radius: 50%; background: var(--navy); color: #fff; font-weight: 900; font-size: 13px; }}
    .callout {{ margin-top: 14px; padding: 16px 18px; border: 1px solid #c8d8ff; border-radius: 10px; background: #eef4ff; color: var(--navy); font-weight: 800; }}
    .warn {{ border-color: #f0d59a; background: #fff7e6; color: #735100; }}
    .file-list {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }}
    .file {{ padding: 14px; border: 1px solid var(--line); border-radius: 10px; background: #fff; }}
    footer {{ margin-top: 26px; color: var(--muted); font-size: 14px; }}
    @keyframes rise {{ from {{ opacity: 0; transform: translateY(16px); }} to {{ opacity: 1; transform: translateY(0); }} }}
    @keyframes fill {{ from {{ width: 0; }} }}
    @keyframes draw {{ from {{ transform: scaleX(0); }} to {{ transform: scaleX(1); }} }}
    @keyframes pulse {{ 0%, 100% {{ box-shadow: 0 0 0 0 rgba(38, 115, 77, 0.34); }} 50% {{ box-shadow: 0 0 0 12px rgba(38, 115, 77, 0); }} }}
    @media (max-width: 920px) {{
      main {{ padding: 24px 14px 48px; }}
      header {{ grid-template-columns: 1fr; min-height: auto; padding: 22px; }}
      section {{ padding: 20px; }}
      .metric-grid, .grid-3, .route-wrap, .timeline, .file-list {{ grid-template-columns: 1fr; }}
      table {{ display: block; overflow-x: auto; white-space: nowrap; }}
    }}
  </style>
</head>
<body>
<main>
  <header>
    <div>
      <p class="eyebrow">Final Data Integration Report</p>
      <h1>VoiceGuide 시나리오용 데이터, 이렇게 합쳤습니다</h1>
      <p class="lead">
        두 ZIP 파일과 현재 전처리 결과를 비교해서, 발표와 앱 데모에 필요한 장점만 남겼습니다.
        목표는 “데이터가 많다”가 아니라 “왜 안전 경로를 선택했는지 설명할 수 있다”입니다.
      </p>
      <div class="metric-grid">
        <div class="metric"><strong>{len(crosswalks):,}</strong><span>동작구 횡단보도</span></div>
        <div class="metric"><strong>{preferred_count:,}</strong><span>우선권장 후보</span></div>
        <div class="metric"><strong>2</strong><span>A/B 비교 경로</span></div>
        <div class="metric"><strong>7</strong><span>최종 산출 파일</span></div>
      </div>
    </div>
    <div class="hero-panel">
      <h3>핵심 선택</h3>
      <p>
        최단 후보 A는 보행지원시설 근거가 부족하고,
        안전 후보 B는 보행등, 음향신호기, 보행자작동신호기 근거가 있어 선택했습니다.
      </p>
      <div class="route-stage" aria-label="A 경로와 B 경로 비교 그림">
        <div class="route-line short"></div>
        <div class="route-line safe"></div>
        <span class="pin start" title="보라매역"></span>
        <span class="pin a" title="최단 후보 A"></span>
        <span class="pin b" title="안전 후보 B"></span>
        <span class="pin dest" title="서울시남부장애인종합복지관"></span>
      </div>
      <div class="legend">
        <span><i class="dot" style="background: var(--amber);"></i>최단 후보 A</span>
        <span><i class="dot" style="background: var(--green);"></i>안전 후보 B</span>
        <span><i class="dot" style="background: var(--blue);"></i>목적지</span>
      </div>
    </div>
  </header>

  <section>
    <h2>무엇을 비교했나</h2>
    <div class="grid-3">
      <article class="card">
        <span class="tag blue">우리 전처리</span>
        <h3>기준본</h3>
        <p>원본 데이터를 목적지, 횡단보도, 음향신호기, 보행자작동신호기, 이동지원센터로 나누고 A/B 시나리오까지 만든 결과입니다.</p>
      </article>
      <article class="card">
        <span class="tag green">voiceguide_scenario.zip</span>
        <h3>채택</h3>
        <p>GeoJSON, 추천 등급, <code>support_evidence</code>처럼 발표에서 바로 읽히는 근거 문구 구조를 가져왔습니다.</p>
      </article>
      <article class="card">
        <span class="tag amber">voiceguide전처리.zip</span>
        <h3>참고</h3>
        <p>데모 HTML 화면 흐름은 참고했습니다. 다만 시나리오 기준이 달라서 90m 예시는 그대로 쓰지 않았습니다.</p>
      </article>
    </div>
  </section>

  <section>
    <h2>최종 판단 결과</h2>
    <table>
      <tr>
        <th>구분</th>
        <th>대표 횡단보도</th>
        <th>보행지원 근거</th>
        <th>점수</th>
        <th>선택</th>
      </tr>
      <tr>
        <td><strong>A: 최단 후보</strong></td>
        <td>{route_a['main_crosswalk_id']}<br>{route_a['main_crosswalk_address']}</td>
        <td>{route_a['support_evidence']}</td>
        <td>
          <strong>{route_a_score}점</strong>
          <div class="score-line"><span class="score-a"></span></div>
        </td>
        <td>선택하지 않음</td>
      </tr>
      <tr>
        <td><strong>B: 설명 가능한 안전 경로</strong></td>
        <td>{route_b['main_crosswalk_id']}<br>{route_b['main_crosswalk_address']}</td>
        <td>{route_b['support_evidence']}</td>
        <td>
          <strong>{route_b_score}점</strong>
          <div class="score-line"><span class="score-b"></span></div>
        </td>
        <td><strong>선택</strong></td>
      </tr>
    </table>
    <div class="callout">
      최종 안내 문장: 최단 후보보다 약 {int(route_b['distance_delta_vs_shortest_m'])}m 더 이동하지만,
      보행등과 음향신호기, 보행자작동신호기 정보가 있는 횡단보도로 안내합니다.
    </div>
  </section>

  <section>
    <h2>작업 흐름</h2>
    <div class="timeline">
      <div class="step"><span class="step-num">1</span><h3>원본 분류</h3><p>복지시설, 횡단보도, 보행지원시설, 이동지원센터를 역할별로 분리했습니다.</p></div>
      <div class="step"><span class="step-num">2</span><h3>좌표 정리</h3><p>위도/경도 컬럼 오류를 보정하고 지도에 올릴 수 있게 정리했습니다.</p></div>
      <div class="step"><span class="step-num">3</span><h3>시설 매칭</h3><p>횡단보도 주변 30m 안의 음향신호기와 버튼 정보를 연결했습니다.</p></div>
      <div class="step"><span class="step-num">4</span><h3>점수화</h3><p>보행등, 음향신호기, 버튼, 고원식, 교통안전시설 상세를 점수로 바꿨습니다.</p></div>
      <div class="step"><span class="step-num">5</span><h3>최종 패키징</h3><p>CSV, GeoJSON, JSON, TTS 문장, 설명 HTML로 묶었습니다.</p></div>
    </div>
  </section>

  <section>
    <h2>횡단보도 등급 분포</h2>
    <table>
      <tr><th>등급</th><th>의미</th><th>개수</th><th>사용 방식</th></tr>
      <tr><td><strong>preferred</strong></td><td>보행지원 근거가 충분한 우선 후보</td><td>{preferred_count:,}</td><td>안전 경로 후보로 먼저 검토</td></tr>
      <tr><td><strong>recommended</strong></td><td>일부 보행지원시설 근거가 있는 후보</td><td>{recommended_count:,}</td><td>주변 후보가 없을 때 검토</td></tr>
      <tr><td><strong>basic</strong></td><td>최소 정보만 있는 후보</td><td>{basic_count:,}</td><td>최단 경로 비교용 또는 보조 후보</td></tr>
      <tr><td><strong>insufficient</strong></td><td>보행지원 근거가 부족한 후보</td><td>{insufficient_count:,}</td><td>단독 추천하지 않음</td></tr>
    </table>
  </section>

  <section>
    <h2>최종 산출 파일</h2>
    <div class="file-list">
      <div class="file"><h3><code>final_route_comparison.csv</code></h3><p>A/B 경로 비교, 선택 여부, 선택 이유를 담은 발표 핵심 파일입니다.</p></div>
      <div class="file"><h3><code>final_crosswalk_accessibility.csv</code></h3><p>동작구 횡단보도 {len(crosswalks):,}건의 보행지원 점수표입니다.</p></div>
      <div class="file"><h3><code>final_crosswalk_accessibility.geojson</code></h3><p>지도에 바로 올릴 수 있는 횡단보도 포인트 파일입니다.</p></div>
      <div class="file"><h3><code>final_scenario_dataset.json</code></h3><p>앱이나 대시보드에서 한 번에 읽기 위한 대표 JSON입니다.</p></div>
      <div class="file"><h3><code>final_tts_guidance.csv</code></h3><p>사용자에게 말할 안내 문장을 따로 정리한 파일입니다.</p></div>
      <div class="file"><h3><code>final_destination_candidates.csv</code></h3><p>동작구 목적지 후보 4개와 지오코딩 필요 상태를 담았습니다.</p></div>
    </div>
  </section>

  <section>
    <h2>주의할 점</h2>
    <div class="callout warn">
      현재 거리는 지도 API 기반 실제 보행거리가 아니라 대표 횡단보도 경유 직선거리 합입니다.
      발표에서는 “공공데이터 기반 시나리오 데이터”라고 말하고,
      “실제 최단 보행거리 검증”은 다음 단계로 분리해야 합니다.
    </div>
  </section>
  <footer>VoiceGuide final data report · generated from processed public data</footer>
</main>
</body>
</html>
"""
    (output_dir / "final_data_usage.html").write_text(html, encoding="utf-8")


def write_readme(output_dir: Path) -> None:
    readme = """# VoiceGuide final scenario-ready dataset

이 폴더는 `voiceguide전처리.zip`, `voiceguide_scenario.zip`, 그리고 현재 전처리 결과의 장점을 합친 최종 산출물입니다.

## 기준

- 현재 전처리 결과를 기준본으로 사용했습니다.
- `voiceguide_scenario.zip`의 GeoJSON, 추천 등급, 근거 문구 구조를 반영했습니다.
- `voiceguide전처리.zip`의 데모 화면 방향은 HTML 설명 구성에 참고했습니다.

## 주의

지도 경로 API를 아직 붙이지 않았으므로 `final_route_comparison.csv`의 거리는 실제 보행 네트워크 거리가 아닙니다.
"""
    (output_dir / "README.md").write_text(readme, encoding="utf-8")


def build(output_dir: Path = DEFAULT_OUT) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    crosswalks = build_crosswalk_accessibility()
    route_comparison = build_route_comparison(crosswalks)
    destinations = build_destination_candidates()
    mobility = build_mobility_fallback()
    tts = read_csv(PROCESSED / "07_scenario_demo" / "scenario_tts_guidance.csv")
    dataset = build_scenario_json(crosswalks, route_comparison, destinations, mobility)

    save_csv(crosswalks, output_dir / "final_crosswalk_accessibility.csv")
    save_csv(route_comparison, output_dir / "final_route_comparison.csv")
    save_csv(destinations, output_dir / "final_destination_candidates.csv")
    save_csv(mobility, output_dir / "final_mobility_fallback_centers.csv")
    save_csv(tts, output_dir / "final_tts_guidance.csv")

    (output_dir / "final_crosswalk_accessibility.geojson").write_text(
        json.dumps(geojson_from_crosswalks(crosswalks), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "final_scenario_dataset.json").write_text(
        json.dumps(dataset, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_usage_html(output_dir, crosswalks, route_comparison)
    write_readme(output_dir)

    print(f"final_output_dir={output_dir}")
    print(f"crosswalk_rows={len(crosswalks)}")
    print(f"preferred_crosswalks={int(crosswalks['route_recommendation_tier'].eq('preferred').sum())}")


if __name__ == "__main__":
    build()
