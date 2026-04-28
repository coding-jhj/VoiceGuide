"""
yolo11m.pt → ONNX 변환 스크립트
실행: python tools/export_onnx.py  (프로젝트 루트에서)
결과: android/app/src/main/assets/yolo11m.onnx  (두 android 폴더 모두)
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

# android 폴더가 두 곳 — 둘 다 업데이트
dst_dirs = [
    Path("android/app/src/main/assets"),                    # c:/VoiceGuide/VoiceGuide/android (신버전)
    Path("../android/app/src/main/assets"),                  # c:/VoiceGuide/android (구버전, 혹시 몰라)
]

for dst_dir in dst_dirs:
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / "yolo11m.onnx"
    shutil.copy(src, dst)
    print(f"완료: {dst.resolve()}  ({dst.stat().st_size / 1024 / 1024:.1f} MB)")
