# from gtts import gTTS
# import os
# import hashlib
# import pygame

# _CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "__tts_cache__")
# os.makedirs(_CACHE_DIR, exist_ok=True)


# def _cache_path(text: str) -> str:
#     key = hashlib.md5(text.encode("utf-8")).hexdigest()
#     return os.path.join(_CACHE_DIR, f"{key}.mp3")


# def speak(text: str):
#     """한국어 텍스트 → 음성 재생. 동일 문장은 캐시에서 즉시 재생 (네트워크 불필요)."""
#     path = _cache_path(text)
#     if not os.path.exists(path):
#         tts = gTTS(text, lang="ko")
#         tts.save(path)

#     pygame.mixer.init()
#     pygame.mixer.music.load(path)
#     pygame.mixer.music.play()
#     while pygame.mixer.music.get_busy():
#         pygame.time.Clock().tick(10)
#     pygame.mixer.music.unload()

# 기존 gtts 코드는 만일을 대비해 주석처리

import os
import hashlib
import pygame
from elevenlabs.client import ElevenLabs

_api_key = os.environ.get("ELEVENLABS_API_KEY", "")
client = ElevenLabs(api_key=_api_key)

_VOICE_ID  = "uyVNoMrnUku1dZyVEXwD"       # Anna Kim (한국어)
_MODEL_ID  = "eleven_multilingual_v2"

_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "__tts_cache__")
os.makedirs(_CACHE_DIR, exist_ok=True)

def _cache_path(text: str) -> str:
    key = hashlib.md5(f"eleven_{text}".encode("utf-8")).hexdigest()
    return os.path.join(_CACHE_DIR, f"{key}.mp3")

def speak(text: str):
    """ElevenLabs TTS로 한국어 음성 재생. 동일 문장은 캐시에서 즉시 재생."""
    path = _cache_path(text)

    if not os.path.exists(path):
        try:
            print(f"[TTS] 생성 중: {text}")
            audio = client.text_to_speech.convert(
                voice_id=_VOICE_ID,
                text=text,
                model_id=_MODEL_ID,
            )
            with open(path, "wb") as f:
                for chunk in audio:
                    f.write(chunk)
        except Exception as e:
            print(f"[TTS] ElevenLabs 오류: {e}")
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

# 서버 시작 시 미리 캐시할 자주 쓰는 문장
_WARMUP_PHRASES = [
    "주변에 장애물이 없어요.",
    "위험! 바로 앞 계단이에요. 기다리세요.",
    "조심하세요. 앞에 낙차가 있어요.",
    "바로 앞에 사람이 있어요. 바로 코앞. 기다리세요.",
    "오른쪽에 의자가 있어요. 가까이. 왼쪽으로 피하세요.",
    "왼쪽에 의자가 있어요. 가까이. 오른쪽으로 피하세요.",
    "위험! 바로 앞 자동차가 있어요!",
    "조심! 오른쪽에 자동차가 접근 중이에요.",
    "분석이 중단됐어요. 주의해서 이동하세요.",
    "음성 안내를 시작할까요? 네 또는 아니오로 말씀해주세요.",
]

def warmup_cache():
    """서버 시작 시 자주 쓰는 문장을 미리 생성해 캐시 — 첫 요청 지연 방지."""
    if not _api_key:
        return
    for phrase in _WARMUP_PHRASES:
        path = _cache_path(phrase)
        if not os.path.exists(path):
            try:
                audio = client.text_to_speech.convert(
                    voice_id=_VOICE_ID, text=phrase, model_id=_MODEL_ID)
                with open(path, "wb") as f:
                    for chunk in audio:
                        f.write(chunk)
                print(f"[TTS] 캐시 완료: {phrase[:20]}...")
            except Exception as e:
                print(f"[TTS] 캐시 실패: {e}")
                return  # API 키 오류 등 → 이후 시도 중단


# 테스트 실행
if __name__ == "__main__":
    speak("왼쪽 앞에 의자가 있어요. 오른쪽으로 피하세요")
