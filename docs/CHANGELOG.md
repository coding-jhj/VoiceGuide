# VoiceGuide 변경 이력

---

## 2026-04-29 (디버깅 세션 — TTS·바운딩박스·분석중지 전면 수정)

### TTS 무음 버그 3개 수정
- **Bug 1 — `/tts` 엔드포인트 HTTP 200 에러**: ElevenLabs 키 없을 때 `{"error":...}` JSON을 HTTP 200으로 반환 → Android가 성공으로 착각 → JSON을 MP3로 저장 → MediaPlayer 실패 → 무음. 수정: API 키 체크 제거, gTTS 폴백 사용, 실패 시 400/500 반환
- **Bug 2 — `speak()` ElevenLabs 라우팅 누락**: 서버 URL 입력 시 `speakElevenLabs()` 분기가 없어서 항상 `speakBuiltIn()` 호출. `isSpeaking()`은 `isElevenLabsSpeaking`을 체크하는데 실제로는 `ttsBusy`가 쌓여 문장이 조용히 버려짐. 수정: `isSpeaking() = ttsBusy || isElevenLabsSpeaking`으로 통합
- **Bug 3 — Gradio 데모 브라우저 무음**: `speak()`가 서버 머신 스피커로만 재생 → 브라우저 사용자 못 들음. 수정: `gr.Audio(autoplay=True)` 출력 추가, MP3 경로 반환

### 서버 첫 요청 느림 + "분석 실패" 반복 수정
- **원인**: 서버 시작 시 Depth V2 모델 미로드 → 첫 `/detect` 요청에서 모델 로딩(10~30초) → Android 8초 timeout 초과 → 연속 실패
- **수정**: `src/api/main.py` lifespan에 `_load_model()` 워밍업 추가 (YOLO 워밍업에 이어 Depth V2도 서버 시작 시 로드)
- Android `connectTimeout` 5s→10s, `readTimeout` 8s→20s

### 바운딩박스 물체 사라져도 유지되는 버그 수정
- **원인**: `sendToServer()` 서버 응답의 `objects` 배열을 무시 → 박스 갱신 코드 없음
- **수정**: 서버 응답 `objects` JSON 파싱 → `Detection`으로 변환 → `boundingBoxOverlay` 즉시 갱신. `objects` 빈 배열이면 `clearDetections()`
- `isSending` 안전망 추가: `finally`에 `isSending.set(false)` → 예외 발생 시 데드락 방지

### 분석 중지 버튼 미작동 수정
- **원인**: `handleSuccess()`가 `isAnalyzing` 체크 없이 백그라운드 Thread 완료 후에도 TTS 호출
- **수정**: `handleSuccess()` 첫 줄에 `if (!isAnalyzing.get()) return` 추가

### 첫 감지 느림 + 새 물체 전환 느림 수정
- **원인 1**: `startAnalysis()` 재시작 시 `detectionHistory` 미초기화 → 이전 세션 투표 버퍼 잔존
- **원인 2**: `VOTE_MIN_COUNT = 2` → 물체가 2프레임 연속 감지돼야 안내 (400~800ms 지연)
- **수정**: `detectionHistory.clear()` 추가, `VOTE_MIN_COUNT` 2→1 (첫 프레임 즉시 통과)

---

## 2026-04-29 (강사 미팅 피드백 즉일 반영)

### FPS 최적화 (10fps 목표)
- `YoloDetector.kt`: NNAPI 하드웨어 가속 추가 (DSP/NPU) → 추론 속도 향상
- CPU 스레드 4개 병렬 처리 (`setIntraOpNumThreads(4)`)
- 캡처 간격: 1000ms → **100ms** (10fps 목표 — 실제 FPS는 추론 속도에 의해 결정)
- FPS < 10 시 Logcat 경고 자동 출력 (`tag:VG_PERF`)

### FPS 시각화 + 구조화 로그
- FPS 스파크라인 그래프 추가: `2.1fps ▄▃▅▄▃▅ | 180ms` 형태로 tvMode에 표시
- 최근 10프레임 FPS 히스토리 관리
- 구조화 성능 로그 추가 (`tag:VG_PERF`):
  ```
  decode|12|infer|180|dedup|3|total|195|objs|2
  mode|server|server_ms|243|net_ms|89|total|332
  ```

### STT 딜레이 수정 (3초 → 1초 이내)
- 침묵 감지 시간: 1200ms → **700ms**
- 가능한 침묵: 1000ms → **500ms**
- WEB_SEARCH 모델 사용 (짧은 명령어 최적화)
- 후보 3개로 키워드 매칭률 향상

