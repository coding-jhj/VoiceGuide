"""Preprocess registered disabled population CSV files for VoiceGuide.

The source export is split into monthly CP949 CSV files. This script keeps the
Cloud Run payload small by writing dashboard-ready JSON artifacts rather than
shipping every raw CSV file.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DIR = Path(
    r"C:\Users\ghksw\Downloads\장애인등록 장애정도별 장애유형별 장애인수(202101~202604)"
)
DEFAULT_OUTPUT_DIR = ROOT / "datasets" / "disabled_population"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def read_rows(source_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    files = sorted(source_dir.glob("PDQCSV_22_*.csv"))
    if not files:
        raise FileNotFoundError(f"No source CSV files found in {source_dir}")

    rows: list[dict[str, Any]] = []
    manifest: list[dict[str, Any]] = []
    for path in files:
        with path.open("r", encoding="cp949", newline="") as f:
            file_rows = 0
            for row in csv.DictReader(f):
                normalized = {
                    "month": row["통계연월"].strip(),
                    "sido": row["통계시도명"].strip(),
                    "sigungu": row["통계시군구명"].strip(),
                    "disability_type": row["장애유형"].strip(),
                    "degree": row["장애정도"].strip(),
                    "count": int(row["등록장애인수"].replace(",", "").strip()),
                }
                rows.append(normalized)
                file_rows += 1
        manifest.append(
            {
                "file_name": path.name,
                "encoding": "cp949",
                "row_count": file_rows,
                "size_bytes": path.stat().st_size,
            }
        )
    return rows, manifest


def build_artifacts(rows: list[dict[str, Any]], manifest: list[dict[str, Any]]) -> dict[str, Any]:
    months = sorted({row["month"] for row in rows})
    latest_month = months[-1]
    first_month = months[0]
    latest_rows = [row for row in rows if row["month"] == latest_month]
    first_rows = [row for row in rows if row["month"] == first_month]

    type_totals = counter_by(latest_rows, "disability_type")
    visual_latest = [row for row in latest_rows if row["disability_type"] == "시각"]
    visual_first = [row for row in first_rows if row["disability_type"] == "시각"]
    visual_total = sum(row["count"] for row in visual_latest)
    total_disabled = sum(row["count"] for row in latest_rows)

    visual_by_degree = counter_by(visual_latest, "degree")
    visual_by_sido = counter_by(visual_latest, "sido")
    visual_by_sigungu = counter_by_region(visual_latest)

    summary = {
        "dataset": "disabled_population_202101_202604",
        "source_dir": str(DEFAULT_SOURCE_DIR),
        "source_file_count": len(manifest),
        "source_encoding": "cp949",
        "output_encoding": "utf-8",
        "row_count": len(rows),
        "month": {
            "first": first_month,
            "latest": latest_month,
            "count": len(months),
        },
        "latest": {
            "month": latest_month,
            "total_disabled": total_disabled,
            "visual_disabled": visual_total,
            "visual_share_pct": round(visual_total / total_disabled * 100, 2),
            "visual_change_from_first": visual_total
            - sum(row["count"] for row in visual_first),
            "visual_by_degree": dict(visual_by_degree),
            "top_visual_sido": ranked_items(visual_by_sido, 10),
            "top_disability_types": ranked_items(type_totals, 10),
        },
        "dashboard_copy": {
            "title": "시각장애 등록 현황",
            "subtitle": f"{latest_month[:4]}년 {int(latest_month[4:])}월 기준",
            "main_stat": f"{visual_total:,}명",
            "supporting_stat": f"전체 등록장애인의 {round(visual_total / total_disabled * 100, 2)}%",
            "caution": "등록장애인 통계이며 실제 앱 사용자 수가 아닙니다.",
        },
        "notes": [
            "Use this dataset as demand and presentation context, not as real-time personal risk data.",
            "Counts are aggregated by administrative region and disability type/degree.",
            "Do not combine this data with personal user disability information.",
        ],
    }

    trend = []
    for month in months:
        month_rows = [row for row in rows if row["month"] == month]
        month_visual = [row for row in month_rows if row["disability_type"] == "시각"]
        trend.append(
            {
                "month": month,
                "total_disabled": sum(row["count"] for row in month_rows),
                "visual_disabled": sum(row["count"] for row in month_visual),
                "visual_severe": sum(
                    row["count"] for row in month_visual if row["degree"] == "심한 장애"
                ),
                "visual_mild": sum(
                    row["count"] for row in month_visual if row["degree"] == "심하지 않은 장애"
                ),
            }
        )

    regions = []
    for (sido, sigungu), count in visual_by_sigungu.items():
        regions.append(
            {
                "month": latest_month,
                "sido": sido,
                "sigungu": sigungu,
                "visual_disabled": count,
                "visual_sido_total": visual_by_sido[sido],
                "visual_region_share_pct": round(count / visual_total * 100, 4),
            }
        )
    regions.sort(key=lambda item: item["visual_disabled"], reverse=True)

    by_type = [
        {"disability_type": key, "count": value, "share_pct": round(value / total_disabled * 100, 2)}
        for key, value in type_totals.most_common()
    ]

    return {
        "summary": summary,
        "trend": trend,
        "regions": regions,
        "by_type": by_type,
        "manifest": {
            "source_dir": str(DEFAULT_SOURCE_DIR),
            "files": manifest,
        },
    }


def counter_by(rows: list[dict[str, Any]], key: str) -> Counter[str]:
    counter: Counter[str] = Counter()
    for row in rows:
        counter[row[key]] += row["count"]
    return counter


def counter_by_region(rows: list[dict[str, Any]]) -> Counter[tuple[str, str]]:
    counter: Counter[tuple[str, str]] = Counter()
    for row in rows:
        counter[(row["sido"], row["sigungu"])] += row["count"]
    return counter


def ranked_items(counter: Counter[str], limit: int) -> list[dict[str, Any]]:
    return [{"name": key, "count": value} for key, value in counter.most_common(limit)]


def write_json(path: Path, payload: Any) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def write_normalized_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "month",
        "sido",
        "sigungu",
        "disability_type",
        "degree",
        "count",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    rows, manifest = read_rows(args.source_dir)
    artifacts = build_artifacts(rows, manifest)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_normalized_csv(args.output_dir / "disabled_population.csv", rows)
    write_json(args.output_dir / "disabled_population_summary.json", artifacts["summary"])
    write_json(args.output_dir / "disabled_population_visual_trend.json", artifacts["trend"])
    write_json(args.output_dir / "disabled_population_visual_regions.json", artifacts["regions"])
    write_json(args.output_dir / "disabled_population_by_type_latest.json", artifacts["by_type"])
    write_json(args.output_dir / "source_manifest.json", artifacts["manifest"])

    print(f"files: {len(manifest)}")
    print(f"rows: {len(rows)}")
    print(f"output: {args.output_dir}")


if __name__ == "__main__":
    main()
