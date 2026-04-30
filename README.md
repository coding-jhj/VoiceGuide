# VoiceGuide

> 시각장애인을 위한 AI 음성 주변 인지 서비스  
> KDT AI Human 3팀 | 2026-04-24 ~ 2026-05-13

---

## 🗺️ 실시간 대시보드

탐지 물체·GPS 이동 경로를 지도로 보여주는 관리자 대시보드입니다.  
**WiFi 없이 LTE 환경에서도 동작** — 무료 외부 서버에 배포하면 어디서나 접속 가능합니다.

### 접속 방법

| 환경 | 대시보드 URL |
|------|------------|
| **로컬 WiFi** | `http://192.168.x.x:8000/dashboard` |
| **GCP Cloud Run** ✅ 현재 운영 중 | `https://voiceguide-135456731041.asia-northeast3.run.app/dashboard` |
| **AWS EC2** | `http://EC2공인IP:8000/dashboard` |
| **Render** | `https://voiceguide-xxx.onrender.com/dashboard` |

> 👉 무료 외부 서버 배포 방법: [docs/DEPLOY_GUIDE.md](docs/DEPLOY_GUIDE.md)  
> GCP, AWS, Oracle Cloud, Render 전부 **무료**로 배포 가능합니다.

### 기능

| 기능 | 설명 |
|------|------|
| **실시간 물체 목록** | 탐지된 물체를 위험도(🔴위험·🟡주의·🟢안전)별 카드로 표시 |
| **GPS 지도** | 현재 위치 + 이동 경로(polyline) 실시간 표시 |
| **2초 자동 갱신** | 앱이 서버에 요청할 때마다 자동 업데이트 |
| **세션 전환** | WiFi SSID 입력으로 복수 기기 모니터링 |

### 외부 서버 배포 후 앱 연결

1. Android 앱 서버 URL 입력창에 아래 URL 입력:
   ```
   https://voiceguide-135456731041.asia-northeast3.run.app
   ```
2. 앱 실행 → 대시보드: `/dashboard` 접속

---

## 프로젝트 한 줄 요약

카메라로 주변을 찍으면 **"왼쪽 바로 앞에 의자가 있어요. 오른쪽으로 비켜보세요."** 처럼  
방향·거리·행동 지침을 한국어로 즉시 음성 안내하는 시각장애인 보행 보조 앱입니다.

---

## 문제 정의

기존 AI 서비스(Google Lookout, Seeing AI)는 물체를 **설명**하지만 **행동을 안내하지 않습니다.**

| 서비스 | 출력 예시 | 한계 |
|--------|---------|------|
| Google Lookout | "의자가 있습니다" | 방향·거리 없음 |
| Microsoft Seeing AI | "왼쪽에 의자가 있습니다" | 행동 안내 없음 |
| **VoiceGuide** | "왼쪽 바로 앞에 의자가 있어요. 오른쪽으로 비켜보세요." | ✓ |

> **"시각장애인이 실내외 이동 중 장애물의 위치와 회피 방향을 즉각적으로 안내받지 못하고 있으므로, 카메라와 음성 명령을 결합한 행동 중심 안내 서비스가 필요하다."**

---

## 차별점

```
기존 서비스 : 환경을 설명한다
VoiceGuide : 환경을 기억하고, 행동을 안내하며, 장소를 기억한다
```

| 차별점 | 구현 방식 | 경쟁 서비스 |
|--------|---------|-----------|
| 행동 중심 안내 | 방향 + 거리 + 회피 방향 동시 제공 | Lookout: 방향 없음 |
| **안전 경로 제안** ⭐ | 정면 위험 시 가장 안전한 방향 자동 안내 | 없음 |
| **군중 밀집 경고** ⭐ | 3명+ "사람이 많아요" / 5명+ "매우 혼잡" | 없음 |
| 계단·낙차 감지 | Depth map 12구역 분석 → YOLO 사각지대 보완 | Seeing AI: 없음 |
| **개인 네비게이팅** ⭐ | 장소 저장·찾기 (WiFi SSID 기반) | 없음 |
| 완전 오프라인 | 서버 없이 폰 단독 ONNX 추론 | 대부분 클라우드 의존 |
| 공간 기억 | 재방문 시 변화만 안내 (매번 같은 설명 반복 X) | 없음 |
| 한국어 특화 | 받침 유무 조사 자동화, 자연스러운 구어체 | 영어 위주 |

---

## 기능 현황

> 발표 기준: **동작 확인** = APK에서 실제로 확인 가능 / **실험 기능** = 동작하나 오탐·정확도 미검증 / **예정 기능** = 구현됐으나 발표 범위 외

### 동작 확인 (발표에서 시연 가능)

