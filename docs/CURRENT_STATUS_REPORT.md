# VoiceGuide 현재 상태 보고서

**작성일**: 2026-05-08  
**프로젝트**: VoiceGuide - 시각장애인 보행 보조 AI 음성 안내 앱  
**현재 기준**: Android 온디바이스 추론 + FastAPI JSON 라우터/대시보드 구조

---

## 1. 현재 구조 요약

VoiceGuide는 서버 추론형 구조에서 온디바이스 우선 구조로 정리되었습니다.

- Android 앱이 CameraX 프레임을 받아 TFLite YOLO를 직접 실행합니다.
- 거리와 위험도는 현재 bbox 크기 기반 보정값과 `VoicePolicy` 기준으로 계산합니다.
- 문장 생성, TTS, 진동, UI 표시는 Android에서 즉시 처리합니다.
- 서버는 이미지/YOLO 추론을 하지 않고, Android가 보낸 JSON을 정규화해 tracker, DB, SSE 대시보드, 이력 조회를 담당합니다.
- `/detect`가 현재 Android의 주 업로드 경로이고, `/detect_json`은 구형 JSON 포맷 및 회귀 테스트 호환용입니다.

---

## 2. 구현된 주요 기능

### Android 앱

| 영역 | 현재 상태 |
|---|---|
| 카메라 | CameraX `ImageAnalysis` 스트림, 필요 시 `ImageCapture` 즉시 캡처 |
| 온디바이스 탐지 | `TfliteYoloDetector.kt`, `yolo11n_320.tflite` 기본, `yolo26n_float32.tflite` fallback |
| 실행 Provider | TFLite GPU FP32 우선, 실패 시 XNNPACK 4 threads fallback |
| 후처리 | raw YOLO 출력과 end-to-end NMS 출력 모두 지원, NMS/IoU 중복 제거 |
| 안정화 | 3프레임 vote, `MvpPipeline` IoU tracking, EMA smoothing, risk score |
| 안내 | `SentenceBuilder.kt` 로컬 한국어 문장 생성, TTS, 진동 패턴, UI 표시 |
| 모드 | 장애물, 찾기, 질문/확인, 들고있는것, 신호등, 다시읽기, 중지/재시작, 볼륨 제어 |
| 서버 연동 | 백그라운드 `POST /detect`, GPS heartbeat `POST /gps` |
| 위치 | 현재 GPS 전송, 이동 경로 저장 API 연동, 앱 내부 장소 저장/조회 |
| 안전 보조 | 조도 센서 기반 어두운 환경 감지, 낙상 의심 후 확인 음성 |

### FastAPI 서버

| 엔드포인트 | 역할 |
|---|---|
| `GET /health` | 서버/DB 상태, DB writer 상태, `inference: disabled` 반환 |
| `GET /api/policy` | `policy.json` 배포, ETag 캐싱, Android client 제한 |
| `POST /detect` | 현재 주 경로. Android 객체 JSON 정규화, tracker 업데이트, NLG, DB enqueue |
| `POST /detect_json` | 구형 detections 포맷 수신, `recent_detections` 저장 |
| `POST /question` | 최근 tracker/DB 상태 기반 질문 응답 |
| `POST /gps` | 현재 위치 저장 및 대시보드 이벤트 publish |
| `GET /status/{session_id}` | 현재 객체, GPS, track, latest_event 조회 |
| `GET /events/{session_id}` | SSE 실시간 대시보드 스트림 |
| `GET /sessions` | 최근 GPS session 목록 조회 |
| `GET /team-locations` | 최근 팀 위치 조회 |
| `POST /locations/save` | 세션별 저장 장소 등록 |
| `GET /locations` | 저장 장소 목록 조회 |
| `GET /locations/find/{label}` | 저장 장소 검색 |
| `DELETE /locations/{label}` | 저장 장소 삭제 |
| `POST /gps/route/save` | 현재 GPS track을 저장 경로로 확정 |
| `GET /routes/{session_id}` | 저장된 GPS 경로 목록 |
| `GET /routes/{session_id}/{route_id}` | 저장 경로 좌표 조회 |
| `GET /history/{session_id}` | 최근 24시간 탐지 이력 |
| `GET /dashboard` | HTML 대시보드 |

### DB/대시보드

| 테이블 | 용도 |
|---|---|
| `detection_events` | 탐지 이벤트 원본/요약 저장 |
| `detections` | 이벤트별 객체 상세 저장 |
| `snapshots` | session별 최근 공간 상태 |
| `gps_history` | 현재 이동 경로 좌표 |
| `recent_detections` | `/detect_json` 호환 및 질문 복원 보조 |
| `saved_locations` | 세션별 저장 장소. `/locations` 라우터에서 등록/조회/검색/삭제 |

---

## 3. 이전 문서 대비 바뀐 점

| 이전 설명 | 현재 코드 기준 |
|---|---|
| 서버가 YOLO/Depth 추론 수행 | 서버 추론 없음. Android가 TFLite로 탐지 후 JSON 전송 |
| Depth 모듈이 거리 계산 담당 | 현재 주 경로는 bbox 기반 거리 추정. `depth_source`는 `on_device_bbox` |
| `/detect_json` 중심 업로드 | Android 현재 주 경로는 `POST /detect`; `/detect_json`은 호환용 |
| `/status`가 `recent_detections` 반환 | 현재 `/status`는 `objects`, `gps`, `track`, `latest_event` 반환 |
| 장소 저장 API가 완성됨 | 서버 `/locations` 라우터가 세션별 저장 장소 등록/조회/검색/삭제를 제공 |
| 서버 FPS가 핵심 병목 | 서버는 추론을 하지 않으므로 현재 병목은 Android 추론/후처리와 네트워크 업로드 빈도 |

