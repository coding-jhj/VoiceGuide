# 4/28 강사님 미팅 결과 정리

*2026-04-28 미팅 후 정리 | 최종 업데이트: 2026-04-28*

---

## 우선순위 요약 (전체 현황)

| 순위 | 항목 | 상태 |
|------|------|------|
| 🔴 P0 | 사용자 질문 응답 기능 구현 | ✅ 완료 |
| 🔴 P0 | 경고 피로 후처리 — 보팅 방식 적용 | ✅ 완료 |
| 🔴 P1 | deque 싱크 버그 수정 | ✅ 완료 |
| 🔴 P1 | 바운딩 박스 비트 불일치 확인 | ✅ float32 확인 완료 |
| 🟡 P2 | 서버 데이터 송수신 테스트 | ✅ 완료 (test_server.py 9개) |
| 🟡 P2 | 외부 DB / LTE 서버 — GCP·Railway·AWS·Oracle | ✅ 완료 (DEPLOY_GUIDE.md) |
| 🟡 P3 | 대시보드 지도 UI | ✅ 완료 (dashboard.html, Leaflet.js) |
| 🟡 P3 | 네비게이션 API 조사 (네이버·카카오·Google) | ✅ 조사 완료 — 대시보드 GPS 경로 반영 |
| 🟡 추가 | 사물 인식률 개선 — 위험 클래스 임계값 조정 | ✅ 완료 |
| 🟡 추가 | TTS 겹침 완전 차단 | ✅ 완료 |
| 🟡 추가 | feature/nlg PR conflict 해결 + merge | ✅ 완료 |
| 🟡 추가 | 추론속도 / FPS 최적화 | ✅ 완료 — 이미지 압축 + 처리시간 측정 UI |
| 🟢 하드웨어 | 뎁스 카메라 → Depth Anything V2로 대체 | ✅ 정상 동작 (/health 확인) |
| 🟡 추가 | 사물 위험 우선 필터 + 신규 위험 감지 | ✅ 완료 |

---

## 미팅 원문 요약 (강사님 발언 기반)

```
경고 피로가 심하면 후처리가 필요함 (예: 보팅 — 10개 프레임 다수결)
바운딩 박스가 정확하지 않음 — 16bit/32bit 비트 불일치 확인 필요
추론속도, FPS 개선 필요
덱 싱크가 안 맞음 — 사용자 질문에 탐지 결과가 연결 안 됨
계단은 객체라 하기에 사이즈가 큼 — 위험한 사물 위주로만
서버 데이터 송수신 테스트 필요
대시보드에 지도가 있어야 함 — 동선 표시
개인 네비게이션 API 조사 (네이버 자전거 네비 참고)
외부 DB (GCP, Supabase 등) — LTE 환경 테스트
내일까지: 서버 논의 + 질문 응답 기능 구현
```

---

## 구현 완료 상세

### ✅ 사용자 질문 응답 기능

**문제**: "앞에 뭐 있어" 말해도 "장애물 모드."만 말하고 즉시 분석 안 함. tracker 누적 상태가 질문 응답에 연결 안 됨.

**구현 내용**:
- `VoiceGuideConstants.kt` + `stt.py`: `"질문"` STT 모드 추가 — "지금 뭐가 있어", "지금 어때" 등
- `MainActivity.kt`: `captureAndProcessAsQuestion()` — 즉시 캡처 + `mode="질문"` 서버 전송
- `MainActivity.kt`: `"장애물"/"확인"` STT 시도 즉시 `captureAndProcess()` 호출 (기존 버그 수정)
- `tracker.py`: `get_current_state(max_age_s=3.0)` — 최근 3초 누적 물체 목록 반환
- `routes.py`: `mode="질문"` 분기 → `build_question_sentence()` — 현재 프레임 + tracker 상태 합산
- `sentence.py`: `build_question_sentence()` 추가 — 계단 > 위험물 > 현재 탐지 > tracker 상태 순 응답

---

### ✅ 보팅 방식 경고 피로 후처리

**문제**: 경고가 너무 자주 발생. 1~2프레임 오탐도 즉시 경고.

**구현 내용**:
- `tracker.py`: `VotingBuffer(window=10, threshold=0.6)` 클래스 추가
  - 최근 10프레임 중 60% 이상 탐지됐을 때만 경고 확정
  - 차량·계단(`ALWAYS_CRITICAL`)은 보팅 없이 즉시 통과 (안전 우선)
- `routes.py`: `_should_suppress()` — 동일 문장 5초 내 재발화 시 `alert_mode="silent"` 강제
- `MainActivity.kt`: `suppressPeriodicUntil` — 질문 응답 후 3초간 periodic TTS 억제
- `handleSuccess()`: `effectiveMode` 적용, beep도 `isSpeaking()` 체크

---

### ✅ deque 싱크 버그 수정

**문제**: tracker가 방향 정보를 저장하지 않아 `get_current_state()` 응답에 방향 누락.

**구현 내용**:
- `tracker.py`: `update()` 내 방향 정보(`direction`) track에 저장
- `tracker.py`: `get_current_state()` — 방향 포함 완전한 물체 정보 반환

---

### ✅ 바운딩 박스 비트 불일치 확인

