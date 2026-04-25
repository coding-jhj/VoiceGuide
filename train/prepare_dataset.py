"""
DuckDuckGo 이미지 검색으로 계단·실내 장애물 이미지를 다운로드하고
YOLO pseudo-label을 자동 생성하여 학습 데이터를 만든다.

실행:
    cd VoiceGuide
    python train/prepare_dataset.py
"""

import json, os, time, urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

DATASET_DIR = Path("datasets/indoor_nav")
IMG_TRAIN   = DATASET_DIR / "images/train"
IMG_VAL     = DATASET_DIR / "images/val"
LBL_TRAIN   = DATASET_DIR / "labels/train"
LBL_VAL     = DATASET_DIR / "labels/val"

VAL_RATIO    = 0.15
CONF_THRESH  = 0.35   # pseudo-label 신뢰도 (낮게 설정해 더 많이 잡음)
STAIRS_CLS   = 80

# 검색어 목록: 다양한 환경의 계단 이미지
SEARCH_QUERIES = [
    ("indoor staircase",          STAIRS_CLS, 80),
    ("staircase indoors",         STAIRS_CLS, 60),
    ("hallway stairs",            STAIRS_CLS, 60),
    ("office building stairs",    STAIRS_CLS, 60),
    ("concrete stairs indoor",    STAIRS_CLS, 60),
    ("wooden stairs inside",      STAIRS_CLS, 60),
    ("hospital corridor stairs",  STAIRS_CLS, 50),
    ("school building staircase", STAIRS_CLS, 50),
]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def collect_urls() -> list[tuple[str, int]]:
    """ddgs로 이미지 URL 수집. (url, cls_id) 반환."""
    from ddgs import DDGS
    results: list[tuple[str, int]] = []

    with DDGS() as ddgs:
        for query, cls_id, count in SEARCH_QUERIES:
            print(f"  검색: '{query}' ({count}장)")
            try:
                for img in ddgs.images(query, max_results=count):
                    url = img.get("image", "")
                    if url and url.startswith("http"):
                        results.append((url, cls_id))
                time.sleep(1.5)   # rate limit 방지
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
        if len(data) < 5000:   # 너무 작은 파일 제외 (에러 페이지 등)
            return False
        dest.write_bytes(data)
        return True
    except Exception:
        return False


def download_all(url_cls: list[tuple[str, int]],
                 img_dir: Path) -> list[tuple[Path, int]]:
    """병렬 다운로드. (이미지 경로, cls_id) 반환."""
    ok = []
    futs = {}
    with ThreadPoolExecutor(max_workers=16) as ex:
        for i, (url, cls_id) in enumerate(url_cls):
            ext = url.split("?")[0].split(".")[-1].lower()
            if ext not in ("jpg","jpeg","png","webp"):
                ext = "jpg"
            dest = img_dir / f"img_{i:04d}.{ext}"
            futs[ex.submit(download_one, url, dest)] = (dest, cls_id)

        for fut in as_completed(futs):
            dest, cls_id = futs[fut]
            if fut.result():
                ok.append((dest, cls_id))

    print(f"  다운로드: {len(ok)}/{len(url_cls)}장 성공")
    return ok


def pseudo_label(img_paths_cls: list[tuple[Path, int]], lbl_dir: Path):
    """
    YOLO11m으로 기존 클래스 라벨 유지 + 계단 bbox 추가.
    계단 이미지이므로 이미지 하단 70%를 stairs bbox로 설정.
    """
    import cv2
    from ultralytics import YOLO

    model = YOLO("yolo11m.pt")
    labeled = 0

    for img_path, stairs_cls in img_paths_cls:
        img = cv2.imread(str(img_path))
        if img is None:
            # PNG → JPG 변환 시도
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

        # ① 기존 YOLO 클래스 자동 라벨
        try:
            results = model(img, conf=CONF_THRESH, verbose=False)[0]
            for box in results.boxes:
                cls = int(box.cls[0])
                x1, y1, x2, y2 = map(float, box.xyxy[0])
                cx = (x1 + x2) / 2 / w
                cy = (y1 + y2) / 2 / h
                bw = (x2 - x1) / w
                bh = (y2 - y1) / h
                lines.append(f"{cls} {cx:.5f} {cy:.5f} {bw:.5f} {bh:.5f}")
        except Exception:
            pass

        # ② 계단 bbox: 이미지 하단 중앙 영역 (계단이 주로 여기 있음)
        lines.append(f"{stairs_cls} 0.50000 0.70000 0.90000 0.60000")

        lbl_file = lbl_dir / (img_path.stem + ".txt")
        lbl_file.write_text("\n".join(lines))
        labeled += 1

    print(f"  라벨 생성: {labeled}개")


def write_yaml(nc: int = 81):
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
    yaml = (
        f"path: {DATASET_DIR.resolve().as_posix()}\n"
        f"train: images/train\n"
        f"val:   images/val\n\n"
        f"nc: {len(coco_names)}\n"
        f"names: {json.dumps(coco_names, ensure_ascii=False)}\n"
    )
    p = DATASET_DIR / "indoor_nav.yaml"
    p.write_text(yaml, encoding="utf-8")
    print(f"YAML: {p}")
    return p


def main():
    print("=" * 60)
    print("VoiceGuide 파인튜닝 데이터셋 준비 (DuckDuckGo)")
    print("=" * 60)

    for d in [IMG_TRAIN, IMG_VAL, LBL_TRAIN, LBL_VAL]:
        d.mkdir(parents=True, exist_ok=True)

    # 1. URL 수집
    print("\n[1/4] 이미지 URL 수집...")
    url_cls = collect_urls()
    if not url_cls:
        print("URL 수집 실패. 네트워크를 확인하세요.")
        write_yaml()
        return

    # 2. train/val 분리
    n_val = max(10, int(len(url_cls) * VAL_RATIO))
    val_urls   = url_cls[:n_val]
    train_urls = url_cls[n_val:]

    # 3. 다운로드
    print(f"\n[2/4] 이미지 다운로드 (train={len(train_urls)}, val={n_val})...")
    train_imgs = download_all(train_urls, IMG_TRAIN)
    val_imgs   = download_all(val_urls,   IMG_VAL)

    if len(train_imgs) < 10:
        print("이미지가 너무 적습니다. 다시 시도하세요.")
        write_yaml()
        return

    # 4. Pseudo-label
    print(f"\n[3/4] YOLO 자동 라벨링...")
    pseudo_label(train_imgs, LBL_TRAIN)
    pseudo_label(val_imgs,   LBL_VAL)

    # 5. YAML
    print(f"\n[4/4] YAML 생성...")
    write_yaml()

    total = len(train_imgs) + len(val_imgs)
    print(f"\n완료! 총 {total}장 준비. 학습 시작:")
    print("  python train/finetune.py")


if __name__ == "__main__":
    main()
