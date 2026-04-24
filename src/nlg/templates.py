# 시계 12개 위치 (인덱스 0 = 12시)
CLOCK_HOURS = ["12시", "1시", "2시", "3시", "4시", "5시",
               "6시",  "7시", "8시", "9시", "10시", "11시"]

# 카메라를 해당 방향으로 들었을 때 시계 인덱스 오프셋
# 예) right(3시 방향): 이미지 12시 → 절대 3시 (+3)
CAMERA_OFFSET = {
    "front": 0,
    "right": 3,
    "back":  6,
    "left":  9,
}

# 절대 시계 방향 → 회피 행동 지시
# 매우 가까이/가까이 거리일 때만 sentence.py에서 붙임
CLOCK_ACTION = {
    "8시":  "오른쪽으로 비켜주세요.",
    "9시":  "오른쪽으로 비켜주세요.",
    "10시": "오른쪽으로 비켜보세요.",
    "11시": "오른쪽으로 비켜보세요.",
    "12시": "멈추세요.",
    "1시":  "왼쪽으로 비켜보세요.",
    "2시":  "왼쪽으로 비켜보세요.",
    "3시":  "왼쪽으로 비켜주세요.",
    "4시":  "왼쪽으로 비켜주세요.",
    "6시":  "조심하세요.",
}

# 거리 레이블 → 문장 내 자연스러운 표현
DISTANCE_KO = {
    "매우 가까이": "매우 가까이",
    "가까이":      "가까이",
    "보통":        "적당한 거리",
    "멀리":        "멀리",
    "매우 멀리":   "매우 멀리",
}

CHANGE_TEMPLATES = {
    "added":   "{obj}이 {count}개 더 있어요.",
    "removed": "{obj}이 사라졌어요.",
}


def get_absolute_clock(image_clock: str, camera_orientation: str) -> str:
    """
    이미지 내 시계 방향 + 카메라 방향 오프셋 → 사용자 기준 절대 시계 방향
    예) image_clock="12시", camera_orientation="right" → "3시"
    """
    offset = CAMERA_OFFSET.get(camera_orientation, 0)
    idx = CLOCK_HOURS.index(image_clock) if image_clock in CLOCK_HOURS else 0
    return CLOCK_HOURS[(idx + offset) % 12]