| 기능 | 트리거 / 동작 | 출력 예시 |
|------|-------------|---------|
| 장애물 음성 안내 | 1초 자동 캡처 | "오른쪽 앞에 의자가 있어요. 왼쪽으로 피해가세요." |
| `장애물` 모드 | "앞에 뭐 있어", "주변 알려줘" | 위험도별 안내 |
| `찾기` 모드 | "의자 찾아줘", "가방 어디있어" | "의자는 왼쪽 가까이에 있어요." |
| `질문` 모드 ⭐ | "지금 뭐가 있어", "지금 어때" | tracker 누적 + 현재 프레임 합산 즉시 응답 |
| `확인` 모드 | "이거 뭐야" | 정면 물체 설명 |
| `저장` 모드 ⭐ | "여기 저장해줘 편의점" | "편의점을 저장했어요." |
| `위치목록` 모드 ⭐ | "저장된 곳 알려줘" | "저장된 장소는 편의점, 화장실이에요." |
| 차량 긴급 경고 | 차량 8m 이내 자동 | "위험! 오른쪽 자동차! 멈추세요!" |
| 경고 계층 분리 ⭐ | 자동 | critical/beep/silent 3단계 |
| 온디바이스 독립 동작 ⭐ | 서버 URL 없이 | 폰 단독 ONNX 추론 |
| 공간 기억 | 재방문 자동 | "의자가 생겼어요." |
| 어두움 경고 | 조도 센서 자동 | "주변이 많이 어두워요." |
| 다시읽기 / 볼륨 / 중지 | "다시 읽어줘", "소리 크게" | 즉시 처리 |

### 실험 기능 (동작하나 발표에서 과장 주의)

| 기능 | 주의사항 |
|------|---------|
| 계단·낙차 감지 | 실내 오탐률 높음 — "대략적인 안내"임을 명시 |
| 거리 수치 안내 | 단안 카메라 기반 근사치 — "약 Xm"으로 표현 |
| 군중 경고 | 3명 이상 감지 시 동작, 인원 수 부정확 가능 |
| 신호등 색상 감지 | 조도·각도 의존적, 역광 시 미동작 |
| 버스 번호 OCR | 측면·야간·흔들림에서 인식 불안정 |
| 안전 경로 제안 | 단순 좌우 판단, 복잡한 경로는 미지원 |

### 예정 기능 (발표 범위 외 — 시연하지 않음)

| 기능 | 현황 |
|------|------|
| 옷 매칭 (GPT Vision) | API 키 필요, 비용 발생 |
| 낙상 감지 → SOS | 가속도 임계값 미검증 |
| 약 복용 알림 | 알림 UI 미완성 |
| 하차 알림 | GPS 정확도 테스트 필요 |
| 바코드 인식 | 라이브러리 통합 미완성 |
| 점자 블록 경고 | 학습 데이터 부족 |

> ⭐ 경쟁 서비스(Google Lookout, Seeing AI)에 없는 차별 기능

---

## 앱 설치 및 사용

> **컴퓨터 연결 없이 폰 하나로 동작합니다.**

### APK 설치 (딱 한 번만)

| 방법 | 설명 |
|------|------|
| **A. APK 파일 받기 (권장)** | 팀장에게 카카오톡/구글드라이브로 APK 받기 → 폰에서 열기 → 설치 |
| B. 직접 빌드 | Android Studio → `android/` 폴더 → ▶ Run |
| C. USB 케이블 | 폰 USB 연결 → USB 디버깅 ON → Android Studio Run |

> 설치 시 "출처를 알 수 없는 앱 허용" 필요 (설정 → 보안)

### 앱 사용

```
앱 실행 → "분석 시작" 버튼 (서버 URL 비워도 됨)
→ 카메라가 1초마다 자동 분석
→ "바로 앞에 의자가 있어요. 멈추세요." 음성 출력
```

| 상황 | 동작 |
|------|------|
| 서버 URL 비움 | 폰 단독 ONNX 추론 (완전 오프라인) |
| 서버 URL 입력 | 같은 WiFi PC 서버와 연동 → 거리 추정 더 정확 |

---

## 인식 대상 (COCO 80클래스 기반 — 오인식 빈번 클래스 제외)

COCO 80클래스를 기반으로 하며, 실환경 테스트에서 오인식이 빈번한 클래스(계단·노트북·냉장고·인형)는 제외했습니다.  
`YOLO_WORLD=1` 환경변수로 **전동킥보드·볼라드·맨홀** 등 한국 특화 클래스도 추가 탐지 가능합니다.

| 환경 | 카테고리 | 주요 클래스 | 위험도 배수 |
|------|---------|-----------|-----------|
| **야외** | 이동 차량 | 자동차·오토바이·버스·트럭·기차·비행기·보트 | **3.0~4.0×** |
| **야외** | 이동 수단 | 자전거·스케이트보드 | 2.0× |
| **야외** | 교통 시설 | 신호등·소화전·정지 표지판·주차 미터기 | 0.6~1.2× |
| **야외** | 동물 | 개·고양이·말·소·새·양·코끼리·곰·얼룩말·기린 | 1.2~4.0× |
| **실내외** | 날카로운 물체 | 칼·가위·유리잔·야구 방망이 | **1.5~2.5×** |
| **실내외** | 대형 가구·구조물 | 의자·소파·테이블·침대·벤치·화분 | 1.0× |
| **실내외** | 바닥 장애물 | 배낭·핸드백·여행가방·우산·공·원반 | 1.0~1.4× |
| **실내외** | 미끄럼 위험 | 바나나·음식류 (바닥에 있으면 감지) | 1.0× |
| **실내외** | 확인용 | 휴대폰·병·컵·책·시계 | 0.5~1.0× |
| **YOLO-World** ⭐ | 한국 특화 | 전동킥보드·볼라드·맨홀·에스컬레이터 | 활성화 시 |

