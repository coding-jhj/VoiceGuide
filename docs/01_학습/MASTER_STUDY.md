# VoiceGuide 전체 학습 가이드

> 이 파일 하나로 프로젝트의 모든 MD 파일을 **어떤 순서로, 무엇을 공부해야 하는지** 안내합니다.  
> 발표 준비, 면접 대비, 팀원 이해 모두 이 파일에서 시작하세요.

---

## 📁 전체 MD 파일 지도

```
docs/
├── CHANGELOG.md              ← 날짜별 모든 변경 이력
├── INDEX.md                  ← 파일 목록 인덱스
│
├── 01_학습/
│   ├── MASTER_STUDY.md       ← 지금 이 파일 (전체 학습 가이드)
│   ├── LEARN.md              ← 코드 동작 원리 (핵심 학습용)
│   ├── CODE_FLOW.md          ← 전체 코드 흐름 다이어그램
│   ├── TECH.md               ← 모듈별 기술 명세 (팀원 역할 분담)
│   ├── SERVER_LEARN.md       ← 서버 쪽 심화 학습
│   ├── ALERT_FATIGUE_GUIDE.md← 경고 피로 방지 설계
│   └── BUG_STUDY.md          ← 실제 버그로 배우는 코드 구조
│
├── 02_미팅/
│   ├── MEETING_0427.md       ← 4/27 미팅 내용
│   ├── MEETING_0428.md       ← 4/28 미팅 내용
│   ├── MEETING_0428_결과.md  ← 4/28 결과 정리
│   ├── MEETING_0429_강사피드백.md ← 강사 피드백 전체
│   ├── MEETING_0429_준비.md  ← 4/29 발표 준비
│   └── INTERVIEW_0427_분석.md ← 시각장애인 인터뷰 분석
│
├── 03_서버/
│   ├── SERVER_GUIDE.md       ← 서버 실행 방법
│   ├── SERVER_ARCHITECTURE.md← 서버 구조 설계
│   ├── SERVER_ROLE_GUIDE.md  ← 서버 담당자용
│   ├── DEPLOY_GUIDE.md       ← 배포 방법
│   ├── GCP_GUIDE.md          ← GCP 배포 가이드
│   ├── GCP_SERVER_SETUP.md   ← GCP 서버 설정
│   ├── NAVIGATION_API_GUIDE.md← 네비게이션 API
│   ├── SUPABASE_QNA.md       ← Supabase Q&A
│   └── WHY_SERVER.md         ← 서버가 왜 필요한가
│
├── 04_팀/
│   ├── TEAM.md               ← 팀 구성 및 역할
│   ├── ROLE_YOODK.md         ← 신유득 담당 상세
│   ├── TEAM_BRIEFING.md      ← 팀 브리핑
│   ├── TEAM_CARDS.md         ← 팀원 카드
│   └── TODO_YOODK_GCP.md     ← GCP 할일 목록
│
├── 05_기획/
│   ├── PRD.md                ← 제품 요구사항 문서
│   ├── PROJECT_GUIDE.md      ← 프로젝트 전체 가이드
│   ├── RESEARCH.md           ← 기술 조사
│   └── mvp_checklist.md      ← MVP 체크리스트
│
├── 06_발표/
│   ├── PRESENTATION.md       ← 발표 자료 구성
│   ├── PRESENTATION_SCRIPT.md← 발표 스크립트
│   └── INSTRUCTOR.md         ← 강사 피드백 모음
│
└── 07_디버그/
    ├── troubleshooting.md    ← 버그 38개 + FPS 기준선
    ├── DETECTION_DEBUG.md    ← 탐지 디버그
    └── CALIBRATION_TEST.md   ← 거리 보정 테스트
```

---

## 🎯 목적별 학습 경로

### 발표 준비 (D-3)
```
1. CODE_FLOW.md    → 전체 흐름 다이어그램 암기
2. LEARN.md        → 각 모듈 동작 원리 이해
3. BUG_STUDY.md    → "왜 이렇게 만들었나" 근거 파악
4. MEETING_0429_강사피드백.md → 강사 지적사항 파악
5. PRESENTATION_SCRIPT.md     → 본인 파트 대본 확인
```

### 처음 입문 (코드 처음 보는 경우)
```
1. docs/README.md 또는 LEARN.md 1~2절만
2. CODE_FLOW.md의 "전체 흐름" 다이어그램
3. troubleshooting.md의 "환경 세팅 요약"
4. 서버 실행 → 앱 실행 → 동작 확인
5. 그 다음 나머지 읽기
```

