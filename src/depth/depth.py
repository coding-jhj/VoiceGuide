import os
import torch
import numpy as np

_depth_model = None
_model_available: bool | None = None  # None = 아직 확인 안 함

_MODEL_PATH = "depth_anything_v2_vits.pth"

# ── 캘리브레이션 파라미터 ────────────────────────────────────────────────────
# Depth Anything V2 는 disparity(역깊이) 출력 → 역수 변환 후 스케일 적용
# DEPTH_INVERT = True : 출력값이 클수록 가깝다 (disparity 포맷)
# DEPTH_SCALE  : (1 / depth_val) * DEPTH_SCALE ≈ 실제 거리(m)
#   보정 방법: 1m 거리 물체 → depth_val 측정 → DEPTH_SCALE = depth_val * 1.0
DEPTH_INVERT = True
DEPTH_SCALE  = 5.0

DIST_VERY_NEAR_M = 0.8
DIST_NEAR_M      = 2.0
DIST_MID_M       = 4.0
DIST_FAR_M       = 7.0
# ────────────────────────────────────────────────────────────────────────────


def _check_model() -> bool:
    global _model_available
    if _model_available is None:
        _model_available = os.path.exists(_MODEL_PATH)
        if _model_available:
            print(f"[Depth V2] 모델 파일 확인: {_MODEL_PATH}")
        else:
            print(f"[Depth V2] 모델 파일 없음 → bbox 기반 거리 사용 ({_MODEL_PATH})")
    return _model_available


def _load_model():
    global _depth_model
    if _depth_model is not None:
        return _depth_model
    try:
        from depth_anything_v2.dpt import DepthAnythingV2
        m = DepthAnythingV2(encoder="vits", features=64,
                            out_channels=[48, 96, 192, 384])
        state = torch.load(_MODEL_PATH, map_location="cpu")
        m.load_state_dict(state)
        m.eval()
        _depth_model = m
        print("[Depth V2] 모델 로드 완료")
    except Exception as e:
        print(f"[Depth V2] 모델 로드 실패: {e}")
        global _model_available
        _model_available = False
    return _depth_model


def _infer_depth_map(image_np) -> np.ndarray | None:
    """이미지 전체에 대해 depth map 1회 추론. 실패 시 None 반환."""
    model = _load_model()
    if model is None:
        return None
    try:
        with torch.no_grad():
            raw = model.infer_image(image_np)  # H x W, float32
        # disparity → depth: 역수 변환
        if DEPTH_INVERT:
            raw = np.where(raw > 1e-6, 1.0 / raw, 10.0)
        # 0-1 정규화 후 미터 스케일 적용
        d_min, d_max = raw.min(), raw.max()
        if d_max > d_min:
            norm = (raw - d_min) / (d_max - d_min)
        else:
            norm = np.zeros_like(raw)
        return norm * DEPTH_SCALE
    except Exception as e:
        print(f"[Depth V2] 추론 오류: {e}")
        return None


def _bbox_dist_m(depth_map: np.ndarray, x1, y1, x2, y2) -> float:
    """
    bbox 내 여러 지점의 depth 중앙값으로 거리 추정.
    바닥 접촉점(bbox 하단) 근처를 더 신뢰.
    """
    h, w = depth_map.shape
    # 샘플링 포인트: 중앙 + 하단 좌/중/우
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    by = max(0, min(y2 - max((y2 - y1) // 8, 2), h - 1))
    pts = [
        (cy, cx),
        (by, max(0, min(x1 + (x2 - x1) // 4, w - 1))),
        (by, max(0, min(cx, w - 1))),
        (by, max(0, min(x1 + 3 * (x2 - x1) // 4, w - 1))),
    ]
    vals = [float(depth_map[r, c]) for r, c in pts
            if 0 <= r < h and 0 <= c < w]
    if not vals:
        return 5.0
    vals.sort()
    raw = vals[len(vals) // 2]  # 중앙값 (이상치 제거)
    return round(max(0.1, min(raw, 10.0)), 1)


def _label(dist_m: float) -> str:
    if dist_m <= DIST_VERY_NEAR_M:   return "매우 가까이"
    elif dist_m <= DIST_NEAR_M:      return "가까이"
    elif dist_m <= DIST_MID_M:       return "보통"
    elif dist_m <= DIST_FAR_M:       return "멀리"
    else:                             return "매우 멀리"


def detect_and_depth(image_bytes: bytes) -> list[dict]:
    """
    YOLO 탐지 + Depth V2 거리 정제 (모델 파일 없으면 bbox 기반 유지).
    depth map을 이미지당 1회만 추론해 성능 최적화.
    """
    import cv2
    nparr = np.frombuffer(image_bytes, np.uint8)
    image_np = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    from src.vision.detect import detect_objects
    objects = detect_objects(image_bytes)

    if _check_model():
        depth_map = _infer_depth_map(image_np)
        if depth_map is not None:
            for obj in objects:
                x1, y1, x2, y2 = obj["bbox"]
                dm = _bbox_dist_m(depth_map, x1, y1, x2, y2)
                obj["distance_m"] = dm
                obj["distance"]   = _label(dm)
                obj["depth_source"] = "v2"
        else:
            for obj in objects:
                obj["depth_source"] = "bbox"
    else:
        for obj in objects:
            obj["depth_source"] = "bbox"

    return objects
