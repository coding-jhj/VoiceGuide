from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
DEFAULT_EXCLUDE_FOLDERS = {"stairs", "door"}


@dataclass(frozen=True)
class PseudoLabel:
    class_id: int
    x_center: float
    y_center: float
    width: float
    height: float
    confidence: float

    def yolo_line(self) -> str:
        return (
            f"{self.class_id} "
            f"{self.x_center:.6f} {self.y_center:.6f} "
            f"{self.width:.6f} {self.height:.6f}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a small COCO replay set from local regression images by "
            "using a pretrained YOLO model as a teacher. Only class ids 0..79 "
            "are written so stairs=80 and door=81 remain reserved for the "
            "fine-tuned Roboflow datasets."
        )
    )
    parser.add_argument("--source", type=Path, default=ROOT / "data" / "test_images")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "fine_tune" / "coco_replay_pseudo")
    parser.add_argument("--teacher", default="yolo11n.pt")
    parser.add_argument("--conf", type=float, default=0.35)
    parser.add_argument("--max-det", type=int, default=12)
    parser.add_argument("--exclude-folders", default="stairs,door")
    parser.add_argument("--copy", action="store_true", help="Copy images instead of hardlinking.")
    return parser.parse_args()


def iter_images(source: Path, excluded_folders: set[str]) -> list[Path]:
    if not source.exists():
        return []
    images: list[Path] = []
    for image in sorted(p for p in source.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES):
        try:
            top_level = image.relative_to(source).parts[0]
        except ValueError:
            top_level = image.parent.name
        if top_level not in excluded_folders:
            images.append(image)
    return images


def reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def link_or_copy(src: Path, dst: Path, copy: bool) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if copy:
        shutil.copy2(src, dst)
        return
    try:
        dst.hardlink_to(src)
    except OSError:
        shutil.copy2(src, dst)


def labels_from_result(result, image_width: int, image_height: int) -> list[PseudoLabel]:
    labels: list[PseudoLabel] = []
    for box in result.boxes:
        class_id = int(box.cls[0])
        if class_id < 0 or class_id > 79:
            continue
        x1, y1, x2, y2 = [float(v) for v in box.xyxy[0]]
        width = max(0.0, (x2 - x1) / image_width)
        height = max(0.0, (y2 - y1) / image_height)
        if width <= 0.0 or height <= 0.0:
            continue
        labels.append(
            PseudoLabel(
                class_id=class_id,
                x_center=((x1 + x2) / 2.0) / image_width,
                y_center=((y1 + y2) / 2.0) / image_height,
                width=width,
                height=height,
                confidence=float(box.conf[0]),
            )
        )
    return labels


def materialize_pseudo_replay(
    source: Path,
    out: Path,
    teacher: str,
    conf: float,
    max_det: int,
    excluded_folders: set[str],
    copy: bool,
) -> dict[str, object]:
    from ultralytics import YOLO

    images = iter_images(source, excluded_folders)
    reset_dir(out)
    model = YOLO(teacher)
    summary = {
        "source": str(source),
        "teacher": teacher,
        "confidence": conf,
        "images": 0,
        "labeled_images": 0,
        "empty_images": 0,
        "boxes": 0,
        "by_class_id": {},
    }
    by_class_id: dict[int, int] = {}

    for image in images:
        rel = image.relative_to(source)
        dst_image = out / rel
        dst_label = dst_image.with_suffix(".txt")
        link_or_copy(image, dst_image, copy)
        result = model(str(image), conf=conf, max_det=max_det, verbose=False)[0]
        height, width = result.orig_shape
        labels = labels_from_result(result, width, height)
        dst_label.write_text("".join(f"{label.yolo_line()}\n" for label in labels), encoding="utf-8")
        summary["images"] += 1
        if labels:
            summary["labeled_images"] += 1
        else:
            summary["empty_images"] += 1
        summary["boxes"] += len(labels)
        for label in labels:
            by_class_id[label.class_id] = by_class_id.get(label.class_id, 0) + 1

    summary["by_class_id"] = {str(key): value for key, value in sorted(by_class_id.items())}
    (out / "pseudo_replay_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary


def main() -> int:
    args = parse_args()
    excluded_folders = {name.strip() for name in args.exclude_folders.split(",") if name.strip()}
    summary = materialize_pseudo_replay(
        source=args.source,
        out=args.out,
        teacher=args.teacher,
        conf=args.conf,
        max_det=args.max_det,
        excluded_folders=excluded_folders,
        copy=args.copy,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
