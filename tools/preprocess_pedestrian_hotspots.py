"""Preprocess pedestrian accident hotspot CSV for VoiceGuide dashboards.

The source file from TAAS-style exports is usually CP949 encoded and includes
Korean column names, point coordinates, and a polygon string per hotspot.
This script normalizes it into UTF-8 CSV plus GeoJSON artifacts that can be
loaded by the dashboard or a future nearby-risk API.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = Path(r"C:\Users\ghksw\Downloads\19_24_pedstrians.csv")
DEFAULT_OUTPUT_DIR = ROOT / "datasets" / "pedestrian_hotspots"

NUMERIC_COLUMNS = {
    "사고건수": int,
    "사상자수": int,
    "사망자수": int,
    "중상자수": int,
    "경상자수": int,
    "부상신고자수": int,
    "경도": float,
    "위도": float,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--cluster-radius-m", type=float, default=120.0)
    return parser.parse_args()


def read_rows(source: Path) -> list[dict[str, Any]]:
    with source.open("r", encoding="cp949", newline="") as f:
        reader = csv.DictReader(f)
        rows: list[dict[str, Any]] = []
        for row in reader:
            clean = {k: (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
            for key, parser in NUMERIC_COLUMNS.items():
                clean[key] = parser(clean[key])
            clean["지점코드"] = str(clean["지점코드"]).strip()
            clean["source_batch_id"] = str(clean["사고다발지id"]).strip()
            clean["source_year"] = int(clean["source_batch_id"][:4])
            clean["risk_score"] = calc_risk_score(clean)
            clean["risk_score_norm"] = 0.0
            clean["risk_percentile"] = 0.0
            clean["risk_level"] = ""
            clean["risk_level_ko"] = ""
            clean["display_name"] = make_display_name(clean["지점명"])
            clean["polygon"] = json.loads(clean["다발지역폴리곤"])
            rows.append(clean)
    return rows


def calc_risk_score(row: dict[str, Any]) -> float:
    return round(
        row["사고건수"]
        + row["사망자수"] * 10
        + row["중상자수"] * 4
        + row["경상자수"]
        + row["부상신고자수"] * 0.5,
        2,
    )


def make_display_name(place_name: str) -> str:
    return (
        place_name.replace("서울특별시 ", "서울 ")
        .replace("부산광역시 ", "부산 ")
        .replace("전라남도 ", "전남 ")
        .replace("경기도 ", "경기 ")
    )


def assign_risk_levels(rows: list[dict[str, Any]]) -> None:
    scores = sorted(row["risk_score"] for row in rows)
    min_score = scores[0]
    max_score = scores[-1]
    high_threshold = percentile(scores, 80)
    medium_threshold = percentile(scores, 40)

    for row in rows:
        score = row["risk_score"]
        if max_score == min_score:
            norm = 1.0
        else:
            norm = (score - min_score) / (max_score - min_score)
        row["risk_score_norm"] = round(norm, 4)
        row["risk_percentile"] = round(percentile_rank(scores, score), 4)
        if score >= high_threshold:
            row["risk_level"] = "high"
            row["risk_level_ko"] = "고위험"
        elif score >= medium_threshold:
            row["risk_level"] = "medium"
            row["risk_level_ko"] = "주의"
        else:
            row["risk_level"] = "low"
            row["risk_level_ko"] = "관심"


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    pos = (len(values) - 1) * pct / 100
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return values[lo]
    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


def percentile_rank(sorted_values: list[float], value: float) -> float:
    count = sum(1 for item in sorted_values if item <= value)
    return count / len(sorted_values) if sorted_values else 0.0


def build_feature(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "Feature",
        "geometry": row["polygon"],
        "properties": {
            "hotspot_fid": row["사고다발지fid"],
            "hotspot_id": row["사고다발지id"],
            "source_batch_id": row["source_batch_id"],
            "source_year": row["source_year"],
            "legal_dong_code": row["법정동코드"],
            "site_code": row["지점코드"],
            "district": row["시도시군구명"],
            "place_name": row["지점명"],
            "display_name": row["display_name"],
            "accidents": row["사고건수"],
            "casualties": row["사상자수"],
            "deaths": row["사망자수"],
            "serious_injuries": row["중상자수"],
            "minor_injuries": row["경상자수"],
            "reported_injuries": row["부상신고자수"],
            "center_lng": row["경도"],
            "center_lat": row["위도"],
            "risk_score": row["risk_score"],
            "risk_score_norm": row["risk_score_norm"],
            "risk_percentile": row["risk_percentile"],
            "risk_level": row["risk_level"],
            "risk_level_ko": row["risk_level_ko"],
        },
    }


def haversine_m(a: dict[str, Any], b: dict[str, Any]) -> float:
    radius = 6_371_000.0
    lat1 = math.radians(a["위도"])
    lat2 = math.radians(b["위도"])
    dlat = lat2 - lat1
    dlng = math.radians(b["경도"] - a["경도"])
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(h))


def cluster_rows(rows: list[dict[str, Any]], radius_m: float) -> list[list[dict[str, Any]]]:
    clusters: list[list[dict[str, Any]]] = []
    for row in sorted(rows, key=lambda item: item["risk_score"], reverse=True):
        best_cluster: list[dict[str, Any]] | None = None
        best_distance = float("inf")
        for cluster in clusters:
            dist = haversine_m(row, cluster[0])
            if dist <= radius_m and dist < best_distance:
                best_cluster = cluster
                best_distance = dist
        if best_cluster is None:
            clusters.append([row])
        else:
            best_cluster.append(row)
    return clusters


def build_cluster_feature(cluster: list[dict[str, Any]], index: int) -> dict[str, Any]:
    top = max(cluster, key=lambda row: row["risk_score"])
    accidents = sum(row["사고건수"] for row in cluster)
    casualties = sum(row["사상자수"] for row in cluster)
    deaths = sum(row["사망자수"] for row in cluster)
    serious = sum(row["중상자수"] for row in cluster)
    years = sorted({row["source_year"] for row in cluster})
    levels = Counter(row["risk_level"] for row in cluster)
    lng = sum(row["경도"] for row in cluster) / len(cluster)
    lat = sum(row["위도"] for row in cluster) / len(cluster)
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [round(lng, 8), round(lat, 8)]},
        "properties": {
            "cluster_id": f"ped_hotspot_cluster_{index:04d}",
            "display_name": top["display_name"],
            "representative_place_name": top["지점명"],
            "representative_district": top["시도시군구명"],
            "member_count": len(cluster),
            "repeat_year_count": len(years),
            "source_years": years,
            "accidents_total": accidents,
            "casualties_total": casualties,
            "deaths_total": deaths,
            "serious_injuries_total": serious,
            "max_risk_score": top["risk_score"],
            "avg_risk_score": round(sum(row["risk_score"] for row in cluster) / len(cluster), 2),
            "risk_level": top["risk_level"],
            "risk_level_ko": top["risk_level_ko"],
            "high_member_count": levels["high"],
            "center_lng": round(lng, 8),
            "center_lat": round(lat, 8),
        },
    }


def write_normalized_csv(rows: list[dict[str, Any]], output_path: Path) -> None:
    fieldnames = [
        "hotspot_fid",
        "hotspot_id",
        "source_year",
        "legal_dong_code",
        "site_code",
        "district",
        "place_name",
        "display_name",
        "accidents",
        "casualties",
        "deaths",
        "serious_injuries",
        "minor_injuries",
        "reported_injuries",
        "center_lng",
        "center_lat",
        "risk_score",
        "risk_score_norm",
        "risk_percentile",
        "risk_level",
        "risk_level_ko",
    ]
    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "hotspot_fid": row["사고다발지fid"],
                    "hotspot_id": row["사고다발지id"],
                    "source_year": row["source_year"],
                    "legal_dong_code": row["법정동코드"],
                    "site_code": row["지점코드"],
                    "district": row["시도시군구명"],
                    "place_name": row["지점명"],
                    "display_name": row["display_name"],
                    "accidents": row["사고건수"],
                    "casualties": row["사상자수"],
                    "deaths": row["사망자수"],
                    "serious_injuries": row["중상자수"],
                    "minor_injuries": row["경상자수"],
                    "reported_injuries": row["부상신고자수"],
                    "center_lng": row["경도"],
                    "center_lat": row["위도"],
                    "risk_score": row["risk_score"],
                    "risk_score_norm": row["risk_score_norm"],
                    "risk_percentile": row["risk_percentile"],
                    "risk_level": row["risk_level"],
                    "risk_level_ko": row["risk_level_ko"],
                }
            )


def build_summary(
    rows: list[dict[str, Any]],
    clusters: list[list[dict[str, Any]]],
    cluster_radius_m: float,
) -> dict[str, Any]:
    by_level = Counter(row["risk_level"] for row in rows)
    by_year = Counter(row["source_year"] for row in rows)
    by_district: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "hotspot_count": 0,
            "accidents": 0,
            "casualties": 0,
            "deaths": 0,
            "serious_injuries": 0,
            "max_risk_score": 0.0,
        }
    )
    for row in rows:
        district = strip_district_suffix(row["시도시군구명"])
        item = by_district[district]
        item["hotspot_count"] += 1
        item["accidents"] += row["사고건수"]
        item["casualties"] += row["사상자수"]
        item["deaths"] += row["사망자수"]
        item["serious_injuries"] += row["중상자수"]
        item["max_risk_score"] = max(item["max_risk_score"], row["risk_score"])

    top_districts = sorted(
        ({"district": key, **value} for key, value in by_district.items()),
        key=lambda item: (item["accidents"], item["max_risk_score"]),
        reverse=True,
    )[:20]
    top_hotspots = [
        {
            "rank": index + 1,
            "display_name": row["display_name"],
            "district": row["시도시군구명"],
            "accidents": row["사고건수"],
            "casualties": row["사상자수"],
            "deaths": row["사망자수"],
            "serious_injuries": row["중상자수"],
            "risk_score": row["risk_score"],
            "risk_level": row["risk_level"],
            "center_lng": row["경도"],
            "center_lat": row["위도"],
        }
        for index, row in enumerate(sorted(rows, key=lambda item: item["risk_score"], reverse=True)[:20])
    ]
    return {
        "dataset": "pedestrian_hotspots_2019_2024",
        "source_file": str(DEFAULT_SOURCE),
        "encoding_in": "cp949",
        "encoding_out": "utf-8",
        "cluster_radius_m": cluster_radius_m,
        "record_count": len(rows),
        "cluster_count": len(clusters),
        "totals": {
            "accidents": sum(row["사고건수"] for row in rows),
            "casualties": sum(row["사상자수"] for row in rows),
            "deaths": sum(row["사망자수"] for row in rows),
            "serious_injuries": sum(row["중상자수"] for row in rows),
            "minor_injuries": sum(row["경상자수"] for row in rows),
            "reported_injuries": sum(row["부상신고자수"] for row in rows),
        },
        "risk_level_counts": dict(by_level),
        "source_year_counts": {str(key): by_year[key] for key in sorted(by_year)},
        "top_hotspots": top_hotspots,
        "top_districts_by_accidents": top_districts,
        "notes": [
            "risk_score = accidents + deaths*10 + serious_injuries*4 + minor_injuries + reported_injuries*0.5",
            "risk_level is quantile-based: top 20 percent high, next 40 percent medium, remaining low.",
            "cluster GeoJSON groups records within the configured radius to expose repeated nearby danger zones.",
        ],
    }


def strip_district_suffix(value: str) -> str:
    return value.rstrip("0123456789").strip()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main() -> None:
    args = parse_args()
    source = args.source
    output_dir = args.output_dir
    if not source.exists():
        raise FileNotFoundError(f"source CSV not found: {source}")

    output_dir.mkdir(parents=True, exist_ok=True)
    raw_copy = output_dir / "19_24_pedestrians_raw_cp949.csv"
    shutil.copy2(source, raw_copy)

    rows = read_rows(source)
    assign_risk_levels(rows)
    clusters = cluster_rows(rows, args.cluster_radius_m)

    write_normalized_csv(rows, output_dir / "pedestrian_hotspots.csv")
    write_json(
        output_dir / "pedestrian_hotspots.geojson",
        {"type": "FeatureCollection", "features": [build_feature(row) for row in rows]},
    )
    write_json(
        output_dir / "pedestrian_hotspot_clusters.geojson",
        {
            "type": "FeatureCollection",
            "features": [
                build_cluster_feature(cluster, index + 1)
                for index, cluster in enumerate(
                    sorted(clusters, key=lambda item: max(row["risk_score"] for row in item), reverse=True)
                )
            ],
        },
    )
    summary = build_summary(rows, clusters, args.cluster_radius_m)
    summary["source_file"] = str(source)
    summary["raw_copy"] = str(raw_copy)
    write_json(output_dir / "pedestrian_hotspots_summary.json", summary)

    print(f"records: {len(rows)}")
    print(f"clusters: {len(clusters)}")
    print(f"output: {output_dir}")


if __name__ == "__main__":
    main()
