import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "train"))

from finetune_voiceguide82 import finetune_train_kwargs, warmup_train_kwargs  # noqa: E402


def _args() -> argparse.Namespace:
    return argparse.Namespace(
        data="datasets/voiceguide82/voiceguide82.yaml",
        epochs=60,
        warmup_epochs=8,
        patience=12,
        imgsz=640,
        batch=12,
        workers=4,
        device="0",
        optimizer="AdamW",
        project="runs/train",
        name="voiceguide82_yolo11n",
    )


def test_warmup_train_kwargs_pin_optimizer_so_lr0_is_honored():
    kwargs = warmup_train_kwargs(_args(), "voiceguide82_yolo11n_warmup")

    assert kwargs["optimizer"] == "AdamW"
    assert kwargs["lr0"] == 1e-3
    assert kwargs["patience"] == 8
    assert kwargs["freeze"] == 10


def test_finetune_train_kwargs_pin_small_learning_rate():
    kwargs = finetune_train_kwargs(_args())

    assert kwargs["optimizer"] == "AdamW"
    assert kwargs["lr0"] == 7e-5
    assert kwargs["patience"] == 12
    assert kwargs["freeze"] == 0
