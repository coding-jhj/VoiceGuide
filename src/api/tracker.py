"""
프레임 간 객체 추적 모듈.

- 거리 EMA 평균화: 프레임 jitter 제거 (실험 없이도 안정적 출력)
- 접근 감지: 거리가 빠르게 줄어들면 "가까워지고 있어요" 경고
- 소멸 감지: 가까웠던 장애물이 사라지면 "장애물 없어졌어요" 안내
"""

import time
from src.nlg.sentence import _i_ga

_EMA_ALPHA   = 0.55   # 새 관측값 가중치 (0~1, 클수록 반응 빠름)
_MAX_AGE_S   = 4.0    # 이 시간(초) 이상 미탐지 시 트랙 삭제
_APPROACH_TH = 0.4    # 이 값(m) 이상 가까워지면 접근 경고


class SessionTracker:
    """WiFi SSID 등 세션 단위 객체 추적기."""

    def __init__(self):
        # key: class 이름, value: {distance_m, class_ko, last_seen, alerted_approach}
        self._tracks: dict[str, dict] = {}

    def update(self, objects: list[dict]) -> tuple[list[dict], list[str]]:
        """
        Returns:
            smoothed_objects : 거리가 평균화된 탐지 결과
            change_messages  : 한국어 변화 메시지 (접근/소멸) 리스트
        """
        now = time.monotonic()
        current_keys = {o["class"] for o in objects}
        changes: list[str] = []

        # ── 소멸 감지 ──────────────────────────────────────────────────────
        for cls, tr in list(self._tracks.items()):
            if cls not in current_keys:
                age = now - tr["last_seen"]
                if age > _MAX_AGE_S:
                    # 가까웠던 장애물이 사라진 경우에만 안내
                    if tr["distance_m"] < 3.0:
                        name = tr["class_ko"]
                        changes.append(f"{name}{_i_ga(name)} 사라졌어요")
                    del self._tracks[cls]


        # ── EMA 평균화 + 접근 감지 ─────────────────────────────────────────
        smoothed = []
        for obj in objects:
            cls  = obj["class"]
            new_d = obj["distance_m"]

            if cls in self._tracks:
                tr = self._tracks[cls]
                old_d = tr["distance_m"]
                smooth_d = round(_EMA_ALPHA * new_d + (1 - _EMA_ALPHA) * old_d, 1)

                # 접근 경고: 이전 대비 0.4m 이상 가까워지고, 아직 충분히 가까움
                delta = old_d - smooth_d
                if delta >= _APPROACH_TH and smooth_d < 2.5 and not tr.get("alerted"):
                    name = obj["class_ko"]
                    changes.append(f"{name}{_i_ga(name)} 가까워지고 있어요")
                    tr["alerted"] = True
                elif delta < 0:
                    tr["alerted"] = False  # 멀어지면 경고 리셋

                tr["distance_m"] = smooth_d
                tr["last_seen"]  = now
            else:
                smooth_d = new_d
                self._tracks[cls] = {
                    "distance_m": smooth_d,
                    "class_ko":   obj["class_ko"],
                    "last_seen":  now,
                    "alerted":    False,
                }

            obj = dict(obj)
            obj["distance_m"] = smooth_d
            smoothed.append(obj)

        return smoothed, changes


# WiFi SSID별 추적기 인스턴스 관리
_trackers: dict[str, SessionTracker] = {}


def get_tracker(session_id: str) -> SessionTracker:
    if session_id not in _trackers:
        _trackers[session_id] = SessionTracker()
    return _trackers[session_id]
