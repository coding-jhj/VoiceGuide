import speech_recognition as sr

KEYWORDS = {
    "장애물": ["앞에 뭐 있어", "주변 알려줘", "뭐 있어"],
    "찾기":   ["찾아줘", "어디있어", "어디 있어"],
    "확인":   ["이거 뭐야", "이게 뭐야", "뭐야"],
}


def listen_and_classify() -> tuple[str, str]:
    """
    Returns: (원문 텍스트, 모드명)
    모드: "장애물" / "찾기" / "확인" / "unknown"
    """
    r = sr.Recognizer()
    with sr.Microphone() as source:
        r.adjust_for_ambient_noise(source, duration=0.5)
        audio = r.listen(source, timeout=5)

    try:
        text = r.recognize_google(audio, language="ko-KR")
    except sr.UnknownValueError:
        return "", "unknown"

    for mode, keywords in KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return text, mode

    return text, "unknown"
