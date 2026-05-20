import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "train"))

from voiceguide_labels import (  # noqa: E402
    COCO80_NAMES,
    DOOR_CLASS_ID,
    STAIRS_CLASS_ID,
    VOICEGUIDE82_NAMES,
    assert_voiceguide82_contract,
    yolo_data_yaml,
)


def test_voiceguide82_appends_classes_without_reordering_coco():
    assert_voiceguide82_contract()
    assert len(COCO80_NAMES) == 80
    assert VOICEGUIDE82_NAMES[:80] == COCO80_NAMES
    assert STAIRS_CLASS_ID == 80
    assert DOOR_CLASS_ID == 81
    assert VOICEGUIDE82_NAMES[80] == "stairs"
    assert VOICEGUIDE82_NAMES[81] == "door"


def test_voiceguide82_yaml_declares_82_classes():
    yaml = yolo_data_yaml("/tmp/voiceguide82")
    assert "nc: 82" in yaml
    assert "  80: stairs" in yaml
    assert "  81: door" in yaml
