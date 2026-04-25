"""
Wikipedia Commons에서 계단(Stairs) 이미지를 다운로드하고
현재 YOLO 모델로 자동 라벨링(pseudo-label)하여 학습 데이터 생성.

전체 흐름:
  1. Wikipedia Commons "Stairs" 카테고리에서 이미지 URL 수집
  2. 이미지 다운로드
  3. 현재 YOLO11m으로 사람/의자 등 기존 클래스 라벨 + 계단 bbox 자동 생성
  4. YOLO 학습 형식(txt)으로 저장

실행:
    cd VoiceGuide
    python train/prepare_dataset.py
"""

import json, os, urllib.request, urllib.parse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

DATASET_DIR = Path("datasets/indoor_nav")
IMG_TRAIN   = DATASET_DIR / "images/train"
IMG_VAL     = DATASET_DIR / "images/val"
LBL_TRAIN   = DATASET_DIR / "labels/train"
LBL_VAL     = DATASET_DIR / "labels/val"

MAX_IMAGES   = 400
VAL_RATIO    = 0.15
STAIRS_CLS   = 80   # 새로 추가할 YOLO 클래스 ID
CONF_THRESH  = 0.40  # pseudo-label 신뢰도

WIKI_API = "https://commons.wikimedia.org/w/api.php"
HEADERS  = {"User-Agent": "VoiceGuide-Research/1.0 (educational project)"}


# ── Wikipedia Commons 이미지 URL 수집 ────────────────────────────────────

def fetch_wiki_images(category: str, limit: int) -> list[str]:
    """Wikipedia Commons 카테고리에서 이미지 URL 목록 반환."""
    urls, cont = [], None

    while len(urls) < limit:
        params: dict = {
            "action": "query",
            "generator": "categorymembers",
            "gcmtitle": f"Category:{category}",
            "gcmtype": "file",
            "gcmlimit": "50",
            "prop": "imageinfo",
            "iiprop": "url|size|mime",
            "format": "json",
        }
        if cont:
            params.update(cont)

        req = urllib.request.Request(
            WIKI_API + "?" + urllib.parse.urlencode(params), headers=HEADERS)
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())

        pages = data.get("query", {}).get("pages", {})
        for p in pages.values():
            info = p.get("imageinfo", [{}])[0]
            url  = info.get("url", "")
            mime = info.get("mime", "")
            w    = info.get("width", 0)
            h    = info.get("height", 0)

            # JPEG만, 최소 400×300 이상
            if "jpeg" in mime and w >= 400 and h >= 300:
                urls.append(url)
                if len(urls) >= limit:
                    break

        cont = data.get("continue")
        if not cont:
            break

    return urls[:limit]


def download_image(url: str, dest: Path) -> bool:
    if dest.exists():
        return True
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=20) as r:
            dest.write_bytes(r.read())
        return True
    except Exception:
        return False


# ── Pseudo-label 생성 ─────────────────────────────────────────────────────

def generate_labels(img_paths: list[Path], lbl_dir: Path):
    """YOLO11m으로 기존 클래스 자동 라벨링 + 계단 bbox 근사."""
    import cv2, numpy as np
    from ultralytics import YOLO

    model = YOLO("yolo11m.pt")

    for img_path in img_paths:
        img = cv2.imread(str(img_path))
        if img is None:
            continue
        h, w = img.shape[:2]

        results = model(img, conf=CONF_THRESH, verbose=False)[0]
        lines = []

        # ① 기존 COCO 클래스 라벨 유지 (전이 학습 효과 보존)
        for box in results.boxes:
            cls = int(box.cls[0])
            x1, y1, x2, y2 = map(float, box.xyxy[0])
            cx = (x1 + x2) / 2 / w
            cy = (y1 + y2) / 2 / h
            bw = (x2 - x1) / w
            bh = (y2 - y1) / h
            lines.append(f"{cls} {cx:.5f} {cy:.5f} {bw:.5f} {bh:.5f}")

        # ② 계단 pseudo-label: 이미지 하단 60%를 계단 bbox로 근사
        #    (Wikipedia 계단 이미지 특성상 계단이 화면 대부분 차지)
        stair_cx, stair_cy = 0.5, 0.7
        stair_bw, stair_bh = 0.8, 0.6
        lines.append(
            f"{STAIRS_CLS} {stair_cx:.5f} {stair_cy:.5f}"
            f" {stair_bw:.5f} {stair_bh:.5f}"
        )

        lbl_file = lbl_dir / (img_path.stem + ".txt")
        lbl_file.write_text("\n".join(lines))


# ── YAML 생성 ─────────────────────────────────────────────────────────────

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
        "stairs",   # id 80 — 신규 추가
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
    print(f"YAML 저장: {p}")
    return p


# ── 메인 ──────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("VoiceGuide 파인튜닝 데이터셋 준비 (Wikipedia Commons)")
    print("=" * 60)

    for d in [IMG_TRAIN, IMG_VAL, LBL_TRAIN, LBL_VAL]:
        d.mkdir(parents=True, exist_ok=True)

    # 1. 이미지 URL 수집
    print(f"\n[1/4] Wikipedia Commons 'Staircases' 이미지 URL 수집 ({MAX_IMAGES}장)...")
    try:
        urls = fetch_wiki_images("Staircases", MAX_IMAGES)
        print(f"  수집: {len(urls)}개 URL")
    except Exception as e:
        print(f"  실패: {e}")
        write_yaml()
        return

    if not urls:
        print("  URL 없음. 네트워크를 확인하세요.")
        write_yaml()
        return

    # 2. train/val 분리
    n_val = max(1, int(len(urls) * VAL_RATIO))
    splits = [
        ("val",   urls[:n_val],  IMG_VAL),
        ("train", urls[n_val:],  IMG_TRAIN),
    ]

    # 3. 이미지 다운로드
    print(f"\n[2/4] 이미지 다운로드...")
    downloaded: dict[str, list[Path]] = {"train": [], "val": []}
    for split_name, split_urls, img_dir in splits:
        ok_paths = []
        with ThreadPoolExecutor(max_workers=12) as ex:
            fname = lambda u: img_dir / (urllib.parse.urlparse(u).path.split("/")[-1])
            futs = {ex.submit(download_image, u, fname(u)): fname(u)
                    for u in split_urls}
            for fut in as_completed(futs):
                if fut.result():
                    ok_paths.append(futs[fut])
        downloaded[split_name] = ok_paths
        print(f"  {split_name}: {len(ok_paths)}/{len(split_urls)}장")

    # 4. Pseudo-label 생성
    print(f"\n[3/4] YOLO 자동 라벨링...")
    generate_labels(downloaded["train"], LBL_TRAIN)
    generate_labels(downloaded["val"],   LBL_VAL)
    print(f"  라벨 생성 완료")

    # 5. YAML
    print(f"\n[4/4] YAML 생성...")
    write_yaml()

    total = len(downloaded["train"]) + len(downloaded["val"])
    print(f"\n완료! 총 {total}장 준비됨")
    print("파인튜닝 실행:")
    print("  python train/finetune.py")


if __name__ == "__main__":
    main()