> 계단은 YOLO 단독 탐지 시 오탐률이 높아 **서버 연결 시 Depth 맵 12구역 분석**으로 감지합니다.

---

## 현재 구현 완료 목록 (2026-04-28 기준)

### AI·비전

| 기능 | 상태 | 상세 |
|------|------|------|
| YOLO11m **COCO80 기반** | ✅ | 오인식 빈번 클래스(계단·노트북·냉장고·인형) 제외 → 80클래스 운영 |
| 9방향 시계 방향 판단 | ✅ | 8시~4시, 위험도 가중치 |
| 차량·동물·날카로운 물체 위험도 강화 | ✅ | 차량 3-4×, 동물 1.2-4×, 칼 2.5× |
| **온디바이스 Voting 버퍼** ⭐ | ✅ | 최근 3프레임 2회 이상 등장한 사물만 안내 (오탐 차단) |
| **거리 기반 음성/비프 분리** ⭐ | ✅ | 가까이→음성 안내, 멀리→비프 (경고 피로 방지) |
| Depth Anything V2 거리 추정 | ✅ | GPU 자동 감지, bbox 면적 기반 fallback |
| 깊이 맵 계단·낙차·턱 감지 | ✅ (서버) | 바닥 12구역 분석 |
| **안전 경로 제안** ⭐ | ✅ | 정면 위험 시 가장 안전한 방향 자동 안내 |
| **군중 밀집 경고** ⭐ | ✅ | 3명+ "사람 많아요", 5명+ "매우 혼잡" |
| **위험 물체 경고** ⭐ | ✅ | 칼·가위 3m 이내 시 즉시 경고 |
| **YOLO-World 확장** ⭐ | ✅ | `YOLO_WORLD=1`로 전동킥보드·볼라드 등 추가 |
| 객체 추적 (EMA) | ✅ | 프레임 간 jitter 제거, 접근·소멸 감지 |

### 서버·API

| 기능 | 상태 | 상세 |
|------|------|------|
| FastAPI `/detect` | ✅ | 질문 포함 6모드 + scene_analysis + GPS 저장 |
| **질문 모드** ⭐ | ✅ | tracker 누적 + 현재 프레임 합산 즉시 응답 |
| **보팅 경고 피로 방지** ⭐ | ✅ | VotingBuffer 10프레임 다수결, critical은 즉시 통과 |
| **TTS 중복 억제** ⭐ | ✅ | 서버 5초 dedup + Android 3초 periodic 억제 |
| **개인 네비게이팅 API** ⭐ | ✅ | POST/GET/DELETE `/locations/*` |
| **GPS 위치 저장** ⭐ | ✅ | `/detect` lat/lng → `gps_history` DB → 대시보드 지도 |
| **`/status/{session_id}`** ⭐ | ✅ | tracker 상태 + GPS 경로 반환 (대시보드 폴링용) |
| **`/dashboard`** ⭐ | ✅ | 실시간 지도 대시보드 HTML — Leaflet.js 다크 테마 |
| **`/health`** ⭐ | ✅ | Depth V2 로드 상태 + DB 모드(SQLite/PostgreSQL) 확인 |
| **Supabase 외부 DB** ⭐ | ✅ | `DATABASE_URL` 설정 시 PostgreSQL 자동 전환 (LTE 지원) |
| 공간 기억 DB | ✅ | SQLite/Supabase, WiFi SSID 기반 재방문 변화 감지 |
| 서버 워밍업 | ✅ | 첫 요청 지연 없음 |
| 전역 예외 핸들러 | ✅ | 오류 시에도 음성 안내 반환 |
| Gradio 데모 | ✅ | 바운딩 박스 시각화, 추론 시간 표시 |
| **서버 테스트** ⭐ | ✅ | `tests/test_server.py` — 9개 엔드포인트 자동 테스트 |

### Android 앱

| 기능 | 상태 | 상세 |
|------|------|------|
| **완전 독립 동작** ⭐ | ✅ | 서버 URL 없이 즉시 실행 |
| **ONNX 온디바이스 추론** | ✅ | **yolo11n.onnx** (앱 내장, 10.7MB 경량) — 서버 URL 입력 시 YOLO11m PyTorch 서버 우선 사용 |
| CameraX 1초 자동 캡처 | ✅ | 즉시 첫 캡처 |
| **TTS AtomicBoolean 완전 잠금** ⭐ | ✅ | 동시 TTS 원천 차단, 차량만 즉시 끊고 재생 |
| **거리 기반 음성/비프 분리** ⭐ | ✅ | 가까이→음성, 멀리→비프 (경고 피로 방지) |
| **온디바이스 Voting 버퍼** ⭐ | ✅ | 3프레임 2회 이상 등장한 사물만 안내 (오탐 차단) |
| Android TTS | ✅ | 한국어, 기본 1.1× / critical 경고 시 1.25× / 발화 후 700ms 침묵 |
| STT 음성 명령 (전체 모드) | ✅ | 장애물/찾기/질문/텍스트/바코드/신호등/색상 외 20개+ |
| STT 미인식 fallback | ✅ | 어떤 말을 해도 기본 장애물 모드로 동작 |
| **개인 네비게이팅** ⭐ | ✅ | 장소 저장·목록·재방문 자동 알림 (WiFi SSID 기반) |
| 카메라 방향 자동 감지 | ✅ | 가속도 센서 → front/left/right/back |
| Failsafe + Watchdog | ✅ | 3회 실패 경고, 6초 무응답 경고 |
| **바운딩박스 오버레이** ⭐ | ✅ | 온디바이스 탐지 결과를 카메라 프리뷰 위에 실시간 시각화 |

