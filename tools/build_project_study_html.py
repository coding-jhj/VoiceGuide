from __future__ import annotations

import html
import json
import re
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "voiceguide_project_study_guide.html"

CODE_PATHS = [
    "android/app/src/main/AndroidManifest.xml",
    "android/app/src/main/assets/policy_default.json",
    "android/app/src/main/java/com/voiceguide/BoundingBoxOverlay.kt",
    "android/app/src/main/java/com/voiceguide/Detection.kt",
    "android/app/src/main/java/com/voiceguide/MainActivity.kt",
    "android/app/src/main/java/com/voiceguide/MvpPipeline.kt",
    "android/app/src/main/java/com/voiceguide/PerfCsvLogger.kt",
    "android/app/src/main/java/com/voiceguide/SentenceBuilder.kt",
    "android/app/src/main/java/com/voiceguide/TfliteYoloDetector.kt",
    "android/app/src/main/java/com/voiceguide/VoiceGuideConstants.kt",
    "android/app/src/main/java/com/voiceguide/VoicePolicy.kt",
    "android/app/src/main/java/com/voiceguide/YoloOutputFormat.kt",
    "android/app/src/main/res/layout/activity_main.xml",
    "android/app/src/main/res/values/colors.xml",
    "android/app/src/main/res/values/strings.xml",
    "android/app/src/main/res/values/styles.xml",
    "android/app/src/test/java/com/voiceguide/PerfCsvLoggerTest.kt",
    "android/app/src/test/java/com/voiceguide/YoloOutputFormatTest.kt",
    "src/api/main.py",
    "src/api/routes.py",
    "src/api/db.py",
    "src/api/detections.py",
    "src/api/events.py",
    "src/api/locations.py",
    "src/api/tracker.py",
    "src/config/policy.py",
    "src/config/policy.json",
    "src/nlg/sentence.py",
    "src/nlg/templates.py",
    "templates/dashboard.html",
    "tests/conftest.py",
    "tests/test_api.py",
    "tests/test_imports.py",
    "tests/test_policy.py",
    "tests/test_sentence.py",
    "tests/test_server.py",
    "tests/test_simulation.py",
    "tools/analyze_perf.py",
    "tools/build_condition_test_images.py",
    "tools/build_test_images.py",
    "tools/contest_eval_report.py",
    "tools/dummy_scenes.py",
    "tools/export_onnx.py",
    "tools/export_selected_yolo_tflite.py",
    "tools/probe_server_link.py",
    "tools/quick_detect.py",
    "tools/simulator.py",
    "tools/test_heatmap.js",
    "tools/test_heatmap_runner.py",
    "tools/verify.py",
    "train/finetune.py",
    "train/finetune_cellphone.py",
    "train/prepare_cellphone.py",
    "train/prepare_dataset.py",
]

AUTO_CODE_ROOTS = [
    "android",
    "src",
    "templates",
    "tests",
    "tools",
    "train",
]

TEXT_SUFFIXES = {
    ".bat",
    ".gradle",
    ".html",
    ".js",
    ".json",
    ".kt",
    ".md",
    ".properties",
    ".pro",
    ".ps1",
    ".py",
    ".toml",
    ".txt",
    ".xml",
    ".yml",
    ".yaml",
}

ROOT_TEXT_FILES = [
    ".dockerignore",
    ".env.example",
    ".gcloudignore",
    ".gitignore",
    "Dockerfile",
    "README.md",
    "pytest.ini",
    "requirements-dev.txt",
    "requirements.txt",
    "ruff.toml",
]


