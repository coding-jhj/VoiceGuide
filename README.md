# VoiceGuide

> 시각장애인을 위한 AI 음성 주변 인지 서비스  
> KDT AI Human 3팀 | 2026-04-24 ~ 2026-05-13

---

## 🗺️ 실시간 대시보드

서버 실행 후 브라우저에서 바로 열 수 있는 관리자용 지도 대시보드입니다.

```
http://서버IP:8000/dashboard
예) http://192.168.0.10:8000/dashboard
```

| 기능 | 설명 |
|------|------|
| **실시간 물체 목록** | 현재 탐지된 물체를 위험도(위험·주의·안전)별로 카드 표시 |
| **GPS 지도** | 사용자 현재 위치 + 이동 경로(polyline) 실시간 표시 |
| **2초 자동 갱신** | 앱이 서버에 분석 요청할 때마다 자동 업데이트 |
| **세션 전환** | WiFi SSID 입력으로 복수 기기 모니터링 가능 |

> 앱에서 GPS 권한을 허용하면 지도에 이동 동선이 자동으로 표시됩니다.

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

## 핵심 기능 (구현 완료 — 2026-04-27 기준)

### 음성 명령 모드 전체

| 모드 | 트리거 키워드 예시 | 출력 예시 |
|------|----------------|---------|
| `장애물` | "앞에 뭐 있어", "주변 알려줘" | "오른쪽 앞에 의자가 있어요. 가까이. 왼쪽으로 피해가세요." |
| `찾기` | "의자 찾아줘", "가방 어디있어" | "의자는 왼쪽 앞에 있어요. 가까이." |
| `확인` | "이거 뭐야" | "오른쪽에 노트북도 있어요." |
| `저장` ⭐ | "여기 저장해줘 편의점" | "편의점을 저장했어요." |
| `위치목록` ⭐ | "저장된 곳 알려줘" | "저장된 장소는 편의점, 화장실이에요." |
| `텍스트` ⭐ | "글자 읽어줘", "간판 읽어줘" | 카메라 속 텍스트 OCR 후 읽어줌 |
| `바코드` ⭐ | "바코드", "상품 뭐야" | "코카콜라 500ml이에요." |
| `버스번호` ⭐ | "버스 번호 알려줘", "몇 번 버스야" | "37번 버스예요." |
| `버스대기` ⭐ | "37번 버스 기다려줘" | 37번 감지 시 진동+음성 강한 알림 |
| `색상` ⭐ | "색깔 알려줘", "무슨 색이야" | "빨간색이에요." |
| `밝기` | "어두워", "밝기 알려줘" | "현재 밝기는 매우 어두워요." |
| `신호등` ⭐ | "신호등", "건너도 돼" | "신호등이 초록불이에요. 건너도 돼요." |
| `식사` ⭐ | "밥 먹을게", "식사 도와줘" | "왼쪽 앞에 포크가 있어요. 손 뻗으면 닿아요." |
| `옷매칭` ⭐ | "이 옷이랑 어울려", "코디 봐줘" | GPT Vision이 색상·패턴 매칭 조언 |
| `옷패턴` ⭐ | "무슨 무늬야", "패턴 알려줘" | "체크무늬 셔츠예요." |
| `돈` ⭐ | "이 돈 얼마야", "지폐 얼마야" | "10000원권 같아요." |
| `약알림` ⭐ | "8시에 약 먹어야 해" | 매일 8시 약 복용 알림 설정 |
| `하차알림` ⭐ | "하차 알려줘" | GPS 200m 이내 도착 시 알림 |
| `다시읽기` | "다시 읽어줘", "뭐라고" | 방금 안내 문장 다시 읽어줌 |
| `볼륨업/다운` | "소리 크게", "소리 작게" | 미디어 볼륨 조절 |
| `중지/재시작` | "잠깐 멈춰", "다시 시작" | 분석 일시정지 / 재개 |
| `긴급(SOS)` ⭐ | "살려줘", "도와줘" | 진동 + 보호자 SMS 자동 발송 |

### 자동 분석 기능 (음성 명령 없이 자동)