### 버그 디버깅 중
```
1. troubleshooting.md  → 비슷한 증상 검색 (버그 38개)
2. PERF_DEBUG.md       → FPS/추론속도 병목 찾기 (WiFi ADB, 파일 로깅, 보행 물리학 기준)
3. BUG_STUDY.md        → 버그 원인 패턴 이해
4. CHANGELOG.md        → 최근 변경사항 확인
5. Logcat tag:VG_DETECT, VG_PERF 필터
```

### 서버 배포해야 할 때
```
1. SERVER_GUIDE.md         → 로컬 실행
2. DEPLOY_GUIDE.md         → 배포 옵션 비교
3. GCP_SERVER_SETUP.md     → GCP 설정
4. SUPABASE_QNA.md         → DB 연결
5. GCP_GUIDE.md (다운로드폴더) → 단계별 실습
```

---

## 📚 파일별 핵심 내용 요약

---

### `CHANGELOG.md` — 날짜별 변경 이력
**읽어야 할 이유**: 코드가 왜 지금 이 모양인지 역사를 알 수 있음

**핵심 날짜:**
- `2026-04-27`: 방향 좌우반전 버그 수정, 앱-서버 연동 완성
- `2026-04-28`: TTS 완전 잠금, 거리 기반 음성/비프 분리, 여러 사물 안내
- `2026-04-29 (강사 피드백)`: FPS 최적화, STT 딜레이 수정, UI 개선
- `2026-04-29 (디버깅)`: TTS 무음 3개 버그, 바운딩박스 유지, 분석중지 미작동, 첫 감지 느림

---

### `LEARN.md` — 코드 동작 원리 ⭐️가장 중요

**읽어야 할 이유**: 각 모듈이 왜 이렇게 설계됐는지 이해

**핵심 개념:**

#### 1. YOLO 방향 판단 (이미지 9구역)
```
[  8시  |  9시  | 10시  | 11시  | 12시  |  1시  |  2시  |  3시  |  4시  ]
[왼쪽   |왼쪽   |왼쪽앞 |왼쪽앞 |바로앞 |오른앞 |오른앞 |오른쪽 |오른쪽 ]

bbox 중심 x ÷ 이미지 너비 = 0.0~1.0
0.52 → 12시 구역 → "바로 앞"
```

#### 2. 위험도 점수 공식
```
risk = 방향가중치 × 거리가중치 × 바닥여부 × 클래스배수
예) 바로앞(1.0) × 매우가까이(1.0) × 바닥(1.4) × 자동차(3.0) = 4.2 → 최고위험
```

#### 3. alert_mode 결정
```
critical: 계단/차량/2.5m 이내 → 말 중이어도 끊고 1.25배 빠르게
silent:   2.5m 이상 → 무음 (UI만 업데이트)
```

#### 4. gTTS vs Android TTS
```
Gradio 데모: gTTS (서버에서 MP3 생성, 브라우저로 반환)
Android 앱:  내장 TTS (기기에서 즉시 재생, 네트워크 불필요)
```

#### 5. EMA 거리 평활화
```
smooth = 0.55 × 현재값 + 0.45 × 이전값
→ YOLO 프레임별 오차 제거, 안정적인 거리 안내
```

#### 6. 공간 기억 (WiFi SSID = 공간 ID)
```
첫 방문: 전체 안내
재방문: 달라진 것만 안내 ("의자가 생겼어요")
→ GPS 대신 WiFi 쓰는 이유: 실내에서도 동작
```

---

### `CODE_FLOW.md` — 전체 코드 흐름

**읽어야 할 이유**: 발표할 때 "이게 어떻게 동작하냐"는 질문에 그림으로 답할 수 있음

**핵심 흐름 (암기용):**
```
카메라 캡처 (100ms마다)
    ↓
ONNX 온디바이스 추론 (서버 없을 때)
또는 서버 POST /detect (서버 있을 때)
    ↓
YOLO 물체 탐지 → 방향 판단 → 위험도 계산
Depth V2 거리 추정 (서버) / bbox 면적 (온디바이스)
    ↓
EMA 평활화 → 공간기억 비교 → 문장 생성
    ↓
alert_mode 결정 → Android TTS 출력
```

**각자 설명해야 할 파트:**

| 이름 | 설명해야 할 부분 |
|------|----------------|
| 정환주 | CameraX 루프, STT 11모드, isSending 플래그, TTS 잠금 |
| 신유득 | /detect 5모드 분기, WiFi SSID 공간ID, alert_mode 결정 |
| 김재현 | 9구역 방향판단, 위험도 공식, CONF_THRESHOLD 선정 이유 |
| 문수찬 | Depth V2 상대깊이, bbox 하위30% 값, 계단 감지 12구역 |
| 임명광 | 긴박도 4단계, 한국어 조사 자동화, 차량 별도 처리 이유 |

---

### `TECH.md` — 모듈별 기술 명세