FILE_NOTES = {
    "android/app/src/main/AndroidManifest.xml": "앱 권한, MainActivity 진입점, 파일 공유 provider, 음성 바로가기 같은 Android 런타임 선언을 모은 파일입니다.",
    "android/app/src/main/assets/policy_default.json": "서버 정책을 못 받을 때 쓰는 기본 위험군, 거리 표현, 발화 기준 정책입니다.",
    "android/app/src/main/java/com/voiceguide/MainActivity.kt": "카메라, YOLO, TTS/STT, GPS, 서버 전송, 성능 CSV 기록까지 앱의 실제 실행 흐름을 조립하는 중심 파일입니다.",
    "android/app/src/main/java/com/voiceguide/TfliteYoloDetector.kt": "TFLite YOLO 모델 로딩, YUV 프레임 전처리, 출력 shape 해석, bbox 후처리를 담당합니다.",
    "android/app/src/main/java/com/voiceguide/MvpPipeline.kt": "검출 결과를 트래킹하고 위험도, 이벤트 타입, 진동 패턴, 발화 여부를 결정하는 온디바이스 안전 판단 레이어입니다.",
    "android/app/src/main/java/com/voiceguide/SentenceBuilder.kt": "검출 객체를 한국어 안내 문장으로 바꾸는 Android 로컬 문장 생성기입니다.",
    "android/app/src/main/java/com/voiceguide/VoicePolicy.kt": "서버 또는 기본 JSON 정책을 읽어 위험군, 거리, 보행 보조 기준을 Kotlin 코드에 제공합니다.",
    "android/app/src/main/java/com/voiceguide/PerfCsvLogger.kt": "실행 중 FPS와 단계별 처리 시간을 CSV로 남겨 성능 분석 자료를 만듭니다.",
    "src/api/main.py": "FastAPI 앱 생성, CORS, 헬스체크, DB 상태 확인, 라우터 연결을 담당하는 서버 입구입니다.",
    "src/api/routes.py": "Android가 호출하는 /detect, /detect_json, /gps, /status, 대시보드 API 대부분이 들어 있는 서버 핵심 라우터입니다.",
    "src/api/db.py": "SQLite/Postgres 양쪽을 지원하는 저장소 레이어로, 탐지 이벤트, GPS, 위치, 히트맵, 성능 지표를 저장하고 조회합니다.",
    "src/api/tracker.py": "서버 측 세션별 객체 트래킹, voting buffer, smoothing, 상태 스냅샷을 관리합니다.",
    "src/api/detections.py": "Android/legacy 입력 객체를 서버 표준 detection 객체로 정규화합니다.",
    "src/nlg/sentence.py": "서버 측 한국어 안내 문장 생성기입니다. 조사, 거리 표현, 질문 모드, 물건 찾기, 들고 있는 물건 안내를 처리합니다.",
    "templates/dashboard.html": "보호자/개발자용 웹 대시보드입니다. 최근 이벤트, 지도, 히트맵, SSE 업데이트 UI가 들어 있습니다.",
}


