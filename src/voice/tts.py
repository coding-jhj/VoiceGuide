import os
import hashlib
import requests
import pygame

_client_id     = os.environ.get("NAVER_CLIENT_ID", "")
_client_secret = os.environ.get("NAVER_CLIENT_SECRET", "")
_SPEAKER = "nara"   # 나라(여성·차분) | mijin(여성·밝음) | jinho(남성)

_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "__tts_cache__")
os.makedirs(_CACHE_DIR, exist_ok=True)


def _cache_path(text: str) -> str:
    key = hashlib.md5(f"clova_{_SPEAKER}_{text}".encode("utf-8")).hexdigest()
    return os.path.join(_CACHE_DIR, f"{key}.mp3")


def _generate(text: str, path: str) -> bool:
    """Clova Voice 생성, 키 없으면 gTTS 폴백."""
    if _client_id and _client_secret:
        try:
            resp = requests.post(
                "https://naveropenapi.apigw.ntruss.com/tts-premium/v1/tts",
                headers={
                    "X-NCP-APIGW-API-KEY-ID": _client_id,
                    "X-NCP-APIGW-API-KEY":    _client_secret,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={"speaker": _SPEAKER, "volume": 0, "speed": 0,
                      "pitch": 0, "format": "mp3", "text": text},
                timeout=10,
            )
            if resp.ok:
                with open(path, "wb") as f:
                    f.write(resp.content)
                return True
            print(f"[TTS] Clova 오류 {resp.status_code}: {resp.text[:80]}")
        except Exception as e:
            print(f"[TTS] Clova 요청 실패: {e}")

    # gTTS 폴백
    try:
        from gtts import gTTS
        gTTS(text, lang="ko").save(path)
        return True
    except Exception as e:
        print(f"[TTS] gTTS 오류: {e}")
        return False


def speak(text: str):
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
    pass
