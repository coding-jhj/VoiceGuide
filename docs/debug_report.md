# VoiceGuide 디버그 리포트
> 작성일: 2026-05-08  
> 기준 커밋: main (feature/jaehyun "Fix detect_json storage and MVP docs" 머지 후)  
> 분석 대상: Android Kotlin 7개 파일, Python 백엔드 9개 파일, 테스트 6개 파일, 기타 2개 파일

---

## 요약 (한눈에 보기)

| 심각도 | 건수 | 설명 |
|--------|------|------|
| 🔴 심각 | 4건 | 크래시 또는 데이터 오염 가능 |
| 🟠 경고 | 7건 | 잘못된 동작 또는 성능 문제 |
| 🟡 개선 권고 | 6건 | 코드 품질 및 유지보수 |
| ✅ 최근 개선 | 10건 | 이번 머지에서 수정된 내용 |

---

## 🔴 심각 (크래시 / 데이터 오염)

### 1. [routes.py:296~301] save_snapshot이 wifi_ssid와 session_id 둘 다로 중복 저장됨

- **위치**: `src/api/routes.py` 296~301줄
- **문제**: `/detect` 엔드포인트에서 `db.save_snapshot(wifi_ssid, objects)`와 `db.save_snapshot(session_id, objects)`를 같은 블록 안에서 두 번 호출한다. 스냅샷이 2개 키로 저장되고, `get_snapshot`은 `wifi_ssid` 기준으로 조회하므로 `session_id`로만 저장된 기록과 엇갈려 공간 변화 감지가 오작동한다.
- **언제 발생하나**: WiFi 없는 기기(`wifi_ssid=""`)에서 `/detect` 호출 시, 빈 문자열 키로 여러 기기의 스냅샷이 뒤섞임.
- **문제 코드**:
  ```python
  previous = db.get_snapshot(wifi_ssid) if should_persist and wifi_ssid else None
  if objects and should_persist:
      db.save_snapshot(wifi_ssid, objects)   # wifi_ssid 기준 저장
      db.save_snapshot(session_id, objects)  # session_id 기준 중복 저장
  ```
- **해결 방향**: `get_snapshot`과 `save_snapshot`을 `session_id` 하나로 통일하고, wifi_ssid 기준 호출을 제거한다.

---

### 2. [test_api.py:97] 새로 추가된 테스트가 잘못된 키로 검증함

- **위치**: `tests/test_api.py` 97~99줄
- **문제**: `test_detect_json_persists_recent_detections`에서 `/detect_json` 호출 후 `db.get_recent_detections("test_detect_json_device", ...)`로 결과를 조회한다. `save_detections`는 `session_id`에 저장하는데, `session_id`는 `_normalize_session_id(wifi_ssid, device_id)` 결과라서 wifi_ssid에 따라 달라진다. 현재는 우연히 통과하지만, wifi_ssid 값이 달라지면 조용히 실패한다.
- **문제 코드**:
  ```python
  recent = db.get_recent_detections("test_detect_json_device", max_age_s=60)
  assert recent  # wifi_ssid가 다르면 항상 빈 list 반환 → assert 실패
  ```
- **해결 방향**: 테스트 내에서 `_normalize_session_id(wifi_ssid, device_id)` 결과를 직접 계산해 조회하거나, session_id를 payload에 명시한다.

---

### 3. [db.py:709~731] PostgreSQL 모드에서 탐지 1건마다 DELETE 실행

- **위치**: `src/api/db.py` 709~731줄
- **문제**: PostgreSQL 모드의 `save_detections`가 `for d in detections:` 루프 안에서 INSERT마다 `DELETE ... WHERE id NOT IN (SELECT ... LIMIT 500)` 서브쿼리를 실행한다. N개 탐지 시 N번 DELETE가 발생하며, 초당 수 회 호출되므로 DB 연결 풀 고갈 및 응답 지연이 발생한다.
- **SQLite는 루프 밖에서 1회 DELETE를 올바르게 처리하는 반면, PostgreSQL은 루프 안에서 N회 실행.**
- **문제 코드**:
  ```python
  for d in detections:
      if _IS_POSTGRES:
          with conn.cursor() as cur:
              cur.execute("INSERT INTO recent_detections ...")
              cur.execute("DELETE FROM recent_detections WHERE ...")  # 매번 실행
  ```
- **해결 방향**: INSERT를 `executemany`로 일괄 처리하고, DELETE는 루프 밖에서 1회만 실행한다.

---

### 4. [tracker.py:324~325] monkey-patch로 인한 키 체계 불일치

- **위치**: `src/api/tracker.py` 324~325줄
- **문제**: 파일 하단에서 `SessionTracker.update = _mvp_update`로 메서드를 교체하는데, 원본 `update`(123줄)는 `_tracks` 딕셔너리에 영어 클래스명(`obj["class"]`)을 키로 사용하고, `_mvp_update`는 `_object_key(obj)` 결과를 키로 사용한다. 동일한 `_tracks` dict를 공유하므로 모듈 임포트 타이밍에 따라 두 키 체계가 섞여 EMA 평활화가 전혀 작동하지 않을 수 있다.
- **해결 방향**: monkey-patch 방식을 제거하고 `_mvp_update`, `_mvp_get_current_state`를 처음부터 클래스 메서드로 정의한다.

