"""
VoiceGuide 거리 추정 모듈
===========================
Depth Anything V2를 사용해 이미지 한 장으로 거리를 추정합니다.
모델 파일이 없으면 bbox 면적 기반 fallback으로 자동 전환됩니다.

중요: 카메라 단안으로는 정확한 미터 거리 측정 불가 (강사님 지적 사항).
이 모듈은 상대적 깊이를 추정하며, 보정값(DEPTH_SCALE)을 통해 근사치를 얻습니다.
"""

import os
import torch
import numpy as np

# ── 모델 상태 (싱글톤 패턴) ──────────────────────────────────────────────────
# 전역 변수로 모델을 한 번만 로드 → 매 요청마다 로드하면 너무 느림
_depth_model = None
_model_available: bool | None = None  # None = 아직 확인 안 함

_MODEL_PATH = "depth_anything_v2_vits.pth"  # 프로젝트 루트에 있어야 함

# ── Depth V2 프레임 스킵 (성능 최적화) ─────────────────────────────────────────
# 매 프레임 실행 시 서버 응답 700ms+ → 3프레임에 1번만 실행해서 300ms 이내 목표
_depth_frame_counter: int = 0
_last_depth_map: "np.ndarray | None" = None
_DEPTH_RUN_EVERY: int = 3

# ── 캘리브레이션 파라미터 ────────────────────────────────────────────────────
# Depth V2의 출력은 "상대적 깊이"라 직접 미터가 아님
# DEPTH_SCALE을 곱해서 미터 단위로 근사
# 보정 방법: 알려진 거리(예: 2m)의 물체를 찍고 depth 값 측정
#            → DEPTH_SCALE = 2.0 / 측정된_depth_val
DEPTH_SCALE = 1.0  # 기본값 (환경별로 조정 필요 — CALIBRATION_TEST.md 참조)

# 거리 구간 정의 (미터)
DIST_VERY_NEAR_M = 0.8
DIST_NEAR_M      = 2.0
DIST_MID_M       = 4.0
DIST_FAR_M       = 7.0


def _check_model() -> bool:
    """모델 파일 존재 여부 확인 (최초 1회만 파일시스템 접근)."""
    global _model_available
    if _model_available is None:
        _model_available = os.path.exists(_MODEL_PATH)
        if _model_available:
            print(f"[Depth V2] 모델 파일 확인: {_MODEL_PATH}")
        else:
            print(f"[Depth V2] 모델 파일 없음 → bbox 기반 거리 사용 ({_MODEL_PATH})")
    return _model_available


# GPU가 있으면 CUDA 사용, 없으면 CPU (RTX 5060 있으면 CUDA 자동 선택)
_DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


def _load_model():
    """모델을 메모리에 로드. 이미 로드되어 있으면 캐시된 것 반환."""
    global _depth_model
    if _depth_model is not None:
        return _depth_model  # 이미 로드됨 → 바로 반환

    try:
        from depth_anything_v2.dpt import DepthAnythingV2
        # ViT-S (Small) 구성: features=64, out_channels 4단계
        m = DepthAnythingV2(encoder="vits", features=64,
                            out_channels=[48, 96, 192, 384])
        # map_location: GPU 없는 환경에서도 CPU로 로드 가능하게
        state = torch.load(_MODEL_PATH, map_location=_DEVICE)
        m.load_state_dict(state)
        m.to(_DEVICE)
        m.eval()  # 추론 모드 (dropout, batchnorm 비활성화 → 속도 향상)
        _depth_model = m
        print(f"[Depth V2] 모델 로드 완료 (device={_DEVICE})")
    except Exception as e:
        print(f"[Depth V2] 모델 로드 실패: {e}")
        global _model_available
        _model_available = False  # 이후 요청에서 fallback 사용
    return _depth_model


def _infer_depth_map(image_np) -> np.ndarray | None:
    """
    이미지 전체에 대해 깊이 맵을 1회 추론.
    실패 시 None 반환 → bbox fallback으로 전환.

    이미지당 1회만 추론하는 이유:
    - 물체마다 따로 추론하면 N배 느림
    - 1회 추론 결과를 모든 bbox에 재사용 → 효율적
    """
    model = _load_model()
    if model is None:
        return None
    try:
        with torch.no_grad():  # 역전파 계산 안 함 → 메모리·속도 절약
            # infer_image: (H, W) float32, 작을수록 가까움
            raw = model.infer_image(image_np)
        # 스케일 적용 후 유효 범위로 클리핑 (0.1m ~ 10m)
        depth_m = np.clip(raw * DEPTH_SCALE, 0.1, 10.0)
        return depth_m
    except Exception as e:
        print(f"[Depth V2] 추론 오류: {e}")
        return None


