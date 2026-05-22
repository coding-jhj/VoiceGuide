from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import cv2


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PREDICTIONS = ROOT / "outputs" / "voiceguide82_eval_rescue_local_conf035" / "predictions.csv"
DEFAULT_IMAGES = ROOT / "data" / "test_images"
DEFAULT_OUT = ROOT / "data" / "fine_tune" / "door_stairs" / "hard_negative" / "stair_like_floor"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mine stair-like false positives as empty-label hard negatives.")
    parser.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument("--images", type=Path, default=DEFAULT_IMAGES)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--class-name", default="stairs")
    parser.add_argument("--exclude-folder", action="append", default=["stairs"])
    parser.add_argument("--padding", type=float, default=0.18)
    parser.add_argument("--min-width", type=int, default=24)
    parser.add_argument("--min-height", type=int, default=12)
    return parser.parse_args()


def padded_crop_bounds(
    xyxy: list[float],
    image_width: int,
    image_height: int,
    padding: float,
) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = xyxy
    width = x2 - x1
    height = y2 - y1
    px = width * padding
    py = height * padding
    left = max(0, int(x1 - px))
    top = max(0, int(y1 - py))
    right = min(image_width, int(x2 + px))
    bottom = min(image_height, int(y2 + py))
    return left, top, right, bottom


def main() -> int:
    args = parse_args()
    excluded = set(args.exclude_folder)
    args.out.mkdir(parents=True, exist_ok=True)
    mined = 0

    with args.predictions.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("class") != args.class_name:
                continue
            if row.get("folder") in excluded:
                continue
            rel = row["image"]
            src = args.images / rel
            mat = cv2.imread(str(src))
            if mat is None:
                continue
            image_height, image_width = mat.shape[:2]
            xyxy = [float(v) for v in json.loads(row["xyxy"])]
            left, top, right, bottom = padded_crop_bounds(xyxy, image_width, image_height, args.padding)
            if right - left < args.min_width or bottom - top < args.min_height:
                continue
            crop = mat[top:bottom, left:right]
            stem = f"stair_fp_{mined:04d}_{Path(rel).stem}"
            image_out = args.out / f"{stem}.jpg"
            label_out = args.out / f"{stem}.txt"
            cv2.imwrite(str(image_out), crop)
            label_out.write_text("", encoding="utf-8")
            mined += 1

    print(f"mined hard negatives: {mined}")
    print(f"target: {args.out}")
    return 0 if mined else 1


if __name__ == "__main__":
    raise SystemExit(main())
