from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path

from voiceguide_labels import assert_voiceguide82_contract

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fine-tune YOLO while keeping COCO80 + stairs=80 + door=81.")
    parser.add_argument("--data", default="datasets/voiceguide82/voiceguide82.yaml")
    parser.add_argument("--pretrained", default="yolo11n.pt")
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--warmup-epochs", type=int, default=8)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=12)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--device", default="0")
    parser.add_argument("--project", default="runs/train")
    parser.add_argument("--name", default="voiceguide82_yolo11n")
    parser.add_argument("--export-copy", default="models/voiceguide82_yolo11n.pt")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    assert_voiceguide82_contract()
    if not Path(args.data).exists():
        print(f"missing dataset yaml: {args.data}")
        print("run: python train/prepare_door_stairs_dataset.py")
        return 1

    from ultralytics import YOLO

    print("=" * 72)
    print("VoiceGuide82 fine-tune")
    print("class contract: COCO 0..79 unchanged, stairs=80, door=81")
    print(f"data: {args.data}")
    print(f"pretrained: {args.pretrained}")
    print("=" * 72)

    warmup_name = f"{args.name}_warmup"
    model = YOLO(args.pretrained)
    model.train(
        data=args.data,
        epochs=args.warmup_epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        workers=args.workers,
        device=args.device,
        freeze=10,
        lr0=1e-3,
        project=args.project,
        name=warmup_name,
        exist_ok=True,
    )

    warmup_best = Path(args.project) / warmup_name / "weights" / "best.pt"
    start = str(warmup_best) if warmup_best.exists() else args.pretrained
    model = YOLO(start)
    results = model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        workers=args.workers,
        device=args.device,
        freeze=0,
        lr0=7e-5,
        lrf=0.01,
        cos_lr=True,
        label_smoothing=0.05,
        close_mosaic=10,
        augment=True,
        project=args.project,
        name=args.name,
        exist_ok=True,
    )

    best = Path(args.project) / args.name / "weights" / "best.pt"
    if not best.exists():
        print("training finished but best.pt was not found")
        return 1

    dst = Path(args.export_copy)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(best, dst)
    print(f"best copied to: {dst}")
    for key in ["metrics/mAP50(B)", "metrics/mAP50-95(B)"]:
        value = results.results_dict.get(key)
        if isinstance(value, float):
            print(f"{key}: {value:.4f}")
    print("next: export to TFLite, then run tools/evaluate_yolo_extended.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