**읽어야 할 이유**: 팀원이 각자 무엇을 만들었는지 기술적 세부사항

**핵심만:**
```
Module A: Android (정환주) — CameraX, OkHttp, TTS, STT
Module B: FastAPI 서버 (신유득) — /detect 엔드포인트 허브
Module C: YOLO 탐지 (김재현) — 80클래스, 9구역, 위험도
Module D: Depth + 음성 (문수찬) — DepthAnythingV2, gTTS, STT
Module E: 문장생성 (임명광) — build_sentence, 조사자동화
```

---

### `BUG_STUDY.md` — 실제 버그로 배우는 코드 구조 ⭐️

**읽어야 할 이유**: 버그의 원인이 코드 구조를 가장 잘 설명해 줌

**버그 5개로 배우는 핵심 개념:**

| 버그 | 배운 개념 |
|------|---------|
| TTS 무음 | ttsBusy 잠금 구조, HTTP 상태코드 의미, isSpeaking() |
| 분석중지 미작동 | Handler vs Thread 차이, AtomicBoolean |
| 첫 감지 느림 | 투표 버퍼(Voting Buffer) 원리, 정밀도-속도 트레이드오프 |
| 바운딩박스 유지 | 픽셀→정규화 좌표 변환, 온디바이스 vs 서버 코드 분리 |
| 서버 첫 요청 느림 | Singleton + Lazy Loading 패턴, timeout 관계 |

---

### `troubleshooting.md` — 버그 38개 + FPS 기준선 ⭐️

**읽어야 할 이유**: 어떤 문제가 생겼을 때 여기서 먼저 찾기

**FPS 실용 기준선 (암기 권장):**

| 등급 | FPS | 추론 | 평가 |
|------|-----|------|------|
| 위험 | <3fps | >400ms | 실사용 불가 |
| 경계선 | 3~5fps | 200~400ms | |
| 실용최소 ✓ | 5fps | ~200ms | 실내 천천히 |
| 쾌적 ✓✓ | 10fps | ~100ms | 실외 보행 |
| 이상적 ✓✓✓ | 15fps | ~67ms | 자신감 있는 보행 |

**환경별 예상 FPS:**

| 환경 | FPS | 평가 |
|------|-----|------|
| YOLO11n + NNAPI | 8~15fps | 쾌적 |
| YOLO11m + NNAPI | 4~8fps | 실용권 |
| YOLO11m + CPU | 1~3fps | 위험 |
| 서버(로컬WiFi) | 3~6fps | 실용권 |
| 서버(클라우드) | 1~3fps | 보행 부적합 |

**주요 버그 번호 (면접/발표 대비):**
- `#0`: TTS 무음 (ElevenLabs→Android 내장 전환)
- `#34`: 분석중지 미작동 (isAnalyzing 체크 누락)
- `#35`: 첫 감지 느림 (VOTE_MIN_COUNT, detectionHistory)
- `#36`: /tts HTTP 200 에러
- `#37`: 바운딩박스 유지 (sendToServer 바운딩박스 갱신 누락)
- `#38`: isSending 데드락

---

### `ALERT_FATIGUE_GUIDE.md` — 경고 피로 방지 설계

**읽어야 할 이유**: 시각장애인 인터뷰에서 도출된 UX 설계 근거

**핵심 내용:**
- 같은 말이 반복되면 사용자가 TTS를 무시하게 됨 (경고 피로)
- 서버 5초 dedup: 같은 문장 5초 내 재발화 차단
- VotingBuffer: 일시적 오탐 차단
- critical 우선: 차량/계단은 항상 통과

---

### `INTERVIEW_0427_분석.md` — 시각장애인 인터뷰 분석

**읽어야 할 이유**: "왜 이렇게 만들었냐"는 질문의 근거

**핵심 인터뷰 결과:**
- "비프음보다 말로 설명해 달라" → 비프 제거, 음성으로 교체
- "같은 말 반복 No" → 중복 억제 로직
- "위험한 것은 빨리 말해 달라" → critical 1.25배 속도
- "방향은 시계 방향으로" → 8시~4시 표현

---

### `MEETING_0429_강사피드백.md` — 강사 피드백

**읽어야 할 이유**: 발표 때 강사가 같은 질문 다시 할 수 있음

**주요 피드백:**
- 계단 감지: YOLO 오탐률 높음 → Depth 맵으로 대체 ✅
- 거리 정확도: 단안 카메라로 정확한 미터 측정 불가 (알고 있음)
- FPS 목표: 10fps 이상
- 서버 배포: GCP Cloud Run 권장

---

### `SERVER_GUIDE.md` / `GCP_GUIDE.md` — 서버 관련

