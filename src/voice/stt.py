import speech_recognition as sr

# ── 모드별 키워드 ─────────────────────────────────────────────────────────────
# 인식된 텍스트에 아래 키워드가 포함되면 해당 모드로 분류

KEYWORDS: dict[str, list[str]] = {
    # 장애물 감지 모드 — 가장 자주 쓰이는 기본 모드
    "장애물": [
        "앞에 뭐 있어", "뭐 있어", "주변 알려줘", "주변 알려",
        "뭐가 있어", "주변", "장애물", "앞에",
        "어떤 게 있어", "보여줘", "뭐가 보여", "어떤 게 보여",
        "분석해줘", "스캔해줘", "살펴봐줘",
        "어디 있는지 알려줘", "주변 상황", "현재 상황",
        "길 어때", "앞이 어때", "앞 어때",
    ],
    # 특정 물건 찾기 모드
    "찾기": [
        "찾아줘", "어디있어", "어디 있어", "어디야", "찾아",
        "어딘지", "위치", "어디에 있어", "어디에 있나",
        "어디로 가", "길 알려줘", "가는 길",
        "보이는지 알려줘", "있는지 알려줘",
    ],
    # 특정 물체 확인 모드
    "확인": [
        "이거 뭐야", "이게 뭐야", "이건 뭐야",
        "뭔데", "이거", "이게", "뭔지", "뭐지",
        "이게 뭐", "이거 뭐", "이게 뭔지",
        "이게 뭔가", "이게 무엇", "이게 무슨",
    ],
    # 현재 위치 저장 모드
    "저장": [
        "여기 저장", "저장해줘", "여기 기억해", "기억해줘",
        "저장해", "여기야", "여기 등록", "등록해줘",
        "여기 표시", "마킹해줘", "위치 저장", "이 곳 저장",
        "여기 이름", "여기 이름 붙여줘",
    ],
    # 저장된 장소 목록/찾기 모드
    "위치목록": [
        "저장된 곳", "기억한 곳", "등록된 곳",
        "저장된 장소", "내 장소", "장소 목록", "저장 목록",
        "어디 저장했어", "기억한 장소", "저장한 곳 알려줘",
        "저장된 곳 알려줘", "내가 저장한 곳",
    ],
}

# 어느 모드에도 해당 안 되면 → 가장 기본 모드로 fallback
_DEFAULT_MODE = "장애물"


def _classify(text: str) -> str:
    """텍스트에서 모드 분류. 매칭 없으면 _DEFAULT_MODE 반환."""
    for mode, keywords in KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return mode
    return _DEFAULT_MODE


def extract_label(text: str) -> str:
    """
    "여기 저장해줘 편의점" → "편의점" 처럼 저장 명령어에서 장소 이름 추출.
    명령어 제거 후 남은 텍스트를 장소 이름으로 반환.
    """
    remove_patterns = [
        "여기 저장해줘", "저장해줘", "여기 기억해줘", "기억해줘",
        "여기 저장", "저장해", "여기야", "여기 등록해줘", "등록해줘",
        "여기 표시해줘", "마킹해줘", "위치 저장", "이 곳 저장",
        "여기 이름 붙여줘",
    ]
    label = text
    for pat in remove_patterns:
        label = label.replace(pat, "")
    label = label.strip()
    return label or ""


def listen_and_classify() -> tuple[str, str]:
    """
    마이크로 음성을 인식하고 모드를 분류.

    Returns:
        (원문 텍스트, 모드명)
        모드: "장애물" / "찾기" / "확인" / "저장" / "위치목록"
        인식 실패 시: ("", "unknown")
    """
    r = sr.Recognizer()
    with sr.Microphone() as source:
        r.adjust_for_ambient_noise(source, duration=0.5)
        audio = r.listen(source, timeout=5)

    try:
        text = r.recognize_google(audio, language="ko-KR")
    except sr.UnknownValueError:
        return "", "unknown"
    except sr.RequestError:
        return "", "unknown"

    mode = _classify(text)
    return text, mode