---

## 🟠 경고 (잘못된 동작 / 성능 저하)

### 5. [routes.py:554] /status/{session_id} — normalize 인자 순서 오류

- **위치**: `src/api/routes.py` 554줄
- **문제**: `_normalize_session_id(session_id)`를 호출하는데, 함수 시그니처는 `(wifi_ssid="", device_id="")`이므로 session_id가 wifi_ssid 위치에 바인딩된다. device_id 우선 로직이 무시된다. `/events/{session_id}`도 동일 문제.
- **문제 코드**:
  ```python
  req_session_id = _normalize_session_id(session_id)  # device_id 인자 누락
  ```
- **해결 방향**: `_normalize_session_id(device_id=session_id)`로 수정하거나, 이 엔드포인트에서는 session_id를 정규화 없이 그대로 사용한다.

---

### 6. [policy.json vs policy_default.json] bbox_calib_area_by_class 필드 불일치

- **위치**: `src/config/policy.json` 39~48줄
- **문제**: `android/app/src/main/assets/policy_default.json`에는 `bbox_calib_area_by_class`가 있어서 클래스별 거리 보정이 작동한다. 서버 `src/config/policy.json`에는 이 필드가 없다. 앱이 서버 policy를 받아오면 클래스별 거리 보정이 통째로 비활성화돼 거리 안내 정확도가 떨어진다.
- **재현 조건**: 서버 URL 설정 후 앱 시작 → `refreshPolicyFromServerAsync()` 성공 시 항상 발생.
- **해결 방향**: `src/config/policy.json`에 `bbox_calib_area_by_class` 섹션을 추가한다.

---

### 7. [VoiceGuideConstants.kt vs templates.py] CLOCK_TO_DIRECTION "12시" 불일치

- **위치**: `android/.../VoiceGuideConstants.kt` / `src/nlg/templates.py`
- **문제**: Android에서 `"12시" → "바로"`, Python에서 `"12시" → "바로 앞"`. 또한 Android의 ZONE_BOUNDARIES는 "5시~7시" 구역이 없어, 서버가 해당 방향을 내려주면 `CLOCK_TO_DIRECTION`에서 null이 반환돼 TTS가 "5시 방향" 같은 숫자를 그대로 읽는다.
- **해결 방향**: 양쪽 CLOCK_TO_DIRECTION을 동기화하고, null 반환 시 fallback 처리를 추가한다.

---

### 8. [events.py] asyncio 이벤트 루프와 동기 컨텍스트 혼용

- **위치**: `src/api/events.py`
- **문제**: `publish()`는 동기 함수이지만 FastAPI의 `async def` 핸들러에서 호출된다. `_subscribers` dict에 대한 동시 접근이 발생할 때 race condition이 생길 수 있다.
- **해결 방향**: `publish()`를 `async def`로 변경하거나, `asyncio.get_event_loop().call_soon_threadsafe()`로 위임한다.

---

### 9. [VoicePolicy.kt:55] double-checked locking 불완전

- **위치**: `android/.../VoicePolicy.kt` 55~66줄
- **문제**: `init()` 내부 synchronized 블록에서 `parsePolicy` 실행 중 다른 스레드가 `requireSnap()`을 호출하면 `snap`이 null이라 `IllegalStateException`이 발생할 수 있다. `onCreate()`에서 TFLite 초기화와 `refreshPolicyFromServerAsync()`가 동시에 시작될 때 위험하다.
- **해결 방향**: `MvpPipeline`이 `VoicePolicy.init()` 완료 전에 `requireSnap()`을 호출하지 않도록 보장하거나, 초기화 완료 여부를 별도 플래그로 관리한다.

---

### 10. [MvpPipeline.kt:82] update() 동기화 없음

- **위치**: `android/.../MvpPipeline.kt` 82줄
- **문제**: `tracks.forEach { it.missed += 1 }` 와 `tracks.removeAll { ... }`이 연달아 실행되는데, `update()`에 `@Synchronized`가 없다. cameraExecutor 스레드 외부에서 `update()`가 호출되는 경로가 생기면 ConcurrentModificationException 위험이 있다.
- **해결 방향**: `MvpPipeline.update()`에 `@Synchronized`를 추가한다.

---

### 11. [TfliteYoloDetector.kt:37] 모델 파일 없을 때 NoSuchElementException 크래시

