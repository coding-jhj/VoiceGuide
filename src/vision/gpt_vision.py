"""
VoiceGuide GPT Vision 모듈
============================
GPT-4o Vision API를 사용해 카메라 이미지를 자연어로 분석합니다.

사용 사례:
  - 옷 색상 매칭 조언 ("이 옷이랑 어울려?")
  - 옷 패턴 설명 ("체크무늬야, 줄무늬야?")
  - YOLO가 못 하는 세밀한 시각 판단

API 키 설정:
  .env 파일에 OPENAI_API_KEY=sk-... 추가
  또는 환경변수로 설정
"""

import os
import base64
import json


def _encode_image(image_bytes: bytes) -> str:
    """이미지 바이트 → base64 문자열 변환 (GPT Vision API 요구 포맷)."""
    return base64.b64encode(image_bytes).decode("utf-8")


def analyze_clothing(image_bytes: bytes, request_type: str) -> str:
    """
    옷 관련 질문을 GPT-4o Vision으로 분석.

    request_type:
      "matching" → 두 가지 색상/패턴이 어울리는지 조언
      "pattern"  → 옷의 패턴(체크/줄무늬/단색 등) 설명

    Returns:
      시각장애인이 바로 이해할 수 있는 한국어 안내 문장
    """
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return "옷 분석 기능을 사용하려면 서버에 OPENAI_API_KEY를 설정해 주세요."

    try:
        import urllib.request
        import urllib.error

        if request_type == "matching":
            prompt = (
                "이 사진에 있는 옷들의 색상과 패턴을 보고, "
                "서로 잘 어울리는지 시각장애인에게 간단하게 알려주세요. "
                "한국어로, 두 문장 이내로, '~어요' 어체로 말해주세요."
            )
        else:
            prompt = (
                "이 사진에 있는 옷의 패턴을 설명해주세요 "
                "(체크무늬, 줄무늬, 단색, 꽃무늬 등). "
                "한국어로, 한 문장으로, '~어요' 어체로 말해주세요."
            )

        payload = json.dumps({
            "model": "gpt-4o",
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/jpeg;base64,{_encode_image(image_bytes)}",
                        "detail": "low"   # 비용 절약: low = 85 token
                    }}
                ]
            }],
            "max_tokens": 100
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"].strip()

    except urllib.error.HTTPError as e:
        if e.code == 401:
            return "API 키가 올바르지 않아요. 서버 설정을 확인해 주세요."
        return "옷 분석 중 오류가 발생했어요."
    except Exception:
        return "옷 분석에 실패했어요. 인터넷 연결을 확인해 주세요."