### TTS 소리 안나는 버그 수정 (2단계)
- **1차 원인**: 서버 URL 입력 시 ElevenLabs TTS 자동 호출 → API 키 없으면 무음
  - 수정: `speak()` 함수가 항상 Android 내장 TTS 사용
- **2차 원인(진짜 원인)**: 오토리슨(`isListening=true`)이 항상 켜져있어서 `speak()`가 항상 차단됨
  - 수정: `speak()` 호출 시 STT를 `cancel()`로 즉시 중단 후 TTS 재생 → 소리 후 오토리슨 자동 재시작

### UI 전면 개선
- 카메라 풀스크린 레이아웃 (기존: 화면 일부)
- 하단 둥근 패널 오버레이 (bg_bottom_panel)
- 분석 중지 시 버튼 빨간색, STT 중 마이크 빨간색 (상태 시각화)
- 앱 아이콘: 마이크 + 음파 디자인으로 변경
- 바운딩박스: 새 캡처 시작 시 즉시 클리어 (지연 제거)

### GCP 서버 가이드
- `docs/GCP_SERVER_SETUP.md` 추가: 강사 지정 스펙 (GPU 없음, 30GB 이하, 서울 리전, Ubuntu 22)
- `docs/MEETING_0429_강사피드백.md` 추가: 미팅 전체 내용 기록

---

## 2026-04-28 (4차 — TTS 완전 잠금 + 거리 기반 음성/비프 + 오인식 추가 수정)

### TTS 완전 겹침 차단
- `ttsBusy` AtomicBoolean 도입: `compareAndSet(false, true)` 실패 시 신규 TTS 버림
- `UtteranceProgressListener.onDone` 후 700ms 뒤 잠금 해제
- 차량만 `immediate=true`로 강제 획득(QUEUE_FLUSH) → 다른 사물은 현재 TTS 끝날 때까지 대기
- `isSpeaking()`을 `ttsBusy` 기반으로 단순화

### 거리 기반 음성/비프 분리
- 가까이(bbox 8% 이상) → 음성 안내 (이미 말해줬어도 아직 가까이면 계속 안내)
- 멀리(bbox 8% 미만) → 비프 (인지용)
- 차량·칼 등 위험 → 항상 음성
- 비프: `TONE_PROP_BEEP2`, 볼륨 100%, 400ms

### 여러 사물 전부 안내
- 문장을 `voiceDetections`만이 아닌 `voted` 전체로 생성 (가까운 순 정렬)
- 멀리 있는 사물도 문장에 포함됨

### 오인식 추가 수정
- class 63(노트북) 제거 — 스피커·모니터 오인식 빈번
- class 72(냉장고) 제거 — 벽 오인식 빈번
- class 77(인형) 이미 제거됨

### 찾기 모드 수정
- `voteFilter`에서 찾기 모드는 쿨다운 우회
- `extractFindTarget`: 공백 정규화 + 키워드 확대 ("어딨어", "어딨나" 등)

### 경고 피로 수정
- 클래스별 5초 쿨다운: 같은 사물 5초 내 재발화 차단
- critical 5초 쿨다운: 같은 경고문 5초 내 재발화 차단
- TTS 종료 후 700ms 침묵 (말 끝나자마자 다음 말 시작 방지)

### 재방문 자동 알림
- `checkRevisit()`: 30초마다 WiFi SSID 확인 → 저장 장소 일치 시 "○○에 도착했어요." 안내
- 같은 SSID 중복 알림 방지

---

## 2026-04-28 (3차 — 계단 제거 + Voting 온디바이스 + 오인식 재수정)

### 계단 감지 전면 제거 (강사님 피드백)
- Android: `VoiceGuideConstants.kt` class 80(계단) 제거, `StairsDetector` 호출 제거
- Android: `SentenceBuilder.kt` 계단 우선순위 로직 제거
- Server: `detect.py` stairs 클래스·필터·상수 전체 제거
- Server: `tracker.py` 계단 즉시통과 로직 제거

### 온디바이스 Voting 버퍼 추가 (경고 피로 방지)
- `MainActivity.kt`에 deque 기반 `voteFilter()` 추가
  - 최근 5프레임 기록, 3회 이상 등장한 사물만 TTS 안내
  - 차량·칼 등 위험 클래스는 즉시 통과
  - `YoloDetector.kt` `.take(2)` → `.take(5)` (투표 입력 확대)
  - `SentenceBuilder.kt` 최종 출력 `.take(3)` (상위 3개 안내)

### TTS 겹침 수정
- `critical` 브랜치: 같은 문장이 이미 재생 중이면 재시작 안 함

### 오인식 재수정 (폰→인형 추가 교정)
- `prepare_cellphone.py`: `teddy_bear(77)` → `cell_phone(67)` 교정 추가
- `VoiceGuideConstants.kt`: class 77(인형) 탐지 대상에서 제거
- 파인튜닝 재실행

