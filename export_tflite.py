"""
yolo11m.pt → ONNX 변환 스크립트
실행: python export_tflite.py
결과: android/app/src/main/assets/yolo11m.onnx
"""
from ultralytics import YOLO
import shutil, os

model = YOLO("yolo11m.pt")
model.export(format="onnx", imgsz=640, half=False, simplify=True)

src = "yolo11m.onnx"
dst_dir = "../android/app/src/main/assets"
dst = f"{dst_dir}/yolo11m.onnx"

os.makedirs(dst_dir, exist_ok=True)
shutil.copy(src, dst)
print(f"완료: {dst}")
print(f"파일 크기: {os.path.getsize(dst) / 1024 / 1024:.1f} MB")
