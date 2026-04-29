# 시각장애인 보이스가이드 프로젝트 - 내비게이션 API 가이드

> 시각장애인용 보이스가이드에 적합한 내비게이션 API를 비교하고 추천합니다.
> 일반 내비게이션보다 **보도 경로 + 음성 안내 + 장애물 정보**가 중요한 프로젝트입니다.

---

## 추천 API 순위

### 1순위 — T Map API ⭐ (가장 추천)

| 항목 | 내용 |
|------|------|
| 제공사 | SK텔레콤 |
| 공식 사이트 | https://openapi.sk.com |
| 비용 | 무료 한도 제공 (일 호출 수 제한) |

**장점**
- 보행자 전용 경로 제공
- 한국어 음성 안내 텍스트 포함
- 교차로 상세 안내 (몇 미터 앞에서 좌회전 등)
- Python으로 REST API 호출 가능
- 국내 도로/골목 데이터 정확도 높음

---

### 2순위 — Kakao Mobility API

| 항목 | 내용 |
|------|------|
| 제공사 | 카카오 |
| 공식 사이트 | https://developers.kakao.com |
| 비용 | 무료 사용 가능 |

**장점**
- 보도 경로 지원
- 국내 POI(편의점, 지하철 출구 등) 데이터 풍부
- 무료 사용 가능

**단점**
- T Map보다 보행자 안내 세부 정보가 적음

---

### 3순위 — Google Maps Directions API

| 항목 | 내용 |
|------|------|
| 제공사 | Google |
| 공식 사이트 | https://developers.google.com/maps |
| 비용 | 일정 쿼리 초과 시 유료 과금 |

**장점**
- 글로벌 커버리지, 안정성 높음
- 보도 경로 지원

**단점**
- 일정 쿼리 초과 시 유료 과금
- 한국 실내/골목 데이터는 T Map보다 약함

---

## 시각장애인 프로젝트를 위한 추가 고려 기능

| 기능 | 활용 방법 | 추천 도구 |
|------|----------|----------|
| 현재 위치 파악 | GPS 기반 좌표 추출 | `geopy` 라이브러리 |
| 음성 출력 (TTS) | 안내 문구를 음성으로 변환 | `gTTS`, `pyttsx3`, 네이버 CLOVA TTS |
| 음성 입력 (STT) | 사용자 음성 명령 인식 | Google STT, OpenAI Whisper |
| 장애물/횡단보도 감지 | 카메라 이미지 분석 | YOLO 모델 |

---

## 최종 추천 조합

```
T Map API          →  경로 안내 (보행자 특화)
       +
네이버 CLOVA TTS   →  음성 출력 (자연스러운 한국어)
       +
OpenAI Whisper     →  음성 입력 (사용자 명령 인식)
```

세 가지를 조합하면 **경로 탐색 → 음성 안내 → 음성 명령 수신** 흐름을 구현할 수 있습니다.

---

## 참고 링크

- T Map Open API: https://openapi.sk.com
- Kakao Developers: https://developers.kakao.com
- Google Maps Platform: https://developers.google.com/maps
- 네이버 CLOVA TTS: https://clova.ai/speech
- OpenAI Whisper (GitHub): https://github.com/openai/whisper
