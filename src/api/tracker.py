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
"""

import time
from src.nlg.sentence import _i_ga

# EMA 공식: new_smooth = alpha * 현재값 + (1-alpha) * 이전값
# alpha가 크면 현재 값을 더 많이 반영 (반응 빠르지만 흔들림)
# alpha가 작으면 이전 값을 더 많이 반영 (안정적이지만 반응 느림)
_EMA_ALPHA   = 0.55   # 현재 55% + 이전 45% → 균형점

# 이 시간 동안 탐지 안 되면 "사라진 물체"로 처리
_MAX_AGE_S   = 4.0    # 4초 (카메라 1초 간격이므로 4프레임 이상 미탐지)

# 이 거리 이상 가까워지면 "접근 중" 경고
_APPROACH_TH = 0.4    # 0.4m (한 프레임에 40cm 이상 가까워지면 이동 물체)


class SessionTracker:
    """
    WiFi SSID 단위의 객체 추적기.
    같은 장소(WiFi)에서는 물체별 거리 기록을 유지함.
    """

    def __init__(self):
        # key: COCO 클래스명(영어), value: 추적 정보 dict
        self._tracks: dict[str, dict] = {}

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
            else:
                # 새로 나타난 물체 → 트랙 생성
                smooth_d = new_d
                self._tracks[cls] = {
                    "distance_m":   smooth_d,
                    "class_ko":     obj["class_ko"],
                    "last_seen":    now,
                    "alerted":      False,       # 일반 접근 경고 발생 여부
                    "alerted_fast": False,       # 빠른 접근 경고 발생 여부
                }

            # 원본 dict를 복사해서 거리만 교체 (원본 훼손 방지)
            obj = dict(obj)
            obj["distance_m"] = smooth_d
            smoothed.append(obj)

        return smoothed, changes


# ── 세션별 추적기 관리 ────────────────────────────────────────────────────────
# WiFi SSID마다 별도 추적기 인스턴스를 유지
# 다른 장소(WiFi)로 이동하면 새 추적기가 만들어짐 → 장소별 물체 기억 분리
_trackers: dict[str, SessionTracker] = {}


def get_tracker(session_id: str) -> SessionTracker:
    """session_id(WiFi SSID)에 해당하는 추적기를 반환. 없으면 생성."""
    if session_id not in _trackers:
        _trackers[session_id] = SessionTracker()
    return _trackers[session_id]
