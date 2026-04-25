"""
깊이 맵 기반 바닥 위험 감지.

Depth Anything V2 출력만으로 계단·낙차·턱을 감지한다.
YOLO 클래스에 없는 위험 요소를 보완하는 핵심 기능.

원리:
- 이미지 하단 = 카메라 바로 앞 바닥 (가까움 = 낮은 depth 값)
- 이미지 상단 = 멀리 있는 바닥 (멀수록 depth 값 커짐)
- 정상 바닥: 하단 → 상단으로 depth가 완만하게 증가
- 계단(하강): 특정 지점에서 depth가 급격히 증가 (바닥이 갑자기 멀어짐)
- 계단(상승)/턱: 특정 지점에서 depth가 급격히 감소 (가까운 장애물 등장)
"""

import numpy as np


_N_BANDS = 12       # 수평 분석 구역 수
_FLOOR_START = 0.40  # 이미지 상단 40%는 제외 (벽·천장 등)
_DROP_THRESH = 1.2   # 계단 하강 판별 깊이 변화(m) 임계값
_STEP_THRESH = 1.0   # 계단 상승/턱 판별 임계값
_MAX_WARN_DIST = 4.5  # 이 거리 이상 장애물은 경고 생략


def detect_floor_hazards(depth_map: np.ndarray) -> list[dict]:
    """
    depth_map: (H, W) float32, 단위≈미터, 작을수록 가까움.
    Returns: list of hazard dicts with keys:
        type       — "drop" | "step"
        distance_m — 감지 위치까지 추정 거리(m)
        message    — 한국어 경고 문장
        risk       — 0.0 ~ 1.0
    """
    h, w = depth_map.shape

    # 바닥 영역: 이미지 하단 60%
    floor_y0 = int(h * _FLOOR_START)
    floor = depth_map[floor_y0:, :]   # shape: (fh, w)
    fh = floor.shape[0]

    if fh < _N_BANDS:
        return []

    # 수평 밴드별 중앙값 깊이 계산
    # band[0] = 이미지 최하단 (카메라 가장 가까운 지점)
    # band[-1] = 바닥 영역 최상단 (가장 먼 지점)
    cx_lo, cx_hi = w // 4, 3 * w // 4  # 중앙 50% 너비만 사용 (측면 노이즈 제거)
    band_h = fh // _N_BANDS
    band_depths = []
    for i in range(_N_BANDS):
        r_end   = fh - i * band_h
        r_start = max(0, r_end - band_h)
        patch   = floor[r_start:r_end, cx_lo:cx_hi]
        if patch.size == 0:
            continue
        band_depths.append(float(np.median(patch)))

    if len(band_depths) < 4:
        return []

    hazards: list[dict] = []

    # ── 변화율 분석 ──────────────────────────────────────────────────────
    for i in range(len(band_depths) - 1):
        d_cur  = band_depths[i]      # 현재 밴드 깊이
        d_next = band_depths[i + 1]  # 한 밴드 앞(더 먼 방향)의 깊이
        delta  = d_next - d_cur      # 양수 = 멀어짐, 음수 = 가까워짐

        # ── 낙차 / 계단 하강 ─────────────────────────────────────────
        if delta > _DROP_THRESH and d_cur < _MAX_WARN_DIST:
            risk = min(1.0, delta / 3.0) * (1 - d_cur / _MAX_WARN_DIST)
            hazards.append({
                "type":       "drop",
                "distance_m": round(d_cur, 1),
                "message":    f"조심! {round(d_cur, 1)}m 앞에 계단이나 낙차가 있어요. 멈추세요.",
                "risk":       round(risk, 2),
            })
            break

        # ── 계단 상승 / 턱 ───────────────────────────────────────────
        if delta < -_STEP_THRESH and d_next < _MAX_WARN_DIST:
            risk = min(1.0, abs(delta) / 2.0) * (1 - d_next / _MAX_WARN_DIST)
            hazards.append({
                "type":       "step",
                "distance_m": round(d_next, 1),
                "message":    f"발 앞에 턱이나 계단이 있어요. 약 {round(d_next, 1)}m.",
                "risk":       round(risk, 2),
            })
            break

    # ── 좌우 경로 폭 분석: 양쪽이 막혀 있으면 좁은 통로 경고 ─────────
    if not hazards:
        mid_band = band_depths[len(band_depths) // 2]
        left_patch  = floor[fh//4:3*fh//4, :w//4]
        right_patch = floor[fh//4:3*fh//4, 3*w//4:]
        left_d  = float(np.median(left_patch))
        right_d = float(np.median(right_patch))

        # 양쪽 벽이 중앙보다 훨씬 가까우면 좁은 통로
        if left_d < mid_band * 0.5 and right_d < mid_band * 0.5 and mid_band < 3.0:
            hazards.append({
                "type":       "narrow",
                "distance_m": round(mid_band, 1),
                "message":    "좁은 통로예요. 천천히 이동하세요.",
                "risk":       0.4,
            })

    return hazards
