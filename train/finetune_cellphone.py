"""
휴대폰 → 노트북 오인식 수정 파인튜닝.

yolo11m_indoor.pt (계단 파인튜닝 완료본)에서 이어서 학습.
학습률을 낮게 유지해 계단/다른 클래스 성능이 무너지지 않도록 함.

실행 순서:
    python train/prepare_cellphone.py   # 데이터 준비
    python train/finetune_cellphone.py  # 파인튜닝

완료 후:
    yolo11m_indoor.pt 덮어쓰기 (계단 + 폰 수정 모두 포함)
    tools/export_onnx.py 로 ONNX 변환 후 Android 앱에 반영
"""

import os, shutil
from pathlib import Path

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

from ultralytics import YOLO

YAML         = "datasets/cellphone_fix/cellphone_fix.yaml"
EPOCHS       = 25          # 기존 지식 유지를 위해 짧게
IMGSZ        = 640
BATCH        = 12          # OOM 나면 8로 줄일 것
WORKERS      = 4
PROJECT      = "runs/train"
NAME         = "cellphone_fix_v1"
DEVICE       = 0


def main():
    if not Path(YAML).exists():
        print(f"오류: {YAML} 없음. 먼저 실행하세요:")
        print("  python train/prepare_cellphone.py")
        return

    # 시작점: 계단 파인튜닝된 모델 우선, 없으면 기본 모델
    start = "yolo11m_indoor.pt" if Path("yolo11m_indoor.pt").exists() else "yolo11m.pt"
    print("=" * 60)
    print("VoiceGuide 휴대폰 오인식 수정 파인튜닝")
    print(f"  시작 모델:  {start}")
    print(f"  데이터:     {YAML}")
    print(f"  에포크:     {EPOCHS}  배치: {BATCH}")
    print("=" * 60)

    model = YOLO(start)

    results = model.train(
        data=YAML,
        epochs=EPOCHS,
        imgsz=IMGSZ,
        batch=BATCH,
        device=DEVICE,
        workers=WORKERS,
        # 기존 지식 유지: 낮은 학습률 + 코사인 스케줄
        lr0=5e-5,
        lrf=0.01,
        cos_lr=True,
        label_smoothing=0.05,
        augment=True,
        # 백본 동결 없이 전체 학습 — 폰/노트북 구별은 헤드 레벨 문제
        freeze=0,
        project=PROJECT,
        name=NAME,
        exist_ok=True,
    )

    best_pt = Path(PROJECT) / NAME / "weights" / "best.pt"
    if not best_pt.exists():
        print("경고: 학습 결과를 찾을 수 없습니다.")
        return

    # 기존 indoor 모델 백업 후 덮어쓰기
    indoor = Path("yolo11m_indoor.pt")
    if indoor.exists():
        shutil.copy2(indoor, "yolo11m_indoor_before_cellphone.pt")
        print("백업: yolo11m_indoor_before_cellphone.pt")

    shutil.copy2(best_pt, indoor)
    print(f"\n완료! {indoor} 업데이트됨 (계단 + 휴대폰 오인식 수정 포함)")

    map50 = results.results_dict.get("metrics/mAP50(B)", "N/A")
    if isinstance(map50, float):
        print(f"mAP50: {map50:.3f}")

    print("\n다음 단계 — ONNX 변환 + Android 반영:")
    print("  python tools/export_onnx.py")


if __name__ == "__main__":
    main()