### 문서·도구

| 파일 | 내용 |
|------|------|
| `docs/LEARN.md` | 팀원 공부용 코드 주석 가이드 |
| `docs/TEAM_BRIEFING.md` | 발표 대본 + Q&A 대비 + 리스크 대응 |
| `docs/PRESENTATION.md` | 경쟁사 비교 + APK 설치 방법 |
| `tools/benchmark.py` | 자동 성능 측정 |
| `data/test_images/` | 41개 카테고리 폴더 (실내외 전체) |

---

## 빠른 시작 (서버 + ngrok 외부 접속)

> Android 앱만 쓸 때는 이 단계 불필요 — SETUP.md → APK 설치만 하면 됨.

### 한 번에 시작 (권장)

```bat
REM 1. 처음 1회만: 의존성 설치
conda activate ai_env
pip install -r requirements.txt
python tools/patch_gradio_client.py

REM 2. 매번: 서버 + ngrok 동시 실행 (CMD 창 2개 자동 열림)
start.bat
```

`start.bat` 실행 시 자동으로:
1. `VoiceGuide-Server` 창 — FastAPI 서버 (`:8000`)
2. `VoiceGuide-ngrok` 창 — ngrok 터널 (외부 URL 생성)

```bat
REM 종료 시
stop.bat
```

### 수동 실행 (개별)

```bash
# 창 1: FastAPI 서버
conda activate ai_env
uvicorn src.api.main:app --host 0.0.0.0 --port 8000

# 창 2: ngrok 외부 터널
ngrok http 8000
# → Forwarding https://xxxx.ngrok-free.app 로 표시된 URL을 앱에 입력
```

### 환경변수 (.env)

```bash
# 없어도 동작, 필요 시만 설정
ELEVENLABS_API_KEY=    # TTS 품질 향상 (없으면 gTTS 자동 사용)
DATABASE_URL=          # Supabase PostgreSQL (없으면 SQLite 자동 사용)
```

### Depth V2 모델 (선택, 없으면 bbox 거리 추정 fallback)

```bash
python -c "
import urllib.request
urllib.request.urlretrieve(
    'https://huggingface.co/depth-anything/Depth-Anything-V2-Small/resolve/main/depth_anything_v2_vits.pth',
    'depth_anything_v2_vits.pth')
print('완료')
"
```

### 앱 연결

| 환경 | 서버 URL |
|------|---------|
| 같은 WiFi (로컬) | `http://192.168.x.x:8000` (`ipconfig`로 확인) |
| 외부 접속 (ngrok) | `start.bat` → ngrok 창의 `Forwarding https://...` URL |
| 외부 서버 | Railway/GCP 배포 후 URL — [DEPLOY_GUIDE.md](docs/DEPLOY_GUIDE.md) |

```bash
# 헬스체크
http://서버IP:8000/health
# → {"status":"ok","depth_v2":"loaded","db":"ok","db_mode":"sqlite"}

# 대시보드
http://서버IP:8000/dashboard

# 성능 로그 확인 (서버 터미널)
# [PERF] detect=Xms | tracker=Yms | nlg+rest=Zms | TOTAL=Wms | objs=N
```

---

## 전체 파이프라인 (구현 완료)

```
[사용자 음성 입력]
    ↓ STT 5모드 키워드 매칭 (문수찬) — 미인식 시 장애물 모드 fallback
[모드 선택: 장애물 / 찾기 / 확인 / 저장 / 위치목록]
    ↓
[저장·위치목록 모드] → 이미지 불필요, SharedPreferences 즉시 처리 (정환주)
    ↓
[카메라 1초 자동 캡처] ─────────────────────── (정환주: Android)
    ↓
[YOLO11m 80클래스 탐지] ────────────────────── (김재현)
  ├─ COCO80 (계단 오탐률 문제로 제외 → Depth 맵으로 대체)
  ├─ 9구역 시계방향 판단, 클래스별 위험도 배수
  └─ scene_analysis: 안전경로·군중·위험물체 분석
    ↓
[Depth Anything V2 거리 추정] ──────────────── (문수찬)
  ├─ GPU 실시간 추론, 보수 추정(하위 30%)
  └─ bbox 면적 기반 fallback (모델 없을 때)
    ↓
[계단·낙차·턱 Depth 감지] ──────────────────── (문수찬)
  └─ 바닥 12구역 깊이 변화 분석
    ↓
[EMA 객체 추적 + 공간 기억] ────────────────── (신유득)
  ├─ 프레임 jitter 제거 (α=0.55)
  └─ WiFi SSID 기반 재방문 변화 감지
    ↓
[문장 생성] ────────────────────────────────── (임명광)
  ├─ 긴박도 4단계 (0.5m/1m/2.5m 분기)
  ├─ 차량·동물 전용 긴급 문장
  └─ 안전경로·군중·위험물체 경고 추가
    ↓
[Android TTS 음성 출력] ────────────────────── (정환주)
  └─ 속도 1.1배, 같은 문장 반복 방지
```

