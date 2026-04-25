# 시계 12개 위치 (인덱스 0 = 12시)
CLOCK_HOURS = ["12시", "1시", "2시", "3시", "4시", "5시",
               "6시",  "7시", "8시", "9시", "10시", "11시"]

# 카메라를 해당 방향으로 들었을 때 시계 인덱스 오프셋
CAMERA_OFFSET = {
    "front": 0,
    "right": 3,
    "back":  6,
    "left":  9,
}

# 시계 방향 → 사람이 실제로 쓰는 방향 표현
CLOCK_TO_DIRECTION = {
    "12시": "바로 앞",
    "1시":  "오른쪽 앞",
    "2시":  "오른쪽 앞",
    "3시":  "오른쪽",
    "4시":  "오른쪽",
    "5시":  "오른쪽",
    "6시":  "뒤",
    "7시":  "왼쪽",
    "8시":  "왼쪽",
    "9시":  "왼쪽",
    "10시": "왼쪽 앞",
    "11시": "왼쪽 앞",
}

# 방향별 회피 행동 (가까울 때만 사용)
CLOCK_ACTION = {
    "12시": "멈추세요",
    "1시":  "왼쪽으로 피해가세요",
    "2시":  "왼쪽으로 피해가세요",
    "3시":  "왼쪽으로 피해가세요",
    "4시":  "왼쪽으로 피해가세요",
    "5시":  "왼쪽으로 피해가세요",
    "6시":  "조심하세요",
    "7시":  "오른쪽으로 피해가세요",
    "8시":  "오른쪽으로 피해가세요",
    "9시":  "오른쪽으로 피해가세요",
    "10시": "오른쪽으로 피해가세요",
    "11시": "오른쪽으로 피해가세요",
}

CHANGE_TEMPLATES = {
    "added":   "{obj}이 {count}개 더 있어요.",
    "removed": "{obj}이 사라졌어요.",
}


def get_absolute_clock(image_clock: str, camera_orientation: str) -> str:
    offset = CAMERA_OFFSET.get(camera_orientation, 0)
    idx = CLOCK_HOURS.index(image_clock) if image_clock in CLOCK_HOURS else 0
    return CLOCK_HOURS[(idx + offset) % 12]
