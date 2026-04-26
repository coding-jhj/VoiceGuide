"""라이브러리 import 빠른 체크 (CI 용)"""
import importlib
import pytest

REQUIRED_LIBS = ["gradio", "cv2", "ultralytics", "gtts", "pygame", "torch", "numpy"]


@pytest.mark.parametrize("lib", REQUIRED_LIBS)
def test_import(lib):
    mod = importlib.import_module(lib)
    assert mod is not None