---

## 모듈별 기술 명세 (구현 완료 기준)

### MODULE A: Android 앱
**담당**: 정환주 (조장) | **브랜치**: `feature/android`  
**파일**: `android/app/src/main/java/com/voiceguide/`

```kotlin
// MainActivity.kt — 핵심 흐름
CameraX 1초 자동 캡처
  → YoloDetector.kt (ONNX Runtime, yolo11m.onnx)  // 온디바이스, 서버 불필요
  → SentenceBuilder.kt (한국어 문장 생성)
  → Android TextToSpeech (한국어, 속도 1.1배)

// STT 5모드 (장애물/찾기/확인/저장/위치목록)
SpeechRecognizer (ko-KR) → classifyKeyword()
  → 저장·위치목록: 이미지 없이 SharedPreferences 즉시 처리
  → 찾기: findTarget 추출 → SentenceBuilder.buildFind()

// 개인 네비게이팅 (SharedPreferences JSON 저장)
"여기 저장해줘 편의점" → saveLocation("편의점", wifiSsid)
"저장된 곳 알려줘"    → getLocations() → TTS 읽어줌

// Failsafe + Watchdog
연속 3회 실패 → "서버 연결 끊겼어요. 주의해서 이동하세요."
6초 무응답   → "분석이 중단됐어요. 주의해서 이동하세요."
```

| 라이브러리 | 용도 |
|-----------|------|
| CameraX | 카메라 라이프사이클 관리 |
| ONNX Runtime Android | 온디바이스 YOLO 추론 |
| Android SpeechRecognizer | STT (오프라인 언어팩 지원) |
| Android TextToSpeech | TTS (완전 오프라인) |
| OkHttp | 서버 연동 (선택 사항) |
| WifiManager | WiFi SSID 수집 |

---

### MODULE B: FastAPI 서버 (허브)
**담당**: 신유득 | **브랜치**: `feature/api`  
**파일**: `src/api/main.py`, `src/api/routes.py`, `src/api/db.py`, `src/api/tracker.py`

```python
# 메인 탐지 API (5모드 처리 + scene_analysis 포함)
POST /detect
  Body: image, wifi_ssid, camera_orientation, mode, query_text
  Returns: { sentence, objects, hazards, scene, changes, depth_source }

# 개인 네비게이팅 ⭐
POST   /locations/save         # WiFi SSID + 장소 이름 저장
GET    /locations              # 저장된 장소 목록
GET    /locations/find/{label} # 장소 검색 + 현재 위치 일치 여부
DELETE /locations/{label}      # 장소 삭제
```

```sql
CREATE TABLE snapshots (id, space_id, timestamp, objects);
CREATE TABLE saved_locations (id, label, wifi_ssid, timestamp);  -- 개인 네비게이팅
```

```python
# EMA 객체 추적기 (tracker.py)
alpha = 0.55  # 현재 55% + 이전 45% → jitter 제거
# 접근 감지: 0.4m 이상 가까워지고 2.5m 이내 → "가방이 가까워지고 있어요"
```

---

### MODULE C: YOLO 탐지 + 방향/위험도
**담당**: 김재현 | **브랜치**: `feature/vision`  
**파일**: `src/vision/detect.py`

```python
def detect_objects(image_bytes: bytes) -> tuple[list[dict], dict]:
    # COCO80 기반 80클래스 (계단 오탐률 높아 제외 → Depth 맵으로 대체)
    # 클래스별 위험도 배수: 차량 3~4×, 동물 1.2~4×, 칼 2.5×
    # 야외 차량: conf 0.38로 멀리서도 일찍 감지 (안전 우선)
    # scene_analysis: 안전경로·군중·위험물체 분석 반환
```

---

### MODULE D: Depth 거리 추정 + STT/TTS
**담당**: 문수찬 | **브랜치**: `feature/voice`  
**파일**: `src/depth/depth.py`, `src/depth/hazard.py`, `src/voice/stt.py`, `src/voice/tts.py`

```python
def detect_and_depth(image_bytes) -> tuple[list[dict], list[dict], dict]:
    # Depth Anything V2: GPU 자동 감지, 보수 추정(하위 30%), 5단계 거리
    # hazard.py: 바닥 12구역 분석 → 낙차/계단/턱 감지

# STT: 5모드, 키워드 15개+, 미매칭 시 장애물 fallback
# TTS: gTTS → MD5 해시 캐시 → pygame 재생
```

