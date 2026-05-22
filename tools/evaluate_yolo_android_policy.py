from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import cv2


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate YOLO predictions after VoiceGuide Android filters.")
    parser.add_argument("--model", default="models/voiceguide82_yolo11n_rescue_local.pt")
    parser.add_argument("--images", default="data/test_images")
    parser.add_argument("--out", default="outputs/voiceguide82_eval_android_policy")
    parser.add_argument("--model-conf", type=float, default=0.05)
    return parser.parse_args()


def iter_images(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES)


def confidence_threshold_for(class_id: int) -> float:
    if class_id == 0:
        return 0.32
    if class_id in {24, 26, 28, 56, 57, 58, 60, 63, 67}:
        return 0.34
    if class_id == 80:
        return 0.50
    if class_id == 81:
        return 0.35
    return 0.30


def passes_geometry(class_id: int, xyxy: list[float], image_width: int, image_height: int) -> bool:
    x1, y1, x2, y2 = xyxy
    width = max(0.0, (x2 - x1) / image_width)
    height = max(0.0, (y2 - y1) / image_height)
    area = width * height
    if class_id == 80:
        return area >= 0.001 and width >= 0.04 and height >= 0.006
    if class_id == 81:
        return area >= 0.035 and height >= width * 1.05
    return True


def main() -> int:
    args = parse_args()
    from ultralytics import YOLO

    image_root = Path(args.images)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    images = iter_images(image_root)
    if not images:
        print(f"no images under {image_root}")
        return 1

    model = YOLO(args.model)
    rows = []
    class_counts: Counter[str] = Counter()
    folder_counts: dict[str, Counter[str]] = defaultdict(Counter)

    for image in images:
        mat = cv2.imread(str(image))
        if mat is None:
            continue
        image_height, image_width = mat.shape[:2]
        result = model(mat, conf=args.model_conf, verbose=False)[0]
        rel = image.relative_to(image_root).as_posix()
        folder = image.parent.name
        kept = 0
        for box in result.boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            xyxy = [float(v) for v in box.xyxy[0]]
            if conf < confidence_threshold_for(cls_id):
                continue
            if not passes_geometry(cls_id, xyxy, image_width, image_height):
                continue
            name = str(model.names.get(cls_id, cls_id))
            class_counts[name] += 1
            folder_counts[folder][name] += 1
            kept += 1
            rows.append({
                "image": rel,
                "folder": folder,
                "class_id": cls_id,
                "class": name,
                "conf": f"{conf:.4f}",
                "xyxy": json.dumps([round(v, 2) for v in xyxy]),
            })
        if kept == 0:
            rows.append({"image": rel, "folder": folder, "class_id": "", "class": "", "conf": "", "xyxy": ""})

    csv_path = out_dir / "predictions.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["image", "folder", "class_id", "class", "conf", "xyxy"])
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "model": args.model,
        "images": len(images),
        "policy": {
            "person_conf": 0.32,
            "common_indoor_conf": 0.34,
            "stairs_conf": 0.50,
            "door_conf": 0.35,
            "stairs_geometry": "area>=0.001 and width>=0.04 and height>=0.006",
            "door_geometry": "area>=0.035 and height>=width*1.05",
        },
        "classes": dict(class_counts),
        "by_folder": {folder: dict(counts) for folder, counts in sorted(folder_counts.items())},
    }
    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"csv: {csv_path}")
    print(f"summary: {summary_path}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
