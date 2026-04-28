# VoiceGuide 변경 이력

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