---

### MODULE E: 문장 생성 + 발표
**담당**: 임명광 | **브랜치**: `feature/nlg`  
**파일**: `src/nlg/sentence.py`, `src/nlg/templates.py`

```python
# 긴박도 4단계: 0.5m 미만 → "위험!" / 1m → 긴급 / 2.5m → 경고 / 이상 → 정보
# 차량: 8m 이내 "위험! 즉시 멈추세요!" / 동물: "조심! 천천히 피해가세요."
# 안전경로·군중·위험물체 scene_analysis 결과를 문장으로 변환
# 한국어 조사 자동화: 의자가/책이, 의자는/책은, 의자를/책을
```

---

### 전체 파이프라인 코드 (정환주 통합)

```python
# src/api/routes.py — /detect 흐름
objects, hazards, scene = detect_and_depth(image_bytes)   # C+D
objects, motion_changes = tracker.update(objects)          # B
space_changes = _space_changes(objects, db.get_snapshot()) # B
sentence = build_sentence(objects, all_changes)            # E
# 안전경로·군중·위험물체 경고 추가
extras = [v for v in [scene.get("danger_warning"),
                      scene.get("crowd_warning"),
                      scene.get("safe_direction")] if v]
if extras: sentence += " " + " ".join(extras)

return { sentence, objects, hazards, scene, changes }
```

---

## 폴더 구조

```
VoiceGuide/
├── README.md              프로젝트 개요 (이 파일)
├── SETUP.md               실기기 데모 실행 가이드
├── app.py                 Gradio 데모 (발표·시연용)
├── requirements.txt
│
├── src/
│   ├── vision/detect.py        YOLO11m 80클래스 탐지 + 방향/위험도 + ALWAYS_CRITICAL
│   ├── depth/depth.py          Depth Anything V2 거리 추정 (bbox fallback 포함)
│   ├── depth/hazard.py         계단/낙차/턱 감지
│   ├── voice/stt.py            STT (질문 포함 6모드, 키워드 23가지+)
│   ├── voice/tts.py            TTS (gTTS + Naver Clova 자동 전환)
│   ├── nlg/sentence.py         한국어 문장 생성 (build_question_sentence 포함)
│   ├── nlg/templates.py        시계방향·행동 템플릿
│   ├── api/routes.py           /detect(질문모드) /status /dashboard /health /locations
│   ├── api/db.py               SQLite↔Supabase 자동 전환 (DATABASE_URL 기반)
│   ├── api/tracker.py          EMA 추적기 + VotingBuffer + get_current_state()
│   └── api/main.py             FastAPI 앱 + /health 엔드포인트
│
├── android/
│   └── app/src/main/java/com/voiceguide/
│       ├── MainActivity.kt         카메라+STT+TTS+GPS+질문모드+suppressPeriodic
│       ├── BoundingBoxOverlay.kt   탐지 결과 바운딩박스 오버레이
│       ├── StairsDetector.kt       계단 전용 감지기 (미사용 — 오탐률 높아 Depth 맵으로 대체)
│       ├── YoloDetector.kt         온디바이스 ONNX 추론 (letterbox 좌표 보정)
│       ├── SentenceBuilder.kt      온디바이스 문장 생성
│       └── VoiceGuideConstants.kt  클래스명·방향·STT 키워드 상수
│
├── templates/
│   └── dashboard.html         실시간 지도 대시보드 (Leaflet.js, 다크 테마)
│
├── 서버_DB/               Supabase/PostgreSQL FastAPI 서버 (신유득)
│   ├── main.py            items CRUD + /detect DB 저장 엔드포인트
│   └── SUPABASE_DB_CONNECT_GUIDE.md
│
├── .env                   환경변수 (DATABASE_URL, API 키 등)
│
├── tools/
│   ├── benchmark.py       성능 자동 실험
│   ├── verify.py          라이브러리 설치 검증
│   ├── export_onnx.py     YOLO → ONNX 변환
│   └── patch_gradio_client.py  gradio_client 버그 패치 (1회)
│
├── tests/
│   ├── test_server.py     서버 9개 엔드포인트 자동 테스트
│   └── ...                기타 pytest 테스트
├── train/                 파인튜닝 파이프라인
├── docs/
│   ├── DEPLOY_GUIDE.md    무료 외부 서버 배포 가이드 (Railway/GCP/AWS/Oracle/Render)
│   ├── CHANGELOG.md       날짜별 변경 이력
│   ├── MEETING_0428_결과.md  4/28 강사님 미팅 피드백 + 구현 결과
│   ├── troubleshooting.md  오류 해결 + 기술 스택
│   └── ...                기타 문서
└── data/test_images/      41개 카테고리 테스트 이미지 폴더
```

---

## 타임라인

> 조장(정환주)이 전체 파이프라인을 선행 구현하고, 팀원들이 각자 모듈을 검증·보완하는 방식으로 진행합니다.

### 조장(정환주) 구현 현황

