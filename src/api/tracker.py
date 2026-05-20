"""
VoiceGuide 객체 추적 모듈
==========================
같은 물체가 여러 프레임에 걸쳐 계속 탐지될 때, 거리 값을 안정화하고
"가까워지고 있어요" 같은 변화를 감지합니다.

왜 필요한가?
- YOLO가 프레임마다 조금씩 다른 결과를 냄 (jitter)
  예) 의자 거리: 1.0m → 1.3m → 0.9m → 1.1m 계속 바뀜
  → TTS가 매번 다른 말을 함 → 혼란스러움
- EMA(지수이동평균)로 부드럽게 만들면:
  1.0 → 1.17 → 1.03 → 1.08 → 안정적

보팅(Voting) 방식 경고 피로 방지:
- 최근 N프레임 중 threshold 비율 이상 탐지된 물체만 확정
- 1~2프레임 오탐은 자동으로 걸러짐
"""

import time
from collections import deque
from src.nlg.sentence import _i_ga

# EMA 공식: new_smooth = alpha * 현재값 + (1-alpha) * 이전값
# alpha가 크면 현재 값을 더 많이 반영 (반응 빠르지만 흔들림)
# alpha가 작으면 이전 값을 더 많이 반영 (안정적이지만 반응 느림)
_EMA_ALPHA   = 0.55   # 현재 55% + 이전 45% → 균형점

# 이 시간 동안 탐지 안 되면 "사라진 물체"로 처리
_MAX_AGE_S   = 8.0    # 8초 — 10fps에서 일시적 miss 때문에 "사라졌어요" 남발 방지

# 이 거리 이상 가까워지면 "접근 중" 경고
_APPROACH_TH = 0.4    # 0.4m (한 프레임에 40cm 이상 가까워지면 이동 물체)

# 보팅 설정 — 경고 피로 방지
_VOTE_WINDOW    = 10   # 최근 N프레임을 기억
_VOTE_THRESHOLD = 0.6  # 이 비율 이상 탐지돼야 확정 (60% = 10프레임 중 6회)


def _object_key(obj: dict) -> str:
    """Prefer mobile ByteTrack-lite IDs, fallback to class name for server-only detections."""
    tid = obj.get("track_id")
    if tid not in (None, "", 0, "0"):
        return f"track:{tid}"
    cls = obj.get("class") or obj.get("class_ko") or "unknown"
    return f"class:{cls}"


def _risk_pattern(risk: float, obj: dict) -> str:
    if obj.get("is_vehicle") and risk >= 0.55:
        return "URGENT"
    if risk >= 0.75:
        return "URGENT"
    if risk >= 0.55:
        return "DOUBLE"
    if risk >= 0.35:
        return "SHORT"
    return "NONE"


class VotingBuffer:
    """
    N프레임 다수결로 경고 피로 방지.

    한 프레임에서 우연히 탐지된 오탐은 걸러주고,
    여러 프레임에 걸쳐 일관되게 탐지된 물체만 확정해서 경고.

    예) 10프레임 중 7회 "의자" 탐지 → 60% 이상 → 확정 → 경고 발생
        10프레임 중 2회 "고양이" 탐지 → 20% → 미확정 → 경고 없음
    """

    def __init__(self, window: int = _VOTE_WINDOW, threshold: float = _VOTE_THRESHOLD):
        self.window    = window
        self.threshold = threshold
        self._frames: deque[set[str]] = deque(maxlen=window)

    def add_frame(self, detected_classes: set[str]) -> None:
        """새 프레임의 탐지 클래스 집합을 버퍼에 추가."""
        self._frames.append(set(detected_classes))

    def is_confirmed(self, cls: str) -> bool:
        """해당 클래스가 충분한 프레임에서 탐지됐는지 확인."""
        if len(self._frames) < 3:
            return True  # 초기 3프레임은 필터링 없이 통과 (시동 단계)
        count = sum(1 for frame in self._frames if cls in frame)
        return (count / len(self._frames)) >= self.threshold

    def filter(self, objects: list[dict]) -> list[dict]:
        """확정된 물체만 반환. 차량은 보팅 없이 즉시 통과."""
        result = []
        for obj in objects:
            cls        = obj.get("class", "")
            is_vehicle = obj.get("is_vehicle", False)
            # 차량은 오탐이어도 즉시 경고 (안전 우선)
            if is_vehicle or self.is_confirmed(cls):
                result.append(obj)
        return result


