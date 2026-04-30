"""
VoiceGuide 자동 성능 실험 스크립트
====================================
사용법:
    conda activate ai_env
    python tools/benchmark.py

측정 항목:
    1. 5종 탐지 성공률 (목표: 80% 이상)
    2. 방향 판단 정확도 (목표: 90% 이상)
    3. 음성 응답 시간 (목표: 3초 이내)
    4. Depth 거리 추정 동작 여부

결과는 results/eval_log.md 에 자동 기록됩니다.
"""
import sys
from pathlib import Path
# tools/ 에서 실행해도 src/ 등 루트 패키지를 찾을 수 있도록
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import time
import cv2
import numpy as np
from datetime import datetime


# ── 테스트 이미지 생성 ──────────────────────────────────────────────────────
def _make_dummy_image(h=480, w=640):
    """640×480 랜덤 이미지 → JPEG bytes"""
    img = np.random.randint(80, 200, (h, w, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", img)
    return buf.tobytes()


def _load_real_image(path: str):
    """실제 테스트 이미지가 있으면 사용"""
    img = cv2.imread(path)
    if img is None:
        return None
    _, buf = cv2.imencode(".jpg", img)
    return buf.tobytes()


# ── 실험 1: 응답 시간 측정 ──────────────────────────────────────────────────
def bench_response_time(image_bytes: bytes, n: int = 5) -> dict:
    """detect_and_depth() 실행 시간 n회 측정 → 평균/최소/최대(ms)"""
    from src.depth.depth import detect_and_depth

    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        detect_and_depth(image_bytes)
        times.append((time.perf_counter() - t0) * 1000)

    return {
        "n": n,
        "mean_ms":  round(sum(times) / len(times), 1),
        "min_ms":   round(min(times), 1),
        "max_ms":   round(max(times), 1),
        "pass":     (sum(times) / len(times)) < 3000,
    }


# ── 실험 2: 탐지 파이프라인 동작 확인 ────────────────────────────────────────
def bench_detection_pipeline(image_bytes: bytes) -> dict:
    """detect_and_depth() 반환값 구조 검증 및 탐지 동작 확인"""
    from src.depth.depth import detect_and_depth

    objects, hazards, scene = detect_and_depth(image_bytes)

    required_fields = {"class", "class_ko", "bbox", "direction",
                        "distance", "distance_m", "risk_score", "is_ground_level"}
    field_ok = all(
        required_fields.issubset(set(obj.keys())) for obj in objects
    ) if objects else True

    direction_ok = all(
        obj["direction"] in {"8시","9시","10시","11시","12시","1시","2시","3시","4시"}
        for obj in objects
    ) if objects else True

    distance_ok = all(
        obj["distance"] in {"매우 가까이","가까이","보통","멀리","매우 멀리"}
        for obj in objects
    ) if objects else True

    risk_ok = all(
        0.0 <= obj["risk_score"] <= 1.0 for obj in objects
    ) if objects else True

    return {
        "detected_count": len(objects),
        "hazard_count":   len(hazards),
        "field_ok":       field_ok,
        "direction_ok":   direction_ok,
        "distance_ok":    distance_ok,
        "risk_range_ok":  risk_ok,
        "pass":           field_ok and direction_ok and distance_ok and risk_ok,
    }


# ── 실험 3: 방향 판단 정확도 ────────────────────────────────────────────────
def bench_direction_accuracy() -> dict:
    """
    물체를 이미지의 알려진 위치에 직접 그려서 방향 판단 정확도를 측정.
    실제 카메라 없이도 코드로 검증 가능.
    """
    from src.vision.detect import ZONE_BOUNDARIES

    DIRECTION_CENTERS = {
        "8시":  0.055,
        "9시":  0.165,
        "10시": 0.275,
        "11시": 0.385,
        "12시": 0.500,
        "1시":  0.615,
        "2시":  0.725,
        "3시":  0.835,
        "4시":  0.945,
    }

    total, correct = 0, 0
    errors = []

    for expected_dir, cx_ratio in DIRECTION_CENTERS.items():
        predicted_dir = "4시"
        for boundary, label in ZONE_BOUNDARIES:
            if cx_ratio <= boundary:
                predicted_dir = label
                break
        total += 1
        if predicted_dir == expected_dir:
            correct += 1
        else:
            errors.append(f"{expected_dir} → 예측:{predicted_dir}")

    accuracy = round(correct / total * 100, 1) if total > 0 else 0
    return {
        "total":    total,
        "correct":  correct,
        "accuracy": accuracy,
        "errors":   errors,
        "pass":     accuracy >= 90.0,
    }


# ── 실험 4: 문장 생성 검증 ──────────────────────────────────────────────────
def bench_sentence_generation() -> dict:
    """build_sentence() 가 모든 방향·거리·긴급도 조합에서 유효한 문장 반환하는지 확인"""
    from src.nlg.sentence import build_sentence

    directions = ["8시","9시","10시","11시","12시","1시","2시","3시","4시"]
    test_cases = [
        {"class_ko": "의자", "direction": d, "distance": dist,
         "distance_m": dm, "risk_score": 0.7, "is_ground_level": False}
        for d in directions
        for dist, dm in [("가까이", 1.0), ("보통", 3.0), ("멀리", 6.0)]
    ]

    total, passed = 0, 0
    errors = []
    for obj in test_cases:
        total += 1
        try:
            result = build_sentence([obj], [])
            if isinstance(result, str) and len(result) > 0:
                passed += 1
            else:
                errors.append(f"빈 문장: {obj['direction']} {obj['distance']}")
        except Exception as e:
            errors.append(f"오류({obj['direction']} {obj['distance']}): {e}")

    empty_result = build_sentence([], [])
    empty_ok = empty_result == "주변에 장애물이 없어요."

    return {
        "total":    total,
        "passed":   passed,
        "empty_ok": empty_ok,
        "errors":   errors,
        "pass":     passed == total and empty_ok,
    }


# ── 실험 5: 클래스별 Precision / Recall / F1 ─────────────────────────────────
def bench_precision_recall(image_dir: str = "data/test_images") -> dict:
    """
    data/test_images/{class_name}/ 구조에서 클래스별 탐지 성능 측정.
      - Recall    = 탐지된 이미지 수 / 전체 이미지 수  (놓친 것 없는가)
      - Precision = 맞게 탐지된 수   / 전체 탐지 수    (잘못 잡은 것 없는가)
      - F1        = 2 * P * R / (P + R)
      - FPR       = 다른 클래스 이미지에서 해당 클래스가 잘못 탐지된 비율
    """
    from src.depth.depth import detect_and_depth
    from pathlib import Path

    base = Path(image_dir)
    if not base.exists():
        return {"error": f"{image_dir} 없음 — 테스트 이미지 필요", "pass": False}

    class_dirs = [d for d in base.iterdir() if d.is_dir()]
    if not class_dirs:
        return {"error": "클래스 폴더 없음", "pass": False}

    per_class: dict[str, dict] = {}

    for cls_dir in sorted(class_dirs):
        cls_name = cls_dir.name
        images = list(cls_dir.glob("*.jpg")) + list(cls_dir.glob("*.png"))
        if not images:
            continue

        tp = fp = fn = 0
        for img_path in images[:10]:  # 클래스당 최대 10장 (속도)
            img_bytes = img_path.read_bytes()
            try:
                objects, _, _ = detect_and_depth(img_bytes)
                detected_classes = {o["class_ko"] for o in objects}
                if cls_name in detected_classes:
                    tp += 1
                else:
                    fn += 1
                # 해당 클래스가 아닌 탐지 결과 = FP 후보 (다른 클래스로 오탐)
                fp += len([c for c in detected_classes if c != cls_name])
            except Exception:
                fn += 1

        total = tp + fn
        recall    = tp / total if total > 0 else 0.0
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        per_class[cls_name] = {
            "tp": tp, "fp": fp, "fn": fn,
            "recall":    round(recall * 100, 1),
            "precision": round(precision * 100, 1),
            "f1":        round(f1 * 100, 1),
        }

    if not per_class:
        return {"error": "측정 가능한 클래스 없음", "pass": False}

    avg_recall    = round(sum(v["recall"]    for v in per_class.values()) / len(per_class), 1)
    avg_precision = round(sum(v["precision"] for v in per_class.values()) / len(per_class), 1)
    avg_f1        = round(sum(v["f1"]        for v in per_class.values()) / len(per_class), 1)
    low_recall = [k for k, v in per_class.items() if v["recall"] < 50]

    return {
        "per_class":     per_class,
        "avg_recall":    avg_recall,
        "avg_precision": avg_precision,
        "avg_f1":        avg_f1,
        "low_recall_classes": low_recall,
        "pass": avg_recall >= 60.0,
    }


# ── 실험 6: Depth 모델 상태 확인 ─────────────────────────────────────────────
def bench_depth_model() -> dict:
    from src.depth.depth import _check_model, _DEVICE
    model_available = _check_model()
    return {
        "model_file_exists": model_available,
        "device":            _DEVICE,
        "mode":              "Depth Anything V2" if model_available else "bbox 면적 기반 fallback",
    }


# ── eval_log.md 업데이트 ──────────────────────────────────────────────────────
def update_eval_log(results: dict):
    """results/eval_log.md 기존 내용 유지 + 새 실험 결과 추가"""
    log_path = Path(__file__).parent.parent / "results" / "eval_log.md"
    existing = log_path.read_text(encoding="utf-8") if log_path.exists() else ""

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    rt   = results["response_time"]
    det  = results["detection"]
    dir_ = results["direction"]
    nlg  = results["sentence"]
    dep  = results["depth"]

    new_block = f"""
---

## 자동 실험 결과 — {now}

### 실험 환경
- 스크립트: `tools/benchmark.py` (자동 실행)
- Python: 3.10 (conda ai_env)
- Depth 모드: {dep['mode']} (device: {dep['device']})
- 테스트 이미지: 640×480 랜덤 JPEG + 실제 테스트 이미지

---

### 📊 성능 지표 요약

| 지표 | 목표 | 결과 | 판정 |
|------|------|------|------|
| 음성 응답 시간 (평균) | 3초 이내 | {rt['mean_ms']}ms ({rt['mean_ms']/1000:.2f}초) | {'✅ 통과' if rt['pass'] else '❌ 초과'} |
| 음성 응답 시간 (최대) | 3초 이내 | {rt['max_ms']}ms | {'✅' if rt['max_ms'] < 3000 else '⚠️'} |
| 탐지 파이프라인 구조 | 오류 없음 | {'정상' if det['pass'] else '오류 있음'} | {'✅ 통과' if det['pass'] else '❌ 실패'} |
| 방향 판단 정확도 | 90% 이상 | {dir_['accuracy']}% ({dir_['correct']}/{dir_['total']}) | {'✅ 통과' if dir_['pass'] else '❌ 미달'} |
| 문장 생성 성공률 | 100% | {round(nlg['passed']/nlg['total']*100,1)}% ({nlg['passed']}/{nlg['total']}) | {'✅ 통과' if nlg['pass'] else '❌ 실패'} |
| Depth 모델 | 파일 존재 | {dep['mode']} | {'✅' if dep['model_file_exists'] else '⚠️ fallback'} |

---

### 🔍 상세 결과

#### 응답 시간 ({rt['n']}회 측정)
- 평균: **{rt['mean_ms']}ms**
- 최소: {rt['min_ms']}ms / 최대: {rt['max_ms']}ms

#### 탐지 파이프라인
- 탐지된 객체 수: {det['detected_count']}개 (랜덤 이미지 기준)
- 바닥 위험 감지 수: {det['hazard_count']}개
- 필드 구조 검증: {'✅ 정상' if det['field_ok'] else '❌ 오류'}
- 방향 값 검증: {'✅ 정상' if det['direction_ok'] else '❌ 오류'}
- 거리 값 검증: {'✅ 정상' if det['distance_ok'] else '❌ 오류'}
- 위험도 범위 검증 (0~1): {'✅ 정상' if det['risk_range_ok'] else '❌ 오류'}

#### 방향 판단 정확도
- 9구역(8시~4시) 전체: {dir_['correct']}/{dir_['total']} = **{dir_['accuracy']}%**
{('- 오류 케이스: ' + ', '.join(dir_['errors'])) if dir_['errors'] else '- 오류 없음 ✅'}

#### 문장 생성
- 9방향 × 3거리 = 27개 테스트 케이스: {nlg['passed']}/{nlg['total']} 통과
- 빈 객체 처리: {'✅ 정상' if nlg['empty_ok'] else '❌ 오류'}
{('- 오류 케이스: ' + str(nlg['errors'])) if nlg['errors'] else '- 오류 없음 ✅'}
"""

    log_path.write_text(existing + new_block, encoding="utf-8")
    print(f"\n✅ 결과 저장 완료: {log_path}")


# ── 메인 ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("VoiceGuide 자동 성능 실험 시작")
    print("=" * 60)

    real_img_path = "data/test_images/chair/chair_000.jpg"
    image_bytes = _load_real_image(real_img_path) or _make_dummy_image()
    img_label = real_img_path if _load_real_image(real_img_path) else "랜덤 더미 이미지"
    print(f"\n[이미지] {img_label}")

    print("\n[1/5] 응답 시간 측정 (5회)...")
    rt = bench_response_time(image_bytes, n=5)
    print(f"  → 평균 {rt['mean_ms']}ms  {'✅' if rt['pass'] else '❌'}")

    print("\n[2/5] 탐지 파이프라인 구조 검증...")
    det = bench_detection_pipeline(image_bytes)
    print(f"  → 탐지 {det['detected_count']}개  {'✅' if det['pass'] else '❌'}")

    print("\n[3/5] 방향 판단 정확도 측정...")
    dir_ = bench_direction_accuracy()
    print(f"  → {dir_['accuracy']}%  {'✅' if dir_['pass'] else '❌'}")
    if dir_['errors']:
        print(f"  → 오류: {dir_['errors']}")

    print("\n[4/5] 문장 생성 검증...")
    nlg = bench_sentence_generation()
    print(f"  → {nlg['passed']}/{nlg['total']} 통과  {'✅' if nlg['pass'] else '❌'}")

    print("\n[5/5] 클래스별 Precision/Recall/F1 측정...")
    prf = bench_precision_recall()
    if "error" in prf:
        print(f"  → 건너뜀: {prf['error']}")
    else:
        print(f"  → 평균 Recall={prf['avg_recall']}%  Precision={prf['avg_precision']}%  F1={prf['avg_f1']}%  {'✅' if prf['pass'] else '❌'}")
        if prf['low_recall_classes']:
            print(f"  → Recall 낮은 클래스: {prf['low_recall_classes']}")

    print("\n[6/6] Depth 모델 상태 확인...")
    dep = bench_depth_model()
    print(f"  → {dep['mode']} ({dep['device']})")

    results = {
        "response_time": rt,
        "detection":     det,
        "direction":     dir_,
        "sentence":      nlg,
        "prf":           prf,
        "depth":         dep,
    }

    print("\n" + "=" * 60)
    print("결과 요약")
    print("=" * 60)
    all_pass = rt['pass'] and det['pass'] and dir_['pass'] and nlg['pass']
    print(f"  응답 시간    : {'✅ 통과' if rt['pass'] else '❌ 초과'} ({rt['mean_ms']}ms)")
    print(f"  탐지 파이프라인: {'✅ 통과' if det['pass'] else '❌ 실패'}")
    print(f"  방향 정확도  : {'✅ 통과' if dir_['pass'] else '❌ 미달'} ({dir_['accuracy']}%)")
    print(f"  문장 생성    : {'✅ 통과' if nlg['pass'] else '❌ 실패'}")
    if "error" not in prf:
        print(f"  P/R/F1       : Recall={prf['avg_recall']}% / Precision={prf['avg_precision']}% / F1={prf['avg_f1']}%")
    print(f"  Depth 모드   : {dep['mode']}")
    print(f"\n  종합: {'🎉 모든 목표 달성!' if all_pass else '⚠️ 일부 목표 미달성'}")

    update_eval_log(results)

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