def _bbox_dist_m(depth_map: np.ndarray, x1, y1, x2, y2) -> float:
    """
    bbox 영역의 깊이 맵에서 거리를 추정.

    전략:
    - bbox 전체 평균 쓰면 물체 뒤쪽(먼 부분)이 섞여서 과대 추정
    - bbox 중앙 + 하단(바닥 접촉점) 여러 지점 샘플링
    - 그 중 하위 30% (가장 가까운 값) 사용 → 안전 우선 (조기 경고)
    """
    h, w = depth_map.shape
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2

    # 하단 접촉점: bbox 아래에서 1/8 위 (바닥에 붙은 지점)
    by = max(0, min(y2 - max((y2 - y1) // 8, 2), h - 1))

    # 샘플링 포인트: 중앙 + 하단 좌/중/우 4곳
    pts = [
        (cy, cx),
        (by, max(0, min(x1 + (x2 - x1) // 4, w - 1))),     # 하단 왼쪽 1/4
        (by, max(0, min(cx,                   w - 1))),     # 하단 중앙
        (by, max(0, min(x1 + 3 * (x2 - x1) // 4, w - 1))), # 하단 오른쪽 3/4
    ]

    vals = [float(depth_map[r, c]) for r, c in pts
            if 0 <= r < h and 0 <= c < w]
    if not vals:
        return 5.0  # 유효 포인트 없으면 "보통 거리"로 기본값

    vals.sort()
    # 하위 30% = 샘플 중 가장 가까운 값 사용
    # 이유: 물체의 가장 가까운 면이 실제 충돌 위험 지점
    conservative_idx = max(0, len(vals) // 3)
    raw = vals[conservative_idx]
    return round(max(0.1, min(raw, 10.0)), 1)


def _label(dist_m: float) -> str:
    """거리(m)를 언어 레이블로 변환. sentence.py의 _format_dist와 연동됨."""
    if dist_m <= DIST_VERY_NEAR_M:   return "매우 가까이"
    elif dist_m <= DIST_NEAR_M:      return "가까이"
    elif dist_m <= DIST_MID_M:       return "보통"
    elif dist_m <= DIST_FAR_M:       return "멀리"
    else:                             return "매우 멀리"


def detect_and_depth(image_bytes: bytes) -> tuple[list[dict], list[dict], dict]:
    """
    YOLO 탐지 + Depth V2 거리 정제 + 바닥 위험 감지를 하나의 함수로 묶음.
    routes.py에서 이 함수 하나만 호출하면 됨.

    처리 순서:
    1. detect_objects()로 YOLO 탐지 (bbox 기반 초기 거리 포함)
    2. _infer_depth_map()으로 깊이 맵 1회 추론
    3. bbox마다 _bbox_dist_m()으로 더 정확한 거리로 교체
    4. detect_floor_hazards()로 계단·낙차·좁은 통로 감지

    Returns:
        objects  — 탐지된 물체 목록 (최대 3개, 위험도 순)
        hazards  — 바닥 위험 목록 (계단, 낙차, 턱)
        scene    — 안전경로·군중경고·위험물체·신호등 분석 결과
    """
    import cv2
    from src.depth.hazard import detect_floor_hazards
    from src.vision.detect import detect_objects

    # YOLO 탐지 (내부에서 cv2.flip으로 좌우 보정 포함)
    nparr    = np.frombuffer(image_bytes, np.uint8)
    image_np = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    global _depth_frame_counter, _last_depth_map
    objects, scene = detect_objects(image_bytes)  # YOLO + scene 분석
    hazards: list[dict] = []

    if _check_model():
        _depth_frame_counter += 1
        # 3프레임마다 1번만 Depth V2 실행 — 나머지는 직전 결과 재사용
        if _depth_frame_counter % _DEPTH_RUN_EVERY == 1 or _last_depth_map is None:
            fresh = _infer_depth_map(image_np)
            if fresh is not None:
                _last_depth_map = fresh
        depth_map = _last_depth_map
        if depth_map is not None:
            for obj in objects:
                x1, y1, x2, y2 = obj["bbox"]
                dm = _bbox_dist_m(depth_map, x1, y1, x2, y2)
                obj["distance_m"]   = dm
                obj["distance"]     = _label(dm)
                obj["depth_source"] = "v2"
            hazards = detect_floor_hazards(depth_map)
        else:
            for obj in objects:
                obj["depth_source"] = "bbox"
    else:
        for obj in objects:
            obj["depth_source"] = "bbox"

    return objects, hazards, scene
