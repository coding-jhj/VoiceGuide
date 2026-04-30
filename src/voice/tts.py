"""
VoiceGuide TTS 모듈 (서버 / Gradio 데모용)
==========================================
Android 앱은 Android TextToSpeech(OS TTS)를 사용하며 이 파일은 서버 데모 전용.

TTS 속도 기준:
  - 긴급(critical): 빠르게 (안드로이드 setSpeechRate(1.25f))
  - 일반(info):     보통 (setSpeechRate(1.1f))
  - 같은 문장 3~5초 이내 반복 없음 (CLASS_COOLDOWN_MS = 5000)
"""
from dotenv import load_dotenv
import os
import hashlib
import pygame

load_dotenv()

_api_key  = os.getenv("ELEVENLABS_API_KEY", "")
_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"   # George (다국어 지원)
_MODEL_ID = "eleven_multilingual_v2"

# 같은 문장 억제 시간 (초) — 중복 발화 방지
_REPEAT_COOLDOWN_SECS = 4.0
_last_spoken: dict[str, float] = {}

_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "__tts_cache__")
os.makedirs(_CACHE_DIR, exist_ok=True)


def _cache_path(text: str) -> str:
    prefix = "eleven" if _api_key else "gtts"
    key = hashlib.md5(f"{prefix}_{text}".encode("utf-8")).hexdigest()
    return os.path.join(_CACHE_DIR, f"{key}.mp3")


def _generate(text: str, path: str) -> bool:
    """ElevenLabs 생성, API 키 없거나 실패하면 gTTS 폴백."""
    if _api_key:
        try:
            from elevenlabs.client import ElevenLabs
            client = ElevenLabs(api_key=_api_key)
            audio_generator = client.text_to_speech.convert(
                text=text,
                voice_id=_VOICE_ID,
                model_id=_MODEL_ID,
                output_format="mp3_44100_128",
            )
            with open(path, "wb") as f:
                for chunk in audio_generator:
                    if chunk:
                        f.write(chunk)
            return True
        except Exception as e:
            print(f"[TTS] ElevenLabs 오류, gTTS 폴백: {e}")

    # gTTS 폴백
    try:
        from gtts import gTTS
        gTTS(text, lang="ko").save(path)
        return True
    except Exception as e:
        print(f"[TTS] gTTS 오류: {e}")
        return False


def speak(text: str):
    import time
    # 같은 문장 반복 억제
    now = time.monotonic()
    if text in _last_spoken and (now - _last_spoken[text]) < _REPEAT_COOLDOWN_SECS:
        return
    _last_spoken[text] = now

    path = _cache_path(text)
    if not os.path.exists(path):
        if not _generate(text, path):
            return
    try:
        pygame.mixer.init()
        pygame.mixer.music.load(path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
        pygame.mixer.music.unload()
    except Exception as e:
        print(f"[TTS] 재생 오류: {e}")


def warmup_cache():
    """서버 시작 시 자주 쓰는 문장 미리 캐싱 — 첫 요청 지연 방지."""
    pass