SECTIONS = [
    {
        "id": "overview",
        "title": "1. 프로젝트를 한 문장으로 잡기",
        "body": """
        <p><strong>VoiceGuide</strong>는 Android 카메라로 주변 사물을 실시간 인식하고, 위험도에 따라 진동과 한국어 음성 안내를 제공하는 시각 보조 MVP입니다. 서버는 FastAPI로 탐지 결과, GPS, 위치 저장, 대시보드, 히트맵, 성능 로그를 관리합니다.</p>
        <div class="flow">
          <div><b>Android</b><span>CameraX, TFLite YOLO, TTS/STT, GPS, CSV 성능 로그</span></div>
          <div><b>판단</b><span>중복 제거, voting, tracking, risk score, vibration, sentence</span></div>
          <div><b>Server</b><span>FastAPI, DB, tracker, NLG, dashboard events</span></div>
          <div><b>Dashboard</b><span>최근 상황, 지도, 히스토리, 히트맵, 상태 확인</span></div>
        </div>
        """,
    },
    {
        "id": "map",
        "title": "2. 폴더별 역할 지도",
        "body": """
        <div class="grid two">
          <article><h3>android/</h3><p>실제 사용자 앱입니다. 카메라 프레임을 받아 YOLO 추론을 하고, 즉시 진동/TTS를 실행합니다. 서버가 꺼져도 핵심 경고는 로컬에서 살아 있어야 합니다.</p></article>
          <article><h3>src/</h3><p>FastAPI 서버입니다. 탐지 결과 저장, 최근 상태 조회, 위치 기능, 대시보드용 이벤트 스트림, 정책 API, 문장 생성 기능을 담당합니다.</p></article>
          <article><h3>templates/</h3><p>서버가 렌더링하는 웹 대시보드 HTML입니다. 발표와 디버깅에서 현재 세션 상태를 눈으로 확인하는 화면입니다.</p></article>
          <article><h3>tests/</h3><p>서버 API, 정책, 문장 생성, 시뮬레이션을 검증하는 pytest 테스트입니다. merge 뒤 회귀를 빨리 잡는 안전망입니다.</p></article>
          <article><h3>tools/</h3><p>성능 분석, 서버 연결 진단, 더미 장면 전송, 테스트 이미지 수집, TFLite export 같은 운영/검증 도구입니다.</p></article>
          <article><h3>train/</h3><p>데이터셋 준비와 YOLO fine-tuning 스크립트입니다. 모델 성능 문제가 생겼을 때 학습 데이터 흐름을 추적하는 출발점입니다.</p></article>
        </div>
        """,
    },
    {
        "id": "android-flow",
        "title": "3. Android 실행 흐름",
        "body": """
        <ol class="steps">
          <li><b>권한과 화면 초기화</b><span>MainActivity가 카메라, 위치, TTS/STT, 서버 URL 입력, 오버레이를 준비합니다.</span></li>
          <li><b>카메라 프레임 수신</b><span>CameraX ImageAnalysis가 프레임을 넘기면 처리 주기를 조절해 배터리와 발열을 관리합니다.</span></li>
          <li><b>YOLO 추론</b><span>TfliteYoloDetector가 YUV 프레임을 모델 입력 크기로 바꾸고, yolo11n 우선으로 TFLite 추론을 수행합니다.</span></li>
          <li><b>검출 안정화</b><span>중복 bbox 제거, 최근 프레임 voting, MvpPipeline tracking/EMA로 순간 오검출을 줄입니다.</span></li>
          <li><b>안전 판단</b><span>거리, 화면 중심성, 객체 종류, bbox 크기로 riskScore를 만들고 진동 패턴과 발화 여부를 정합니다.</span></li>
          <li><b>사용자 피드백</b><span>긴급 경고는 로컬에서 바로 진동/TTS가 나가고, 서버 전송은 백그라운드로 진행됩니다.</span></li>
          <li><b>성능 기록</b><span>PerfCsvLogger가 FPS와 단계별 ms 값을 CSV로 저장해 병목 분석이 가능하게 합니다.</span></li>
        </ol>
        """,
    },
    {
        "id": "server-flow",
        "title": "4. 서버와 대시보드 흐름",
        "body": """
        <p>서버는 앱의 즉시 경고를 대신하지 않고, 기록/관찰/문장 생성/상태 공유를 맡습니다. 이 분리가 중요합니다. 네트워크가 느려도 보행 안전 판단은 Android에서 먼저 끝나야 합니다.</p>
        <div class="diagram">
          <div>POST /detect_json<br><small>Android detection payload</small></div>
          <div>normalize + tracker<br><small>detections.py, tracker.py</small></div>
          <div>DB 저장<br><small>db.py</small></div>
          <div>SSE/REST 조회<br><small>dashboard.html</small></div>
        </div>
        <p><code>/api/policy</code>는 앱과 서버가 같은 위험군/거리 기준을 공유하게 해 주는 연결고리입니다. 정책이 어긋나면 같은 검출 결과라도 앱과 서버 안내가 달라질 수 있습니다.</p>
        """,
    },
    {
        "id": "model",
        "title": "5. 모델과 인식 파이프라인에서 꼭 봐야 할 점",
        "body": """
        <div class="callout warning">
          <b>모델 파일은 코드만큼 위험합니다.</b>
          <p>최근 merge 이슈처럼 TFLite 파일 하나가 바뀌면 컴파일은 성공해도 모든 객체가 특정 클래스로 쏠릴 수 있습니다. 그래서 모델 출력 shape, class index, confidence 분포, 샘플 이미지 결과를 함께 봐야 합니다.</p>
        </div>
        <ul class="checklist">
          <li><code>yolo11n_320.tflite</code>가 기본 모델이며 Android는 이 파일을 우선 선택합니다.</li>
          <li><code>YoloOutputFormat.kt</code>는 raw YOLO 출력인지 NMS 완료 출력인지 shape로 구분합니다.</li>
          <li><code>TfliteYoloDetector.kt</code>는 output tensor를 읽어 bbox, confidence, class를 Detection으로 바꿉니다.</li>
          <li>문/계단 fine-tuning은 모델, class map, threshold, 정책이 같이 맞아야 앱 기능으로 살아납니다.</li>
        </ul>
        """,
    },
    {
        "id": "tests",
        "title": "6. 테스트와 디버깅 루트",
        "body": """
        <p>이 프로젝트는 Android 빌드, Kotlin unit test, Python pytest, 도구 스크립트를 함께 봐야 전체 상태가 보입니다.</p>
        <div class="command-grid">
          <code>cd android && ./gradlew testDebugUnitTest assembleDebug</code>
          <span>Android 컴파일과 로컬 단위 테스트 확인</span>
          <code>python -m pytest</code>
          <span>FastAPI, 문장 생성, 정책, 시뮬레이션 테스트 확인</span>
          <code>python tools/probe_server_link.py</code>
          <span>앱-서버 연결 문제를 더미 이미지로 빠르게 진단</span>
          <code>python tools/analyze_perf.py</code>
          <span>FPS/latency 로그를 그래프로 변환</span>
        </div>
        """,
    },
    {
        "id": "reading",
        "title": "7. 공부 순서 추천",
        "body": """
        <ol class="steps compact">
          <li><b>README와 이 문서 1~4장</b><span>전체 목표와 데이터 흐름을 먼저 잡습니다.</span></li>
          <li><b>MainActivity.kt</b><span>앱이 실제로 어떻게 움직이는지 큰 흐름을 따라갑니다.</span></li>
          <li><b>TfliteYoloDetector.kt → MvpPipeline.kt</b><span>인식 결과가 안전 판단으로 바뀌는 과정을 봅니다.</span></li>
          <li><b>SentenceBuilder.kt / src/nlg/sentence.py</b><span>같은 객체가 어떤 문장으로 안내되는지 이해합니다.</span></li>
          <li><b>routes.py → db.py → dashboard.html</b><span>서버 저장과 대시보드 표시 경로를 연결합니다.</span></li>
          <li><b>tests/와 tools/</b><span>고장났을 때 어디부터 확인할지 자기 손에 익힙니다.</span></li>
        </ol>
        """,
    },
]