| 날짜 | 정환주 (조장) — 완료 내용 |
|------|----------------------|
| 4/24 ✅ | Android 개발환경 + 카메라 캡처 / FastAPI + Gradio MVP / YOLO11m 방향 판단 9구역 / gTTS TTS / 한국어 문장 템플릿 설계 |
| 4/25 ✅ | CameraX 1초 캡처 + ONNX 온디바이스 / EMA 객체 추적기 + SQLite 공간 DB + /detect API / **계단 파인튜닝 mAP50=0.992** / **Depth Anything V2 서버 통합** + 계단·낙차 감지 / NLG 긴박도 4단계 + 조사 자동화 |
| **4/26 ✅🔥** | **Android 독립 앱 완성** (서버 없이 동작) + failsafe / **개인 네비게이팅** API + Android SharedPreferences / **COCO80→81 전체** + YOLO-World 스텁 / **STT 5모드** + 키워드 15개+ + fallback / 안전경로·군중 경고 / docs 전체 (LEARN.md, TEAM_BRIEFING.md 등) |
| **4/27 ✅** | 팀원 브랜치 merge + 선택 반영 / **API 키 보안** (.env + git 히스토리 제거) / requirements 누락 패키지 추가 / **alert_mode** Android 반영 (critical 1.25× / beep / silent) / TTS 캐시 워밍업 |
| **4/28 ✅🔥** | **강사님 미팅 피드백 전체 즉일 구현** — `"질문"` STT 모드 + tracker 즉시 응답 / **VotingBuffer** 10프레임 다수결 경고 피로 / TTS 5초 dedup + Android 3초 억제 / **GPS + 실시간 대시보드** (Leaflet.js) / **Supabase 외부 DB** 연동 (LTE 지원) / **Railway 배포** 설정 / `/health` 엔드포인트 / feature/nlg PR conflict 해결 → merge / 서버 9개 엔드포인트 테스트 스크립트 |

### 팀원별 담당 및 예정 일정

| 날짜 | 신유득 (서버 검증) | 김재현 (YOLO 검증) | 문수찬 (음성 검증) | 임명광 (발표) |
|------|------|------|------|------|
| **4/27 ✅** | 서버 end-to-end 동작 확인 | 테스트 이미지 수집 시작 | **gTTS → ElevenLabs TTS 교체** (Anna Kim 보이스) | **NLG 개선** — `get_alert_mode()` 경고 피로 방지, 문구 자연스럽게 수정 |
| 4/28 | 서버 안정화·예외 처리 검증 | 인식률 측정 + 오인식 정리 | Depth 임계값 튜닝 | 경쟁 서비스 비교표 |
| 4/29 | 공간 기억 연동 테스트 | 위험도 파라미터 검증 | TTS 발음 개선 | 기술 슬라이드 |
| 4/30 | ngrok 외부 접근 확인 | 테스트 이미지 추가 수집 | STT 소음 재테스트 | 데모 스크립트 |
| 5/1~5/2 | 서버 통합 안정화 | 전체 클래스 인식률 정리 | 음성 흐름 점검 | PPT 본문 완성 |
| 5/6~5/7 | 서버 문서화 | 최종 인식률 데이터 정리 | 함수 최종 완성 | 발표 대본 완성 |

### 전체 마감 일정

| 날짜 | 내용 |
|------|------|
| 5/8 | **전체 통합 테스트 + 오류 수정** |
| 5/9 | **데모 영상 최종 녹화** |
| 5/12 | **발표 리허설 1~2회** |
| 5/13 | **최종 발표** |

---

## 팀 구성 및 역할

| 멤버 | 역할 | 담당 모듈 | 주요 산출물 |
|------|------|---------|-----------|
| **정환주 (조장)** | Android 앱 + 전체 아키텍처 | `android/`, 파이프라인 통합 | 완전 독립 Android 앱 |
| **신유득** | FastAPI 서버 허브 | `src/api/` | /detect API + DB + 모듈 통합 |
| **김재현** | YOLO + 방향/위험도 | `src/vision/` | 80클래스 탐지 + 위험도 파라미터 |
| **문수찬** | Depth + 음성 | `src/depth/`, `src/voice/` | Depth V2 + STT/TTS |
| **임명광** | 문장 생성 + 발표 | `src/nlg/` | NLG + PPT |

---

## 팀 내 함수 인터페이스

```python
# C+D가 작성 → B가 호출
def detect_and_depth(image_bytes: bytes) -> tuple[list[dict], list[dict], dict]:
    # objects: [{class_ko, direction, distance_m, risk_score, is_vehicle, ...}]
    # hazards: [{type, distance_m, message, risk}]
    # scene:   {safe_direction, crowd_warning, danger_warning, person_count}

# E가 작성 → B가 호출
def build_sentence(objects, changes, camera_orientation="front") -> str:
    # "왼쪽 바로 앞에 의자가 있어요. 오른쪽으로 비켜보세요."
```

---

## Git 브랜치 전략

```
main ← 현재 작업 브랜치
  └── develop
        ├── feature/android   (정환주)
        ├── feature/api       (신유득)
        ├── feature/vision    (김재현)
        ├── feature/voice     (문수찬)
        └── feature/nlg       (임명광)
```

