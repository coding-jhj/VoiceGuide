from gtts import gTTS
import os
import hashlib
import pygame

_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "__tts_cache__")
os.makedirs(_CACHE_DIR, exist_ok=True)


def _cache_path(text: str) -> str:
    key = hashlib.md5(text.encode("utf-8")).hexdigest()
    return os.path.join(_CACHE_DIR, f"{key}.mp3")


def speak(text: str):
    """한국어 텍스트 → 음성 재생. 동일 문장은 캐시에서 즉시 재생 (네트워크 불필요)."""
    path = _cache_path(text)
    if not os.path.exists(path):
        tts = gTTS(text, lang="ko")
        tts.save(path)

    pygame.mixer.init()
    pygame.mixer.music.load(path)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        pygame.time.Clock().tick(10)
    pygame.mixer.music.unload()
