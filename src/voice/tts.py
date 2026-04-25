from gtts import gTTS
import os
import sys
import tempfile


def speak(text: str):
    """한국어 텍스트 → 음성 재생 (Windows/macOS/Linux 공통)"""
    tts = gTTS(text, lang="ko")
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        tmp_path = f.name
    tts.save(tmp_path)

    try:
        import pygame
        pygame.mixer.init()
        pygame.mixer.music.load(tmp_path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
        pygame.mixer.music.unload()
    finally:
        os.unlink(tmp_path)
