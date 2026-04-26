"""
yolo11m.pt → ONNX 변환 스크립트
실행: python tools/export_onnx.py  (프로젝트 루트에서)
결과: android/app/src/main/assets/yolo11m.onnx
"""
import os
import shutil
from pathlib import Path

_src = "yolo11m_indoor.pt" if os.path.exists("yolo11m_indoor.pt") else "yolo11m.pt"
print(f"내보낼 모델: {_src}")

from ultralytics import YOLO
model = YOLO(_src)
model.export(format="onnx", imgsz=640, half=False, simplify=True)

src = Path("yolo11m.onnx")
dst_dir = Path("android/app/src/main/assets")
dst = dst_dir / "yolo11m.onnx"

dst_dir.mkdir(parents=True, exist_ok=True)
shutil.copy(src, dst)
print(f"완료: {dst}")
print(f"파일 크기: {dst.stat().st_size / 1024 / 1024:.1f} MB")