- **위치**: `android/.../TfliteYoloDetector.kt` 37~40줄
- **문제**: `listOf(...).first { ... }`를 사용해 assets에서 모델 파일을 찾는데, 두 파일 모두 없으면 `NoSuchElementException`이 발생한다. `tryInitTfliteDetector()`가 잡긴 하지만 사용자에게 불친절한 오류 메시지만 나오고 앱이 완전히 비작동 상태가 된다.
- **문제 코드**:
  ```kotlin
  modelName = listOf("yolo11n_320.tflite", "yolo26n_float32.tflite").first { name ->
      try { context.assets.open(name).close(); true }
      catch (_: Exception) { false }
  }
  ```
- **해결 방향**: `first`를 `firstOrNull`로 바꾸고, null이면 명시적으로 사용자 친화적인 오류 메시지를 throw한다.

---

## 🟡 개선 권고

### 12. [db.py:260] datetime.now() — timezone 미지정

- **위치**: `src/api/db.py` 260줄
- **문제**: `cutoff = (datetime.now() - timedelta(seconds=max_age_s)).isoformat()`가 timezone 정보 없는 naive datetime을 생성한다. 서버가 UTC가 아닌 timezone에서 실행되면 `recent_detections` 시간 비교가 틀린다.
- **해결 방향**: `datetime.now(timezone.utc).isoformat()`으로 통일한다.

---

### 13. [SentenceBuilder.kt] 전역 stableClock — 세션 재시작 시 오염 가능

- **위치**: `android/.../SentenceBuilder.kt` 8줄
- **문제**: `stableClock`이 싱글톤 전역 상태로 유지된다. Activity가 재생성되거나 분석이 재시작될 때 `clearStableClocks()`를 빠뜨리면 이전 세션의 방향 정보가 새 세션에 남는다.
- **해결 방향**: `startAnalysis()` 외에 `onStart()`에서도 `clearStableClocks()`를 호출한다.

---

### 14. [test_server.py] /locations 엔드포인트 미존재

- **위치**: `tests/test_server.py`
- **상태**: 해결됨.
- **변경**: `src/api/routes.py`에 `/locations` 등록/조회/검색/삭제 라우트를 추가했고, `src/api/locations.py`에서 응답 조립과 세션 scope 처리를 담당한다.
- **검증**: `tests/test_api.py`에 TestClient 기반 `/locations` 회귀 테스트를 추가했고, `tests/test_server.py`의 skip을 제거했다.

---

### 15. [requirements.txt] torch/torchvision — 서버 배포 시 이미지 크기 5GB 초과

- **위치**: `requirements.txt`
- **문제**: 서버 런타임 코드에서 torch/ultralytics를 실제로 import하지 않는데 requirements.txt에 포함되어 있다. Docker 이미지가 5GB 이상이 돼 Cloud Run 메모리 제한을 초과할 수 있다.
- **해결 방향**: `requirements-server.txt`(런타임)와 `requirements-dev.txt`(학습/도구)를 분리한다.

---

### 16. [MainActivity.kt:1461] inFlightCount 해제 누락 경로 가능성

- **위치**: `android/.../MainActivity.kt` 1461줄
- **문제**: `processOnDeviceInternal`의 `work` Runnable에서 네트워크 없음 + `isAnalyzing=false` 조건이 겹치면 `releaseInFlight()`가 두 번 불리거나 아예 안 불릴 수 있다.
- **해결 방향**: `inFlightCount` 감소를 try/finally 블록의 finally에 배치한다.

---

### 17. [simulator.py:42] 헤더 키 대소문자 — X-Api-Key vs X-API-Key

- **위치**: `tools/simulator.py` 42줄
- **문제**: simulator는 `X-Api-Key`를 사용하고 서버는 `x_api_key`를 파싱한다. FastAPI가 자동으로 소문자 변환하므로 실제 오류는 없지만, 명시적으로 통일하는 것이 혼란을 줄인다.

---

## ✅ 최근 머지로 개선된 부분

| 항목 | 내용 |
|------|------|
| `recent_detections` 테이블 분리 | detect_json 저장 경로를 기존 `detections` 테이블과 분리해 OperationalError 수정 |
| detect_json 회귀 테스트 추가 | `/detect_json` 저장 검증 테스트 추가 (22 passed 확인) |
| 서버 import 기준 정리 | 서버 불필요한 torch/ultralytics import 제거 |
| README TFLite 기준 수정 | ONNX/yolo11n → yolo26n_float32.tflite/TFLite로 일치화 |
| MainActivity.kt 주석 정리 | ONNX 관련 잔여 주석 제거 |
| android/gradlew 추가 | Linux/macOS/CI 환경에서 `./gradlew` 실행 가능 |
| 물체 없을 때 DB 저장 방지 | `if objects and should_persist:` 조건으로 빈 탐지 결과 저장 차단 |
| 중복 bbox deduplicate | IoU 0.3 이상 같은 클래스 bbox를 confidence 기준으로 제거 |
| 익명 세션 UUID 격리 | unknown SSID 기기들이 같은 session_id를 공유하던 버그 수정 |
| ETag 기반 policy 캐싱 | 불필요한 policy.json 재다운로드 방지 |
