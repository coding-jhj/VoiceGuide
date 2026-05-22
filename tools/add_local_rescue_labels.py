from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "data" / "test_images"
TARGET_ROOT = ROOT / "data" / "fine_tune" / "door_stairs"

DOOR_CLASS_ID = 81
STAIRS_CLASS_ID = 80

# Hand-estimated rescue labels for the local demo-style images that previously
# triggered door/stairs confusion. These are not a replacement for a full
# contest validation set; they are a focused correction set.
LABELS: dict[str, dict[str, list[tuple[float, float, float, float]]]] = {
    "door": {
        "door_000.jpg": [(0.540, 0.520, 0.140, 0.180)],
        "door_001.jpg": [(0.225, 0.520, 0.220, 0.660), (0.770, 0.415, 0.120, 0.300)],
        "door_002.jpg": [(0.545, 0.455, 0.180, 0.360)],
        "door_003.jpg": [(0.305, 0.500, 0.260, 0.780)],
        "door_004.jpg": [(0.535, 0.480, 0.120, 0.350)],
        "door_005.jpg": [(0.255, 0.520, 0.260, 0.720)],
        "door_006.jpg": [(0.135, 0.510, 0.130, 0.650)],
    },
    "stairs": {
        "stairs_000.jpg": [(0.705, 0.435, 0.570, 0.390), (0.545, 0.745, 0.300, 0.280)],
        "stairs_001.jpg": [(0.545, 0.370, 0.760, 0.440)],
        "stairs_002.jpg": [(0.500, 0.560, 0.820, 0.820)],
        "stairs_003.jpg": [(0.470, 0.560, 0.560, 0.720)],
        "stairs_004.jpg": [(0.430, 0.530, 0.720, 0.740)],
        "stairs_005.jpg": [(0.455, 0.515, 0.690, 0.700)],
        "stairs_006.jpg": [(0.500, 0.550, 0.760, 0.860)],
        "stairs_007.jpg": [(0.600, 0.560, 0.560, 0.720)],
        "stairs_008.jpg": [(0.555, 0.580, 0.720, 0.670)],
        "stairs_009.jpg": [(0.455, 0.560, 0.760, 0.760)],
    },
}


def write_yolo_label(path: Path, class_id: int, boxes: list[tuple[float, float, float, float]]) -> None:
    lines = [f"{class_id} {x:.6f} {y:.6f} {w:.6f} {h:.6f}" for x, y, w, h in boxes]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    copied = 0
    for class_name, image_labels in LABELS.items():
        class_id = DOOR_CLASS_ID if class_name == "door" else STAIRS_CLASS_ID
        target_dir = TARGET_ROOT / class_name
        target_dir.mkdir(parents=True, exist_ok=True)
        for image_name, boxes in image_labels.items():
            src = SOURCE_ROOT / class_name / image_name
            if not src.exists():
                raise FileNotFoundError(src)
            dst = target_dir / image_name
            shutil.copy2(src, dst)
            write_yolo_label(dst.with_suffix(".txt"), class_id, boxes)
            copied += 1
    print(f"local rescue images copied: {copied}")
    print(f"target: {TARGET_ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
