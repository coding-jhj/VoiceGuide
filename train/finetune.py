"""
YOLO11m 실내 보행 특화 파인튜닝.

RTX 5060 8GB 기준 약 1~2시간 소요 (50 에포크).

실행:
    cd VoiceGuide
    python train/finetune.py

학습 완료 후:
    runs/train/indoor_nav_v1/weights/best.pt  ← 이게 새 모델
    → src/vision/detect.py의 model = YOLO("...pt") 경로를 변경하면 적용됨
"""

import os
import shutil
from pathlib import Path

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"  # Windows OpenMP 충돌 방지

from ultralytics import YOLO


PRETRAINED   = "yolo11m.pt"          # COCO 사전학습 가중치 (전이 학습 시작점)
YAML         = "datasets/indoor_nav/indoor_nav.yaml"
EPOCHS       = 50
IMGSZ        = 640
BATCH        = 12                    # RTX 5060 8GB 기준 (OOM 나면 8로 줄일 것)
WORKERS      = 4
PROJECT      = "runs/train"
NAME         = "indoor_nav_v1"
DEVICE       = 0                     # GPU 0번


def main():
    print("=" * 60)
    print("VoiceGuide YOLO11m 파인튜닝 시작")
    print(f"  모델:   {PRETRAINED}")
    print(f"  데이터: {YAML}")
    print(f"  에포크: {EPOCHS}  |  배치: {BATCH}  |  해상도: {IMGSZ}")
    print("=" * 60)

    if not Path(YAML).exists():
        print(f"\n오류: {YAML} 없음. 먼저 실행하세요:")
        print("  python train/prepare_dataset.py")
        return

    model = YOLO(PRETRAINED)

    # ── 1단계: 백본 동결, 헤드만 학습 (빠른 수렴) ─────────────────────
    print("\n[1/2] 백본 동결 — 새 클래스 헤드 학습 (10 에포크)...")
    model.train(
        data=YAML, epochs=10, imgsz=IMGSZ, batch=BATCH,
        device=DEVICE, workers=WORKERS,
        freeze=10,           # 첫 10개 레이어 동결 (백본 보존)
        lr0=1e-3,
        project=PROJECT, name=NAME + "_warmup",
        exist_ok=True, verbose=False,
    )

    # ── 2단계: 전체 레이어 파인튜닝 ──────────────────────────────────
    print(f"\n[2/2] 전체 파인튜닝 ({EPOCHS} 에포크)...")
    warmup_best = Path(PROJECT) / (NAME + "_warmup") / "weights" / "best.pt"
    start_from  = str(warmup_best) if warmup_best.exists() else PRETRAINED

    model = YOLO(start_from)
    results = model.train(
        data=YAML, epochs=EPOCHS, imgsz=IMGSZ, batch=BATCH,
        device=DEVICE, workers=WORKERS,
        lr0=1e-4,            # 2단계는 작은 lr로 세밀 조정
        cos_lr=True,         # 코사인 학습률 스케줄
        label_smoothing=0.1, # 과적합 방지
        augment=True,        # 데이터 증강
        project=PROJECT, name=NAME,
        exist_ok=True,
    )

    best_pt = Path(PROJECT) / NAME / "weights" / "best.pt"
    if best_pt.exists():
        # 학습된 모델을 프로젝트 루트로 복사
        dest = Path("yolo11m_indoor.pt")
        shutil.copy2(best_pt, dest)
        print(f"\n완료! 새 모델 저장됨: {dest}")
        print("\n적용 방법:")
        print('  src/vision/detect.py 에서')
        print('  model = YOLO("yolo11m.pt")  →  model = YOLO("yolo11m_indoor.pt")')
        print(f"\n결과 요약:")
        print(f"  mAP50:   {results.results_dict.get('metrics/mAP50(B)', 'N/A'):.3f}")
        print(f"  mAP50-95: {results.results_dict.get('metrics/mAP50-95(B)', 'N/A'):.3f}")
    else:
        print("경고: 학습 결과 파일을 찾을 수 없습니다.")


if __name__ == "__main__":
    main()