class SessionTracker:
    """
    WiFi SSID 단위의 객체 추적기.
    같은 장소(WiFi)에서는 물체별 거리 기록을 유지함.
    """

    def __init__(self):
        # key: _object_key() 결과 ("track:N" 또는 "class:이름")
        self._tracks: dict[str, dict] = {}
        self._voting = VotingBuffer()

    def update(self, objects: list[dict]) -> tuple[list[dict], list[str]]:
        """
        새 프레임의 탐지 결과를 받아 거리를 평활화하고 변화를 감지.

        Args:
            objects: 온디바이스 탐지 JSON을 서버에서 정규화한 물체 목록

        Returns:
            smoothed_objects: 거리가 EMA로 안정화된 물체 목록
            change_messages:  변화 한국어 메시지 리스트
                              예) ["가방이 가까워지고 있어요", "의자가 사라졌어요"]
        """
        now = time.monotonic()
        current_keys = {_object_key(o) for o in objects}
        current_classes = {o.get("class", "") for o in objects}
        changes: list[str] = []

        self._voting.add_frame(current_classes)

        # ── 소멸 감지 ──────────────────────────────────────────────────────
        for key, tr in list(self._tracks.items()):
            if key not in current_keys and now - tr["last_seen"] > _MAX_AGE_S:
                del self._tracks[key]

        # ── EMA 평활화 + 접근 감지 ─────────────────────────────────────────
        smoothed: list[dict] = []
        for raw in objects:
            obj = dict(raw)
            key = _object_key(obj)
            new_d = float(obj.get("distance_m") or 99.0)
            new_r = float(obj.get("risk_score") or 0.0)

            if key in self._tracks:
                tr = self._tracks[key]
                old_d = float(tr.get("distance_m", new_d))
                smooth_d = round(_EMA_ALPHA * new_d + (1 - _EMA_ALPHA) * old_d, 1)
                smooth_r = new_r
                delta = old_d - smooth_d

                # 일반 접근 경고: 0.4m 이상 가까워지고 아직 2.5m 이내
                if delta >= _APPROACH_TH and smooth_d < 2.5 and not tr.get("alerted"):
                    name = obj.get("class_ko", obj.get("class", "물체"))
                    changes.append(f"{name}{_i_ga(name)} 가까워지고 있어요")
                    tr["alerted"] = True
                elif delta < 0:
                    tr["alerted"] = False

                # 빠른 접근 경고: 0.8m 이상 급격히 가까워지면
                if delta >= 0.8 and smooth_d < 3.0 and not tr.get("alerted_fast"):
                    name = obj.get("class_ko", obj.get("class", "물체"))
                    changes.append(f"조심! {name}{_i_ga(name)} 빠르게 다가오고 있어요")
                    tr["alerted_fast"] = True
                elif delta < 0:
                    tr["alerted_fast"] = False

                tr.update({
                    "distance_m": smooth_d,
                    "risk_score": smooth_r,
                    "last_seen": now,
                    "seen_count": tr.get("seen_count", 0) + 1,
                    "direction": obj.get("direction", tr.get("direction", "12시")),
                    "class": obj.get("class", tr.get("class", "")),
                    "class_ko": obj.get("class_ko", tr.get("class_ko", "")),
                    "track_id": obj.get("track_id", tr.get("track_id", 0)),
                })
            else:
                smooth_d = new_d
                smooth_r = new_r
                self._tracks[key] = {
                    "distance_m": smooth_d,
                    "risk_score": smooth_r,
                    "class": obj.get("class", ""),
                    "class_ko": obj.get("class_ko", obj.get("class", "")),
                    "direction": obj.get("direction", "12시"),
                    "last_seen": now,
                    "seen_count": 1,
                    "track_id": obj.get("track_id", 0),
                    "alerted": False,
                    "alerted_fast": False,
                }

            obj["distance_m"] = smooth_d
            obj["risk_score"] = max(0.0, min(smooth_r, 1.0))
            obj["vibration_pattern"] = obj.get("vibration_pattern") or _risk_pattern(obj["risk_score"], obj)
            obj["track_id"] = obj.get("track_id", self._tracks[key].get("track_id", 0))
            smoothed.append(obj)

        # Android에서 이미 보팅 완료된 결과가 오므로 서버는 EMA 평활화만 수행
        confirmed = self._voting.filter(smoothed)
        confirmed.sort(key=lambda o: o.get("risk_score", 0.0), reverse=True)
        return confirmed, changes

    def get_current_state(self, max_age_s: float = 3.0) -> list[dict]:
        """
        현재 추적 중인 물체 목록 반환 — 사용자 질문 응답에 사용.

        max_age_s 이내에 탐지된 물체만 반환 (너무 오래된 정보는 제외).
        tracker에 쌓인 모든 맥락 정보를 꺼내서 질문에 답하는 핵심 메서드.

        예) 사용자가 "지금 뭐가 있어?" 질문 →
            현재 프레임 탐지 결과 + tracker 누적 상태를 합쳐 응답
        """
        now = time.monotonic()
        result = []
        for key, tr in self._tracks.items():
            if now - tr["last_seen"] <= max_age_s:
                result.append({
                    "class": tr.get("class", key),
                    "class_ko": tr.get("class_ko", tr.get("class", key)),
                    "distance_m": tr.get("distance_m", 99.0),
                    "direction": tr.get("direction", "12시"),
                    "risk_score": tr.get("risk_score", 0.0),
                    "track_id": tr.get("track_id", 0),
                    "vibration_pattern": _risk_pattern(float(tr.get("risk_score", 0.0)), tr),
                    "depth_source": "tracker",
                })
        result.sort(key=lambda o: o["distance_m"])
        return result


# ── 세션별 추적기 관리 ────────────────────────────────────────────────────────
# WiFi SSID마다 별도 추적기 인스턴스를 유지
# 다른 장소(WiFi)로 이동하면 새 추적기가 만들어짐 → 장소별 물체 기억 분리
_trackers: dict[str, SessionTracker] = {}


def get_tracker(session_id: str) -> SessionTracker:
    """session_id(WiFi SSID)에 해당하는 추적기를 반환. 없으면 생성."""
    if session_id not in _trackers:
        _trackers[session_id] = SessionTracker()
    return _trackers[session_id]
