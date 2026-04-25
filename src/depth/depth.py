import torch

_depth_model = None

# ── 튜닝 파라미터 (Depth Anything V2 활성화 시 사용) ──────────────────────
# Depth Anything V2는 상대적(relative) depth를 출력 → 미터 변환 필요
#
# DEPTH_SCALE: depth 값 * DEPTH_SCALE ≈ 실제 거리(m)
#   - 카메라·환경마다 달라지므로 현장 실험으로 보정
#   - 보정 방법: 실제 1m 거리 물체 찍고 depth_val * DEPTH_SCALE = 1.0 되도록 조정
DEPTH_SCALE = 10.0

# 거리 임계값 (미터 단위로 직접 설정)
DIST_VERY_NEAR_M = 0.5    # 이하 → "매우 가까이"  (~50 cm 이내)
DIST_NEAR_M      = 1.5    # 이하 → "가까이"        (~1.5 m 이내)
DIST_MID_M       = 3.0    # 이하 → "보통"          (~3 m 이내)
DIST_FAR_M       = 5.0    # 이하 → "멀리"          (~5 m 이내)
                           # 초과         → "매우 멀리"
# ────────────────────────────────────────────────────────────────────────────


def get_depth_model():
    global _depth_model
    if _depth_model is None:
        from depth_anything_v2.dpt import DepthAnythingV2
        _depth_model = DepthAnythingV2(
            encoder="vits", features=64,
            out_channels=[48, 96, 192, 384]
        )
        _depth_model.load_state_dict(
            torch.load("depth_anything_v2_vits.pth", map_location="cpu")
        )
        _depth_model.eval()
    return _depth_model


def estimate_distance(image_np, x1, y1, x2, y2) -> str:
    """
    bbox 중심점 depth 값으로 거리 분류 (미터 단위 임계값 사용)
    Returns: "매우 가까이" / "가까이" / "보통" / "멀리" / "매우 멀리"
    """
    model = get_depth_model()
    depth_map = model.infer_image(image_np)
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    depth_val = float(depth_map[cy][cx])

    dist_m = depth_val * DEPTH_SCALE

    if dist_m <= DIST_VERY_NEAR_M:
        return "매우 가까이"
    elif dist_m <= DIST_NEAR_M:
        return "가까이"
    elif dist_m <= DIST_MID_M:
        return "보통"
    elif dist_m <= DIST_FAR_M:
        return "멀리"
    else:
        return "매우 멀리"


def detect_and_depth(image_bytes: bytes) -> list[dict]:
    """
    C의 detect_objects() + D의 estimate_distance() 통합
    B가 호출하는 최종 함수
    """
    import numpy as np
    import cv2

    nparr = np.frombuffer(image_bytes, np.uint8)
    image_np = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    from src.vision.detect import detect_objects
    objects = detect_objects(image_bytes)

    # Depth V2 활성화: depth_anything_v2_vits.pth 준비 후 주석 해제
    # for obj in objects:
    #     x1, y1, x2, y2 = obj["bbox"]
    #     obj["distance"] = estimate_distance(image_np, x1, y1, x2, y2)

    return objects
