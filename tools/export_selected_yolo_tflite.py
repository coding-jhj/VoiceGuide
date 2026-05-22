"""Export the selected VoiceGuide YOLO model to Android TFLite assets.

This project intentionally keeps the mobile model small. The default export is
YOLO11n at 320px input size, matching android/app/src/main/assets/yolo11n_320.tflite.

Usage:
    python tools/export_selected_yolo_tflite.py
    python tools/export_selected_yolo_tflite.py --source yolo11n.pt --imgsz 320
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "android" / "app" / "src" / "main" / "assets"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export selected YOLO model for VoiceGuide Android")
    parser.add_argument("--source", default="yolo11n.pt", help="Ultralytics .pt model path or model name")
    parser.add_argument("--imgsz", type=int, default=320, help="TFLite input image size")
    parser.add_argument("--opset", type=int, default=18, help="ONNX opset used by the TFLite export path")
    parser.add_argument(
        "--output-name",
        default="yolo11n_320.tflite",
        help="Android asset filename used by TfliteYoloDetector.kt",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    from ultralytics import YOLO

    model = YOLO(args.source)
    exported = Path(model.export(format="tflite", imgsz=args.imgsz, half=False, int8=False, nms=False, opset=args.opset))

    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    target = ASSET_DIR / args.output_name
    shutil.copy2(exported, target)
    print(f"exported {args.source} imgsz={args.imgsz} -> {target}")


if __name__ == "__main__":
    main()
