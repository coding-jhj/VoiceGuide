"""
라이브러리 import 체크 — 서버 없이 실행 가능 (CI용)

핵심 라이브러리: 항상 실행 (pytest)
데모 라이브러리: pytest -m demo 로만 실행 (없어도 서버는 동작)
"""
import importlib
import pytest

# 서버 동작에 반드시 필요한 핵심 라이브러리
CORE_LIBS = ["cv2", "ultralytics", "gtts", "torch", "numpy", "fastapi"]

# Gradio 데모/오디오 재생용 — 없어도 API 서버는 정상 동작
DEMO_LIBS = ["gradio", "pygame"]


@pytest.mark.parametrize("lib", CORE_LIBS)
def test_core_import(lib):
    """핵심 서버 라이브러리 import 확인 — CI에서 항상 실행"""
    mod = importlib.import_module(lib)
    assert mod is not None


@pytest.mark.demo
@pytest.mark.parametrize("lib", DEMO_LIBS)
def test_demo_import(lib):
    """데모 전용 라이브러리 — pytest -m demo 로 별도 실행"""
    mod = importlib.import_module(lib)
    assert mod is not None