| 기능 | 동작 | 출력 예시 |
|------|------|---------|
| 안전 경로 제안 ⭐ | 정면 위험 시 가장 안전한 방향 자동 안내 | "왼쪽 방향이 가장 안전해요." |
| 군중 경고 ⭐ | 3명 이상 감지 시 밀집 경고 | "사람이 많아요. 천천히 이동하세요." |
| 위험 물체 경고 ⭐ | 칼·가위 3m 이내 즉시 경고 | "위험! 근처에 칼이 있어요! 조심하세요." |
| 차량 긴급 경고 | 차량 8m 이내 접근 시 강화 경고 | "위험! 오른쪽에 자동차가 있어요! 즉시 멈추세요!" |
| 신호등 색상 감지 ⭐ | 빨간불/초록불 자동 구별 | "신호등이 초록불이에요. 건너도 돼요." |
| 점자 블록 경고 ⭐ | 보행 경로 위 자전거·킥보드 감지 | "보행 경로에 자전거가 있어요. 우회하세요." |
| 빠른 접근 경고 ⭐ | 날아오는·떨어지는 물체 감지 | "조심! 공이 빠르게 다가오고 있어요!" |
| 계단·낙차 감지 | Depth 맵 12구역 분석 | "조심! 앞에 계단이나 낙차가 있어요." |
| 울퉁불퉁한 길 감지 ⭐ | 바닥 깊이 분산 분석 | "바닥이 고르지 않아요. 천천히 걸으세요." |
| 공간 기억 | 재방문 시 달라진 것만 안내 | "의자가 생겼어요." |
| 낙상 감지 ⭐ | 가속도 급변 → 10초 무응답 시 SOS | "괜찮으세요? 10초 안에 말씀해 주세요." |
| 어두움 경고 ⭐ | 조도 센서로 어두운 환경 감지 | "주변이 많이 어두워요. 조심하세요." |
| 경고 계층 분리 ⭐ | `critical`/`beep`/`silent` 3단계 — 위험도별 음성·비프·무음 분기 | 위험 시 1.25× 빠르게, 1m 이내 비프음만 |
| 음성 자동 시작 ⭐ | 앱 시작 시 버튼 없이 말로 시작 | "음성 안내를 시작할까요?" |
| Google Assistant 연동 ⭐ | "OK Google, 보이스가이드 열어줘" | 자동 분석 시작 |

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

## 인식 대상 (COCO 80클래스 전체 + 계단 파인튜닝 = 81클래스)

COCO 80클래스를 전부 사용하고 계단을 직접 파인튜닝으로 추가했습니다.  
`YOLO_WORLD=1` 환경변수로 **전동킥보드·볼라드·맨홀** 등 한국 특화 클래스도 추가 탐지 가능합니다.

| 환경 | 카테고리 | 주요 클래스 | 위험도 배수 |
|------|---------|-----------|-----------|
| **야외** | 이동 차량 | 자동차·오토바이·버스·트럭·기차·비행기·보트 | **3.0~4.0×** |
| **야외** | 이동 수단 | 자전거·스케이트보드 | 2.0× |
| **야외** | 교통 시설 | 신호등·소화전·정지 표지판·주차 미터기 | 0.6~1.2× |
| **야외** | 동물 | 개·고양이·말·소·새·양·코끼리·곰·얼룩말·기린 | 1.2~4.0× |
| **실내외** | 날카로운 물체 | 칼·가위·유리잔·야구 방망이 | **1.5~2.5×** |
| **실내외** | 대형 가구·구조물 | 의자·소파·테이블·침대·냉장고·벤치·화분 | 1.0× |
| **실내외** | 바닥 장애물 | 배낭·핸드백·여행가방·우산·공·원반 | 1.0~1.4× |
| **실내외** | 미끄럼 위험 | 바나나·음식류 (바닥에 있으면 감지) | 1.0× |
| **실내외** | 확인용 | 휴대폰·노트북·병·컵·책·시계 | 0.5~1.0× |
| **파인튜닝** | **계단·낙차** | 계단 (mAP50=0.992) | **최우선** |
| **YOLO-World** ⭐ | 한국 특화 | 전동킥보드·볼라드·맨홀·에스컬레이터 | 활성화 시 |

---

## 현재 구현 완료 목록 (2026-04-26 기준)

### AI·비전

| 기능 | 상태 | 상세 |
|------|------|------|
| YOLO11m **COCO80 전체 + 계단** | ✅ | 81클래스, conf 클래스별 차등 적용 |
| **계단 파인튜닝** | ✅ | 404장 학습, mAP50=**0.992** (정밀도 91.7% / 재현율 100%) |
| 9방향 시계 방향 판단 | ✅ | 8시~4시, 위험도 가중치 |
| 차량·동물·날카로운 물체 위험도 강화 | ✅ | 차량 3-4×, 동물 1.2-4×, 칼 2.5× |
| Depth Anything V2 거리 추정 | ✅ | GPU 자동 감지, bbox 면적 기반 fallback |
| 깊이 맵 계단·낙차·턱 감지 | ✅ | 바닥 12구역 분석 |
| **안전 경로 제안** ⭐ | ✅ | 정면 위험 시 가장 안전한 방향 자동 안내 |
| **군중 밀집 경고** ⭐ | ✅ | 3명+ "사람 많아요", 5명+ "매우 혼잡" |
| **위험 물체 경고** ⭐ | ✅ | 칼·가위 3m 이내 시 즉시 경고 |
| **YOLO-World 확장** ⭐ | ✅ | `YOLO_WORLD=1`로 전동킥보드·볼라드 등 추가 |
| 객체 추적 (EMA) | ✅ | 프레임 간 jitter 제거, 접근·소멸 감지 |

### 서버·API

| 기능 | 상태 | 상세 |
|------|------|------|
| FastAPI `/detect` | ✅ | 5모드 처리 + scene_analysis 응답 |
| **개인 네비게이팅 API** ⭐ | ✅ | POST/GET/DELETE `/locations/*` |
| 공간 기억 DB | ✅ | SQLite, WiFi SSID 기반 재방문 변화 감지 |
| 서버 워밍업 | ✅ | 첫 요청 지연 없음 |
| 전역 예외 핸들러 | ✅ | 오류 시에도 음성 안내 반환 |
| Gradio 데모 | ✅ | 바운딩 박스 시각화, 추론 시간 표시 |

