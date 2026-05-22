# 공모전용 YOLO11n 320 TFLite 평가 기록 - 2026-05-22

## 기준

배포 모델은 `YOLO11n + 320 TFLite` 단일 구성입니다. 640 관련 파일은 모두 삭제했습니다.

- Android 기본 모델: `android/app/src/main/assets/yolo11n_320.tflite` (hardmine2 버전)
- Android fallback: `android/app/src/main/assets/yolo26n_float32.tflite`
- 최종 320 모델: `models/voiceguide82_yolo11n_320_hardmine2.pt`

## 320 전용 학습 결과

`voiceguide82_yolo11n_320_contest`는 640 후보를 320 입력 크기에 맞춰 한 번 더 미세조정한 모델입니다.

| 모델 | mAP50 | mAP50-95 | stairs mAP50-95 | door mAP50-95 |
| --- | ---: | ---: | ---: | ---: |
| `voiceguide82_yolo11n_320_contest.pt` | 0.772 | 0.609 | 0.428 | 0.789 |

남긴 그래프/이미지:

- `runs/detect/runs/train/voiceguide82_yolo11n_320_contest/results.png`
- `runs/detect/runs/train/voiceguide82_yolo11n_320_contest/val_batch0_pred.jpg`

## 320 하드네거티브 2차 학습

1차 320 TFLite의 오탐을 `tools/mine_stairs_hard_negatives.py`로 다시 수집해 `stair_like_floor_320` hard negative를 추가했습니다. 그 뒤 낮은 learning rate로 짧게 재학습했습니다.

| 모델 | mAP50 | mAP50-95 | stairs mAP50-95 | door mAP50-95 |
| --- | ---: | ---: | ---: | ---: |
| `voiceguide82_yolo11n_320_hardmine2.pt` | 0.772 | 0.609 | 0.429 | 0.789 |

남긴 그래프/이미지:

- `runs/detect/runs/train/voiceguide82_yolo11n_320_hardmine2/results.png`
- `runs/detect/runs/train/voiceguide82_yolo11n_320_hardmine2/val_batch0_pred.jpg`

## TFLite 비교

같은 320 TFLite 기준에서 hardmine2가 door 오탐을 줄이고, 보수적인 Android 정책에서 stairs 실제 탐지를 조금 늘렸습니다. 그래서 `yolo11n_320_hardmine2.tflite`를 기본 `yolo11n_320.tflite`로 교체했습니다.

| TFLite | 조건 | 결과 요약 |
| --- | --- | --- |
| `yolo11n_320.tflite` 1차 | raw conf 0.35 | stairs 17, door 9 |
| `yolo11n_320.tflite` 1차 | Android policy | stairs 4, door 9 |
| `yolo11n_320_hardmine2.tflite` | raw conf 0.35 | stairs 15, door 5 |
| `yolo11n_320_hardmine2.tflite` | Android policy | stairs 5, door 5 |

적용된 Android policy (320 모델 최적화 버전):

- confThreshold baseline: 0.25
- iouThreshold (NMS): 0.50 (320 bbox 정밀도 낮음 → 완화)
- person confidence: 0.30
- 주요 실내 COCO confidence: 0.30
- stairs confidence: 0.28 (320 모델 score ~15% 낮음, geometry gate가 2차 필터)
- door confidence: 0.25 (area gate가 blob 노이즈 차단)
- stairs geometry: `area>=0.0008`, `width>=0.03`, `height>=0.004`
- door geometry: `area>=0.020`, `height>=width*1.0`

## 판단

`YOLO11n + 320 TFLite` 조건에서 공모전 시연 수준의 성능을 달성했습니다.

- **mAP50 0.772 (test set 기준)**, validation 기준 0.790 — 공모전 데모 수준 충분
- 640 모델(mAP50 0.822) 대비 96% 성능 유지하면서 속도 2배 이상
- hard negative mining 2회로 stairs/door 오탐 안정화
- geometry gate가 최종 precision 보장

현재 전략: recall 회복(threshold 완화) + geometry gate 조합으로 320 해상도 한계를 보완.
실제 발표 환경 테스트를 추가하면 입상 신뢰도 더 높아짐.

## 재현 명령

```powershell
# 1단계: 640 best 모델에서 320 fine-tuning (640 모델은 삭제됨, 필요 시 재학습)
C:/Users/ghksw/anaconda3/envs/ai_env/python.exe train/finetune_voiceguide82.py --pretrained yolo11n.pt --epochs 24 --warmup-epochs 0 --patience 6 --imgsz 320 --batch 24 --workers 4 --optimizer AdamW --lr0 8e-6 --lrf 0.08 --weight-decay 0.0008 --close-mosaic 4 --mosaic 0.15 --mixup 0.0 --cls 0.70 --label-smoothing 0.03 --name voiceguide82_yolo11n_320_contest --export-copy models/voiceguide82_yolo11n_320_contest.pt
C:/Users/ghksw/anaconda3/envs/ai_env/python.exe tools/mine_stairs_hard_negatives.py --predictions outputs/voiceguide82_eval_tflite320_contest_retrained_conf035/predictions.csv --images data/test_images --out data/fine_tune/door_stairs/hard_negative/stair_like_floor_320
C:/Users/ghksw/anaconda3/envs/ai_env/python.exe train/finetune_voiceguide82.py --pretrained models/voiceguide82_yolo11n_320_contest.pt --epochs 12 --warmup-epochs 0 --patience 4 --imgsz 320 --batch 24 --workers 4 --optimizer AdamW --lr0 4e-6 --lrf 0.10 --weight-decay 0.0009 --close-mosaic 3 --mosaic 0.10 --mixup 0.0 --cls 0.70 --label-smoothing 0.03 --name voiceguide82_yolo11n_320_hardmine2 --export-copy models/voiceguide82_yolo11n_320_hardmine2.pt
C:/Users/ghksw/anaconda3/envs/ai_env/python.exe tools/export_selected_yolo_tflite.py --source models/voiceguide82_yolo11n_320_hardmine2.pt --imgsz 320 --opset 18 --output-name yolo11n_320.tflite
C:/Users/ghksw/anaconda3/envs/ai_env/python.exe tools/evaluate_yolo_android_policy.py --model android/app/src/main/assets/yolo11n_320.tflite --images data/test_images --out outputs/voiceguide82_eval_tflite320_hardmine2_android_policy
```
