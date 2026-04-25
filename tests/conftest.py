import pytest
import cv2
import numpy as np


@pytest.fixture(scope="session")
def sample_image_bytes() -> bytes:
    """640×480 더미 컬러 이미지 (JPEG bytes)."""
    img = np.random.randint(80, 200, (480, 640, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", img)
    return buf.tobytes()


@pytest.fixture(scope="session")
def sample_jpeg_bytes(sample_image_bytes) -> bytes:
    return sample_image_bytes