def read_text(rel: str) -> str:
    path = ROOT / rel
    return path.read_text(encoding="utf-8", errors="replace")


def file_meta(rel: str) -> dict[str, object]:
    text = read_text(rel)
    lines = text.count("\n") + (1 if text else 0)
    symbols = re.findall(
        r"^\s*(?:class|data class|object|interface|enum class|fun|def|async def)\s+([A-Za-z_][\w]*)",
        text,
        flags=re.MULTILINE,
    )
    routes = re.findall(r"@\w+\.(?:get|post|delete|put|patch)\(\"([^\"]+)\"", text)
    return {
        "rel": rel,
        "text": text,
        "lines": lines,
        "size": (ROOT / rel).stat().st_size,
        "symbols": symbols[:24],
        "routes": routes[:24],
        "note": FILE_NOTES.get(rel, "프로젝트 동작을 구성하는 실제 코드/설정 파일입니다. 아래 원문을 펼치면 현재 저장소 기준 내용을 그대로 확인할 수 있습니다."),
    }


def collect_code_paths() -> list[str]:
    paths = set(CODE_PATHS)
    for rel in ROOT_TEXT_FILES:
        if (ROOT / rel).exists():
            paths.add(rel)
    for root_rel in AUTO_CODE_ROOTS:
        root = ROOT / root_rel
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            rel_parts = path.relative_to(ROOT).parts
            if "build" in rel_parts or ".gradle" in rel_parts:
                continue
            if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"Dockerfile"}:
                continue
            if path.name == "local.properties":
                continue
            paths.add(path.relative_to(ROOT).as_posix())
    return sorted(paths)


