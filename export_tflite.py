"""
yolo11n.pt → ONNX 변환 스크립트
실행: python export_tflite.py
결과: android/app/src/main/assets/yolo11n.onnx
"""
from ultralytics import YOLO
import shutil, os

model = YOLO("yolo11n.pt")
model.export(format="onnx", imgsz=640, half=False)

src = "yolo11n.onnx"
dst = "android/app/src/main/assets/yolo11n.onnx"

os.makedirs("android/app/src/main/assets", exist_ok=True)
shutil.copy(src, dst)
print(f"완료: {dst} 로 복사됨")
