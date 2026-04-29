# 탐지/바운딩 박스 디버깅 보고서

## 요약

바운딩 박스가 실제 물체 위치와 맞지 않았던 주된 원인은 `src/vision/detect.py`에서 YOLO 추론 전에 이미지를 좌우 반전하고 있었기 때문입니다.

문제는 YOLO는 좌우 반전된 이미지 기준으로 박스를 예측하는데, Gradio 화면, Android 화면, Depth Anything 거리 샘플링은 원본 이미지 기준으로 그 좌표를 사용했다는 점입니다.

즉, 탐지는 되었지만 반환된 `bbox` 좌표계가 원본 이미지와 달라서 박스가 반대편에 그려지고, Depth 거리도 엉뚱한 위치에서 샘플링될 수 있었습니다.

## 원인

수정 전 문제 코드:

```python
img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
img = cv2.flip(img, 1)
```

이 코드 때문에 발생한 흐름:

- YOLO는 좌우 반전된 이미지에서 물체를 탐지했습니다.
- 반환된 `bbox` 좌표는 반전 이미지 기준 좌표였습니다.
- 하지만 Gradio와 Android는 원본 이미지 위에 그 좌표를 그대로 그렸습니다.
- Depth Anything은 원본 이미지의 depth map을 만들고, 반전 좌표로 깊이를 샘플링했습니다.

결과적으로 실제 물체는 오른쪽에 있는데 박스는 왼쪽에 찍히거나, 거리 추정이 물체가 아닌 다른 영역을 기준으로 계산될 수 있었습니다.

## 수정 내용

`detect_objects()`에서 무조건 좌우 반전하던 코드를 제거했습니다.

현재 처리 방식:

```python
img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
h, w = img.shape[:2]
```

나중에 전면 카메라 미러링 보정이 필요하면, 이미지 자체를 뒤집어서 YOLO에 넣기보다는 `camera_orientation` 또는 별도 좌표 변환 로직으로 처리하는 편이 안전합니다.

## 검증 환경

- Conda 환경: `ai_env`
- Python: `3.10.20`
- YOLO 모델: `yolo11m.pt`
- Depth 모델: `depth_anything_v2_vits.pth`

실행한 검증 명령:

```powershell
python -m compileall -q app.py src
python -m pytest -q tests -p no:cacheprovider
```

결과:

```text
21 passed, 2 warnings
```

Depth Anything 확인:

```text
[Depth V2] 모델 파일 확인: depth_anything_v2_vits.pth
[Depth V2] 모델 로드 완료 (device=cpu)
sources ['v2']
```

## 바운딩 박스 정렬 검증

검증은 아래 세 가지를 비교했습니다.

- 원본 이미지에 YOLO를 바로 실행한 결과
- 수정 전 방식: 좌우 반전 이미지에 YOLO를 실행한 뒤, 그 좌표를 원본 이미지에 그대로 그린 결과
- 수정 후 방식: `detect_objects()`에서 반환한 결과

| 이미지 | 원본 YOLO 탐지 수 | 수정 전 flip 탐지 수 | 수정 후 반환 수 | 수정 후 원본 대비 평균 IoU | 수정 전 평균 X축 오차 |
|---|---:|---:|---:|---:|---:|
| `data/test_images/backpack/backpack_000.jpg` | 7 | 6 | 3 | 1.000 | 427.6 px |
| `data/test_images/car/01_15-05-23-Berlin-Sachsendamm-Tesla-RalfR-N3S_7354.jpg` | 5 | 5 | 3 | 1.000 | 378.1 px |
| `data/test_images/bus/01_168_bus_on_Camden_High_Street,_May_2021.jpg` | 9 | 6 | 3 | 1.000 | 601.4 px |

해석:

- 수정 전 방식은 원본 기준으로 중심 좌표가 수백 픽셀씩 어긋났습니다.
- 수정 후 반환 박스는 원본 YOLO 결과와 평균 IoU `1.000`으로 일치했습니다.

## 비교 이미지

생성된 디버그 이미지:

- `results/detection_debug/backpack_000_bbox_compare.jpg`
- `results/detection_debug/01_15-05-23-Berlin-Sachsendamm-Tesla-RalfR-N3S_7354_bbox_compare.jpg`
- `results/detection_debug/01_168_bus_on_Camden_High_Street,_May_2021_bbox_compare.jpg`

색상 의미:

- 빨간색: 수정 전, 좌우 반전 좌표를 원본 이미지에 그대로 그린 박스
- 초록색: 원본 이미지 기준 raw YOLO 박스
- 파란색: 수정 후 `detect_objects()` 반환 박스

## 남은 참고 사항

현재 `detect_objects()`는 YOLO가 탐지한 모든 박스를 반환하지 않고, 위험도(`risk_score`) 기준 상위 3개만 반환합니다.

그래서 YOLO가 실제로는 더 많은 물체를 잡았더라도 화면이나 API 결과에는 3개만 보일 수 있습니다. 이 부분은 오류라기보다 음성 안내를 짧게 유지하려는 설계입니다.

다만 시각 디버깅 화면에서 모든 박스를 보고 싶다면, 다음처럼 구조를 나누는 것이 좋습니다.

- 음성 안내용: 위험도 상위 3개
- 화면 디버깅/검증용: 전체 탐지 박스

또한 현재 기본 모델은 `yolo11m.pt`라서 일반 COCO 물체에는 강하지만, 실내 장애물이나 한국 보행 환경 특화 물체는 오탐이 남을 수 있습니다. 정확도를 더 올리려면 `yolo11m_indoor.pt` 같은 파인튜닝 모델을 사용하는 것이 좋습니다.