def asset_table() -> str:
    rows = []
    for rel in [
        "android/app/src/main/assets/yolo11n_320.tflite",
        "android/app/src/main/assets/yolo26n_float32.tflite",
        "android/app/src/main/assets/yolo11m.onnx",
        "models/yolo11n.pt",
        "models/yolo11m.pt",
        "models/depth_anything_v2_vits.pth",
    ]:
        p = ROOT / rel
        if p.exists():
            rows.append(f"<tr><td><code>{html.escape(rel)}</code></td><td>{p.stat().st_size:,} bytes</td></tr>")
    return "<table><thead><tr><th>파일</th><th>크기</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"


def code_block(meta: dict[str, object]) -> str:
    rel = str(meta["rel"])
    lang = Path(rel).suffix.lstrip(".") or "text"
    symbols = ", ".join(str(s) for s in meta["symbols"]) or "주요 symbol 없음"
    routes = ", ".join(str(r) for r in meta["routes"])
    route_line = f"<p class=\"tiny\"><b>API route:</b> {html.escape(routes)}</p>" if routes else ""
    return f"""
    <details class="code-card">
      <summary>
        <span>{html.escape(rel)}</span>
        <small>{meta["lines"]} lines · {meta["size"]:,} bytes</small>
      </summary>
      <div class="code-note">
        <p>{html.escape(str(meta["note"]))}</p>
        <p class="tiny"><b>주요 symbol:</b> {html.escape(symbols)}</p>
        {route_line}
      </div>
      <pre><code class="language-{html.escape(lang)}">{html.escape(str(meta["text"]))}</code></pre>
    </details>
    """


def group_for(rel: str) -> str:
    if rel.startswith("android/"):
        return "Android 앱 코드"
    if rel.startswith("src/api"):
        return "FastAPI 서버 코드"
    if rel.startswith("src/nlg") or rel.startswith("src/config"):
        return "정책과 문장 생성"
    if rel.startswith("templates"):
        return "대시보드"
    if rel.startswith("tests") or "/src/test/" in rel:
        return "테스트"
    if rel.startswith("tools"):
        return "도구 스크립트"
    if rel.startswith("train"):
        return "학습/데이터 준비"
    return "기타"


