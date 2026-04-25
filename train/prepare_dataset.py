"""
실내 보행 특화 데이터셋 준비 스크립트.

Open Images V7에서 계단(Stairs)·문(Door)·기둥(Column) 클래스를 다운로드하고
YOLO 형식으로 변환한 뒤, 기존 COCO indoor 이미지와 합쳐 학습 데이터를 만든다.

실행:
    pip install fiftyone
    cd VoiceGuide
    python train/prepare_dataset.py
"""

import os
import sys
import shutil
import json
from pathlib import Path

DATASET_DIR = Path("datasets/indoor_nav")
IMAGES_TRAIN = DATASET_DIR / "images" / "train"
IMAGES_VAL   = DATASET_DIR / "images" / "val"
LABELS_TRAIN = DATASET_DIR / "labels" / "train"
LABELS_VAL   = DATASET_DIR / "labels" / "val"

# ── 추가 탐지 클래스 (COCO 80 + 신규) ────────────────────────────────────
# YOLO fine-tuning 시 전체 클래스 목록 (index = label id)
# COCO 80 클래스는 그대로 유지하고, 신규 클래스를 뒤에 추가
NEW_CLASSES = {
    80: "stairs",
    81: "door",
    82: "pole",
    83: "threshold",
}

# Open Images에서 다운로드할 클래스 (영문 라벨 그대로)
OI_CLASSES = ["Stairs", "Door", "Pole"]
MAX_SAMPLES_PER_CLASS = 800


def setup_dirs():
    for d in [IMAGES_TRAIN, IMAGES_VAL, LABELS_TRAIN, LABELS_VAL]:
        d.mkdir(parents=True, exist_ok=True)
    print("폴더 생성 완료:", DATASET_DIR)


def download_open_images():
    """fiftyone으로 Open Images V7 다운로드."""
    try:
        import fiftyone.zoo as foz
        import fiftyone as fo
    except ImportError:
        print("fiftyone 없음. 설치 중...")
        os.system(f"{sys.executable} -m pip install fiftyone -q")
        import fiftyone.zoo as foz
        import fiftyone as fo

    all_samples = []
    for cls in OI_CLASSES:
        print(f"  다운로드: {cls} ({MAX_SAMPLES_PER_CLASS}장)")
        try:
            ds = foz.load_zoo_dataset(
                "open-images-v7",
                split="train",
                label_types=["detections"],
                classes=[cls],
                max_samples=MAX_SAMPLES_PER_CLASS,
                dataset_name=f"oi_{cls.lower()}",
            )
            all_samples.extend(list(ds))
        except Exception as e:
            print(f"  경고: {cls} 다운로드 실패 — {e}")

    return all_samples


def convert_to_yolo(samples, split="train"):
    """Open Images 포맷 → YOLO txt 포맷 변환."""
    img_dir = IMAGES_TRAIN if split == "train" else IMAGES_VAL
    lbl_dir = LABELS_TRAIN if split == "train" else LABELS_VAL

    oi_to_new = {"Stairs": 80, "Door": 81, "Pole": 82}
    converted = 0

    for sample in samples:
        if not hasattr(sample, "detections") or sample.detections is None:
            continue

        # 이미지 복사
        src = sample.filepath
        dst = img_dir / Path(src).name
        shutil.copy2(src, dst)

        # 라벨 변환
        label_lines = []
        img_w = sample.metadata.width  if sample.metadata else 1
        img_h = sample.metadata.height if sample.metadata else 1

        for det in sample.detections.detections:
            label_str = det.label
            cls_id = oi_to_new.get(label_str)
            if cls_id is None:
                continue
            bx, by, bw, bh = det.bounding_box  # [0,1] normalized, xywh
            cx = bx + bw / 2
            cy = by + bh / 2
            label_lines.append(f"{cls_id} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")

        if label_lines:
            lbl_file = lbl_dir / (Path(src).stem + ".txt")
            lbl_file.write_text("\n".join(label_lines))
            converted += 1

    print(f"  변환 완료: {converted}개 ({split})")
    return converted


def write_yaml():
    """YOLO 학습 설정 YAML 생성."""
    # COCO 80 클래스명
    coco_names = [
        "person","bicycle","car","motorcycle","airplane","bus","train","truck",
        "boat","traffic light","fire hydrant","stop sign","parking meter","bench",
        "bird","cat","dog","horse","sheep","cow","elephant","bear","zebra","giraffe",
        "backpack","umbrella","handbag","tie","suitcase","frisbee","skis","snowboard",
        "sports ball","kite","baseball bat","baseball glove","skateboard","surfboard",
        "tennis racket","bottle","wine glass","cup","fork","knife","spoon","bowl",
        "banana","apple","sandwich","orange","broccoli","carrot","hot dog","pizza",
        "donut","cake","chair","couch","potted plant","bed","dining table","toilet",
        "tv","laptop","mouse","remote","keyboard","cell phone","microwave","oven",
        "toaster","sink","refrigerator","book","clock","vase","scissors","teddy bear",
        "hair drier","toothbrush",
        "stairs","door","pole","threshold",  # 신규 클래스
    ]
    yaml_content = f"""# VoiceGuide 실내 보행 특화 데이터셋
path: {DATASET_DIR.resolve()}
train: images/train
val:   images/val

nc: {len(coco_names)}
names: {json.dumps(coco_names, ensure_ascii=False)}
"""
    yaml_path = DATASET_DIR / "indoor_nav.yaml"
    yaml_path.write_text(yaml_content, encoding="utf-8")
    print("YAML 저장:", yaml_path)
    return yaml_path


def main():
    print("=" * 60)
    print("VoiceGuide 파인튜닝 데이터셋 준비")
    print("=" * 60)

    setup_dirs()

    print("\n[1/3] Open Images V7 다운로드...")
    samples = download_open_images()

    if not samples:
        print("  데이터를 가져오지 못했습니다. 수동으로 이미지를 datasets/indoor_nav/에 배치하세요.")
    else:
        split = int(len(samples) * 0.85)
        print(f"\n[2/3] YOLO 포맷 변환... (train={split}, val={len(samples)-split})")
        convert_to_yolo(samples[:split], "train")
        convert_to_yolo(samples[split:], "val")

    print("\n[3/3] 학습 설정 YAML 생성...")
    yaml_path = write_yaml()

    print("\n완료! 이제 파인튜닝을 실행하세요:")
    print(f"  python train/finetune.py")


if __name__ == "__main__":
    main()
