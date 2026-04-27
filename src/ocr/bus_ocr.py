"""
VoiceGuide 버스 번호 OCR 모듈
================================
EasyOCR을 사용해 버스 번호판의 숫자를 인식합니다.

ML Kit(Android)보다 EasyOCR이 더 좋은 이유:
  - 더 다양한 각도·조명 조건에서 인식
  - 번호판처럼 작고 흐릿한 텍스트에 강함
  - GPU 가속 지원 (서버에 RTX 5060 있음)

왜 별도 모듈인가?
  EasyOCR은 모델 로딩에 10~30초 걸림.
  서버 시작 시 한 번만 로드해서 이후 요청은 빠르게 처리.
  (YOLO 워밍업과 같은 원리)
"""

import re
import numpy as np

# 싱글톤: 서버 시작 시 한 번만 로드
_reader = None


def _get_reader():
    """EasyOCR Reader 싱글톤 반환. 최초 호출 시에만 모델 로드."""
    global _reader
    if _reader is None:
        import easyocr
        print("[BusOCR] EasyOCR 모델 로드 중... (최초 1회, 30초 소요 가능)")
        # ko: 한국어, en: 영어 (버스 번호는 숫자라 영어 숫자 인식 포함)
        # gpu=True: RTX 5060 활용, False: CPU fallback
        try:
            _reader = easyocr.Reader(["ko", "en"], gpu=True, verbose=False)
            print("[BusOCR] GPU 모드로 로드 완료")
        except Exception:
            _reader = easyocr.Reader(["ko", "en"], gpu=False, verbose=False)
            print("[BusOCR] CPU 모드로 로드 완료")
    return _reader


def _preprocess(img_np: np.ndarray) -> np.ndarray:
    """
    OCR 전 이미지 전처리 — 번호판 인식률 향상.

    처리 순서:
      1. 그레이스케일: 색상 노이즈 제거
      2. CLAHE: 지역별 대비 자동 향상 (역광·어두운 번호판 보정)
      3. 언샤프 마스킹: 글자 경계선 선명화

    CLAHE(Contrast Limited Adaptive Histogram Equalization):
      전체 이미지 대신 타일 단위로 히스토그램 평활화
      → 밝은 부분·어두운 부분 동시에 개선 가능
    """
    import cv2
    gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)

    # CLAHE: clipLimit 높을수록 대비 강함, tileGridSize는 분할 크기
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # 언샤프 마스킹: 가우시안 블러 뺀 뒤 원본에 더해서 선명화
    blurred   = cv2.GaussianBlur(enhanced, (0, 0), 3)
    sharpened = cv2.addWeighted(enhanced, 1.5, blurred, -0.5, 0)

    # EasyOCR은 BGR 3채널 또는 그레이스케일 모두 받음
    return sharpened


def _extract_bus_number(results: list) -> str | None:
    """
    EasyOCR 결과에서 버스 번호 추출.

    버스 번호 특징:
      - 1~4자리 숫자 (1번 ~ 9999번)
      - 간혹 알파벳 포함 (N37, M5100 등 심야/광역버스)
      - 신뢰도 0.3 이상인 것만 사용

    results 형식: [(bbox, text, confidence), ...]
    """
    candidates = []
    for (_, text, conf) in results:
        if conf < 0.3:  # 신뢰도 너무 낮으면 무시
            continue
        clean = text.strip()

        # 순수 숫자 1~4자리
        if re.fullmatch(r"\d{1,4}", clean):
            candidates.append((int(conf * 100), clean))
            continue

        # 알파벳+숫자 조합 (N37, M5100 등)
        if re.fullmatch(r"[A-Za-z]\d{1,4}", clean):
            candidates.append((int(conf * 100), clean))

    if not candidates:
        return None

    # 신뢰도 높은 것 우선, 같으면 짧은 것 (노선 번호 가능성 높음)
    candidates.sort(key=lambda x: (-x[0], len(x[1])))
    return candidates[0][1]


def recognize_bus_number(image_bytes: bytes, bus_crop: list | None = None) -> str | None:
    """
    버스 번호 인식 메인 함수.

    Args:
        image_bytes: 전체 이미지 바이트
        bus_crop: [x1, y1, x2, y2] 버스 bbox 상단 영역 좌표 (없으면 전체 이미지 사용)

    Returns:
        인식된 버스 번호 문자열 ("37", "N37" 등) 또는 None
    """
    import cv2
    reader = _get_reader()

    # 이미지 디코딩
    nparr  = np.frombuffer(image_bytes, np.uint8)
    img    = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    img    = cv2.flip(img, 1)  # detect.py와 동일하게 좌우 반전 보정

    # bus_crop 좌표가 있으면 그 영역만 잘라서 OCR (배경 노이즈 제거)
    if bus_crop and len(bus_crop) == 4:
        x1, y1, x2, y2 = bus_crop
        # 좌표 유효성 확인
        h, w = img.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if x2 > x1 and y2 > y1:
            img = img[y1:y2, x1:x2]

    # 이미지가 너무 작으면 확대 (OCR 정확도 향상)
    h, w = img.shape[:2]
    if w < 200 or h < 50:
        scale = max(200 / w, 50 / h, 2.0)
        img = cv2.resize(img, (int(w * scale), int(h * scale)),
                         interpolation=cv2.INTER_CUBIC)

    # 전처리 적용
    processed = _preprocess(img)

    # EasyOCR 실행 (두 가지 모드: 원본 + 전처리)
    try:
        results_orig = reader.readtext(img,       detail=1, paragraph=False)
        results_proc = reader.readtext(processed, detail=1, paragraph=False)
        results = results_orig + results_proc  # 두 결과 합쳐서 후보 풀 확장
    except Exception as e:
        print(f"[BusOCR] OCR 실패: {e}")
        return None

    return _extract_bus_number(results)


def warmup():
    """서버 시작 시 모델 미리 로드 (첫 요청 지연 방지)."""
    try:
        _get_reader()
    except Exception as e:
        print(f"[BusOCR] 워밍업 실패: {e}")
