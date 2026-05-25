# VoiceGuide Scenario Data

`final_*` 파일 4개를 기준으로 넣은 발표/앱 데모용 최종 공공데이터 패키지입니다.

## Main files

- `final_route_comparison.csv`
  - 보라매역 → 서울시남부장애인종합복지관 시나리오의 A/B 경로 비교표입니다.
  - `approx_distance_m`, `distance_delta_vs_shortest_m`, `final_selection_reason`을 포함합니다.
- `final_crosswalk_accessibility.csv`
  - 동작구 횡단보도 1,025건의 보행지원시설 점수표입니다.
  - 등급 분포: `preferred` 54건, `recommended` 314건, `basic` 610건, `insufficient` 47건.
  - 음향신호기/보행자작동신호기 근접 ID와 거리 컬럼을 포함합니다.
- `final_crosswalk_accessibility.geojson`
  - `final_crosswalk_accessibility.csv`에서 생성한 지도 레이어용 GeoJSON입니다.
- `final_scenario_dataset.json`
  - 목적지 후보, 추천 횡단보도, A/B 비교, TTS 문장, 이동지원센터 fallback을 한 번에 읽는 JSON입니다.
- `final_tts_guidance.csv`
  - 사용자에게 들려줄 안내 문장과 진동 패턴입니다.
- `final_data_usage.html`
  - 팀 공유/발표 설명용 HTML입니다.
- `before_after_update.html`
  - 다운로드 최종 데이터 반영 전과 반영 후의 차이를 설명하는 비교 HTML입니다.

기존 코드 호환을 위해 `dongjak_crosswalk_accessibility.csv`, `dongjak_crosswalk_accessibility.geojson`, `voiceguide_scenario_dataset.json`, `voiceguide_scenario_data_usage.html`도 같은 최종 데이터 기준으로 맞춰 둡니다.

## Demo pair

- A: `06-0000016344` · 동작구 신대방동 349-35도 · 817m · 1점 · `basic`
- B: `06-0000032157` · 동작구 신대방동 산112-5도 · 825m · 7점 · `preferred`
- 선택 이유: 약 8m 더 이동하지만 보행등, 음향신호기, 보행자작동신호기 근거가 있어 B를 선택합니다.
- 안내 문장: 최단 후보보다 약 8미터 더 이동하지만, 보행등과 음향신호기, 보행자작동신호기 정보가 있는 횡단보도로 안내합니다.

현재 거리는 지도 경로 API가 아니라 대표 횡단보도 경유 직선거리 합 기반 데모값입니다.