---

## 4. 성능 관련 현재 설정

### Android

| 항목 | 값/설명 |
|---|---|
| 프레임 간격 | `INTERVAL_MS = 50ms` |
| 온디바이스 동시 처리 | `MAX_ON_DEVICE_IN_FLIGHT = 1` |
| 서버 동시 요청 | `MAX_SERVER_IN_FLIGHT = 4` |
| MVP/TTS 갱신 주기 | `MVP_UPDATE_INTERVAL_MS = 750ms` |
| 서버 업로드 최소 간격 | `SERVER_UPLOAD_INTERVAL_MS = 250ms` |
| 변화 없어도 강제 업로드 | `SERVER_FORCE_SEND_FRAMES = 5` |
| 서버 업로드 객체 수 | 최대 5개, confidence 0.45 이상 또는 위험 bypass 클래스 |
| vote 기준 | 최근 3프레임 중 2회 이상. 차량/위험물은 bypass |

### 서버

| 항목 | 값/설명 |
|---|---|
| DB writer | background thread + queue |
| Queue max | `DETECTION_EVENT_QUEUE_MAX = 512` |
| Batch size | `DETECTION_EVENT_BATCH_SIZE = 24` |
| Flush interval | `DETECTION_EVENT_FLUSH_INTERVAL_S = 0.25` |
| `/detect` 저장 샘플링 | `DETECT_SAVE_EVERY_N_FRAMES = 5` |
| Snapshot 최소 간격 | `SNAPSHOT_MIN_INTERVAL_S = 1.0` |
| 보관 정책 | session별 detection event 200개, snapshot 20개, recent detection 500개 |

---

## 5. 검증 상태

### 자동 테스트

현재 테스트는 서버를 직접 띄우지 않는 FastAPI TestClient, NLG, 정책, import 테스트를 기준으로 합니다.

```bash
python -m pytest tests/ -v -m "not integration"
```

최근 실행 결과:

```text
22 passed, 9 deselected
```

주요 회귀 테스트:

- `/api/policy` 응답 및 policy 구조
- `/detect` 응답 스키마와 `depth_source`
- `/detect_json` 저장 및 `recent_detections` 회귀
- `/spaces/snapshot`
- `/locations` 저장/조회/검색/삭제
- API key 보호 라우트
- 한국어 NLG 조사/거리/찾기 문장
- 서버 런타임 import

`tests/test_server.py`의 integration 테스트는 실제 `localhost:8000` 서버가 떠 있어야 합니다.

```bash
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
python -m pytest tests/test_server.py -v -m integration
```

### 수동 시뮬레이션

`test_simulation.py`는 현재 API 스키마 기준으로 다음을 확인합니다.

- `/health`
- `/api/policy`
- `/detect`
- `/status/{session_id}`
- `/question`
- `/detect_json`
- `/gps`
- `/team-locations`
- `/sessions`
- `/dashboard`

실행:

```bash
python test_simulation.py
```

---

## 6. 남은 이슈와 우선순위

### 높음

1. Android 실기 성능 검증
   - Logcat `VG_PERF` 기준으로 preprocess/infer/postprocess/total/FPS 확인
   - GPU delegate 실패 시 XNNPACK fallback 성능 비교
   - `yolo11n_320.tflite`와 `yolo26n_float32.tflite` 모델별 실제 기기 성능 기록

2. TTS/UI 안정성
   - `ttsBusy`, `pendingStatusText`, `speakCooldownUntil` 흐름은 개선되어 있으나 실기에서 중복 발화와 UI 깜빡임 재확인 필요
   - 질문 직후 periodic 안내 억제(`suppressPeriodicUntil`) 동작 검증 필요

3. 서버 비동기 저장 검증
   - `/detect`는 DB 저장을 enqueue합니다. 대시보드/이력 조회에서 writer queue 지연과 drop count 확인 필요
   - Cloud Run 환경에서 SQLite 대신 PostgreSQL/Supabase 사용 시 connection pool과 batch writer 검증 필요

### 중간

4. Android 장소 동기화 경로 정리
   - 서버 `/locations` 라우터는 구현되어 있습니다.
   - Android가 현재 `SharedPreferences`와 서버 저장 장소를 어떻게 동기화할지 결정해야 합니다.

5. `/detect_json` 경로 정리
   - Android에는 `sendDetectionsJson()` 구형 경로 함수가 남아 있습니다.
   - 현재 주 경로인 `/detect`만 유지할지, 외부 테스트/호환을 위해 계속 둘지 결정해야 합니다.

6. 대시보드/이력 API 정리
   - SSE `/events/{session_id}`
   - `/team-locations`
   - `/history/{session_id}` 및 `/routes/{session_id}`는 라우터에 있으므로 대시보드 노출 방식 정리

### 낮음

7. 확장 기능
   - 신호등 색상/장면 정보는 서버 `scene` 필드에 연결 가능한 구조만 있습니다.
   - 낙상 감지는 보호자/응급 연동 없이 로컬 확인 음성까지만 구현되어 있습니다.
   - 약 알림, 하차 알림, 바코드 인식은 아직 제품 기능으로 완성되지 않았습니다.

---

## 7. 결론

현재 MVP의 핵심 방향은 명확합니다.

- 사용자 안내는 Android에서 즉시 처리합니다.
- 서버는 모델 서버가 아니라 실시간 상태 동기화와 기록 저장 서버입니다.
- 성능 개선의 초점은 서버 YOLO가 아니라 Android TFLite 추론, 프레임 안정화, TTS/UI 발화 빈도, JSON 업로드 샘플링입니다.
- 문서와 시뮬레이션도 이 구조에 맞춰 갱신되었습니다.