**핵심 명령어 (외워두기):**
```bash
# 로컬 실행
cd C:\VoiceGuide\VoiceGuide
C:\Users\ghksw\anaconda3\envs\ai_env\python.exe -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000

# 서버 정상 확인
curl http://localhost:8000/health
# 결과: {"depth_v2":"loaded","device":"cuda","db_mode":"sqlite"}

# Android 서버 URL 입력값
http://본인PC_IP:8000    ← ipconfig로 확인
```

---

### `PRD.md` — 제품 요구사항

**읽어야 할 이유**: 발표 때 "왜 만들었냐" 설명 근거

**핵심 문장:**
> 시각장애인이 실내·실외를 혼자 보행할 때, 주변 장애물을 실시간으로 감지하고  
> 자연어 음성으로 안내해 보행 안전성을 높이는 모바일 앱

**핵심 수치 (면접용):**
- 대상: 시각장애인 약 25만 명 (국내)
- 목표 FPS: 5fps 이상 (실용최소선)
- 지원 언어: 한국어
- 플랫폼: Android (CameraX + ONNX)

---

## 🔑 핵심 코드 위치 (파일:함수)

| 기능 | 파일 | 함수/클래스 |
|------|------|-----------|
| 메인 루프 | `MainActivity.kt` | `captureAndProcess()` |
| TTS 재생 | `MainActivity.kt` | `speak()` → `speakBuiltIn()` |
| STT 분기 | `MainActivity.kt` | `classifyKeyword()` → `handleSttResult()` |
| ONNX 추론 | `YoloDetector.kt` | `detect()` |
| 문장 생성 (앱) | `SentenceBuilder.kt` | `build()` |
| 서버 엔드포인트 | `routes.py` | `detect()` |
| YOLO + Depth | `depth.py` | `detect_and_depth()` |
| 문장 생성 (서버) | `sentence.py` | `build_sentence()` |
| 한국어 조사 | `sentence.py` | `_i_ga()`, `_un_neun()` |
| 거리 평활화 | `tracker.py` | `TrackerSession.update()` |
| 공간기억 | `db.py` | `get_snapshot()`, `save_snapshot()` |

---

## ❓ 발표 예상 질문 & 답변 요약

**Q. 왜 GPS 대신 WiFi SSID를 공간 ID로 쓰나요?**
> 실내에서는 GPS 신호가 약하거나 없습니다. WiFi SSID는 실내에서도 안정적으로 동작하고, 같은 WiFi를 쓰면 같은 공간으로 볼 수 있어서 재방문 감지에 활용합니다.

**Q. 거리가 정확한가요?**
> Depth Anything V2는 상대적 깊이(relative depth)를 추정합니다. 정확한 미터 단위 거리는 아니지만, "가까운지 먼지"를 판단하기에 충분합니다. 실용상 "약 1.5미터"처럼 표현하되, 오차가 있음을 사용자에게 알리는 설계입니다.

**Q. 계단을 YOLO로 감지하지 않는 이유는?**
> YOLO11m의 COCO 데이터셋에 계단이 포함되어 있지만, 실내 환경에서 오탐률이 높습니다. 대신 Depth Anything V2로 생성한 깊이 맵을 12구역으로 나눠 "바닥이 갑자기 깊어지면 계단"으로 판단합니다.

**Q. 왜 ElevenLabs를 쓰지 않나요?**
> 초기에 도입했으나 API 키가 없으면 무음이 되는 버그가 발생했습니다. Android 내장 TTS는 항상 동작하고 지연이 없어서 시각장애인 앱에 더 안전합니다.

**Q. 10fps가 안 나오면 어떻게 되나요?**
> 현재 YOLO11m + CPU만 있으면 1~3fps로 "위험 영역"입니다. YOLO11n으로 전환하거나 NNAPI 하드웨어 가속을 사용하면 8~15fps로 쾌적 수준이 됩니다. 서버 모드(로컬 WiFi)는 3~6fps로 실용 최소선을 만족합니다.

---

## 📖 공부 순서 추천

### Day 1 (2시간)
1. **이 파일** 전체 읽기 (30분)
2. `CODE_FLOW.md` 읽고 전체 흐름 그려보기 (30분)
3. 서버 실행 + 앱 실행 직접 해보기 (1시간)

### Day 2 (2시간)
1. `LEARN.md` 전체 읽기 (1시간)
2. `BUG_STUDY.md` — 자신이 직접 겪은 버그 파트 읽기 (30분)
3. `troubleshooting.md` — 버그 목록 훑기 (30분)

### Day 3 (발표 전날)
1. `CHANGELOG.md` — 최근 변경 이력 (30분)
2. `MEETING_0429_강사피드백.md` (30분)
3. `PRESENTATION_SCRIPT.md` — 본인 파트 (1시간)
4. 예상 질문 답변 연습 (위의 Q&A 참고)
