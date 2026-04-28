"""
휴대폰 → 노트북 오인식 수정 데이터셋 준비.

전략:
  - 휴대폰 이미지 다운로드 → YOLO가 laptop(63)으로 탐지한 걸 cell_phone(67)으로 교정
  - 노트북 이미지도 포함 → 두 클래스 구별 능력 유지
  - 기존 indoor_nav 데이터와 합쳐서 계단 지식도 보존

실행:
    cd VoiceGuide
    python train/prepare_cellphone.py
"""

import json, os, time, urllib.request, shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

DATASET_DIR = Path("datasets/cellphone_fix")
IMG_TRAIN   = DATASET_DIR / "images/train"
IMG_VAL     = DATASET_DIR / "images/val"
LBL_TRAIN   = DATASET_DIR / "labels/train"
LBL_VAL     = DATASET_DIR / "labels/val"

VAL_RATIO   = 0.15
CONF_THRESH = 0.30
CELL_PHONE_CLS  = 67   # COCO cell phone
LAPTOP_CLS      = 63   # COCO laptop
TEDDY_BEAR_CLS  = 77   # COCO teddy bear (폰과 혼동 빈번)

# (검색어, 실제_클래스, 목표_장수)
# 실제_클래스: 이 검색어 이미지의 주 피사체가 무엇인지 → bbox 강제 라벨에 사용
SEARCH_QUERIES = [
    # 휴대폰 — 노트북과 헷갈리는 각도/배치 위주
    ("smartphone lying flat on table",  CELL_PHONE_CLS, 70),
    ("cell phone on desk top view",     CELL_PHONE_CLS, 60),
    ("phone screen face up",            CELL_PHONE_CLS, 60),
    ("smartphone on wooden table",      CELL_PHONE_CLS, 60),
    ("mobile phone close up",           CELL_PHONE_CLS, 50),
    ("phone in hand screen visible",    CELL_PHONE_CLS, 50),
    ("cell phone tilted angle",         CELL_PHONE_CLS, 50),
    # 노트북 — 구별 학습용
    ("open laptop on desk",             LAPTOP_CLS,     60),
    ("notebook computer screen",        LAPTOP_CLS,     50),
    ("laptop computer keyboard visible",LAPTOP_CLS,     50),
]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def collect_urls() -> list[tuple[str, int]]:
    from ddgs import DDGS
    results: list[tuple[str, int]] = []
    with DDGS() as ddgs:
        for query, cls_id, count in SEARCH_QUERIES:
            print(f"  검색: '{query}' ({count}장 목표)")
            try:
                for img in ddgs.images(query, max_results=count):
                    url = img.get("image", "")
                    if url and url.startswith("http"):
                        results.append((url, cls_id))
                time.sleep(1.5)
            except Exception as e:
                print(f"    경고: {e}")
                time.sleep(3)
    print(f"  총 {len(results)}개 URL 수집")
    return results


def download_one(url: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 5000:
        return True
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=12) as r:
            data = r.read()
        if len(data) < 5000:
            return False
        dest.write_bytes(data)
        return True
    except Exception:
        return False


def download_all(url_cls: list[tuple[str, int]], img_dir: Path) -> list[tuple[Path, int]]:
    ok = []
    futs = {}
    with ThreadPoolExecutor(max_workers=16) as ex:
        for i, (url, cls_id) in enumerate(url_cls):
            ext = url.split("?")[0].split(".")[-1].lower()
            if ext not in ("jpg", "jpeg", "png", "webp"):
                ext = "jpg"
            dest = img_dir / f"img_{i:04d}.{ext}"
            futs[ex.submit(download_one, url, dest)] = (dest, cls_id)
        for fut in as_completed(futs):
            dest, cls_id = futs[fut]
            if fut.result():
                ok.append((dest, cls_id))
    print(f"  다운로드: {len(ok)}/{len(url_cls)}장 성공")
    return ok


