"""
ByteTrack(track) vs 단순 Detect(detect) 바운딩 박스 안정성 비교.

두 방식 모두 동일한 best.pt 모델을 사용하고,
val 이미지 폴더의 연속 이미지를 시퀀스처럼 처리해 박스 떨림을 수치화한다.

실행:
    cd VoiceGuide
    python tools/compare_tracking.py

결과:
    runs/compare_tracking/detect/  ← 단순 detect 결과 이미지
    runs/compare_tracking/track/   ← ByteTrack 결과 이미지
    runs/compare_tracking/report.txt ← 안정성 수치 비교
"""

import os, json
from pathlib import Path
import numpy as np

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

from ultralytics import YOLO

MODEL   = Path("runs/detect/runs/train/roboflow_v1/weights/best.pt")
VAL_DIR = Path("datasets/roboflow_merged/images/val")
OUT_DIR = Path("runs/compare_tracking")
CONF    = 0.30
IMGSZ   = 320
MAX_IMGS = 80   # 비교에 사용할 이미지 수


def bbox_center(box):
    """xyxy → (cx, cy, w, h)"""
    x1, y1, x2, y2 = box
    return (x1+x2)/2, (y1+y2)/2, x2-x1, y2-y1


def stability_score(frames: list[list]) -> dict:
    """
    연속 프레임에서 같은 클래스의 박스 중심 이동량 평균.
    낮을수록 안정적.
    """
    moves = []
    prev = {}
    for dets in frames:
        curr = {}
        for cls, cx, cy, w, h in dets:
            curr.setdefault(cls, []).append((cx, cy, w, h))
        for cls, boxes in curr.items():
            if cls in prev:
                for (cx, cy, _, _), (px, py, _, _) in zip(boxes, prev[cls]):
                    moves.append(((cx-px)**2 + (cy-py)**2)**0.5)
        prev = curr

    return {
        "mean_move_px": float(np.mean(moves)) if moves else 0.0,
        "std_move_px":  float(np.std(moves))  if moves else 0.0,
        "n_frames":     len(frames),
        "n_transitions": len(moves),
    }


def run_detect(model, images):
    """단순 detect — 매 프레임 독립 추론."""
    frames = []
    out_dir = OUT_DIR / "detect"
    out_dir.mkdir(parents=True, exist_ok=True)

    for img in images:
        results = model.predict(str(img), conf=CONF, imgsz=IMGSZ,
                                save=True, project=str(out_dir),
                                name="imgs", exist_ok=True, verbose=False)
        dets = []
        for r in results:
            for box in r.boxes:
                cx, cy, w, h = box.xywh[0].tolist()
                cls = int(box.cls[0])
                dets.append((cls, cx, cy, w, h))
        frames.append(dets)
    return frames


def run_bytetrack(model, images):
    """ByteTrack — 연속 프레임을 시퀀스로 처리."""
    frames = []
    out_dir = OUT_DIR / "track"
    out_dir.mkdir(parents=True, exist_ok=True)

    for img in images:
        results = model.track(str(img), conf=CONF, imgsz=IMGSZ,
                              tracker="bytetrack.yaml",
                              persist=True,
                              save=True, project=str(out_dir),
                              name="imgs", exist_ok=True, verbose=False)
        dets = []
        for r in results:
            for box in r.boxes:
                cx, cy, w, h = box.xywh[0].tolist()
                cls = int(box.cls[0])
                dets.append((cls, cx, cy, w, h))
        frames.append(dets)
    return frames


def main():
    if not MODEL.exists():
        print(f"오류: {MODEL} 없음. 파인튜닝을 먼저 완료하세요.")
        return
    if not VAL_DIR.exists():
        print(f"오류: {VAL_DIR} 없음.")
        return

    images = sorted(VAL_DIR.glob("*.jpg"))[:MAX_IMGS]
    if len(images) < 10:
        images += sorted(VAL_DIR.glob("*.png"))[:MAX_IMGS - len(images)]

    print(f"비교 이미지: {len(images)}장")
    print(f"모델: {MODEL}\n")

    model = YOLO(str(MODEL))

    print("[1/2] 단순 Detect 실행...")
    detect_frames = run_detect(model, images)
    detect_stats  = stability_score(detect_frames)

    # ByteTrack은 모델 상태 초기화 후 실행
    model = YOLO(str(MODEL))
    print("[2/2] ByteTrack 실행...")
    track_frames = run_bytetrack(model, images)
    track_stats  = stability_score(track_frames)

    report_lines = [
        "=" * 50,
        "바운딩 박스 안정성 비교 결과",
        "=" * 50,
        f"이미지 수: {len(images)}장",
        f"모델: {MODEL.name}",
        "",
        "[단순 Detect]",
        f"  박스 중심 평균 이동: {detect_stats['mean_move_px']:.2f} px",
        f"  표준편차:           {detect_stats['std_move_px']:.2f} px",
        f"  측정 전환 수:       {detect_stats['n_transitions']}",
        "",
        "[ByteTrack]",
        f"  박스 중심 평균 이동: {track_stats['mean_move_px']:.2f} px",
        f"  표준편차:           {track_stats['std_move_px']:.2f} px",
        f"  측정 전환 수:       {track_stats['n_transitions']}",
        "",
    ]

    dm = detect_stats["mean_move_px"]
    tm = track_stats["mean_move_px"]
    if tm < dm:
        diff_pct = (dm - tm) / dm * 100 if dm > 0 else 0
        report_lines.append(f"결론: ByteTrack이 {diff_pct:.1f}% 더 안정적")
    elif dm < tm:
        diff_pct = (tm - dm) / tm * 100 if tm > 0 else 0
        report_lines.append(f"결론: 단순 Detect가 {diff_pct:.1f}% 더 안정적")
    else:
        report_lines.append("결론: 두 방식 동일")

    report_lines += [
        "",
        "참고: EMA_ALPHA=0.30 (Android 적용됨) 은 이 비교와 별개로",
        "      Android 앱 내부에서 박스를 추가로 스무딩합니다.",
        "=" * 50,
    ]

    report = "\n".join(report_lines)
    print("\n" + report)

    report_path = OUT_DIR / "report.txt"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    print(f"\n결과 저장: {OUT_DIR}")
    print(f"  detect 이미지: {OUT_DIR}/detect/imgs/")
    print(f"  track  이미지: {OUT_DIR}/track/imgs/")
    print(f"  수치 리포트:   {report_path}")


if __name__ == "__main__":
    main()
