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
_MAX_AGE_S   = 4.0    # 4초 (카메라 1초 간격이므로 4프레임 이상 미탐지)

# 이 거리 이상 가까워지면 "접근 중" 경고
_APPROACH_TH = 0.4    # 0.4m (한 프레임에 40cm 이상 가까워지면 이동 물체)

# 보팅 설정 — 경고 피로 방지
_VOTE_WINDOW    = 10   # 최근 N프레임을 기억
_VOTE_THRESHOLD = 0.6  # 이 비율 이상 탐지돼야 확정 (60% = 10프레임 중 6회)


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
        # key: COCO 클래스명(영어), value: 추적 정보 dict
        self._tracks: dict[str, dict] = {}
        self._voting = VotingBuffer()  # 보팅 버퍼 — 경고 피로 방지

    def update(self, objects: list[dict]) -> tuple[list[dict], list[str]]:
        """
        새 프레임의 탐지 결과를 받아 거리를 평활화하고 변화를 감지.

        Args:
            objects: detect_and_depth()가 반환한 탐지 물체 목록

        Returns:
            smoothed_objects: 거리가 EMA로 안정화된 물체 목록
            change_messages:  변화 한국어 메시지 리스트
                              예) ["가방이 가까워지고 있어요", "의자가 사라졌어요"]
        """
        now = time.monotonic()  # 단조 시계: 시스템 시간 변경에 영향 없음
        current_keys = {o["class"] for o in objects}  # 이번 프레임에 탐지된 클래스 집합
        changes: list[str] = []

        # 보팅 버퍼에 현재 프레임 추가 (경고 피로 방지용)
        self._voting.add_frame(current_keys)

        # ── 소멸 감지 ──────────────────────────────────────────────────────
        # 이전에 있었는데 지금 없는 물체 → 일정 시간 지나면 "사라졌어요" 안내
        for cls, tr in list(self._tracks.items()):
            if cls not in current_keys:
                age = now - tr["last_seen"]  # 마지막으로 봤을 때로부터 경과 시간(초)
                if age > _MAX_AGE_S:
                    # 가까웠던 물체가 사라진 경우만 안내 (멀리 있던 건 안내 불필요)
                    if tr["distance_m"] < 3.0:
                        name = tr["class_ko"]
                        changes.append(f"{name}{_i_ga(name)} 사라졌어요")
                    del self._tracks[cls]  # 트랙 삭제

        # ── EMA 평활화 + 접근 감지 ─────────────────────────────────────────
        smoothed = []
        for obj in objects:
            cls   = obj["class"]       # 영어 클래스명 (트랙 키)
            new_d = obj["distance_m"]  # 이번 프레임의 raw 거리

            if cls in self._tracks:
                # 기존 트랙이 있으면 → EMA 적용
                tr    = self._tracks[cls]
                old_d = tr["distance_m"]

                # EMA: 현재 55% + 이전 45%
                smooth_d = round(_EMA_ALPHA * new_d + (1 - _EMA_ALPHA) * old_d, 1)

                # delta: 양수 = 물체가 가까워지는 중, 음수 = 멀어지는 중
                delta = old_d - smooth_d

                # 일반 접근 경고: 0.4m 이상 가까워지고 아직 2.5m 이내
                if delta >= _APPROACH_TH and smooth_d < 2.5 and not tr.get("alerted"):
                    name = obj["class_ko"]
                    changes.append(f"{name}{_i_ga(name)} 가까워지고 있어요")
                    tr["alerted"] = True
                elif delta < 0:
                    tr["alerted"] = False  # 멀어지면 경고 리셋 (다음 접근 시 다시 경고 가능)

                # 빠른 접근 경고: 0.8m 이상 급격히 가까워지면 → 낙하·날아오는 물체
                # 일반 접근(0.4m)보다 2배 빠른 경우 = 뭔가 날아오거나 떨어지는 중
                if delta >= 0.8 and smooth_d < 3.0 and not tr.get("alerted_fast"):
                    name = obj["class_ko"]
                    changes.append(f"조심! {name}{_i_ga(name)} 빠르게 다가오고 있어요!")
                    tr["alerted_fast"] = True
                elif delta < 0:
                    tr["alerted_fast"] = False

                tr["distance_m"] = smooth_d
                tr["last_seen"]  = now
                tr["direction"]  = obj.get("direction", tr.get("direction", "12시"))
            else:
                # 새로 나타난 물체 → 트랙 생성
                smooth_d = new_d
                self._tracks[cls] = {
                    "distance_m":   smooth_d,
                    "class_ko":     obj["class_ko"],
                    "direction":    obj.get("direction", "12시"),
                    "last_seen":    now,
                    "alerted":      False,       # 일반 접근 경고 발생 여부
                    "alerted_fast": False,       # 빠른 접근 경고 발생 여부
                }

            # 원본 dict를 복사해서 거리만 교체 (원본 훼손 방지)
            obj = dict(obj)
            obj["distance_m"] = smooth_d
            smoothed.append(obj)

        # 보팅 필터: 오탐 제거 (차량은 즉시 통과)
        confirmed = self._voting.filter(smoothed)
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
        for cls, tr in self._tracks.items():
            age = now - tr["last_seen"]
            if age <= max_age_s:
                result.append({
                    "class":      cls,
                    "class_ko":   tr["class_ko"],
                    "distance_m": tr["distance_m"],
                    "direction":  tr.get("direction", "12시"),
                    "depth_source": "tracker",
                })
        # 거리 가까운 순으로 정렬
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
