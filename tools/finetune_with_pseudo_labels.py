"""
Fine-tune YOLO11n for stairs(80) + door(81) WITHOUT catastrophic forgetting.

Root cause: previous training used only stairs/door images with no COCO annotations,
so the model treated all COCO objects as background and forgot how to detect them.

Fix: pseudo-label approach
  1. Run original yolo11n.pt (COCO-pretrained, 80 classes) on the merged dataset images.
  2. Save high-confidence COCO detections (cls 0-79) as pseudo-labels alongside
     the existing stairs/door human labels.
  3. Re-train on the combined labels so the model learns stairs/door while
     being penalized for forgetting COCO classes.
  4. Export to TFLite for Android.

Usage:
  python tools/finetune_with_pseudo_labels.py
  python tools/finetune_with_pseudo_labels.py --skip-pseudo  # re-train only, labels already exist
"""

import argparse
import shutil
from pathlib import Path

import torch
from ultralytics import YOLO

ROOT        = Path(__file__).parent.parent
MERGED_DIR  = ROOT / "datasets" / "roboflow_merged"
OUTPUT_DIR  = ROOT / "datasets" / "roboflow_merged_fixed"
MERGED_YAML = ROOT / "datasets" / "roboflow_merged" / "merged.yaml"

PSEUDO_CONF = 0.40   # min confidence to accept a COCO pseudo-label
SPLITS      = ["train", "val"]


def build_pseudo_labels(coco_model: YOLO, split: str):
    """Run coco_model on all images in <split> and write COCO pseudo-labels."""
    img_dir   = MERGED_DIR / "images" / split
    src_lbl   = MERGED_DIR / "labels" / split
    dst_lbl   = OUTPUT_DIR / "labels" / split
    dst_img   = OUTPUT_DIR / "images" / split
    dst_lbl.mkdir(parents=True, exist_ok=True)
    dst_img.mkdir(parents=True, exist_ok=True)

    image_paths = list(img_dir.glob("*.jpg")) + list(img_dir.glob("*.png"))
    print(f"[pseudo] {split}: {len(image_paths)} images")

    for img_path in image_paths:
        # Copy image
        shutil.copy2(img_path, dst_img / img_path.name)

        # Read existing human labels (stairs=80, door=81)
        lbl_name = img_path.stem + ".txt"
        human_lines: list[str] = []
        src_lbl_file = src_lbl / lbl_name
        if src_lbl_file.exists():
            human_lines = src_lbl_file.read_text().splitlines()

        # Run COCO model — returns 80-class detections
        results = coco_model.predict(str(img_path), conf=PSEUDO_CONF,
                                     verbose=False, imgsz=320)[0]

        pseudo_lines: list[str] = []
        if results.boxes is not None and len(results.boxes):
            boxes = results.boxes
            for cls_id, conf, xywhn in zip(
                boxes.cls.tolist(),
                boxes.conf.tolist(),
                boxes.xywhn.tolist(),
            ):
                cls_id = int(cls_id)   # 0-79 COCO class
                cx, cy, w, h = xywhn
                pseudo_lines.append(f"{cls_id} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")

        all_lines = human_lines + pseudo_lines
        (dst_lbl / lbl_name).write_text("\n".join(all_lines))

    print(f"[pseudo] {split}: pseudo-labels written to {dst_lbl}")


def build_fixed_yaml():
    dst = OUTPUT_DIR / "merged_fixed.yaml"
    dst.write_text(f"""\
path: {OUTPUT_DIR.as_posix()}
train: images/train
val:   images/val

nc: 82
names: ["person", "bicycle", "car", "motorcycle", "airplane", "bus", "train",
        "truck", "boat", "traffic light", "fire hydrant", "stop sign",
        "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep",
        "cow", "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella",
        "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard",
        "sports ball", "kite", "baseball bat", "baseball glove", "skateboard",
        "surfboard", "tennis racket", "bottle", "wine glass", "cup", "fork",
        "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
        "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair",
        "couch", "potted plant", "bed", "dining table", "toilet", "tv",
        "laptop", "mouse", "remote", "keyboard", "cell phone", "microwave",
        "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase",
        "scissors", "teddy bear", "hair drier", "toothbrush", "stairs", "door"]
""")
    return dst


def train(yaml_path: Path):
    # Start from the COCO-pretrained base model, not the corrupted fine-tuned one.
    # freeze=10 freezes the backbone (layers 0-9), so only the detection neck/head
    # is updated — COCO feature extraction is preserved, reducing forgetting further.
    model = YOLO("yolo11n.pt")
    model.train(
        data=str(yaml_path),
        epochs=50,
        imgsz=320,
        batch=32,
        device="0" if torch.cuda.is_available() else "cpu",
        project="runs/train",
        name="roboflow_fixed",
        exist_ok=True,
        pretrained=True,
        freeze=10,         # freeze backbone — prevent COCO forgetting
        lr0=0.0002,        # lower LR since backbone is frozen
        lrf=0.01,
        cos_lr=True,
        close_mosaic=10,
        amp=True,
        patience=20,
        cls=1.0,           # higher cls weight to balance stairs/door vs COCO
        optimizer="AdamW",
        augment=True,
        seed=0,
        verbose=True,
    )
    return ROOT / "runs" / "train" / "roboflow_fixed" / "weights" / "best.pt"


def export_tflite(pt_path: Path):
    model = YOLO(str(pt_path))
    model.export(
        format="tflite",
        imgsz=320,
        int8=False,
        half=False,
        simplify=True,
        nms=False,
    )
    tflite_dir = pt_path.parent / "best_saved_model"
    candidates = list(tflite_dir.glob("*.tflite"))
    if candidates:
        dst = ROOT / "android" / "app" / "src" / "main" / "assets" / "yolo11n_320.tflite"
        shutil.copy2(candidates[0], dst)
        print(f"[export] copied {candidates[0].name} → {dst}")
    else:
        print(f"[export] TFLite file not found in {tflite_dir}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-pseudo", action="store_true",
                        help="Skip pseudo-label generation (labels already exist)")
    parser.add_argument("--skip-train", action="store_true",
                        help="Skip training (only generate pseudo-labels)")
    parser.add_argument("--skip-export", action="store_true",
                        help="Skip TFLite export after training")
    args = parser.parse_args()

    yaml_path = OUTPUT_DIR / "merged_fixed.yaml"

    if not args.skip_pseudo:
        print("[step 1] Generating COCO pseudo-labels using yolo11n.pt ...")
        coco_model = YOLO("yolo11n.pt")   # original COCO weights (downloaded automatically)
        for split in SPLITS:
            build_pseudo_labels(coco_model, split)
        yaml_path = build_fixed_yaml()
        print(f"[step 1] Done. Fixed YAML: {yaml_path}")
    else:
        print("[step 1] Skipped pseudo-label generation.")
        yaml_path = build_fixed_yaml()

    if not args.skip_train:
        print("[step 2] Training with frozen backbone + combined labels ...")
        best_pt = train(yaml_path)
        print(f"[step 2] Training done. Best weights: {best_pt}")

        if not args.skip_export:
            print("[step 3] Exporting to TFLite ...")
            export_tflite(best_pt)
            print("[step 3] Export done. App assets updated.")
    else:
        print("[step 2] Skipped training.")


if __name__ == "__main__":
    main()
