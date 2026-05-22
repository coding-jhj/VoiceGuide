import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "train"))

from prepare_door_stairs_dataset import collect_external_hard_negatives, remap_yolo_label_text  # noqa: E402


def test_remap_yolo_label_text_replaces_only_class_column():
    text = "0 0.50000 0.40000 0.20000 0.30000\n0 0.1 0.2 0.3 0.4\n"

    remapped = remap_yolo_label_text(text, 80)

    assert remapped == "80 0.50000 0.40000 0.20000 0.30000\n80 0.1 0.2 0.3 0.4\n"


def test_remap_yolo_label_text_keeps_empty_negative_labels_empty():
    assert remap_yolo_label_text("", 81) == ""


def test_collect_external_hard_negatives_skips_excluded_top_level_folders(tmp_path):
    for rel in ["chair/a.jpg", "stairs/b.jpg", "door/c.jpg", "cell_phone/d.png"]:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake")

    items = collect_external_hard_negatives([tmp_path], {"stairs", "door"})

    assert [image.relative_to(tmp_path).as_posix() for image, class_id in items] == [
        "cell_phone/d.png",
        "chair/a.jpg",
    ]
    assert all(class_id is None for _, class_id in items)