**확인 결과**:
- `YoloDetector.kt`: `FloatBuffer.allocate()` → `float32` 사용 확인 ✅
- 픽셀값 `/ 255f` → 0.0~1.0 정규화 정상 ✅
- 좌표: ONNX 출력 `/ inputSize(640)` → 0~1 정규화 → View 크기 곱 변환 정상 ✅
- `BoundingBoxOverlay.kt`: feature/nlg의 FILL_CENTER 변환으로 핸드폰별 해상도 대응 ✅

---

### ✅ 서버 데이터 송수신 테스트

**구현 내용**:
- `tests/test_server.py` — 9개 엔드포인트 자동 테스트
  - `/health`, `/detect(장애물)`, `/detect(질문)`, `/detect(찾기)`, `/detect(저장)`
  - `/status`, `/locations`, GPS 저장·조회, `/dashboard`
- 실행 방법: `python tests/test_server.py` (서버 켠 상태에서)

---

### ✅ 외부 DB / LTE 서버 구성

**구현 내용**:
- `src/api/db.py`: `DATABASE_URL` 환경변수 유무로 SQLite ↔ PostgreSQL 자동 전환
  - 없으면 SQLite (로컬), 있으면 Supabase PostgreSQL (외부)
- `railway.toml`: Railway 무료 배포 설정 파일
- `.env`: `DATABASE_URL` 플레이스홀더 추가
- `docs/DEPLOY_GUIDE.md`: Railway·GCP·AWS·Oracle Cloud·Render 전체 배포 가이드

**서버 선택 기준**:
| 상황 | 선택 |
|------|------|
| 빠른 LTE 테스트 | Railway + Supabase (5분, YOLO만) |
| Depth V2 완전 기능 | Oracle Cloud Always Free (RAM 24GB) |
| PC 가져갈 수 있을 때 | ngrok (2분, GPU 그대로) |

---

### ✅ 대시보드 지도 UI

**구현 내용**:
- `templates/dashboard.html`: Leaflet.js + OpenStreetMap 다크 테마 실시간 대시보드
  - 2초 폴링 자동 갱신
  - 탐지 물체 위험도 카드 (🔴위험·🟡주의·🟢안전)
  - GPS 현재 위치 마커 + 이동 경로(polyline)
  - WiFi SSID 입력으로 세션 전환
- `GET /dashboard` 엔드포인트
- `GET /status/{session_id}` — tracker 상태 + GPS 경로 반환
- Android `currentLat`/`currentLng` 상시 업데이트 → `/detect` 전송 → DB 저장

**접속 방법**:
```
http://서버IP:8000/dashboard          ← 로컬
https://voiceguide-xxx.railway.app/dashboard  ← 외부 서버
```

---

### ✅ 네비게이션 API 조사

**조사 결과**: 대시보드에 GPS 이동 경로(polyline) 이미 구현됨.
실제 경로 안내(A→B 네비게이션)는 추가 API 키 필요:

| API | 특징 | 무료 한도 |
|-----|------|---------|
| **네이버 지도 API** | 한국 지도 정확, 자전거 경로 제공 | 월 3만 건 |
| **카카오맵 API** | 한국 최다 POI, 도보/자전거 경로 | 무제한 (등록 필요) |
| **Google Maps Platform** | 글로벌, Directions API | 월 $200 크레딧 |

현재 대시보드: Leaflet.js + OpenStreetMap (API 키 불필요) ← 현재 구현
실제 길 안내 추가 시: 네이버 지도 API 권장 (한국 자전거 경로 지원)

---

### ✅ 사물 인식률 개선

**구현 내용**:
- `detect.py`: 차량(`0.35`), 칼·가위(`0.42~0.45`) 임계값 하향 → 더 멀리서 더 일찍 탐지
- `ALWAYS_CRITICAL` 집합 추가: 차량·계단·칼·가위·곰·코끼리 → 보팅 없이 즉시 경고

---

## ✅ 추론속도 / FPS 최적화 — 완료

**구현 내용**:
- `routes.py`: `process_ms` 필드 추가 — 서버 내부 처리 시간(ms) 응답에 포함
- `MainActivity.kt`: `optimizeImageForUpload()` — 전송 전 640px 리사이즈 + JPEG 75% 압축
  - 전송 크기 약 40~60% 감소 → 네트워크 지연 단축
  - YOLO는 어차피 640×640으로 리사이즈하므로 품질 손실 없음
- `MainActivity.kt`: `tvMode`에 `서버:XXXms 네트워크:XXXms` 실시간 표시
- `templates/dashboard.html`: 네비게이션 / Google 로드뷰 버튼 추가 (GPS 수신 시 활성화)
  - 네이버 지도로 열기
  - 카카오맵으로 열기
  - Google Street View (로드뷰)

### 사물 클래스 신규 추가

전동킥보드·볼라드 등 COCO에 없는 한국 특화 클래스.
- YOLO-World 모드(`YOLO_WORLD=1`)로 이미 일부 지원
- 파인튜닝 추가는 데이터 수집 필요 → 기능 완성 후 진행

---

## 팀 운영 방향 (강사님 코멘트)

- **서로 회의를 더 자주, 명확하게** — 방향 공유와 팀플레이에 집중
- 음성 모델 성능보다 **시각장애인에게 임팩트 있는 기능** 우선
- 기능 추가보다 **현재 기능 완성도** 먼저
- 발표를 위해 **추론 속도(FPS) 최적화**도 신경 쓸 것
