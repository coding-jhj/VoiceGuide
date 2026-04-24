TEMPLATES = {
    # (direction, distance) → 문장 템플릿
    # direction: left / center / right
    # distance: 가까이 / 보통 / 멀리

    ("left",   "가까이"): "{obj}가 왼쪽 바로 앞에 있어요. 오른쪽으로 비켜보세요.",
    ("center", "가까이"): "{obj}가 정면 가까이에 있어요. 멈추세요.",
    ("right",  "가까이"): "{obj}가 오른쪽 바로 앞에 있어요. 왼쪽으로 비켜보세요.",

    ("left",   "보통"):   "{obj}가 왼쪽에 있어요.",
    ("center", "보통"):   "{obj}가 앞에 있어요. 조심하세요.",
    ("right",  "보통"):   "{obj}가 오른쪽에 있어요.",

    ("left",   "멀리"):   "{obj}가 왼쪽 멀리에 있어요.",
    ("center", "멀리"):   "{obj}가 멀리 앞에 있어요.",
    ("right",  "멀리"):   "{obj}가 오른쪽 멀리에 있어요.",
}

# 템플릿에 없는 조합용 폴백
FALLBACK_TEMPLATE = "{obj}가 {direction_ko} {distance}에 있어요."

DIRECTION_KO = {
    "left":   "왼쪽",
    "center": "앞",
    "right":  "오른쪽",
}

CHANGE_TEMPLATES = {
    "added":   "{obj}이 {count}개 더 있어요.",
    "removed": "{obj}이 사라졌어요.",
}