**커밋 메시지 컨벤션**
```
feat(vision): YOLO 방향 판단 로직 추가
fix(api):     /detect 핸들러의 오류 수정
docs(nlg):    문장 템플릿 추가
```

---

## 성공 지표

| 지표 | 목표 | 측정 방법 |
|------|------|---------|
| 탐지 성공률 | 100% | 80클래스 + Depth V2 / 미탐지 시 bbox fallback |
| 음성 응답 시간 | 3초 이내 | 이미지 입력 → 음성 출력 측정 |
| STT 인식률 | 100% | 5모드 × 키워드 15개+ / 미매칭 시 장애물 fallback |
| 방향 판단 정확도 | 100% | 8시~4시 9구역 결정론적 분류 |
| 개인 네비게이팅 | 100% | WiFi SSID 기반 장소 저장·찾기·목록 |

---

## 공모전 연계

```
부트캠프 팀 데모 (5/13)
    ↓ 결과물 재활용
2026 국민행복 서비스 발굴·창제 경진대회 (6/1 마감)
    - 주제: "사회보장 + AI 기술 융합 서비스"
    - 포스터 예시: "시각장애인용 지능형 웨어러블 가이드" 직접 언급
    - 추가 작업: 사업계획서
```

---

## 비상 플랜

| 상황 | 대응 |
|------|------|
| Android 데모 실패 | Gradio 데모로 대체 |
| 서버 배포 실패 | ngrok 로컬 서버로 대체 |
| Depth V2 모델 파일 없을 경우 | bbox 면적 비율 자동 fallback |
| STT 불안정 | 버튼 입력으로 즉시 대체 |

---

## 참고 자료

### AI 모델

| 자료 | 링크 |
|------|------|
| Depth Anything V2 (NeurIPS 2024) | [depth-anything-v2.github.io](https://depth-anything-v2.github.io) |
| Depth Anything V2 논문 | [arxiv.org/abs/2406.09414](https://arxiv.org/abs/2406.09414) |
| Depth Anything V2 모델 가중치 | [huggingface.co/depth-anything](https://huggingface.co/depth-anything/Depth-Anything-V2-Small) |
| YOLO11 공식 문서 | [docs.ultralytics.com/models/yolo11](https://docs.ultralytics.com/models/yolo11/) |
| YOLO11 GitHub | [github.com/ultralytics/ultralytics](https://github.com/ultralytics/ultralytics) |
| Apple Depth Pro (ICLR 2025) | [machinelearning.apple.com/research/depth-pro](https://machinelearning.apple.com/research/depth-pro) |

### Android 구현

| 자료 | 링크 |
|------|------|
| Depth Anything Android (ONNX) | [github.com/shubham0204/Depth-Anything-Android](https://github.com/shubham0204/Depth-Anything-Android) |
| ONNX Runtime Android 가이드 | [onnxruntime.ai/docs/tutorials/mobile](https://onnxruntime.ai/docs/tutorials/mobile/) |
| CameraX 공식 문서 | [developer.android.com/training/camerax](https://developer.android.com/training/camerax) |

### 사용자 조사 · 논문

| 자료 | 링크 |
|------|------|
| UC Davis 사용자 조사 (2024) — 행동 안내 부재가 핵심 불편 | [arxiv.org/abs/2504.06379](https://arxiv.org/abs/2504.06379) |
| Nature Scientific Reports (2025) — 보조기기 실사용 포기 원인 | [doi.org/10.1038/s41598-025-91755-w](https://doi.org/10.1038/s41598-025-91755-w) |
| VISA 시스템 논문 (J. Imaging 2025) — AR+YOLO+Depth 실내 내비 | [doi.org/10.3390/jimaging11010009](https://doi.org/10.3390/jimaging11010009) |
| WHO 시각장애 통계 — 전 세계 2억 8500만 명 | [who.int/news-room/fact-sheets/detail/blindness-and-visual-impairment](https://www.who.int/news-room/fact-sheets/detail/blindness-and-visual-impairment) |

### 경쟁 서비스

| 서비스 | 링크 |
|--------|------|
| Google Lookout | [lookout.app](https://lookout.app) |
| Microsoft Seeing AI | [microsoft.com/en-us/ai/seeing-ai](https://www.microsoft.com/en-us/ai/seeing-ai) |
| Be My Eyes | [bemyeyes.com](https://www.bemyeyes.com) |

---

## AI 도구 사용 가이드 (팀원용)

이 프로젝트는 팀원 각자가 AI 코딩 도구(Claude, Cursor, Copilot 등)를 사용해 개발합니다.  
AI 도구에 질문할 때 아래 컨텍스트를 프롬프트에 포함하세요.

```
나는 VoiceGuide 프로젝트의 [역할명]을 담당하고 있습니다.
시각장애인을 위한 실내외 장애물 음성 안내 서비스입니다.
기술 스택: Python, YOLO11m(파인튜닝), Depth Anything V2, FastAPI, Android ONNX
내 담당 모듈: [모듈명]
내가 작성해야 할 함수/파일: [파일명 또는 함수명]
```
