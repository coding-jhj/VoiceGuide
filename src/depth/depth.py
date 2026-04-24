import torch

_depth_model = None


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
    bbox 중심점 depth 값으로 거리 분류
    Returns: "가까이" / "보통" / "멀리"

    주의: Depth Anything V2는 상대적(relative) depth 출력
    → 임계값은 실내 환경 실험으로 결정 (4/28 현장 실험 예정)
    """
    model = get_depth_model()
    depth_map = model.infer_image(image_np)
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    depth_val = float(depth_map[cy][cx])

    NEAR_THRESHOLD = 0.3  # TODO: 실험으로 결정
    MID_THRESHOLD  = 0.6  # TODO: 실험으로 결정

    if depth_val < NEAR_THRESHOLD:
        return "가까이"
    elif depth_val < MID_THRESHOLD:
        return "보통"
    else:
        return "멀리"


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

    # MVP: distance는 C가 계산한 bbox 비율 그대로 사용
    # 서버 연동 후: 아래 주석 해제
    # for obj in objects:
    #     x1, y1, x2, y2 = obj["bbox"]
    #     obj["distance"] = estimate_distance(image_np, x1, y1, x2, y2)

    return objects
