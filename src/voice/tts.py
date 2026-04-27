import os
import hashlib
import requests
import pygame

_api_key  = os.environ.get("ELEVENLABS_API_KEY", "")
_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"   # Rachel (무료 플랜 지원, 한국어 가능)
_MODEL_ID = "eleven_multilingual_v2"

_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "__tts_cache__")
os.makedirs(_CACHE_DIR, exist_ok=True)


def _cache_path(text: str) -> str:
    key = hashlib.md5(f"eleven_{text}".encode("utf-8")).hexdigest()
    return os.path.join(_CACHE_DIR, f"{key}.mp3")


def _generate(text: str, path: str) -> bool:
    """ElevenLabs REST API로 음성 생성. SDK 없이 직접 HTTP 호출."""
    if not _api_key:
        return False
    try:
        resp = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{_VOICE_ID}",
            headers={"xi-api-key": _api_key, "Content-Type": "application/json"},
            json={"text": text, "model_id": _MODEL_ID},
            timeout=15,
        )
        if resp.ok:
            with open(path, "wb") as f:
                f.write(resp.content)
            return True
        print(f"[TTS] ElevenLabs 오류 {resp.status_code}: {resp.text[:100]}")
    except Exception as e:
        print(f"[TTS] 요청 실패: {e}")
    return False


def speak(text: str):
    """ElevenLabs TTS로 음성 재생. 캐시 있으면 즉시 재생."""
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
    """서버 시작 시 자주 쓰는 문장 미리 생성."""
    if not _api_key:
        return
    phrases = [
        "주변에 장애물이 없어요.",
        "바로 앞에 계단이 있어요. 멈추세요.",
        "바로 앞에 사람이 있어요.",
        "분석이 중단됐어요. 주의해서 이동하세요.",
    ]
    for phrase in phrases:
        path = _cache_path(phrase)
        if not os.path.exists(path):
            _generate(phrase, path)
