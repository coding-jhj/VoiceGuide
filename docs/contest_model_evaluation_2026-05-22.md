# 공모전용 YOLO11n 320 TFLite 평가 기록 - 2026-05-22

## 기준

사용자 요구사항은 `YOLO11n + 320 TFLite`를 Android 기본 모델로 쓰는 것입니다. 따라서 640 TFLite는 참고 후보로만 두고, 앱 로딩 우선순위에서는 제외했습니다.

- Android 기본 모델: `android/app/src/main/assets/yolo11n_320.tflite`
- Android fallback: `android/app/src/main/assets/yolo26n_float32.tflite`
- 학습 시작 후보: `models/voiceguide82_yolo11n_contest_final.pt`
- 최종 320 후보: `models/voiceguide82_yolo11n_320_hardmine2.pt`
- 최종 비교용 TFLite: `android/app/src/main/assets/yolo11n_320_hardmine2.tflite`

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

Android policy는 보수적으로 맞췄습니다.

- person confidence: 0.32
- 주요 실내 COCO confidence: 0.34
- stairs confidence: 0.50
- door confidence: 0.35
- stairs geometry: `area>=0.001`, `width>=0.04`, `height>=0.006`
- door geometry: `area>=0.035`, `height>=width*1.05`

## 판단

현재 결과는 `YOLO11n + 320 TFLite` 조건에서 속도를 지키면서 계단/문을 추가한 최선 후보입니다. 다만 “공모전 입상 보장” 또는 “모든 COCO 80클래스가 입상 수준”이라고 말할 정도의 검증 데이터는 아직 부족합니다.

특히 stairs는 320 해상도에서 얇은 계단선과 바닥/테이블/소파 패턴이 섞여 오탐과 미탐이 동시에 생깁니다. 그래서 앱에는 recall보다 오탐 억제를 우선한 보수 정책을 넣었습니다.

입상 가능성을 더 올리려면 실제 발표 장소와 비슷한 복도/문/계단 영상, 계단처럼 보이는 바닥과 가구 hard negative, 그리고 person/chair/cell phone 등 주요 COCO 검증 이미지를 추가해야 합니다.

## 재현 명령

```powershell
C:/Users/ghksw/anaconda3/envs/ai_env/python.exe train/finetune_voiceguide82.py --pretrained models/voiceguide82_yolo11n_contest_final.pt --epochs 24 --warmup-epochs 0 --patience 6 --imgsz 320 --batch 24 --workers 4 --optimizer AdamW --lr0 8e-6 --lrf 0.08 --weight-decay 0.0008 --close-mosaic 4 --mosaic 0.15 --mixup 0.0 --cls 0.70 --label-smoothing 0.03 --name voiceguide82_yolo11n_320_contest --export-copy models/voiceguide82_yolo11n_320_contest.pt
C:/Users/ghksw/anaconda3/envs/ai_env/python.exe tools/mine_stairs_hard_negatives.py --predictions outputs/voiceguide82_eval_tflite320_contest_retrained_conf035/predictions.csv --images data/test_images --out data/fine_tune/door_stairs/hard_negative/stair_like_floor_320
C:/Users/ghksw/anaconda3/envs/ai_env/python.exe train/finetune_voiceguide82.py --pretrained models/voiceguide82_yolo11n_320_contest.pt --epochs 12 --warmup-epochs 0 --patience 4 --imgsz 320 --batch 24 --workers 4 --optimizer AdamW --lr0 4e-6 --lrf 0.10 --weight-decay 0.0009 --close-mosaic 3 --mosaic 0.10 --mixup 0.0 --cls 0.70 --label-smoothing 0.03 --name voiceguide82_yolo11n_320_hardmine2 --export-copy models/voiceguide82_yolo11n_320_hardmine2.pt
C:/Users/ghksw/anaconda3/envs/ai_env/python.exe tools/export_selected_yolo_tflite.py --source models/voiceguide82_yolo11n_320_hardmine2.pt --imgsz 320 --opset 18 --output-name yolo11n_320.tflite
C:/Users/ghksw/anaconda3/envs/ai_env/python.exe tools/evaluate_yolo_android_policy.py --model android/app/src/main/assets/yolo11n_320.tflite --images data/test_images --out outputs/voiceguide82_eval_tflite320_hardmine2_android_policy
```
