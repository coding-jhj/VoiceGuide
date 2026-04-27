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
from elevenlabs import save

_api_key = os.environ.get("ELEVENLABS_API_KEY", "")
client = ElevenLabs(api_key=_api_key)

_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "__tts_cache__")
os.makedirs(_CACHE_DIR, exist_ok=True)

def _cache_path(text: str) -> str:
    key = hashlib.md5(f"eleven_{text}".encode("utf-8")).hexdigest()
    return os.path.join(_CACHE_DIR, f"{key}.mp3")

def speak(text: str):
    """ElevenLabs TTS를 사용하여 한국어 음성 재생. 캐싱 로직 포함."""
    path = _cache_path(text)
    
    if not os.path.exists(path):
        try:
            print(f"ElevenLabs 생성 중: {text}")
            audio = client.generate(
                text=text,
                voice="uyVNoMrnUku1dZyVEXwD",  # 원하는 Voice ID 또는 이름 (예: Adam, Bella) 현재는 anna kim으로 설정
                model="eleven_multilingual_v2"  # 한국어 지원 모델
            )
            save(audio, path)
        except Exception as e:
            print(f"ElevenLabs 오류 발생: {e}")
            # 만약 ElevenLabs 실패 시 백업으로 기존 gTTS를 쓰게 하려면 여기에 로직을 추가할 수 있습니다.
            return
    try:
        pygame.mixer.init()
        pygame.mixer.music.load(path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
        pygame.mixer.music.unload()
    except Exception as e:
        print(f"재생 오류 발생: {e}")

# 테스트 실행
if __name__ == "__main__":
    speak("왼쪽 앞에 의자가 있어요. 오른쪽으로 피해가세요")
