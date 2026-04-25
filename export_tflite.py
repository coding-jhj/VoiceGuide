"""
yolo11n.pt → TFLite 변환 스크립트
실행: python export_tflite.py
결과: yolo11n_saved_model/yolo11n_float32.tflite
"""
from ultralytics import YOLO
import shutil, os

model = YOLO("yolo11n.pt")
model.export(format="tflite", imgsz=640, half=False)

src = "yolo11n_saved_model/yolo11n_float32.tflite"
dst = "android/app/src/main/assets/yolo11n.tflite"

os.makedirs("android/app/src/main/assets", exist_ok=True)
shutil.copy(src, dst)
print(f"완료: {dst} 로 복사됨")