---

## 2026-04-28 (2차 — 오인식 수정 + PyTorch GPU 셋업)

### 버그 수정

- **휴대폰 → 노트북 오인식 수정** (YOLO 파인튜닝)
  - 원인: YOLO11m이 phone 화면을 laptop(class 63)으로 오분류
  - 해결: 휴대폰/노트북 이미지 348장 수집 → laptop 탐지 결과를 cell_phone(67)으로 교정 라벨링 → 파인튜닝
  - 결과: mAP50 0.624 → **0.748** 향상
  - 기존 계단 모델(`yolo11m_indoor.pt`)에서 이어받아 계단 정확도 보존

- **목소리 겹침 미수정 원인 파악**
  - `c:/VoiceGuide/android/`(구버전, `suppressPeriodicUntil` 없음) vs `c:/VoiceGuide/VoiceGuide/android/`(신버전) 폴더 혼동
  - → 신버전 폴더(`VoiceGuide/android/`)로 빌드해야 3초 TTS 억제 적용됨

### 파인튜닝 파이프라인 추가

- `train/prepare_cellphone.py` — DuckDuckGo 이미지 수집 + laptop→cell_phone 라벨 교정
- `train/finetune_cellphone.py` — `yolo11m_indoor.pt` 기반, lr=5e-5 / 25 에포크
- `tools/export_onnx.py` — ONNX 변환 후 두 android 폴더(`VoiceGuide/android/`, `../android/`) 동시 갱신

### 환경 설정

- PyTorch CPU→GPU 전환: `torch 2.4.1+cpu` → `torch 2.11.0+cu128` (RTX 5060 Blackwell 지원)
- ONNX Runtime Android 업그레이드: `1.17.3` → `1.19.0` (PyTorch 2.11 내보낸 opset 18 모델 호환)

---

## 2026-04-28

### 신규 기능

- **질문 모드** (`"질문"` STT 키워드) — "지금 뭐가 있어?" 즉시 응답
  - 기존 버그: STT → "장애물" → else 분기 → "장애물 모드."만 말하고 종료
  - 수정: 즉시 캡처 + tracker 누적 상태 포함 포괄 응답

- **보팅(Voting) 방식 경고 피로 방지**
  - `VotingBuffer`: 최근 10프레임 중 60%+ 탐지된 물체만 확정
  - 차량·계단은 안전 우선으로 보팅 없이 즉시 통과

- **실시간 대시보드** (`GET /dashboard`)
  - Leaflet.js + OpenStreetMap 다크 테마 지도
  - GPS 이동 경로(polyline), 탐지 물체 위험도 카드
  - 2초 폴링 자동 갱신

- **GPS 위치 연동**
  - Android `currentLat`/`currentLng` 상시 업데이트
  - `/detect` 전송 시 lat/lng 포함 → DB 저장 (`gps_history` 테이블)
  - `/status/{session_id}` 엔드포인트 — 현재 tracker 상태 + GPS 경로 반환

- **서버 테스트 스크립트** (`tests/test_server.py`)
  - 9개 엔드포인트 자동 테스트 (장애물/질문/찾기/저장/GPS/대시보드 등)

### 버그 수정

- `MainActivity`: "장애물"/"확인" STT 시 즉시 `captureAndProcess()` 호출 (기존: 다음 주기까지 대기)
- `tracker.py`: `update()`에서 `direction` 필드 누락 수정 → `get_current_state()` 방향 정보 포함
- `routes.py`: `build_question_sentence` import 추가, 질문 모드 분기 추가

### feature/nlg 브랜치 merge

- myungkwang PR: 비프음 인식 수정, 바운딩박스 인식 오류 수정
- `StairsDetector.kt` 추가
- `BoundingBoxOverlay.kt`: FILL_CENTER 변환으로 bbox 정확도 개선
- `YoloDetector.kt`: 레터박스 처리 개선

---

## 2026-04-27

### 신규 기능

- **경고 계층 분리** — critical/beep/silent 3단계 alert_mode
- **TTS 목소리 겹침 완전 해결** — `ttsRequestId`로 stale 재생 차단
- **Naver Clova Voice** — `.env`의 `NAVER_CLIENT_ID`/`SECRET` 설정 시 자동 전환
- **stairs 오탐 방지** — 최소 신뢰도 0.50 → 0.72

### 강사님 피드백 반영

- 거리 수치("약 1.2m") → 상대 표현("가까이/바로 코앞") 전환
- 타겟 유저: 전맹(완전 시각 장애) 명확화
- 방향 좌우 반전 버그 수정 (`cv2.flip`)
