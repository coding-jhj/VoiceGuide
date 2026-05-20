from __future__ import annotations

import argparse
import random
import shutil
from pathlib import Path

from voiceguide_labels import (
    DOOR_CLASS_ID,
    NEGATIVE_TAGS,
    STAIRS_CLASS_ID,
    assert_voiceguide82_contract,
    yolo_data_yaml,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "data" / "fine_tune" / "door_stairs"
DEFAULT_COCO_REPLAY = ROOT / "data" / "fine_tune" / "coco_replay"
DEFAULT_OUT = ROOT / "datasets" / "voiceguide82"

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a YOLO dataset that keeps COCO ids 0..79 and appends "
            "stairs=80, door=81. Manual labels are expected in YOLO txt format."
        )
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--coco-replay", type=Path, default=DEFAULT_COCO_REPLAY)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--val-ratio", type=float, default=0.18)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--copy", action="store_true", help="Copy files instead of hardlinking when possible.")
    return parser.parse_args()


def image_files(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return sorted(p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES)


def direct_image_files(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return sorted(p for p in path.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES)


def label_for(image: Path) -> Path:
    return image.with_suffix(".txt")


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


def write_label(dst: Path, src_label: Path | None, class_id: int | None) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src_label and src_label.exists():
        dst.write_text(src_label.read_text(encoding="utf-8"), encoding="utf-8")
        return
    if class_id is None:
        dst.write_text("", encoding="utf-8")
        return
    # Fallback bootstrap label only. Replace with hand-corrected boxes before final training.
    dst.write_text(f"{class_id} 0.50000 0.50000 0.82000 0.82000\n", encoding="utf-8")


def collect_split(source: Path, coco_replay: Path, val_ratio: float, seed: int) -> tuple[list[tuple[Path, int | None]], list[tuple[Path, int | None]]]:
    positives: list[tuple[Path, int | None]] = []
    for image in image_files(source / "stairs"):
        positives.append((image, STAIRS_CLASS_ID))
    for image in image_files(source / "door"):
        positives.append((image, DOOR_CLASS_ID))

    negatives: list[tuple[Path, int | None]] = []
    for tag in NEGATIVE_TAGS:
        negatives.extend((image, None) for image in image_files(source / "hard_negative" / tag))
    negatives.extend((image, None) for image in direct_image_files(source / "hard_negative"))

    replay = [(image, None) for image in image_files(coco_replay)]
    all_items = positives + negatives + replay
    rng = random.Random(seed)
    rng.shuffle(all_items)
    n_val = max(1, int(len(all_items) * val_ratio)) if all_items else 0
    return all_items[n_val:], all_items[:n_val]


def materialize(items: list[tuple[Path, int | None]], split: str, out: Path, copy: bool) -> dict[str, int]:
    counts = {"images": 0, "fallback_labels": 0, "empty_negative_labels": 0}
    for idx, (image, class_id) in enumerate(items):
        stem = f"{split}_{idx:05d}_{image.stem}"
        dst_image = out / "images" / split / f"{stem}{image.suffix.lower()}"
        dst_label = out / "labels" / split / f"{stem}.txt"
        link_or_copy(image, dst_image, copy)
        src_label = label_for(image)
        if not src_label.exists() and class_id is not None:
            counts["fallback_labels"] += 1
        if class_id is None and not src_label.exists():
            counts["empty_negative_labels"] += 1
        write_label(dst_label, src_label if src_label.exists() else None, class_id)
        counts["images"] += 1
    return counts


def write_readme(out: Path) -> None:
    text = """# VoiceGuide82 dataset layout

This dataset keeps COCO class ids 0..79 unchanged and appends:

- 80: stairs
- 81: door

Recommended source layout before running this script:

```text
data/fine_tune/door_stairs/
  stairs/*.jpg + optional matching *.txt
  door/*.jpg + optional matching *.txt
  hard_negative/
    hanging_clothes/*.jpg
    mannequin/*.jpg
    person_poster/*.jpg
    mirror_reflection/*.jpg
    clothes_on_chair/*.jpg
    empty_door_frame/*.jpg
    stair_railing_only/*.jpg

data/fine_tune/coco_replay/
  person/*.jpg + *.txt
  chair/*.jpg + *.txt
  cell_phone/*.jpg + *.txt
  ...
```

Hard negative images should have an empty `.txt` label file unless a real COCO object is present.
This is what teaches the model that hanging clothes, posters, and mannequins are not `person`.

Fallback labels are only a bootstrap aid. For final contest training, hand-correct door/stairs boxes.
"""
    (out / "README.md").write_text(text, encoding="utf-8")


def main() -> int:
    args = parse_args()
    assert_voiceguide82_contract()
    for rel in ["images/train", "images/val", "labels/train", "labels/val"]:
        reset_dir(args.out / rel)

    train_items, val_items = collect_split(args.source, args.coco_replay, args.val_ratio, args.seed)
    train_counts = materialize(train_items, "train", args.out, args.copy)
    val_counts = materialize(val_items, "val", args.out, args.copy)
    yaml_path = args.out / "voiceguide82.yaml"
    yaml_path.write_text(yolo_data_yaml(args.out.resolve().as_posix()), encoding="utf-8")
    write_readme(args.out)

    print(f"dataset: {args.out}")
    print(f"yaml: {yaml_path}")
    print(f"train: {train_counts}")
    print(f"val: {val_counts}")
    if train_counts["fallback_labels"] or val_counts["fallback_labels"]:
        print("warning: fallback full-image labels were created. Hand-correct them before final training.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