def render() -> str:
    metas = [file_meta(rel) for rel in collect_code_paths() if (ROOT / rel).exists()]
    grouped: dict[str, list[dict[str, object]]] = {}
    for meta in metas:
        grouped.setdefault(group_for(str(meta["rel"])), []).append(meta)

    toc = "".join(f"<a href=\"#{s['id']}\">{s['title']}</a>" for s in SECTIONS)
    section_html = "".join(
        f"<section id=\"{s['id']}\" class=\"panel\"><h2>{s['title']}</h2>{s['body']}</section>"
        for s in SECTIONS
    )
    code_sections = []
    for group, items in grouped.items():
        code_sections.append(
            f"<section class=\"panel code-section\"><h2>{html.escape(group)}</h2>"
            + "".join(code_block(item) for item in items)
            + "</section>"
        )

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    total_lines = sum(int(meta["lines"]) for meta in metas)
    arch_img = "image/architecture-overview.png"
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>VoiceGuide 프로젝트 구조 학습 가이드</title>
  <style>
    :root {{
      color-scheme: light;
      --paper: #f7f4ee;
      --paper-2: #fffdf8;
      --ink: #252a2e;
      --muted: #66706b;
      --line: #ded7c9;
      --green: #2f6f5e;
      --blue: #355c7d;
      --coral: #b86650;
      --gold: #a97d2b;
      --code: #172026;
      --code-line: #2a3840;
      --shadow: 0 18px 45px rgba(39, 49, 45, .12);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Pretendard", "Inter", "Segoe UI", "Apple SD Gothic Neo", sans-serif;
      background:
        linear-gradient(180deg, rgba(255,255,255,.72), rgba(247,244,238,.96)),
        radial-gradient(circle at 12% 4%, rgba(184,102,80,.15), transparent 30%),
        radial-gradient(circle at 88% 12%, rgba(47,111,94,.16), transparent 32%),
        var(--paper);
      color: var(--ink);
      line-height: 1.68;
      letter-spacing: 0;
    }}
    a {{ color: inherit; }}
    .hero {{
      min-height: 74vh;
      display: grid;
      grid-template-columns: minmax(280px, 1.05fr) minmax(280px, .95fr);
      gap: 42px;
      align-items: center;
      padding: 64px clamp(22px, 5vw, 76px) 36px;
    }}
    .hero h1 {{
      font-size: clamp(2.25rem, 4.25vw, 4.65rem);
      line-height: 1.04;
      margin: 0 0 22px;
      max-width: 860px;
    }}
    .hero p {{ max-width: 720px; font-size: 1.08rem; color: var(--muted); margin: 0 0 26px; }}
    .hero-media {{
      min-height: 420px;
      border: 1px solid var(--line);
      background: linear-gradient(180deg, #fffdf8, #f3efe6);
      box-shadow: var(--shadow);
      overflow: hidden;
      display: grid;
      place-items: center;
      padding: 18px;
    }}
    .hero-media img {{ width: 100%; height: 100%; object-fit: contain; filter: saturate(.9) contrast(.98); }}
    .stats {{ display: flex; flex-wrap: wrap; gap: 10px; }}
    .stat {{ border: 1px solid var(--line); background: rgba(255,253,248,.74); padding: 10px 14px; min-width: 132px; }}
    .stat b {{ display: block; font-size: 1.25rem; color: var(--green); }}
    .stat span {{ color: var(--muted); font-size: .86rem; }}
    .layout {{ display: grid; grid-template-columns: 260px minmax(0, 1fr); gap: 28px; padding: 0 clamp(18px, 4vw, 64px) 72px; align-items: start; }}
    nav {{ position: sticky; top: 18px; border: 1px solid var(--line); background: rgba(255,253,248,.86); padding: 14px; box-shadow: 0 10px 25px rgba(39,49,45,.07); }}
    nav strong {{ display: block; margin: 0 0 10px; color: var(--green); }}
    nav a {{ display: block; text-decoration: none; padding: 8px 9px; border-bottom: 1px solid rgba(222,215,201,.72); font-size: .92rem; color: #3e4743; }}
    main {{ min-width: 0; }}
    .panel {{ background: rgba(255,253,248,.9); border: 1px solid var(--line); padding: clamp(22px, 3vw, 34px); margin-bottom: 22px; box-shadow: 0 12px 28px rgba(39,49,45,.06); }}
    h2 {{ margin: 0 0 16px; font-size: clamp(1.45rem, 2.2vw, 2.2rem); color: var(--blue); }}
    h3 {{ margin: 0 0 8px; color: var(--green); }}
    code {{ font-family: "Cascadia Mono", "D2Coding", Consolas, monospace; }}
    .flow, .diagram {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-top: 18px; }}
    .flow div, .diagram div, .grid article {{ border: 1px solid var(--line); background: #fbf8f0; padding: 16px; }}
    .flow b, .diagram b {{ display: block; color: var(--coral); margin-bottom: 4px; }}
    .flow span, small {{ color: var(--muted); }}
    .grid.two {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }}
    .steps {{ padding-left: 0; list-style: none; display: grid; gap: 10px; counter-reset: step; }}
    .steps li {{ counter-increment: step; position: relative; border-left: 4px solid var(--green); background: #fbf8f0; padding: 14px 16px 14px 52px; }}
    .steps li::before {{ content: counter(step); position: absolute; left: 14px; top: 15px; width: 24px; height: 24px; display: grid; place-items: center; background: var(--green); color: white; font-weight: 700; font-size: .82rem; }}
    .steps span {{ display: block; color: var(--muted); }}
    .callout {{ border-left: 5px solid var(--coral); padding: 16px 18px; background: #fff6ef; }}
    .checklist {{ display: grid; gap: 8px; padding-left: 20px; }}
    .command-grid {{ display: grid; grid-template-columns: minmax(260px, .9fr) 1fr; gap: 8px 12px; align-items: center; }}
    .command-grid code {{ background: #eef3ef; padding: 9px 10px; border: 1px solid #d7e2db; white-space: normal; overflow-wrap: anywhere; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
    th, td {{ border: 1px solid var(--line); padding: 10px; text-align: left; vertical-align: top; }}
    th {{ background: #efe7d8; color: #43514b; }}
    .code-card {{ border: 1px solid var(--line); background: #fbf8f0; margin: 10px 0; }}
    .code-card summary {{ cursor: pointer; display: flex; justify-content: space-between; gap: 18px; padding: 13px 15px; color: var(--green); font-weight: 700; }}
    .code-card summary small {{ font-weight: 500; white-space: nowrap; }}
    .code-note {{ border-top: 1px solid var(--line); padding: 12px 15px; color: var(--muted); }}
    .tiny {{ font-size: .9rem; margin: 6px 0; }}
    pre {{ margin: 0; padding: 18px; overflow: auto; background: var(--code); color: #e6edf0; border-top: 1px solid var(--code-line); max-height: 620px; }}
    pre code {{ font-size: .84rem; line-height: 1.55; white-space: pre; }}
    .asset-wrap {{ margin-top: 18px; }}
    footer {{ padding: 36px clamp(18px, 4vw, 64px); color: var(--muted); }}
    @media (max-width: 980px) {{
      .hero {{ grid-template-columns: 1fr; min-height: auto; }}
      .hero-media {{ min-height: 280px; }}
      .layout {{ grid-template-columns: 1fr; }}
      nav {{ position: static; }}
      .flow, .diagram, .grid.two, .command-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header class="hero">
    <div>
      <p class="eyebrow">VoiceGuide Study Guide · generated {html.escape(now)}</p>
      <h1>프로젝트 구조를 코드까지 펼쳐보는 학습 지도</h1>
      <p>처음 보는 사람도 Android 앱, 서버, 대시보드, 모델, 테스트가 어떻게 맞물리는지 따라갈 수 있게 정리했습니다. 설명은 위에서 흐름을 잡고, 아래에서는 실제 코드 원문을 접어서 확인하는 방식입니다.</p>
      <div class="stats">
        <div class="stat"><b>{len(metas)}</b><span>수록 파일</span></div>
        <div class="stat"><b>{total_lines:,}</b><span>수록 코드 라인</span></div>
        <div class="stat"><b>4</b><span>핵심 레이어</span></div>
      </div>
    </div>
    <figure class="hero-media">
      <img src="{html.escape(arch_img)}" alt="VoiceGuide architecture overview">
    </figure>
  </header>
  <div class="layout">
    <nav>
      <strong>읽는 순서</strong>
      {toc}
      <a href="#assets">모델/자산 파일</a>
      <a href="#source-code">전체 코드 원문</a>
    </nav>
    <main>
      {section_html}
      <section id="assets" class="panel">
        <h2>8. 모델/자산 파일 인벤토리</h2>
        <p>아래 파일들은 코드 리뷰만으로는 상태를 알기 어렵습니다. 모델 교체 후에는 반드시 샘플 이미지 결과와 output shape를 같이 확인해야 합니다.</p>
        <div class="asset-wrap">{asset_table()}</div>
      </section>
      <section id="source-code" class="panel">
        <h2>9. 전체 코드 원문</h2>
        <p>아래는 이 문서를 만들 때 저장소에서 직접 읽어온 코드입니다. 파일명을 클릭하면 펼쳐집니다.</p>
      </section>
      {''.join(code_sections)}
    </main>
  </div>
  <footer>
    이 문서는 <code>tools/build_project_study_html.py</code>로 생성되었습니다. 코드가 바뀌면 스크립트를 다시 실행해 최신 학습 가이드를 만들 수 있습니다.
  </footer>
</body>
</html>
"""


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(), encoding="utf-8", newline="\n")
    print(OUT)


if __name__ == "__main__":
    main()
