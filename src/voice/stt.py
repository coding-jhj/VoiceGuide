"""
VoiceGuide STT(음성 인식) 모듈 — 서버용 PC 마이크 버전
=========================================================
Android 앱은 SpeechRecognizer(내장)를 직접 쓰고,
이 파일은 Gradio 데모 / PC 테스트용으로만 사용됩니다.

실제 시각장애인이 쓰는 경로:
  Android SpeechRecognizer → handleSttResult() → classifyKeyword()
  (VoiceGuideConstants.kt의 STT_KEYWORDS 기준)

이 파일:
  PC 마이크 → Google Speech API → _classify() → 모드 반환
  (KEYWORDS 기준 — Android와 동일한 키워드)
"""

import speech_recognition as sr

# ── 모드별 키워드 ─────────────────────────────────────────────────────────────
# 인식된 텍스트에 이 키워드가 포함되면 해당 모드로 분류됨
# any(kw in text for kw in keywords) → 하나라도 포함되면 해당 모드
KEYWORDS: dict[str, list[str]] = {

    # 질문 모드 — 사용자가 직접 "지금 뭐가 있어?" 물어볼 때 즉시 응답
    # 장애물 모드와 다른 점: 즉시 캡처 + tracker 누적 상태까지 합쳐서 응답
    "질문": [
        "지금 뭐가 있어", "지금 뭐 있어", "지금 어때",
        "현재 상황 알려줘", "지금 주변 알려줘",
        "뭐가 보여", "지금 뭐야", "상황 설명해줘",
        "지금 알려줘", "어떤 게 있어", "현재 어때",
        "지금 상황", "뭐가 있는지", "주변에 뭐가",
    ],

    # 장애물 모드 — 자동 분석 모드. 주기적 캡처 결과 안내
    "장애물": [
        "앞에 뭐 있어", "뭐 있어", "주변 알려줘", "주변 알려",
        "뭐가 있어", "주변", "장애물", "앞에",
        "어떤 게 있어", "보여줘", "어떤 게 보여",
        "분석해줘", "스캔해줘", "살펴봐줘",
        "어디 있는지 알려줘", "주변 상황", "현재 상황",
        "길 어때", "앞이 어때", "앞 어때",
    ],

    # 찾기 모드 — "의자 찾아줘" → 의자 방향/거리 안내
    "찾기": [
        "찾아줘", "어디있어", "어디 있어", "어디야", "찾아",
        "어딘지", "위치", "어디에 있어", "어디에 있나",
        "어디로 가", "길 알려줘", "가는 길",
        "보이는지 알려줘", "있는지 알려줘",
    ],

    # 확인 모드 — "이거 뭐야" → 카메라 정면 물체 설명
    "확인": [
        "이거 뭐야", "이게 뭐야", "이건 뭐야",
        "뭔데", "이거", "이게", "뭔지", "뭐지",
        "이게 뭐", "이거 뭐", "이게 뭔지",
        "이게 뭔가", "이게 무엇", "이게 무슨",
    ],

    # 저장 모드 — "여기 저장해줘 편의점" → WiFi SSID + 이름 저장
    "저장": [
        "여기 저장", "저장해줘", "여기 기억해", "기억해줘",
        "저장해", "여기야", "여기 등록", "등록해줘",
        "여기 표시", "마킹해줘", "위치 저장", "이 곳 저장",
        "여기 이름", "여기 이름 붙여줘",
    ],

    # 위치목록 모드 — "저장된 곳 알려줘" → 저장 장소 목록 읽어줌
    "위치목록": [
        "저장된 곳", "기억한 곳", "등록된 곳",
        "저장된 장소", "내 장소", "장소 목록", "저장 목록",
        "어디 저장했어", "기억한 장소", "저장한 곳 알려줘",
        "저장된 곳 알려줘", "내가 저장한 곳",
    ],
}

# 어떤 키워드에도 안 걸리면 기본 장애물 모드로 fallback
# → "배고파" 같은 엉뚱한 말을 해도 안내가 멈추지 않음
_DEFAULT_MODE = "장애물"


def _classify(text: str) -> str:
    """
    인식된 텍스트에서 모드를 분류.
    순서: 장애물 → 찾기 → 확인 → 저장 → 위치목록
    (먼저 매칭되는 모드로 결정 — 키워드 중복 방지 설계)
    """
    for mode, keywords in KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return mode
    return _DEFAULT_MODE  # 미매칭 시 장애물 모드


def extract_label(text: str) -> str:
    """
    저장 명령어에서 장소 이름만 추출.
    예) "여기 저장해줘 편의점" → "편의점"
    예) "기억해줘 화장실"      → "화장실"

    명령어 패턴을 순서대로 제거하고 남은 텍스트가 장소 이름.
    """
    remove_patterns = [
        "여기 저장해줘", "저장해줘", "여기 기억해줘", "기억해줘",
        "여기 저장", "저장해", "여기야", "여기 등록해줘", "등록해줘",
        "여기 표시해줘", "마킹해줘", "위치 저장", "이 곳 저장",
        "여기 이름 붙여줘",
    ]
    label = text
    for pat in remove_patterns:
        label = label.replace(pat, "")  # 명령어 제거
    return label.strip()  # 앞뒤 공백 제거 후 반환


def listen_and_classify() -> tuple[str, str]:
    """
    PC 마이크로 음성을 1회 녹음하고 모드를 분류.
    Gradio 데모의 /stt 엔드포인트에서 호출됨.

    Returns:
        (인식된 텍스트, 모드명)
        인식 실패: ("", "unknown")
    """
    r = sr.Recognizer()
    with sr.Microphone() as source:
        # 주변 소음 수준을 0.5초 동안 측정해서 민감도 자동 조정
        r.adjust_for_ambient_noise(source, duration=0.5)
        # timeout=5: 5초 안에 말 안 하면 포기
        audio = r.listen(source, timeout=5)

    try:
        # Google Speech-to-Text API 호출 (인터넷 필요)
        # Android는 이 대신 SpeechRecognizer 내장 API 사용
        text = r.recognize_google(audio, language="ko-KR")
    except sr.UnknownValueError:
        # 말소리를 인식했지만 텍스트로 변환 불가 (너무 조용하거나 소음)
        return "", "unknown"
    except sr.RequestError:
        # API 서버 연결 실패
        return "", "unknown"

    mode = _classify(text)
    return text, mode