### Android 앱

| 기능 | 상태 | 상세 |
|------|------|------|
| **완전 독립 동작** ⭐ | ✅ | 서버 URL 없이 즉시 실행 |
| **ONNX 온디바이스 추론** | ✅ | yolo11m.onnx, 서버 연결 실패 시 자동 전환 |
| CameraX 1초 자동 캡처 | ✅ | 즉시 첫 캡처, 같은 문장 반복 방지 |
| Android TTS | ✅ | 한국어, 기본 1.1× / critical 경고 시 1.25× 자동 전환 |
| STT **5모드 음성 명령** | ✅ | 장애물/찾기/확인/저장/위치목록, 키워드 15개+ |
| STT 미인식 fallback | ✅ | 어떤 말을 해도 기본 장애물 모드로 동작 |
| **개인 네비게이팅** ⭐ | ✅ | SharedPreferences 장소 저장·찾기·목록 |
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

## 빠른 시작 (서버/Gradio 데모 — 발표용 PC)

> Android 앱만 쓸 때는 이 단계 불필요. SETUP.md → APK 설치만 하면 됨.

```bash
git clone https://github.com/coding-jhj/VoiceGuide.git && cd VoiceGuide
conda activate ai_env
pip install -r requirements.txt
python tools/patch_gradio_client.py          # 딱 1회

# Depth V2 모델 다운로드 (94MB, 서버 전용 — 없어도 bbox fallback으로 동작)
python -c "
import urllib.request
urllib.request.urlretrieve(
    'https://huggingface.co/depth-anything/Depth-Anything-V2-Small/resolve/main/depth_anything_v2_vits.pth',
    'depth_anything_v2_vits.pth')
print('완료')
"

python app.py                                # Gradio 데모 (localhost:7860)
python app.py --share                        # 폰에서 접속 가능한 공개 URL
uvicorn src.api.main:app --host 0.0.0.0 --port 8000   # FastAPI 서버
ipconfig   # → IPv4 주소 확인 → 앱에 http://192.168.x.x:8000 입력
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
[YOLO11m 81클래스 탐지] ────────────────────── (김재현)
  ├─ COCO80 전체 + 계단 파인튜닝 (mAP50=0.992)
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
    # COCO80 전체 + 계단 파인튜닝 = 81클래스 (mAP50=0.992)
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
│   ├── vision/detect.py        YOLO11m 81클래스 탐지 + 방향/위험도
│   ├── depth/depth.py          Depth Anything V2 거리 추정
│   ├── depth/hazard.py         계단/낙차/턱 감지
│   ├── voice/stt.py            STT (5모드, 키워드 15개+)
│   ├── voice/tts.py            TTS (ElevenLabs + pygame 캐시, Gradio 데모용)
│   ├── nlg/sentence.py         한국어 문장 생성 (긴박도 4단계, get_alert_mode 포함)
│   ├── nlg/templates.py        시계방향·행동 템플릿
│   ├── api/routes.py           /detect /locations /stt API
│   ├── api/db.py               SQLite (snapshots + saved_locations)
│   └── api/tracker.py          EMA 객체 추적기
│
├── android/
│   └── app/src/main/java/com/voiceguide/
│       ├── MainActivity.kt         카메라+STT+TTS+개인네비게이팅
│       ├── BoundingBoxOverlay.kt   탐지 결과 바운딩박스 오버레이
│       ├── YoloDetector.kt         온디바이스 ONNX 추론
│       ├── SentenceBuilder.kt      온디바이스 문장 생성
│       └── VoiceGuideConstants.kt  클래스명·방향·키워드 상수
│
│
├── 서버_DB/               Supabase/PostgreSQL FastAPI 서버 (신유득, 선택 사항)
│   ├── main.py            items CRUD + /detect DB 저장 엔드포인트
│   └── SUPABASE_DB_CONNECT_GUIDE.md
│
├── tools/
│   ├── benchmark.py       성능 자동 실험
│   ├── verify.py          라이브러리 설치 검증
│   ├── export_onnx.py     YOLO → ONNX 변환
│   └── patch_gradio_client.py  gradio_client 버그 패치 (1회)
│
├── tests/                 pytest 테스트
├── train/                 파인튜닝 파이프라인
├── docs/                  프로젝트 문서 전체
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
| **4/27 ✅** | 팀원 브랜치 merge + 선택 반영 / **API 키 보안** (.env + git 히스토리 제거) / requirements 누락 패키지 추가 (elevenlabs·easyocr·python-dotenv·websockets) / **alert_mode** Android 반영 (critical 1.25× 즉각 끊기 / beep / silent) / TTS 캐시 워밍업 / 문서 전체 업데이트 |

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
| **김재현** | YOLO + 방향/위험도 | `src/vision/` | 81클래스 탐지 + 파인튜닝 |
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
| 탐지 성공률 | 100% | 81클래스 + Depth V2 / 미탐지 시 bbox fallback |
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
