from __future__ import annotations

COCO80_NAMES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck",
    "boat", "traffic light", "fire hydrant", "stop sign", "parking meter", "bench",
    "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe",
    "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard",
    "sports ball", "kite", "baseball bat", "baseball glove", "skateboard", "surfboard",
    "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl",
    "banana", "apple", "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza",
    "donut", "cake", "chair", "couch", "potted plant", "bed", "dining table", "toilet",
    "tv", "laptop", "mouse", "remote", "keyboard", "cell phone", "microwave", "oven",
    "toaster", "sink", "refrigerator", "book", "clock", "vase", "scissors", "teddy bear",
    "hair drier", "toothbrush",
]

STAIRS_CLASS_ID = 80
DOOR_CLASS_ID = 81
VOICEGUIDE82_NAMES = COCO80_NAMES + ["stairs", "door"]

NEGATIVE_TAGS = [
    "hanging_clothes",
    "mannequin",
    "person_poster",
    "mirror_reflection",
    "clothes_on_chair",
    "empty_door_frame",
    "stair_railing_only",
    "stair_like_floor",
    "stair_like_floor_320",
]


def assert_voiceguide82_contract() -> None:
    if len(COCO80_NAMES) != 80:
        raise AssertionError(f"COCO80 must contain 80 names, got {len(COCO80_NAMES)}")
    if VOICEGUIDE82_NAMES[:80] != COCO80_NAMES:
        raise AssertionError("COCO class order changed; keep ids 0..79 untouched")
    if VOICEGUIDE82_NAMES[STAIRS_CLASS_ID] != "stairs":
        raise AssertionError("class 80 must be stairs")
    if VOICEGUIDE82_NAMES[DOOR_CLASS_ID] != "door":
        raise AssertionError("class 81 must be door")


def yolo_data_yaml(dataset_path: str) -> str:
    assert_voiceguide82_contract()
    names = "\n".join(f"  {i}: {name}" for i, name in enumerate(VOICEGUIDE82_NAMES))
    return (
        f"path: {dataset_path}\n"
        "train: images/train\n"
        "val: images/val\n\n"
        f"nc: {len(VOICEGUIDE82_NAMES)}\n"
        "names:\n"
        f"{names}\n"
    )
