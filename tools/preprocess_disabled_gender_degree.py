"""Preprocess disabled population by gender and degree CSV files for VoiceGuide."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DIR = Path(
    r"C:\Users\ghksw\Downloads\장애인등록 장애정도별 성별 장애인수(202601~202604)"
)
DEFAULT_OUTPUT_DIR = ROOT / "datasets" / "disabled_gender_degree"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def read_rows(source_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    files = sorted(source_dir.glob("PDQCSV_23_*.csv"))
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
                    "degree": row["장애정도"].strip(),
                    "gender": row["성별"].strip(),
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


def counter_by(rows: list[dict[str, Any]], key: str) -> Counter[str]:
    counter: Counter[str] = Counter()
    for row in rows:
        counter[row[key]] += row["count"]
    return counter


def build_region_rows(rows: list[dict[str, Any]], total_disabled: int) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["sido"], row["sigungu"])].append(row)

    regions = []
    for (sido, sigungu), group in grouped.items():
        by_gender = counter_by(group, "gender")
        by_degree = counter_by(group, "degree")
        total = sum(row["count"] for row in group)
        regions.append(
            {
                "month": group[0]["month"],
                "sido": sido,
                "sigungu": sigungu,
                "total_disabled": total,
                "male": by_gender.get("남자", 0),
                "female": by_gender.get("여자", 0),
                "severe": by_degree.get("심한 장애", 0),
                "mild": by_degree.get("심하지 않은 장애", 0),
                "male_share_pct": round(by_gender.get("남자", 0) / total * 100, 2) if total else 0,
                "female_share_pct": round(by_gender.get("여자", 0) / total * 100, 2) if total else 0,
                "severe_share_pct": round(by_degree.get("심한 장애", 0) / total * 100, 2) if total else 0,
                "mild_share_pct": round(by_degree.get("심하지 않은 장애", 0) / total * 100, 2) if total else 0,
                "national_share_pct": round(total / total_disabled * 100, 4) if total_disabled else 0,
            }
        )
    regions.sort(key=lambda item: item["total_disabled"], reverse=True)
    return regions


def ranked_regions(regions: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    return [
        {
            "sido": row["sido"],
            "sigungu": row["sigungu"],
            "total_disabled": row["total_disabled"],
        }
        for row in regions[:limit]
    ]


def build_artifacts(rows: list[dict[str, Any]], manifest: list[dict[str, Any]]) -> dict[str, Any]:
    months = sorted({row["month"] for row in rows})
    latest_month = months[-1]
    latest_rows = [row for row in rows if row["month"] == latest_month]
    total_disabled = sum(row["count"] for row in latest_rows)
    by_gender = counter_by(latest_rows, "gender")
    by_degree = counter_by(latest_rows, "degree")
    regions = build_region_rows(latest_rows, total_disabled)

    summary = {
        "dataset": "disabled_gender_degree_202601_202604",
        "source_dir": str(DEFAULT_SOURCE_DIR),
        "source_file_count": len(manifest),
        "source_encoding": "cp949",
        "output_encoding": "utf-8",
        "row_count": len(rows),
        "month": {
            "first": months[0],
            "latest": latest_month,
            "count": len(months),
        },
        "latest": {
            "month": latest_month,
            "total_disabled": total_disabled,
            "by_gender": dict(by_gender),
            "by_degree": dict(by_degree),
            "male_share_pct": round(by_gender.get("남자", 0) / total_disabled * 100, 2),
            "female_share_pct": round(by_gender.get("여자", 0) / total_disabled * 100, 2),
            "severe_share_pct": round(by_degree.get("심한 장애", 0) / total_disabled * 100, 2),
            "mild_share_pct": round(by_degree.get("심하지 않은 장애", 0) / total_disabled * 100, 2),
            "top_regions": ranked_regions(regions, 10),
        },
        "dashboard_copy": {
            "title": "현재 도시 등록장애인 현황",
            "subtitle": f"{latest_month[:4]}.{latest_month[4:]} 기준",
            "main_stat": f"{total_disabled:,}명",
            "supporting_stat": "성별·장애정도별 전체 등록장애인 공공 통계",
            "caution": "전체 등록장애인 통계이며 시각장애 전용 또는 개인 정보가 아닙니다.",
        },
        "notes": [
            "Use as regional welfare context, not as personal user inference.",
            "This dataset is all registered disabled people by gender and degree.",
            "Keep visual disability counts from disabled_population as the primary VoiceGuide target context.",
        ],
    }

    trend = []
    for month in months:
        month_rows = [row for row in rows if row["month"] == month]
        total = sum(row["count"] for row in month_rows)
        gender = counter_by(month_rows, "gender")
        degree = counter_by(month_rows, "degree")
        trend.append(
            {
                "month": month,
                "total_disabled": total,
                "male": gender.get("남자", 0),
                "female": gender.get("여자", 0),
                "severe": degree.get("심한 장애", 0),
                "mild": degree.get("심하지 않은 장애", 0),
            }
        )

    return {
        "summary": summary,
        "regions": regions,
        "trend": trend,
        "manifest": {
            "source_dir": str(DEFAULT_SOURCE_DIR),
            "files": manifest,
        },
    }


def write_json(path: Path, payload: Any) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def write_normalized_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = ["month", "sido", "sigungu", "degree", "gender", "count"]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    rows, manifest = read_rows(args.source_dir)
    artifacts = build_artifacts(rows, manifest)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_normalized_csv(args.output_dir / "disabled_gender_degree.csv", rows)
    write_json(args.output_dir / "disabled_gender_degree_summary.json", artifacts["summary"])
    write_json(args.output_dir / "disabled_gender_degree_regions.json", artifacts["regions"])
    write_json(args.output_dir / "disabled_gender_degree_trend.json", artifacts["trend"])
    write_json(args.output_dir / "source_manifest.json", artifacts["manifest"])

    print(f"files: {len(manifest)}")
    print(f"rows: {len(rows)}")
    print(f"output: {args.output_dir}")


if __name__ == "__main__":
    main()
