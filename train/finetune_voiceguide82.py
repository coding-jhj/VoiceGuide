from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path

from voiceguide_labels import assert_voiceguide82_contract

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"


def arg_value(args: argparse.Namespace, name: str, default: object) -> object:
    return getattr(args, name, default)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fine-tune YOLO while keeping COCO80 + stairs=80 + door=81.")
    parser.add_argument("--data", default="datasets/voiceguide82/voiceguide82.yaml")
    parser.add_argument("--pretrained", default="yolo11n.pt")
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--warmup-epochs", type=int, default=8)
    parser.add_argument("--patience", type=int, default=12)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=12)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--device", default="0")
    parser.add_argument("--optimizer", default="AdamW")
    parser.add_argument("--warmup-freeze", type=int, default=10)
    parser.add_argument("--warmup-lr0", type=float, default=1e-3)
    parser.add_argument("--freeze", type=int, default=0)
    parser.add_argument("--lr0", type=float, default=7e-5)
    parser.add_argument("--lrf", type=float, default=0.01)
    parser.add_argument("--weight-decay", type=float, default=0.0005)
    parser.add_argument("--close-mosaic", type=int, default=10)
    parser.add_argument("--mosaic", type=float, default=1.0)
    parser.add_argument("--mixup", type=float, default=0.0)
    parser.add_argument("--cls", type=float, default=0.5)
    parser.add_argument("--label-smoothing", type=float, default=0.05)
    parser.add_argument("--cos-lr", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--project", default="runs/train")
    parser.add_argument("--name", default="voiceguide82_yolo11n")
    parser.add_argument("--export-copy", default="models/voiceguide82_yolo11n.pt")
    return parser.parse_args()


def warmup_train_kwargs(args: argparse.Namespace, warmup_name: str) -> dict[str, object]:
    return {
        "data": args.data,
        "epochs": args.warmup_epochs,
        "patience": max(3, min(args.patience, args.warmup_epochs)),
        "imgsz": args.imgsz,
        "batch": args.batch,
        "workers": args.workers,
        "device": args.device,
        "freeze": arg_value(args, "warmup_freeze", 10),
        "optimizer": args.optimizer,
        "lr0": arg_value(args, "warmup_lr0", 1e-3),
        "weight_decay": arg_value(args, "weight_decay", 0.0005),
        "plots": True,
        "project": args.project,
        "name": warmup_name,
        "exist_ok": True,
    }


def finetune_train_kwargs(args: argparse.Namespace) -> dict[str, object]:
    return {
        "data": args.data,
        "epochs": args.epochs,
        "patience": args.patience,
        "imgsz": args.imgsz,
        "batch": args.batch,
        "workers": args.workers,
        "device": args.device,
        "freeze": arg_value(args, "freeze", 0),
        "optimizer": args.optimizer,
        "lr0": arg_value(args, "lr0", 7e-5),
        "lrf": arg_value(args, "lrf", 0.01),
        "cos_lr": arg_value(args, "cos_lr", True),
        "label_smoothing": arg_value(args, "label_smoothing", 0.05),
        "weight_decay": arg_value(args, "weight_decay", 0.0005),
        "close_mosaic": arg_value(args, "close_mosaic", 10),
        "mosaic": arg_value(args, "mosaic", 1.0),
        "mixup": arg_value(args, "mixup", 0.0),
        "cls": arg_value(args, "cls", 0.5),
        "augment": True,
        "plots": True,
        "project": args.project,
        "name": args.name,
        "exist_ok": True,
    }


def best_weight_from_results(results: object, args: argparse.Namespace) -> Path:
    save_dir = getattr(results, "save_dir", None)
    candidates = []
    if save_dir:
        candidates.append(Path(save_dir) / "weights" / "best.pt")
    candidates.extend(
        [
            Path(args.project) / args.name / "weights" / "best.pt",
            Path("runs/detect") / args.project / args.name / "weights" / "best.pt",
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


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
    if args.warmup_epochs > 0:
        model = YOLO(args.pretrained)
        model.train(**warmup_train_kwargs(args, warmup_name))
        warmup_best = Path(args.project) / warmup_name / "weights" / "best.pt"
        start = str(warmup_best) if warmup_best.exists() else args.pretrained
    else:
        start = args.pretrained

    model = YOLO(start)
    results = model.train(**finetune_train_kwargs(args))

    best = best_weight_from_results(results, args)
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
