# Door/Stairs Fine-Tuning Workflow

VoiceGuide contest model must keep the original COCO 80 class ids and append new indoor classes only at the end.

```text
0..79: COCO classes, unchanged
80: stairs
81: door
```

Do not reorder COCO classes. Android, server policy, TFLite output parsing, and evaluation scripts all depend on this contract.

## Dataset Layout

Prepare manually reviewed images under:

```text
data/fine_tune/door_stairs/
  stairs/*.jpg + optional matching *.txt
  door/*.jpg + optional matching *.txt
  hard_negative/
    hanging_clothes/*.jpg
    mannequin/*.jpg
    person_poster/*.jpg
    mirror_reflection/*.jpg
    clothes_on_chair/*.jpg
    empty_door_frame/*.jpg
    stair_railing_only/*.jpg

data/fine_tune/coco_replay/
  person/*.jpg + *.txt
  chair/*.jpg + *.txt
  cell_phone/*.jpg + *.txt
  ...
```

Hard negatives are important for cases like clothes hanging on a rack being detected as `person`.
If the image contains no real object, create an empty `.txt` label file.
If a real COCO object is present, label only that real object.

## Build Dataset

```bash
python train/prepare_door_stairs_dataset.py
```

This creates:

```text
datasets/voiceguide82/
  images/train
  images/val
  labels/train
  labels/val
  voiceguide82.yaml
```

Fallback full-image labels are only for bootstrapping. Correct door/stairs boxes by hand before final training.

## Train

```bash
python train/finetune_voiceguide82.py --pretrained yolo11n.pt
```

The script starts from COCO-pretrained YOLO, freezes early layers for a short warmup, then fine-tunes with a small learning rate to reduce forgetting.

Output copy:

```text
models/voiceguide82_yolo11n.pt
```

## Evaluate Before Android Export

```bash
python tools/evaluate_yolo_extended.py --model models/voiceguide82_yolo11n.pt --images data/test_images
```

Check:

- `stairs` appears on stairs images.
- `door` appears on door images.
- `person` does not appear often on hanging-clothes/mannequin/poster hard negatives.
- COCO classes such as `person`, `chair`, and `cell phone` still work.

Only after this should the model be exported to TFLite and copied into Android assets.
