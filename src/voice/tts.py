from gtts import gTTS
import os
import tempfile


def speak(text: str):
    """한국어 텍스트 → 음성 재생"""
    tts = gTTS(text, lang="ko")
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        tts.save(f.name)
        os.system(f"afplay {f.name}")    # macOS
        # os.system(f"mpg321 {f.name}") # Linux
