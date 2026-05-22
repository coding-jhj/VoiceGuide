import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_coco_pseudo_replay import PseudoLabel, iter_images  # noqa: E402


def test_iter_images_excludes_door_and_stairs(tmp_path):
    for rel in ["person/a.jpg", "stairs/b.jpg", "door/c.jpg", "chair/d.png"]:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake")

    images = iter_images(tmp_path, {"stairs", "door"})

    assert [image.relative_to(tmp_path).as_posix() for image in images] == [
        "chair/d.png",
        "person/a.jpg",
    ]


def test_pseudo_label_formats_yolo_without_confidence_column():
    label = PseudoLabel(
        class_id=56,
        x_center=0.5,
        y_center=0.25,
        width=0.125,
        height=0.75,
        confidence=0.91,
    )

    assert label.yolo_line() == "56 0.500000 0.250000 0.125000 0.750000"