def make_labels(img_paths_cls: list[tuple[Path, int]], lbl_dir: Path):
    """
    YOLO 자동 라벨 + 교정:
    - 휴대폰 이미지(target=67): laptop(63) 탐지 결과를 cell_phone(67)으로 교체
    - 노트북 이미지(target=63): 그대로 사용
    휴대폰 이미지에 YOLO가 폰을 아예 못 잡으면 이미지 중앙 60%에 강제 bbox 추가.
    """
    import cv2
    from ultralytics import YOLO

    src_model = "yolo11m_indoor.pt" if Path("yolo11m_indoor.pt").exists() else "yolo11m.pt"
    print(f"  라벨링 모델: {src_model}")
    model = YOLO(src_model)
    labeled = 0

    for img_path, target_cls in img_paths_cls:
        img = cv2.imread(str(img_path))
        if img is None:
            try:
                from PIL import Image as PILImage
                pil = PILImage.open(img_path).convert("RGB")
                jpg_path = img_path.with_suffix(".jpg")
                pil.save(jpg_path, "JPEG", quality=90)
                img = cv2.imread(str(jpg_path))
                img_path = jpg_path
            except Exception:
                continue
        if img is None:
            continue

        h, w = img.shape[:2]
        lines = []
        has_target = False

        try:
            results = model(img, conf=CONF_THRESH, verbose=False)[0]
            for box in results.boxes:
                cls = int(box.cls[0])
                x1, y1, x2, y2 = map(float, box.xyxy[0])
                cx = (x1 + x2) / 2 / w
                cy = (y1 + y2) / 2 / h
                bw = (x2 - x1) / w
                bh = (y2 - y1) / h

                if target_cls == CELL_PHONE_CLS:
                    # 휴대폰 이미지: laptop·teddy_bear → cell_phone 교정
                    if cls in (LAPTOP_CLS, TEDDY_BEAR_CLS):
                        cls = CELL_PHONE_CLS
                    if cls == CELL_PHONE_CLS:
                        has_target = True
                else:
                    # 노트북 이미지: 그대로 사용
                    if cls == LAPTOP_CLS:
                        has_target = True

                lines.append(f"{cls} {cx:.5f} {cy:.5f} {bw:.5f} {bh:.5f}")
        except Exception:
            pass

        # 휴대폰 이미지인데 폰 bbox가 없으면 중앙 강제 추가
        if target_cls == CELL_PHONE_CLS and not has_target:
            lines.append(f"{CELL_PHONE_CLS} 0.50000 0.50000 0.60000 0.80000")

        if not lines:
            continue

        lbl_file = lbl_dir / (img_path.stem + ".txt")
        lbl_file.write_text("\n".join(lines))
        labeled += 1

    print(f"  라벨 생성: {labeled}개")


def write_yaml():
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
        "stairs",
    ]
    yaml_str = (
        f"path: {DATASET_DIR.resolve().as_posix()}\n"
        f"train: images/train\n"
        f"val:   images/val\n\n"
        f"nc: {len(coco_names)}\n"
        f"names: {json.dumps(coco_names, ensure_ascii=False)}\n"
    )
    p = DATASET_DIR / "cellphone_fix.yaml"
    p.write_text(yaml_str, encoding="utf-8")
    print(f"YAML: {p}")
    return p


def merge_with_indoor_nav():
    """
    기존 indoor_nav 데이터(계단)의 심볼릭 링크 또는 복사본을 추가.
    계단 지식을 유지하기 위해 train 폴더에 병합.
    """
    src_img = Path("datasets/indoor_nav/images/train")
    src_lbl = Path("datasets/indoor_nav/labels/train")
    if not src_img.exists():
        print("  indoor_nav 데이터 없음 — 건너뜀 (계단 데이터는 yolo11m_indoor.pt에 이미 반영됨)")
        return

    copied = 0
    for f in src_img.glob("*"):
        dst = IMG_TRAIN / f"stairs_{f.name}"
        if not dst.exists():
            shutil.copy2(f, dst)
            copied += 1
    for f in src_lbl.glob("*"):
        dst = LBL_TRAIN / f"stairs_{f.name}"
        if not dst.exists():
            shutil.copy2(f, dst)

    print(f"  indoor_nav에서 {copied}장 병합 완료")


def main():
    print("=" * 60)
    print("VoiceGuide 휴대폰 오인식 수정 데이터셋 준비")
    print("=" * 60)

    for d in [IMG_TRAIN, IMG_VAL, LBL_TRAIN, LBL_VAL]:
        d.mkdir(parents=True, exist_ok=True)

    print("\n[1/5] 이미지 URL 수집...")
    url_cls = collect_urls()
    if not url_cls:
        print("URL 수집 실패.")
        write_yaml()
        return

    n_val = max(10, int(len(url_cls) * VAL_RATIO))
    val_urls   = url_cls[:n_val]
    train_urls = url_cls[n_val:]

    print(f"\n[2/5] 다운로드 (train={len(train_urls)}, val={n_val})...")
    train_imgs = download_all(train_urls, IMG_TRAIN)
    val_imgs   = download_all(val_urls,   IMG_VAL)

    if len(train_imgs) < 20:
        print("이미지 부족. 네트워크 확인 후 재시도.")
        write_yaml()
        return

    print(f"\n[3/5] 라벨 생성 (교정 포함)...")
    make_labels(train_imgs, LBL_TRAIN)
    make_labels(val_imgs,   LBL_VAL)

    print(f"\n[4/5] 기존 계단 데이터 병합...")
    merge_with_indoor_nav()

    print(f"\n[5/5] YAML 생성...")
    write_yaml()

    total = len(train_imgs) + len(val_imgs)
    print(f"\n완료! 총 {total}장 준비. 다음 단계:")
    print("  python train/finetune_cellphone.py")


if __name__ == "__main__":
    main()
