# import os
# import hashlib
# import requests
# import pygame

# _client_id     = os.environ.get("NAVER_CLIENT_ID", "")
# _client_secret = os.environ.get("NAVER_CLIENT_SECRET", "")
# _SPEAKER = "nara"   # 나라(여성·차분) | mijin(여성·밝음) | jinho(남성)

# _CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "__tts_cache__")
# os.makedirs(_CACHE_DIR, exist_ok=True)


# def _cache_path(text: str) -> str:
#     key = hashlib.md5(f"clova_{_SPEAKER}_{text}".encode("utf-8")).hexdigest()
#     return os.path.join(_CACHE_DIR, f"{key}.mp3")


# def _generate(text: str, path: str) -> bool:
#     """Clova Voice 생성, 키 없으면 gTTS 폴백."""
#     if _client_id and _client_secret:
#         try:
#             resp = requests.post(
#                 "https://naveropenapi.apigw.ntruss.com/tts-premium/v1/tts",
#                 headers={
#                     "X-NCP-APIGW-API-KEY-ID": _client_id,
#                     "X-NCP-APIGW-API-KEY":    _client_secret,
#                     "Content-Type": "application/x-www-form-urlencoded",
#                 },
#                 data={"speaker": _SPEAKER, "volume": 0, "speed": 0,
#                       "pitch": 0, "format": "mp3", "text": text},
#                 timeout=10,
#             )
#             if resp.ok:
#                 with open(path, "wb") as f:
#                     f.write(resp.content)
#                 return True
#             print(f"[TTS] Clova 오류 {resp.status_code}: {resp.text[:80]}")
#         except Exception as e:
#             print(f"[TTS] Clova 요청 실패: {e}")

#     # gTTS 폴백
#     try:
#         from gtts import gTTS
#         gTTS(text, lang="ko").save(path)
#         return True
#     except Exception as e:
#         print(f"[TTS] gTTS 오류: {e}")
#         return False


# def speak(text: str):
#     path = _cache_path(text)
#     if not os.path.exists(path):
#         if not _generate(text, path):
#             return
#     try:
#         pygame.mixer.init()
#         pygame.mixer.music.load(path)
#         pygame.mixer.music.play()
#         while pygame.mixer.music.get_busy():
#             pygame.time.Clock().tick(10)
#         pygame.mixer.music.unload()
#     except Exception as e:
#         print(f"[TTS] 재생 오류: {e}")


# def warmup_cache():
#     pass

from dotenv import load_dotenv
import os
import hashlib
import pygame
from elevenlabs.client import ElevenLabs


load_dotenv()

_api_key = os.getenv("ELEVENLABS_API_KEY")
client = ElevenLabs(api_key=_api_key)

_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "__tts_cache__")
os.makedirs(_CACHE_DIR, exist_ok=True)

def _cache_path(text: str) -> str:
    key = hashlib.md5(f"eleven_{text}".encode("utf-8")).hexdigest()
    return os.path.join(_CACHE_DIR, f"{key}.mp3")

def speak(text: str):
    path = _cache_path(text)
    
    if not os.path.exists(path):
        try:
            print(f"ElevenLabs 생성 중: {text}")
            
            audio_generator = client.text_to_speech.convert(
                text=text,
                voice_id="JBFqnCBsd6RMkjVDRZzb", # 기본모델
                model_id="eleven_multilingual_v2",
                output_format="mp3_44100_128",
            )
            
            with open(path, "wb") as f:
                for chunk in audio_generator:
                    if chunk:
                        f.write(chunk)
                        
        except Exception as e:
            print(f"ElevenLabs 오류 발생: {e}")
            return

    # 재생 로직 (기존과 동일)
    try:
        pygame.mixer.init()
        pygame.mixer.music.load(path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
        pygame.mixer.music.unload()
    except Exception as e:
        print(f"재생 오류 발생: {e}")

if __name__ == "__main__":
    speak("왼쪽 앞에 의자가 있어요. 오른쪽으로 피해가세요")