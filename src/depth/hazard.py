"""
VoiceGuide 바닥 위험 감지 모듈
================================
Depth Anything V2의 깊이 맵을 분석해서
YOLO가 탐지하지 못하는 계단·낙차·턱·좁은 통로를 감지합니다.

핵심 원리:
  카메라가 앞을 향할 때,
  이미지 하단 = 발 바로 앞 바닥 (가까움 = 낮은 depth 값)
  이미지 상단 = 멀리 있는 바닥 (멀수록 depth 값 큼)

  정상 바닥: 아래→위로 갈수록 depth가 완만하게 증가
  낙차/계단(하강): 특정 지점에서 depth가 급격히 커짐
                   → 바닥이 갑자기 멀어짐 = 발 앞이 뚝 떨어짐
  턱/계단(상승): 특정 지점에서 depth가 급격히 작아짐
                → 가까운 장애물이 갑자기 등장 = 발 앞에 턱이 있음
"""

import numpy as np

_N_BANDS     = 12     # 바닥 영역을 12개 수평 띠로 나눔 (더 세밀할수록 정확하지만 느림)
_FLOOR_START = 0.40   # 이미지 상단 40%는 분석 제외 (벽·천장·하늘 등 바닥 아닌 영역)
_DROP_THRESH = 1.2    # 낙차 판별 임계값 (m): 1.2m 이상 갑자기 깊어지면 낙차로 판단
_STEP_THRESH = 1.0    # 턱 판별 임계값 (m): 1.0m 이상 갑자기 얕아지면 턱으로 판단
_MAX_WARN_DIST = 4.5  # 경고 최대 거리: 4.5m 이상 먼 곳의 위험은 경고 생략


def detect_floor_hazards(depth_map: np.ndarray) -> list[dict]:
    """
    깊이 맵에서 바닥 위험을 감지해 경고 목록을 반환.

    Args:
        depth_map: (H, W) float32 배열, 단위 ≈ 미터, 값이 작을수록 가까움
                   Depth V2의 출력을 DEPTH_SCALE 보정한 값

    Returns:
        list of hazard dict, 각 항목:
            type       — "drop"(낙차) | "step"(턱) | "narrow"(좁은통로)
            distance_m — 위험 지점까지 추정 거리(m)
            message    — 한국어 경고 문장 (TTS로 바로 읽을 수 있는 형태)
            risk       — 0.0 ~ 1.0 (높을수록 위험)
    """
    h, w = depth_map.shape

    # 분석할 바닥 영역: 이미지 하단 60%
    floor_y0 = int(h * _FLOOR_START)
    floor = depth_map[floor_y0:, :]   # shape: (fh, w)
    fh = floor.shape[0]

    if fh < _N_BANDS:
        return []  # 이미지가 너무 작으면 분석 불가

    # ── 수평 밴드별 중앙값 깊이 계산 ─────────────────────────────────────
    # 이미지 측면(벽·장애물)의 노이즈를 줄이기 위해 중앙 50% 너비만 사용
    cx_lo, cx_hi = w // 4, 3 * w // 4
    band_h = fh // _N_BANDS

    band_depths = []
    for i in range(_N_BANDS):
        # band[0] = 이미지 최하단 (발 바로 앞, 가장 가까운 지점)
        # band[-1] = 바닥 영역 최상단 (가장 먼 지점)
        r_end   = fh - i * band_h
        r_start = max(0, r_end - band_h)
        patch   = floor[r_start:r_end, cx_lo:cx_hi]
        if patch.size == 0:
            continue
        # 중앙값: 평균보다 이상치(벽·물체)에 덜 민감
        band_depths.append(float(np.median(patch)))

    if len(band_depths) < 4:
        return []  # 밴드가 4개 이상 있어야 변화율 분석 의미 있음

    hazards: list[dict] = []

    # ── 인접 밴드 간 깊이 변화율 분석 ────────────────────────────────────
    for i in range(len(band_depths) - 1):
        d_cur  = band_depths[i]       # i번 밴드의 깊이 (발에 가까운 쪽)
        d_next = band_depths[i + 1]   # i+1번 밴드의 깊이 (조금 더 먼 쪽)
        delta  = d_next - d_cur       # 양수 = 멀어짐(낙차), 음수 = 가까워짐(턱)

        # ── 낙차 / 계단 하강 감지 ─────────────────────────────────────
        # delta > _DROP_THRESH: 바닥이 갑자기 1.2m 이상 멀어짐 → 낙차
        # d_cur < _MAX_WARN_DIST: 너무 먼 곳의 낙차는 경고 불필요
        if delta > _DROP_THRESH and d_cur < _MAX_WARN_DIST:
            # risk: delta가 클수록, 가까울수록 위험도 증가
            risk = min(1.0, delta / 3.0) * (1 - d_cur / _MAX_WARN_DIST)
            hazards.append({
                "type":       "drop",
                "distance_m": round(d_cur, 1),
                "message":    f"조심! {round(d_cur, 1)}m 앞에 계단이나 낙차가 있어요. 멈추세요.",
                "risk":       round(risk, 2),
            })
            break  # 가장 가까운 위험 1개만 보고 (여러 개 경고는 혼란)

        # ── 계단 상승 / 턱 감지 ──────────────────────────────────────
        # delta < -_STEP_THRESH: 바닥이 갑자기 1.0m 이상 가까워짐 → 턱/계단
        if delta < -_STEP_THRESH and d_next < _MAX_WARN_DIST:
            risk = min(1.0, abs(delta) / 2.0) * (1 - d_next / _MAX_WARN_DIST)
            hazards.append({
                "type":       "step",
                "distance_m": round(d_next, 1),
                "message":    f"발 앞에 턱이나 계단이 있어요. 약 {round(d_next, 1)}m.",
                "risk":       round(risk, 2),
            })
            break

    # ── 좁은 통로 감지 (낙차·턱 없을 때만) ──────────────────────────────
    # 좌우 벽이 중앙보다 훨씬 가까우면 좁은 통로로 판단
    if not hazards:
        mid_band    = band_depths[len(band_depths) // 2]  # 중간 밴드 깊이
        left_patch  = floor[fh // 4:3 * fh // 4, :w // 4]        # 왼쪽 25%
        right_patch = floor[fh // 4:3 * fh // 4, 3 * w // 4:]    # 오른쪽 25%
        left_d  = float(np.median(left_patch))
        right_d = float(np.median(right_patch))

        # 양쪽이 중앙보다 50% 이상 가깝고, 통로 자체가 3m 이내
        if left_d < mid_band * 0.5 and right_d < mid_band * 0.5 and mid_band < 3.0:
            hazards.append({
                "type":       "narrow",
                "distance_m": round(mid_band, 1),
                "message":    "좁은 통로예요. 천천히 이동하세요.",
                "risk":       0.4,
            })

    return hazards
