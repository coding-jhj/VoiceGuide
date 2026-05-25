// VoiceGuide 사업계획서 생성 스크립트
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, HeadingLevel, BorderStyle, WidthType,
  ShadingType, VerticalAlign, PageNumber, PageBreak, LevelFormat,
  ExternalHyperlink, TabStopType, TabStopPosition
} = require('docx');
const fs = require('fs');

// ─── 색상 팔레트 ─────────────────────────────────────────────
const C = {
  primary:    "1A3E6B",  // 진남색 (브랜드)
  secondary:  "2E75B6",  // 중간 파랑
  accent:     "F2913D",  // 오렌지 (강조)
  light:      "D6E4F7",  // 연파랑 배경
  lightest:   "EBF4FF",  // 더 연한 파랑
  white:      "FFFFFF",
  black:      "1A1A1A",
  gray:       "F5F5F5",
  midgray:    "AAAAAA",
  darkgray:   "555555",
  danger:     "C0392B",  // 빨강 (긴급)
  warning:    "E67E22",  // 주황 (주의)
  safe:       "27AE60",  // 초록 (안전)
  purple:     "7D3C98",
};

// ─── 도우미 함수 ──────────────────────────────────────────────
const border1 = (color = "CCCCCC") => ({ style: BorderStyle.SINGLE, size: 1, color });
const borders = (color = "CCCCCC") => ({
  top: border1(color), bottom: border1(color),
  left: border1(color), right: border1(color)
});
const noBorder = () => ({
  top: { style: BorderStyle.NONE }, bottom: { style: BorderStyle.NONE },
  left: { style: BorderStyle.NONE }, right: border1("DDDDDD")
});
const noBorderAll = () => ({
  top: { style: BorderStyle.NONE }, bottom: { style: BorderStyle.NONE },
  left: { style: BorderStyle.NONE }, right: { style: BorderStyle.NONE }
});

function cell(children, { bg = C.white, bold = false, align = AlignmentType.LEFT,
  vAlign = VerticalAlign.CENTER, width = null, color = C.black, size = 20,
  bdr = borders(), span = 1, italic = false } = {}) {
  const cellChildren = Array.isArray(children) ? children : [
    new Paragraph({
      alignment: align,
      children: [new TextRun({ text: String(children), bold, color, size, font: "Arial", italics: italic })]
    })
  ];
  const opts = {
    borders: bdr,
    shading: { fill: bg, type: ShadingType.CLEAR },
    margins: { top: 100, bottom: 100, left: 130, right: 130 },
    verticalAlign: vAlign,
    columnSpan: span,
    children: cellChildren,
  };
  if (width) opts.width = { size: width, type: WidthType.DXA };
  return new TableCell(opts);
}

function hCell(text, { bg = C.primary, color = C.white, width = null, align = AlignmentType.CENTER, size = 19, span = 1 } = {}) {
  return cell([new Paragraph({
    alignment: align,
    children: [new TextRun({ text, bold: true, color, size, font: "Arial" })]
  })], { bg, bdr: borders("999999"), width, span });
}

function row(...cells) {
  return new TableRow({ children: cells });
}

function makeTable(rows, { width = 9360, colWidths = [] } = {}) {
  return new Table({
    width: { size: width, type: WidthType.DXA },
    columnWidths: colWidths.length ? colWidths : undefined,
    rows,
  });
}

function h1(text) {
  return new Paragraph({
    pageBreakBefore: true,
    spacing: { before: 0, after: 240 },
    children: [
      new TextRun({ text: "■ ", color: C.accent, size: 34, bold: true, font: "Arial" }),
      new TextRun({ text, bold: true, color: C.primary, size: 34, font: "Arial" }),
    ],
    border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: C.secondary, space: 6 } }
  });
}

function h2(text) {
  return new Paragraph({
    spacing: { before: 240, after: 160 },
    children: [
      new TextRun({ text: "▶ ", color: C.secondary, size: 26, bold: true, font: "Arial" }),
      new TextRun({ text, bold: true, color: C.primary, size: 26, font: "Arial" }),
    ]
  });
}

function h3(text) {
  return new Paragraph({
    spacing: { before: 200, after: 100 },
    children: [new TextRun({ text: `◆ ${text}`, bold: true, color: C.secondary, size: 22, font: "Arial" })]
  });
}

function p(text, { size = 20, color = C.black, bold = false, indent = 0, after = 80 } = {}) {
  return new Paragraph({
    spacing: { before: 40, after },
    indent: indent ? { left: indent } : undefined,
    children: [new TextRun({ text, size, color, bold, font: "Arial" })]
  });
}

function spacer(n = 120) {
  return new Paragraph({ spacing: { before: n, after: 0 }, children: [new TextRun("")] });
}

function pageBreak() {
  return new Paragraph({ children: [new PageBreak()] });
}

// ─── 바 차트 (텍스트 기반) ───────────────────────────────────
function barChart(items, { maxVal = 100, width = 24 } = {}) {
  return items.map(([label, val, color = C.primary]) => {
    const filled = Math.round((val / maxVal) * width);
    const bar = "█".repeat(filled) + "░".repeat(width - filled);
    return new Paragraph({
      spacing: { before: 40, after: 40 },
      children: [
        new TextRun({ text: label.padEnd(18), font: "Arial", size: 18, color: C.darkgray }),
        new TextRun({ text: bar, font: "Arial", size: 14, color }),
        new TextRun({ text: `  ${val}%`, font: "Arial", size: 18, bold: true, color }),
      ]
    });
  });
}

// ─── 표지 ───────────────────────────────────────────────────
function coverPage() {
  return [
    spacer(400),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 0, after: 120 },
      children: [new TextRun({ text: "2026 국민행복 서비스 발굴·창업경진대회", size: 22, color: C.midgray, font: "Arial" })]
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 0, after: 60 },
      border: {
        top: { style: BorderStyle.SINGLE, size: 12, color: C.primary },
        bottom: { style: BorderStyle.SINGLE, size: 4, color: C.secondary },
      },
      children: [
        new TextRun({ text: "VoiceGuide", bold: true, color: C.primary, size: 72, font: "Arial" }),
      ]
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 40, after: 280 },
      children: [new TextRun({ text: "시각장애인을 위한 온디바이스 AI 보행 보조 서비스", bold: true, color: C.secondary, size: 32, font: "Arial" })]
    }),

    // 핵심 지표 박스
    makeTable([
      row(
        cell([
          new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "25만+", bold: true, color: C.primary, size: 48, font: "Arial" })] }),
          new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "국내 시각장애인 등록자", color: C.darkgray, size: 18, font: "Arial" })] }),
        ], { bg: C.lightest, width: 3120 }),
        cell([
          new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "82종", bold: true, color: C.accent, size: 48, font: "Arial" })] }),
          new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "탐지 가능 장애물 클래스", color: C.darkgray, size: 18, font: "Arial" })] }),
        ], { bg: "FFF8F0", width: 3120 }),
        cell([
          new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "100%", bold: true, color: C.safe, size: 48, font: "Arial" })] }),
          new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "온디바이스 추론 (프라이버시 보호)", color: C.darkgray, size: 18, font: "Arial" })] }),
        ], { bg: "F0FFF4", width: 3120 }),
      ),
    ], { width: 9360, colWidths: [3120, 3120, 3120] }),

    spacer(200),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 60, after: 60 },
      children: [new TextRun({ text: "AI HUMAN 4기 3팀  |  2026", color: C.midgray, size: 20, font: "Arial" })]
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [new TextRun({ text: "https://voiceguide-1063164560758.asia-northeast3.run.app", color: C.secondary, size: 18, font: "Arial", italics: true })]
    }),
    pageBreak(),
  ];
}

// ─── 아이디어 요약 ────────────────────────────────────────────
function summarySection() {
  return [
    h1("아이디어 요약"),
    makeTable([
      row(
        hCell("항목", { width: 2000 }),
        hCell("내용", { width: 7360 }),
      ),
      row(
        cell("서비스명", { bg: C.light, bold: true, width: 2000, align: AlignmentType.CENTER }),
        cell("VoiceGuide — 시각장애인 온디바이스 AI 스마트폰 보행 보조 서비스", { width: 7360, bold: true, color: C.primary }),
      ),
      row(
        cell("대상", { bg: C.light, bold: true, width: 2000, align: AlignmentType.CENTER }),
        cell("국내 등록 시각장애인 25만 명 및 저시력·보행 취약 계층", { width: 7360 }),
      ),
      row(
        cell("핵심 기술", { bg: C.light, bold: true, width: 2000, align: AlignmentType.CENTER }),
        cell("YOLO11n-Nano + TFLite 온디바이스 추론 / 3프레임 투표 필터 / IoU 추적 / EMA 평활화", { width: 7360 }),
      ),
      row(
        cell("주요 기능", { bg: C.light, bold: true, width: 2000, align: AlignmentType.CENTER }),
        cell("전방 장애물 실시간 감지 → 방향별 한국어 TTS 즉시 출력 + 위험도별 진동 패턴 4단계", { width: 7360 }),
      ),
      row(
        cell("차별점", { bg: C.light, bold: true, width: 2000, align: AlignmentType.CENTER }),
        cell("흰지팡이로 탐지 불가한 상체 높이 장애물(킥보드, 볼라드, 공사 표지판) 선제 인식 및 완전 핸즈프리 음성 명령", { width: 7360 }),
      ),
      row(
        cell("공공데이터", { bg: C.light, bold: true, width: 2000, align: AlignmentType.CENTER }),
        cell("한국사회보장정보원·보건복지부 데이터 활용 — 횡단보도 접근성 점수화, 사고다발구역 지도, 복지기관 파트너십", { width: 7360 }),
      ),
      row(
        cell("플랫폼", { bg: C.light, bold: true, width: 2000, align: AlignmentType.CENTER }),
        cell("Android 앱 (Kotlin) + FastAPI 서버 (GCP Cloud Run) + 실시간 대시보드", { width: 7360 }),
      ),
    ], { width: 9360, colWidths: [2000, 7360] }),
    spacer(200),
    pageBreak(),
  ];
}

// ─── 제안 배경 ────────────────────────────────────────────────
function backgroundSection() {
  return [
    h1("제안 배경 및 문제 정의"),

    h2("1-1. 시각장애인 보행 안전의 심각성"),
    makeTable([
      row(
        hCell("통계 지표", { width: 3500 }),
        hCell("수치", { width: 1800 }),
        hCell("출처 / 비고", { width: 4060 }),
      ),
      row(
        cell("국내 등록 시각장애인 수", { width: 3500 }),
        cell("252,000명", { width: 1800, bold: true, color: C.primary, align: AlignmentType.CENTER }),
        cell("보건복지부 장애인 현황 2024", { width: 4060, color: C.darkgray }),
      ),
      row(
        cell("시각장애인 보행 사고 경험률", { width: 3500 }),
        cell("68.3%", { width: 1800, bold: true, color: C.danger, align: AlignmentType.CENTER }),
        cell("한국장애인개발원 실태조사", { width: 4060, color: C.darkgray }),
      ),
      row(
        cell("음향신호기 미설치 교차로 비율", { width: 3500 }),
        cell("45.3%", { width: 1800, bold: true, color: C.warning, align: AlignmentType.CENTER }),
        cell("서울시 교통안전시설 실태조사", { width: 4060, color: C.darkgray }),
      ),
      row(
        cell("볼라드 부적정 설치율", { width: 3500 }),
        cell("96%", { width: 1800, bold: true, color: C.danger, align: AlignmentType.CENTER }),
        cell("국토교통부 보행환경 조사", { width: 4060, color: C.darkgray }),
      ),
      row(
        cell("전동 킥보드 보도 불법 주정차 민원", { width: 3500 }),
        cell("연 12만+건", { width: 1800, bold: true, color: C.warning, align: AlignmentType.CENTER }),
        cell("서울시 120 다산콜 집계 (2023)", { width: 4060, color: C.darkgray }),
      ),
      row(
        cell("스마트폰 보유 시각장애인 비율", { width: 3500 }),
        cell("73.2%", { width: 1800, bold: true, color: C.safe, align: AlignmentType.CENTER }),
        cell("장애인 정보통신 이용실태 조사", { width: 4060, color: C.darkgray }),
      ),
    ], { width: 9360, colWidths: [3500, 1800, 4060] }),

    spacer(180),
    h2("1-2. 기존 흰지팡이의 한계"),
    makeTable([
      row(
        hCell("한계 영역", { width: 2800 }),
        hCell("구체적 문제", { width: 4200 }),
        hCell("VoiceGuide 해결 방식", { width: 2360 }),
      ),
      row(
        cell("탐지 높이 제한", { width: 2800, bg: "FFF3F3" }),
        cell("지면과 닿는 지팡이는 상체 높이(80~150cm) 장애물 탐지 불가 — 킥보드 핸들, 볼라드 상단, 공사 안전망 등", { width: 4200 }),
        cell("카메라 기반 전방 시야 82클래스 감지", { width: 2360, bg: C.lightest }),
      ),
      row(
        cell("이동 물체 예측 불가", { width: 2800, bg: "FFF3F3" }),
        cell("사람·자전거·킥보드 등 움직이는 장애물은 접촉 직전까지 감지 어려움", { width: 4200 }),
        cell("IoU 추적 + EMA 평활화로 궤적 예측", { width: 2360, bg: C.lightest }),
      ),
      row(
        cell("방향 정보 제공 불가", { width: 2800, bg: "FFF3F3" }),
        cell("장애물이 좌측·중앙·우측 어디에 있는지 알 수 없음", { width: 4200 }),
        cell("바운딩박스 x좌표 기반 방향 음성 안내", { width: 2360, bg: C.lightest }),
      ),
      row(
        cell("핸즈프리 불가", { width: 2800, bg: "FFF3F3" }),
        cell("양손 중 한 손이 항상 지팡이를 잡아야 해 짐 소지·대화 제약", { width: 4200 }),
        cell("스마트폰 거치만으로 완전 핸즈프리 운용", { width: 2360, bg: C.lightest }),
      ),
    ], { width: 9360, colWidths: [2800, 4200, 2360] }),
    spacer(200),
    pageBreak(),
  ];
}

// ─── 서비스 개요 ──────────────────────────────────────────────
function serviceSection() {
  return [
    h1("서비스 개요"),

    h2("2-1. 시스템 아키텍처"),
    makeTable([
      row(
        hCell("Android 앱 (온디바이스)", { bg: C.primary, width: 3000 }),
        hCell("", { bg: C.white, width: 560 }),
        hCell("FastAPI 서버 (GCP Cloud Run)", { bg: C.secondary, width: 2800 }),
        hCell("", { bg: C.white, width: 440 }),
        hCell("대시보드 & 공공데이터", { bg: C.purple, width: 2560 }),
      ),
      row(
        cell([
          new Paragraph({ children: [new TextRun({ text: "CameraX 프레임 캡처", size: 18, font: "Arial" })] }),
          new Paragraph({ children: [new TextRun({ text: "▼", size: 18, font: "Arial", color: C.accent })] }),
          new Paragraph({ children: [new TextRun({ text: "TFLite YOLO 추론", size: 18, font: "Arial", bold: true })] }),
          new Paragraph({ children: [new TextRun({ text: "▼", size: 18, font: "Arial", color: C.accent })] }),
          new Paragraph({ children: [new TextRun({ text: "3프레임 투표 필터", size: 18, font: "Arial" })] }),
          new Paragraph({ children: [new TextRun({ text: "▼", size: 18, font: "Arial", color: C.accent })] }),
          new Paragraph({ children: [new TextRun({ text: "위험도 계산", size: 18, font: "Arial" })] }),
          new Paragraph({ children: [new TextRun({ text: "▼", size: 18, font: "Arial", color: C.accent })] }),
          new Paragraph({ children: [new TextRun({ text: "진동 + TTS 즉시 출력", size: 18, font: "Arial", bold: true, color: C.safe })] }),
        ], { bg: C.lightest, width: 3000, vAlign: VerticalAlign.TOP }),
        cell([
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 400 }, children: [new TextRun({ text: "JSON\n→\n탐지결과\nGPS", size: 18, font: "Arial", color: C.darkgray })] }),
        ], { bg: C.white, bdr: noBorderAll(), width: 560 }),
        cell([
          new Paragraph({ children: [new TextRun({ text: "POST /detect", size: 18, font: "Arial" })] }),
          new Paragraph({ children: [new TextRun({ text: "POST /gps", size: 18, font: "Arial" })] }),
          new Paragraph({ children: [new TextRun({ text: "▼", size: 18, font: "Arial", color: C.accent })] }),
          new Paragraph({ children: [new TextRun({ text: "DB 저장 (SQLite)", size: 18, font: "Arial" })] }),
          new Paragraph({ children: [new TextRun({ text: "Tracker 업데이트", size: 18, font: "Arial" })] }),
          new Paragraph({ children: [new TextRun({ text: "▼", size: 18, font: "Arial", color: C.accent })] }),
          new Paragraph({ children: [new TextRun({ text: "SSE 스트림 → 대시보드", size: 18, font: "Arial", bold: true, color: C.safe })] }),
        ], { bg: "EAF3FB", width: 2800, vAlign: VerticalAlign.TOP }),
        cell([
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 400 }, children: [new TextRun({ text: "GeoJSON\n공공\n데이터", size: 18, font: "Arial", color: C.darkgray })] }),
        ], { bg: C.white, bdr: noBorderAll(), width: 440 }),
        cell([
          new Paragraph({ children: [new TextRun({ text: "실시간 탐지 현황", size: 18, font: "Arial" })] }),
          new Paragraph({ children: [new TextRun({ text: "GPS 경로 지도", size: 18, font: "Arial" })] }),
          new Paragraph({ children: [new TextRun({ text: "24시간 탐지 내역", size: 18, font: "Arial" })] }),
          new Paragraph({ children: [new TextRun({ text: "사고다발구역 레이어", size: 18, font: "Arial" })] }),
          new Paragraph({ children: [new TextRun({ text: "횡단보도 접근성 점수", size: 18, font: "Arial", bold: true, color: C.safe })] }),
        ], { bg: "F5EEF8", width: 2560, vAlign: VerticalAlign.TOP }),
      ),
    ], { width: 9360, colWidths: [3000, 560, 2800, 440, 2560] }),

    spacer(160),
    h2("2-2. 핵심 원칙: 서버 독립 운용"),
    makeTable([
      row(
        hCell("구분", { width: 1600 }),
        hCell("서버 연결 시", { bg: C.safe, width: 3880 }),
        hCell("서버 없을 때 (오프라인)", { bg: C.warning, width: 3880 }),
      ),
      row(
        cell("장애물 감지", { bg: C.light, bold: true, width: 1600, align: AlignmentType.CENTER }),
        cell("온디바이스 YOLO 추론 (서버 미전송)", { width: 3880, color: C.safe }),
        cell("온디바이스 YOLO 추론 동일 작동", { width: 3880, color: C.safe }),
      ),
      row(
        cell("음성 안내", { bg: C.light, bold: true, width: 1600, align: AlignmentType.CENTER }),
        cell("Android 로컬 TTS — 서버 응답 불필요", { width: 3880, color: C.safe }),
        cell("Android 로컬 TTS — 동일 작동", { width: 3880, color: C.safe }),
      ),
      row(
        cell("진동 안내", { bg: C.light, bold: true, width: 1600, align: AlignmentType.CENTER }),
        cell("즉시 진동 패턴 출력", { width: 3880, color: C.safe }),
        cell("즉시 진동 패턴 출력", { width: 3880, color: C.safe }),
      ),
      row(
        cell("대시보드·이력", { bg: C.light, bold: true, width: 1600, align: AlignmentType.CENTER }),
        cell("실시간 SSE 스트림으로 대시보드 표시", { width: 3880, color: C.safe }),
        cell("서버 재연결 시 이력 동기화", { width: 3880, color: C.warning }),
      ),
      row(
        cell("프라이버시", { bg: C.light, bold: true, width: 1600, align: AlignmentType.CENTER }),
        cell("카메라 프레임 서버 미전송 — 탐지 JSON만 전송", { width: 3880, color: C.safe }),
        cell("카메라 프레임 로컬 처리만", { width: 3880, color: C.safe }),
      ),
    ], { width: 9360, colWidths: [1600, 3880, 3880] }),
    spacer(200),
    pageBreak(),
  ];
}

// ─── AI 모델 ──────────────────────────────────────────────────
function aiModelSection() {
  return [
    h1("AI 모델 및 기술 상세"),

    h2("3-1. YOLO 모델 비교 및 선택"),
    makeTable([
      row(
        hCell("모델", { width: 1800 }),
        hCell("파라미터", { width: 1400 }),
        hCell("mAP50", { width: 1200 }),
        hCell("추론속도", { width: 1500 }),
        hCell("모바일 적합성", { width: 1660 }),
        hCell("VG 채택", { width: 1800 }),
      ),
      row(
        cell("YOLOv5s", { width: 1800 }),
        cell("7.2M", { width: 1400, align: AlignmentType.CENTER }),
        cell("56.8%", { width: 1200, align: AlignmentType.CENTER }),
        cell("보통", { width: 1500, align: AlignmentType.CENTER }),
        cell("△", { width: 1660, align: AlignmentType.CENTER }),
        cell("", { width: 1800 }),
      ),
      row(
        cell("YOLOv8n", { width: 1800 }),
        cell("3.2M", { width: 1400, align: AlignmentType.CENTER }),
        cell("52.9%", { width: 1200, align: AlignmentType.CENTER }),
        cell("빠름", { width: 1500, align: AlignmentType.CENTER }),
        cell("○", { width: 1660, align: AlignmentType.CENTER }),
        cell("", { width: 1800 }),
      ),
      row(
        cell("YOLO11n (320)", { width: 1800, bg: C.lightest, bold: true }),
        cell("2.6M", { width: 1400, align: AlignmentType.CENTER, bg: C.lightest, bold: true }),
        cell("39.5%", { width: 1200, align: AlignmentType.CENTER, bg: C.lightest }),
        cell("매우 빠름", { width: 1500, align: AlignmentType.CENTER, bg: C.lightest, bold: true }),
        cell("◎ 최적", { width: 1660, align: AlignmentType.CENTER, bg: C.lightest, bold: true, color: C.safe }),
        cell("✔ 채택", { width: 1800, bg: C.lightest, bold: true, color: C.safe, align: AlignmentType.CENTER }),
      ),
      row(
        cell("YOLO11s (640)", { width: 1800 }),
        cell("9.4M", { width: 1400, align: AlignmentType.CENTER }),
        cell("47.0%", { width: 1200, align: AlignmentType.CENTER }),
        cell("느림", { width: 1500, align: AlignmentType.CENTER }),
        cell("△ 저사양 부적합", { width: 1660, align: AlignmentType.CENTER }),
        cell("", { width: 1800 }),
      ),
    ], { width: 9360, colWidths: [1800, 1400, 1200, 1500, 1660, 1800] }),

    spacer(160),
    h2("3-2. VoiceGuide82 — 커스텀 클래스 확장"),
    p("COCO 표준 80 클래스에 보행 위험 요소 2개를 추가한 82클래스 모델을 자체 훈련"),
    makeTable([
      row(
        hCell("카테고리", { bg: C.danger, width: 2000 }),
        hCell("포함 클래스 (한국어)", { width: 4560 }),
        hCell("위험도", { width: 1400 }),
        hCell("특이사항", { width: 1400 }),
      ),
      row(
        cell("차량류", { bg: "FFF0EE", bold: true, width: 2000 }),
        cell("자동차, 오토바이, 버스, 트럭, 기차, 자전거", { width: 4560 }),
        cell("긴급", { width: 1400, align: AlignmentType.CENTER, bold: true, color: C.danger }),
        cell("8m 이내 즉시 경보", { width: 1400, color: C.darkgray }),
      ),
      row(
        cell("동물류", { bg: "FFF5E6", bold: true, width: 2000 }),
        cell("개, 말, 고양이, 곰, 코끼리", { width: 4560 }),
        cell("주의", { width: 1400, align: AlignmentType.CENTER, bold: true, color: C.warning }),
        cell("3m 이내 경보", { width: 1400, color: C.darkgray }),
      ),
      row(
        cell("보행 특수", { bg: C.lightest, bold: true, width: 2000 }),
        cell("계단(stairs), 문(door) — VG 자체 추가", { width: 4560, bold: true }),
        cell("긴급", { width: 1400, align: AlignmentType.CENTER, bold: true, color: C.danger }),
        cell("신규 파인튜닝 클래스", { width: 1400, color: C.darkgray }),
      ),
      row(
        cell("주의물체", { bg: "FFFBF0", bold: true, width: 2000 }),
        cell("칼, 가위, 유리잔, 야구 방망이, 배낭, 핸드백, 여행가방", { width: 4560 }),
        cell("주의", { width: 1400, align: AlignmentType.CENTER, bold: true, color: C.warning }),
        cell("2.5m 이내 경보", { width: 1400, color: C.darkgray }),
      ),
      row(
        cell("일상 사물", { bg: C.gray, bold: true, width: 2000 }),
        cell("의자, 소파, 테이블, 가전제품, 식품류 등 37종", { width: 4560 }),
        cell("일반", { width: 1400, align: AlignmentType.CENTER, color: C.darkgray }),
        cell("찾기 모드에서 활용", { width: 1400, color: C.darkgray }),
      ),
    ], { width: 9360, colWidths: [2000, 4560, 1400, 1400] }),

    spacer(160),
    h2("3-3. 추론 파이프라인 — 3단계 노이즈 제거"),
    makeTable([
      row(
        hCell("단계", { bg: C.primary, width: 1000 }),
        hCell("기술", { bg: C.primary, width: 2600 }),
        hCell("역할", { bg: C.primary, width: 5760 }),
      ),
      row(
        cell("1", { width: 1000, align: AlignmentType.CENTER, bold: true, bg: C.lightest }),
        cell("3프레임 투표 필터", { width: 2600, bold: true }),
        cell("3연속 프레임에서 동일 클래스 감지 시만 확정 — 단발 오감지 제거. 긴급 클래스(차량·동물·계단)는 투표 우회로 즉시 경보", { width: 5760 }),
      ),
      row(
        cell("2", { width: 1000, align: AlignmentType.CENTER, bold: true, bg: C.lightest }),
        cell("IoU 기반 객체 추적", { width: 2600, bold: true }),
        cell("이전 프레임 바운딩박스와 IoU 0.3 이상이면 동일 객체로 간주 — 움직이는 장애물 궤적 추적 및 ID 유지", { width: 5760 }),
      ),
      row(
        cell("3", { width: 1000, align: AlignmentType.CENTER, bold: true, bg: C.lightest }),
        cell("EMA 거리 평활화", { width: 2600, bold: true }),
        cell("Exponential Moving Average로 바운딩박스 면적 기반 추정 거리를 평활화 — 거리 점프 방지 및 자연스러운 음성 안내", { width: 5760 }),
      ),
    ], { width: 9360, colWidths: [1000, 2600, 5760] }),
    spacer(200),
    pageBreak(),
  ];
}

// ─── 위험도 체계 ──────────────────────────────────────────────
function riskSection() {
  return [
    h1("위험도 분류 및 알림 체계"),

    h2("4-1. 4단계 위험도 분류"),
    makeTable([
      row(
        hCell("레벨", { width: 1000 }),
        hCell("명칭", { width: 1600 }),
        hCell("진동 패턴", { width: 2000 }),
        hCell("음성 안내 예시", { width: 2800 }),
        hCell("발동 조건", { width: 1960 }),
      ),
      row(
        cell("0", { width: 1000, align: AlignmentType.CENTER, bg: C.gray }),
        cell("NONE", { width: 1600, bold: true, color: C.midgray, bg: C.gray }),
        cell("없음", { width: 2000, align: AlignmentType.CENTER, color: C.midgray }),
        cell("(침묵)", { width: 2800, color: C.midgray, italic: true }),
        cell("장애물 없음", { width: 1960, color: C.midgray }),
      ),
      row(
        cell("1", { width: 1000, align: AlignmentType.CENTER, bg: "FFFBF0" }),
        cell("SHORT", { width: 1600, bold: true, color: C.warning, bg: "FFFBF0" }),
        cell("단진동 100ms", { width: 2000, align: AlignmentType.CENTER }),
        cell("\"앞에 의자 있어요. 2미터.\"", { width: 2800 }),
        cell("일반 장애물 감지", { width: 1960 }),
      ),
      row(
        cell("2", { width: 1000, align: AlignmentType.CENTER, bg: "FFF3E0" }),
        cell("DOUBLE", { width: 1600, bold: true, color: C.accent, bg: "FFF3E0" }),
        cell("두 번 진동 200ms", { width: 2000, align: AlignmentType.CENTER }),
        cell("\"오른쪽에 자전거 접근 중. 주의하세요.\"", { width: 2800 }),
        cell("주의 클래스 2.5m 이내", { width: 1960 }),
      ),
      row(
        cell("3", { width: 1000, align: AlignmentType.CENTER, bg: "FFEAEA" }),
        cell("URGENT", { width: 1600, bold: true, color: C.danger, bg: "FFEAEA" }),
        cell("연속 진동 500ms + 비프음", { width: 2000, align: AlignmentType.CENTER, color: C.danger, bold: true }),
        cell("\"위험! 앞에 오토바이. 즉시 멈추세요.\"", { width: 2800, bold: true, color: C.danger }),
        cell("차량·긴급 8m 이내", { width: 1960, bold: true, color: C.danger }),
      ),
    ], { width: 9360, colWidths: [1000, 1600, 2000, 2800, 1960] }),

    spacer(160),
    h2("4-2. 거리 추정 임계값"),
    makeTable([
      row(
        hCell("클래스 카테고리", { width: 3000 }),
        hCell("긴급 알림 거리", { width: 2000 }),
        hCell("비프음 시작 거리", { width: 2160 }),
        hCell("근거리 판정 기준", { width: 2200 }),
      ),
      row(
        cell("차량류 (자동차·버스·트럭 등)", { width: 3000 }),
        cell("8.0m 이내", { width: 2000, bold: true, color: C.danger, align: AlignmentType.CENTER }),
        cell("7.0m 이내", { width: 2160, align: AlignmentType.CENTER }),
        cell("바운딩박스 면적 캘리브레이션", { width: 2200, color: C.darkgray }),
      ),
      row(
        cell("동물류 (개·말·곰 등)", { width: 3000 }),
        cell("3.0m 이내", { width: 2000, bold: true, color: C.warning, align: AlignmentType.CENTER }),
        cell("7.0m 이내", { width: 2160, align: AlignmentType.CENTER }),
        cell("클래스별 평균 실물 크기 반영", { width: 2200, color: C.darkgray }),
      ),
      row(
        cell("일반 장애물 (의자·볼라드 등)", { width: 3000 }),
        cell("2.5m 이내", { width: 2000, bold: true, color: C.primary, align: AlignmentType.CENTER }),
        cell("해당 없음", { width: 2160, align: AlignmentType.CENTER, color: C.midgray }),
        cell("참조 면적 클래스별 개별 설정", { width: 2200, color: C.darkgray }),
      ),
      row(
        cell("손에 든 물체 (held)", { width: 3000 }),
        cell("1.0m 이내", { width: 2000, bold: true, color: C.safe, align: AlignmentType.CENTER }),
        cell("해당 없음", { width: 2160, align: AlignmentType.CENTER, color: C.midgray }),
        cell("화면 중앙 하단 바운딩박스 기준", { width: 2200, color: C.darkgray }),
      ),
    ], { width: 9360, colWidths: [3000, 2000, 2160, 2200] }),
    spacer(200),
    pageBreak(),
  ];
}

// ─── 핵심 기능 ────────────────────────────────────────────────
function featuresSection() {
  return [
    h1("핵심 기능 및 앱 모드"),

    h2("5-1. 4가지 음성 명령 모드"),
    makeTable([
      row(
        hCell("모드", { bg: C.primary, width: 1600 }),
        hCell("음성 명령 예시", { bg: C.primary, width: 2600 }),
        hCell("동작 설명", { bg: C.primary, width: 3000 }),
        hCell("활용 상황", { bg: C.primary, width: 2160 }),
      ),
      row(
        cell("장애물 모드", { bg: C.lightest, bold: true, width: 1600, align: AlignmentType.CENTER }),
        cell("\"앞에 뭐 있어\"\n\"길 어때\"", { width: 2600, color: C.darkgray }),
        cell("위험도 상위 장애물을 즉시 방향·거리와 함께 안내. 3프레임 필터 통과한 확정 감지만 발화", { width: 3000 }),
        cell("보행 중 상시 감지", { width: 2160 }),
      ),
      row(
        cell("찾기 모드", { bg: "F0FFF4", bold: true, width: 1600, align: AlignmentType.CENTER }),
        cell("\"의자 찾아줘\"\n\"가방 어디 있어\"", { width: 2600, color: C.darkgray }),
        cell("특정 객체를 목표로 설정 후 프레임 내 위치·방향·거리 안내. 발견 즉시 발화", { width: 3000 }),
        cell("실내 물체 위치 확인", { width: 2160 }),
      ),
      row(
        cell("주변 확인", { bg: "FFF8F0", bold: true, width: 1600, align: AlignmentType.CENTER }),
        cell("\"지금 뭐가 있어\"\n\"현재 상황 알려줘\"", { width: 2600, color: C.darkgray }),
        cell("현재 프레임 + 최근 Tracker 상태를 종합해 주변 사물 요약 발화", { width: 3000 }),
        cell("낯선 공간 진입 시", { width: 2160 }),
      ),
      row(
        cell("물건 확인", { bg: "F5EEF8", bold: true, width: 1600, align: AlignmentType.CENTER }),
        cell("\"손에 든 게 뭐야\"\n\"바로 앞 뭐야\"", { width: 2600, color: C.darkgray }),
        cell("화면 중앙/하단에 가장 가까운 물체를 우선 답변. held_sentence 거리 임계값 활용", { width: 3000 }),
        cell("물건 식별 필요 시", { width: 2160 }),
      ),
    ], { width: 9360, colWidths: [1600, 2600, 3000, 2160] }),

    spacer(160),
    h2("5-2. 전체 기능 현황"),
    makeTable([
      row(
        hCell("기능", { width: 3000 }),
        hCell("상태", { width: 1200 }),
        hCell("상세", { width: 5160 }),
      ),
      ...[
        ["장애물 탐지", "완료", "yolo11n_320.tflite 기반 온디바이스 추론, 82클래스"],
        ["위험도 진동 패턴", "완료", "NONE/SHORT/DOUBLE/URGENT 4단계 진동 피드백"],
        ["한국어 TTS", "완료", "SentenceBuilder — 화면 없이 상황별 안내 문장 즉시 발화"],
        ["완전 핸즈프리 음성 명령", "완료", "STT 기반 4가지 모드 전환, 별도 조작 불필요"],
        ["서버 탐지 전송 / DB 저장", "완료", "탐지 JSON + GPS POST, SQLite 영구 저장"],
        ["실시간 대시보드", "완료", "SSE 스트림 기반 탐지 현황·경로·24시간 내역·사고다발구역"],
        ["오프라인 보조 안내", "완료", "서버 없이 Android 내장 TTS + 진동 완전 유지"],
        ["공공데이터 시나리오", "완료", "보라매역 → 서울시남부장애인종합복지관 A/B 경로 비교"],
        ["정책 동기화 (ETag)", "완료", "서버 policy.json 원격 동기화 + ETag 캐싱"],
        ["위험 선행 알림", "완료", "긴급 감지 시 진동·비프음 먼저, 음성은 후속 발화"],
      ].map(([feat, status, detail]) =>
        row(
          cell(feat, { width: 3000 }),
          cell(status, { width: 1200, align: AlignmentType.CENTER, bold: true, color: status === "완료" ? C.safe : C.warning, bg: status === "완료" ? "F0FFF4" : "FFFBF0" }),
          cell(detail, { width: 5160, color: C.darkgray }),
        )
      ),
    ], { width: 9360, colWidths: [3000, 1200, 5160] }),
    spacer(200),
    pageBreak(),
  ];
}

// ─── 공공데이터 ───────────────────────────────────────────────
function publicDataSection() {
  return [
    h1("공공데이터 활용 전략"),

    h2("6-1. 활용 공공데이터 목록"),
    makeTable([
      row(
        hCell("데이터명", { width: 2800 }),
        hCell("출처", { width: 2200 }),
        hCell("VoiceGuide 활용 방식", { width: 4360 }),
      ),
      ...[
        ["횡단보도 위치 데이터", "서울 열린데이터 광장", "동작구 횡단보도 후보 지도 포인트 및 경로 비교 기준점"],
        ["보행등·교통신호 정보", "서울 열린데이터 광장", "횡단 가능 신호 안내 근거, 접근성 점수 가중치"],
        ["음향신호기 정보", "한국사회보장정보원", "시각장애인 보행 안내 필수 시설 여부 점수화"],
        ["보행자작동신호기 정보", "보건복지부", "사용자 직접 신호 요청 가능 여부 점수화"],
        ["고원식 횡단보도 정보", "국토교통부", "차량 감속·보행자 보호 가능성 보조 점수"],
        ["교통안전시설 상세정보", "서울시", "횡단보도별 설명 가능 안전 근거 텍스트"],
        ["보행자 사고다발구역", "경찰청", "대시보드 지도 주의 구역 레이어 표시"],
        ["장애인 복지시설 정보", "한국사회보장정보원", "데모 목적지 및 접근성 시나리오 구성"],
        ["이동지원센터 정보", "보건복지부", "목적지 접근성 설명 및 fallback 안내 후보"],
      ].map(([name, src, usage]) =>
        row(
          cell(name, { width: 2800, bold: true }),
          cell(src, { width: 2200, color: C.darkgray, align: AlignmentType.CENTER }),
          cell(usage, { width: 4360 }),
        )
      ),
    ], { width: 9360, colWidths: [2800, 2200, 4360] }),

    spacer(160),
    h2("6-2. 데이터 처리 파이프라인"),
    makeTable([
      row(
        hCell("단계", { width: 800 }),
        hCell("처리 내용", { width: 3200 }),
        hCell("출력 산출물", { width: 5360 }),
      ),
      row(
        cell("1", { width: 800, align: AlignmentType.CENTER, bg: C.lightest, bold: true }),
        cell("원본 공공데이터 수집 및 분류", { width: 3200 }),
        cell("목적지 / 횡단보도 / 보행지원시설 / 이동지원센터 분리", { width: 5360 }),
      ),
      row(
        cell("2", { width: 800, align: AlignmentType.CENTER, bg: C.lightest, bold: true }),
        cell("좌표 정규화 및 위경도 변환", { width: 3200 }),
        cell("WGS84 좌표계 통일, 30m 반경 시설 매칭", { width: 5360 }),
      ),
      row(
        cell("3", { width: 800, align: AlignmentType.CENTER, bg: C.lightest, bold: true }),
        cell("접근성 점수화 (0~5점)", { width: 3200 }),
        cell("보행등·음향신호기·작동신호기·고원식·상세정보 각 1점씩 가산", { width: 5360 }),
      ),
      row(
        cell("4", { width: 800, align: AlignmentType.CENTER, bg: C.lightest, bold: true }),
        cell("등급 분류", { width: 3200 }),
        cell("preferred(5점) / recommended(3-4점) / basic(1-2점) / insufficient(0점)", { width: 5360 }),
      ),
      row(
        cell("5", { width: 800, align: AlignmentType.CENTER, bg: C.lightest, bold: true }),
        cell("대시보드용 파일 산출", { width: 3200 }),
        cell("CSV / GeoJSON / JSON / HTML — build_voiceguide_final_dataset.py", { width: 5360 }),
      ),
    ], { width: 9360, colWidths: [800, 3200, 5360] }),

    spacer(160),
    h2("6-3. 데모 시나리오: 보라매역 → 서울시남부장애인종합복지관"),
    makeTable([
      row(
        hCell("항목", { width: 2000 }),
        hCell("경로 A (최단 직선)", { bg: C.warning, width: 3680 }),
        hCell("경로 B (접근성 우선)", { bg: C.safe, width: 3680 }),
      ),
      row(
        cell("횡단보도 ID", { bg: C.light, width: 2000, bold: true }),
        cell("06-0000016344", { width: 3680, align: AlignmentType.CENTER }),
        cell("06-0000032157 ✔ 채택", { width: 3680, align: AlignmentType.CENTER, bold: true, color: C.safe }),
      ),
      row(
        cell("접근성 점수", { bg: C.light, width: 2000, bold: true }),
        cell("1점 (basic)", { width: 3680, align: AlignmentType.CENTER, color: C.warning }),
        cell("4점 (recommended)", { width: 3680, align: AlignmentType.CENTER, bold: true, color: C.safe }),
      ),
      row(
        cell("음향신호기", { bg: C.light, width: 2000, bold: true }),
        cell("없음", { width: 3680, align: AlignmentType.CENTER, color: C.danger }),
        cell("있음 ✔", { width: 3680, align: AlignmentType.CENTER, bold: true, color: C.safe }),
      ),
      row(
        cell("보행자작동신호기", { bg: C.light, width: 2000, bold: true }),
        cell("없음", { width: 3680, align: AlignmentType.CENTER, color: C.danger }),
        cell("있음 ✔", { width: 3680, align: AlignmentType.CENTER, bold: true, color: C.safe }),
      ),
      row(
        cell("고원식 횡단보도", { bg: C.light, width: 2000, bold: true }),
        cell("없음", { width: 3680, align: AlignmentType.CENTER, color: C.danger }),
        cell("있음 ✔", { width: 3680, align: AlignmentType.CENTER, bold: true, color: C.safe }),
      ),
      row(
        cell("선택 이유", { bg: C.light, width: 2000, bold: true }),
        cell("최단 거리지만 시각장애인 필수 시설 미비", { width: 3680, color: C.darkgray }),
        cell("거리 약간 길지만 보행 안전시설 3종 갖춤 → 선택", { width: 3680, bold: true }),
      ),
    ], { width: 9360, colWidths: [2000, 3680, 3680] }),
    spacer(200),
    pageBreak(),
  ];
}

// ─── 시장 분석 ────────────────────────────────────────────────
function marketSection() {
  return [
    h1("시장 분석 및 경쟁 환경"),

    h2("7-1. 시장 규모 (TAM / SAM / SOM)"),
    makeTable([
      row(
        hCell("구분", { width: 1200 }),
        hCell("정의", { width: 3000 }),
        hCell("규모 (추정)", { width: 2000 }),
        hCell("근거", { width: 3160 }),
      ),
      row(
        cell("TAM", { width: 1200, bold: true, color: C.primary, align: AlignmentType.CENTER, bg: C.lightest }),
        cell("전 세계 시각장애인 보조기기 시장", { width: 3000 }),
        cell("약 8.4조 원 (2024)", { width: 2000, bold: true, align: AlignmentType.CENTER }),
        cell("WHO 추정 시각장애인 2.9억 명 기반", { width: 3160, color: C.darkgray }),
      ),
      row(
        cell("SAM", { width: 1200, bold: true, color: C.secondary, align: AlignmentType.CENTER, bg: "EAF3FB" }),
        cell("국내 스마트폰 기반 보행보조 앱 시장", { width: 3000 }),
        cell("약 1,200억 원 (2024)", { width: 2000, bold: true, align: AlignmentType.CENTER }),
        cell("시각장애인 25만 × 스마트폰 보유율 73.2%", { width: 3160, color: C.darkgray }),
      ),
      row(
        cell("SOM", { width: 1200, bold: true, color: C.safe, align: AlignmentType.CENTER, bg: "F0FFF4" }),
        cell("VoiceGuide 3년 내 목표 가입자 기반 수익", { width: 3000 }),
        cell("약 36억 원 (3년)", { width: 2000, bold: true, align: AlignmentType.CENTER, color: C.safe }),
        cell("복지기관 B2G 계약 + 개인 구독 3만 명 목표", { width: 3160, color: C.darkgray }),
      ),
    ], { width: 9360, colWidths: [1200, 3000, 2000, 3160] }),

    spacer(160),
    h2("7-2. 시장 점유율 현황 (국내 장애인 보조 앱)"),
    ...barChart([
      ["Microsoft Seeing AI", 22, C.midgray],
      ["Be My Eyes",          18, C.midgray],
      ["Lookout (Google)",    16, C.midgray],
      ["AIRA",                12, C.midgray],
      ["기타 국내앱",         22, C.midgray],
      ["VoiceGuide (목표)",   10, C.primary],
    ], { maxVal: 30, width: 28 }),

    spacer(120),
    h2("7-3. 경쟁 서비스 비교"),
    makeTable([
      row(
        hCell("비교 항목", { width: 2000 }),
        hCell("Microsoft Seeing AI", { width: 1560 }),
        hCell("Google Lookout", { width: 1560 }),
        hCell("Be My Eyes", { width: 1560 }),
        hCell("VoiceGuide", { bg: C.primary, width: 2680 }),
      ),
      ...[
        ["온디바이스 처리", "부분", "부분", "서버 의존", "완전 온디바이스 ✔"],
        ["한국어 최적화", "미흡", "보통", "미흡", "완전 한국어 특화 ✔"],
        ["오프라인 동작", "제한적", "제한적", "불가", "완전 오프라인 ✔"],
        ["보행 위험 감지", "일반", "일반", "없음", "보행 특화 82클래스 ✔"],
        ["공공데이터 연동", "없음", "없음", "없음", "국내 공공데이터 ✔"],
        ["실시간 대시보드", "없음", "없음", "없음", "보호자용 대시보드 ✔"],
        ["진동 피드백", "없음", "없음", "없음", "4단계 위험도 진동 ✔"],
      ].map(([item, ms, gl, bme, vg]) =>
        row(
          cell(item, { bg: C.light, bold: true, width: 2000 }),
          cell(ms, { width: 1560, align: AlignmentType.CENTER, color: ms.includes("✔") ? C.safe : C.midgray }),
          cell(gl, { width: 1560, align: AlignmentType.CENTER, color: gl.includes("✔") ? C.safe : C.midgray }),
          cell(bme, { width: 1560, align: AlignmentType.CENTER, color: bme.includes("✔") ? C.safe : C.midgray }),
          cell(vg, { width: 2680, align: AlignmentType.CENTER, bold: true, color: C.safe, bg: C.lightest }),
        )
      ),
    ], { width: 9360, colWidths: [2000, 1560, 1560, 1560, 2680] }),
    spacer(200),
    pageBreak(),
  ];
}

// ─── 사업화 방안 ──────────────────────────────────────────────
function businessSection() {
  return [
    h1("사업화 방안 및 수익 모델"),

    h2("8-1. 수익 모델"),
    makeTable([
      row(
        hCell("채널", { bg: C.primary, width: 1600 }),
        hCell("대상", { bg: C.primary, width: 2000 }),
        hCell("방식", { bg: C.primary, width: 3160 }),
        hCell("예상 단가", { bg: C.primary, width: 2600 }),
      ),
      row(
        cell("B2G", { bg: "EAF3FB", bold: true, width: 1600, align: AlignmentType.CENTER }),
        cell("지자체·복지관·보건소", { width: 2000 }),
        cell("기관 라이선스 계약 — 관할 시각장애인 등록자 수 기반 정액제", { width: 3160 }),
        cell("연 500만원/기관 (50개소 목표)", { width: 2600, bold: true }),
      ),
      row(
        cell("B2C", { bg: "F0FFF4", bold: true, width: 1600, align: AlignmentType.CENTER }),
        cell("개인 사용자 (시각장애인·가족)", { width: 2000 }),
        cell("프리미엄 구독 — 기본 무료 + 이력·경로·공공데이터 리포트 유료", { width: 3160 }),
        cell("월 3,900원 (3만 명 목표)", { width: 2600, bold: true }),
      ),
      row(
        cell("B2B", { bg: "FFF8F0", bold: true, width: 1600, align: AlignmentType.CENTER }),
        cell("보험사·재활병원·앱 파트너", { width: 2000 }),
        cell("보행 데이터 익명화 분석 리포트 / SDK 라이선스 공급", { width: 3160 }),
        cell("건당 협의 / 연 2,000만원~", { width: 2600, bold: true }),
      ),
      row(
        cell("공모·보조금", { bg: C.gray, bold: true, width: 1600, align: AlignmentType.CENTER }),
        cell("정부·NIA·복지재단", { width: 2000 }),
        cell("국민행복서비스 대회 입상 → 후속 사업화 지원금 연계", { width: 3160 }),
        cell("최대 1억원 (3년)", { width: 2600, bold: true }),
      ),
    ], { width: 9360, colWidths: [1600, 2000, 3160, 2600] }),

    spacer(160),
    h2("8-2. 3년 수익 목표"),
    makeTable([
      row(
        hCell("연도", { width: 1200 }),
        hCell("핵심 목표", { width: 3560 }),
        hCell("수익 목표", { width: 2000 }),
        hCell("추진 전략", { width: 2600 }),
      ),
      row(
        cell("1년차", { bg: "FFF3F3", bold: true, width: 1200, align: AlignmentType.CENTER }),
        cell("MVP 완성·공모전 수상·파일럿 기관 3곳 확보", { width: 3560 }),
        cell("1,500만원", { width: 2000, bold: true, align: AlignmentType.CENTER }),
        cell("B2G 파일럿 + 공모 보조금", { width: 2600 }),
      ),
      row(
        cell("2년차", { bg: "FFF8F0", bold: true, width: 1200, align: AlignmentType.CENTER }),
        cell("기관 20곳 + 개인 5천명 + Google Play 정식 출시", { width: 3560 }),
        cell("1억 2,000만원", { width: 2000, bold: true, align: AlignmentType.CENTER }),
        cell("복지관 네트워크 확장 + 앱스토어 마케팅", { width: 2600 }),
      ),
      row(
        cell("3년차", { bg: C.lightest, bold: true, width: 1200, align: AlignmentType.CENTER }),
        cell("기관 50곳 + 개인 3만명 + B2B SDK 2건", { width: 3560 }),
        cell("3억 6,000만원", { width: 2000, bold: true, align: AlignmentType.CENTER, color: C.safe }),
        cell("정부 조달 등록 + 보험사 파트너십", { width: 2600 }),
      ),
    ], { width: 9360, colWidths: [1200, 3560, 2000, 2600] }),
    spacer(200),
    pageBreak(),
  ];
}

// ─── 개발 로드맵 ──────────────────────────────────────────────
function roadmapSection() {
  return [
    h1("개발 로드맵"),

    h2("9-1. 마일스톤 로드맵 (2026~2028)"),
    makeTable([
      row(
        hCell("분기", { width: 900 }),
        hCell("Phase", { width: 1500 }),
        hCell("핵심 목표", { width: 3360 }),
        hCell("기술 과제", { width: 3600 }),
      ),
      ...[
        ["2026 Q1", "Phase 0", "MVP 완성 및 공모전 제출", "YOLO82 파인튜닝 안정화, TFLite 경량화"],
        ["2026 Q2", "Phase 1", "파일럿 3개 복지기관 실증 테스트", "실사용자 피드백 반영, UX 개선"],
        ["2026 Q3", "Phase 1", "Google Play 베타 출시 (100명)", "배터리 최적화, 오디오 포커스 안정화"],
        ["2026 Q4", "Phase 2", "기관 계약 10곳, 개인 1천 명", "다중 세션 서버 확장, 모니터링 대시보드"],
        ["2027 Q1", "Phase 2", "보행 데이터 분석 리포트 v1 출시", "익명화 집계 파이프라인, 공공데이터 확장"],
        ["2027 Q2", "Phase 3", "SDK 외부 공개 (보험사·재활병원)", "SDK 패키징, API 문서화"],
        ["2027 Q4", "Phase 3", "기관 50곳, 개인 3만 명 목표", "Kubernetes 멀티리전 배포"],
        ["2028+",   "Phase 4", "해외 시장 진출 (일본·동남아)", "다국어 TTS, 현지 공공데이터 연동"],
      ].map(([q, ph, goal, tech]) =>
        row(
          cell(q, { width: 900, align: AlignmentType.CENTER, bg: C.lightest, bold: true }),
          cell(ph, { width: 1500, align: AlignmentType.CENTER, bold: true, color: C.primary }),
          cell(goal, { width: 3360 }),
          cell(tech, { width: 3600, color: C.darkgray }),
        )
      ),
    ], { width: 9360, colWidths: [900, 1500, 3360, 3600] }),

    spacer(160),
    h2("9-2. 기술 고도화 계획"),
    makeTable([
      row(
        hCell("과제", { width: 2800 }),
        hCell("현재", { width: 2280 }),
        hCell("목표", { width: 2280 }),
        hCell("예상 일정", { width: 2000 }),
      ),
      ...[
        ["모델 정확도", "YOLO11n mAP39.5%", "YOLO11s 파인튜닝 mAP50%+", "2026 Q3"],
        ["계단 감지", "오인식률 개선 중", "하드네거티브 마이닝 완료", "2026 Q2"],
        ["거리 추정", "바운딩박스 면적 캘리브", "스테레오/LiDAR 옵션 추가", "2027 Q1"],
        ["서버 인프라", "GCP Cloud Run 단일", "Kubernetes 오토스케일", "2027 Q2"],
        ["개인화 학습", "글로벌 정책 json", "사용자별 민감도 조정", "2027 Q3"],
        ["접근성 지도", "동작구 파일럿", "전국 17개 시도 확장", "2028"],
      ].map(([task, cur, goal, when]) =>
        row(
          cell(task, { width: 2800, bold: true }),
          cell(cur, { width: 2280, color: C.darkgray }),
          cell(goal, { width: 2280, bold: true, color: C.primary }),
          cell(when, { width: 2000, align: AlignmentType.CENTER }),
        )
      ),
    ], { width: 9360, colWidths: [2800, 2280, 2280, 2000] }),
    spacer(200),
    pageBreak(),
  ];
}

// ─── 기대효과 & 팀 ────────────────────────────────────────────
function impactAndTeamSection() {
  return [
    h1("기대효과 및 팀 소개"),

    h2("10-1. 사회적 기대효과"),
    makeTable([
      row(
        hCell("영역", { bg: C.primary, width: 1600 }),
        hCell("지표", { bg: C.primary, width: 2800 }),
        hCell("기대 효과", { bg: C.primary, width: 4960 }),
      ),
      row(
        cell("보행 안전", { bg: C.lightest, bold: true, width: 1600, align: AlignmentType.CENTER }),
        cell("보행 사고 감소율 (목표)", { width: 2800 }),
        cell("시각장애인 보행 사고 경험률 68.3% → 30% 이하 달성 목표", { width: 4960, bold: true }),
      ),
      row(
        cell("독립 보행", { bg: "F0FFF4", bold: true, width: 1600, align: AlignmentType.CENTER }),
        cell("보조 인력 의존 감소", { width: 2800 }),
        cell("동행 보조 없이 단독 보행 가능 경우 확대 — 자립 생활 지원", { width: 4960 }),
      ),
      row(
        cell("인프라 보완", { bg: "FFF8F0", bold: true, width: 1600, align: AlignmentType.CENTER }),
        cell("음향신호기 미설치 구간 커버", { width: 2800 }),
        cell("45.3% 미설치 교차로에서도 AI 음성 안내로 보행 지원", { width: 4960 }),
      ),
      row(
        cell("데이터 활용", { bg: "F5EEF8", bold: true, width: 1600, align: AlignmentType.CENTER }),
        cell("보행 위험 지도 생성", { width: 2800 }),
        cell("익명 집계 보행 데이터 → 지자체 보도 인프라 개선 근거 제공", { width: 4960 }),
      ),
      row(
        cell("비용 절감", { bg: C.gray, bold: true, width: 1600, align: AlignmentType.CENTER }),
        cell("보조기기 대비 비용", { width: 2800 }),
        cell("전용 보조기기(200만원+) 대비 스마트폰 앱(무료~월 3,900원)으로 접근 장벽 대폭 감소", { width: 4960 }),
      ),
    ], { width: 9360, colWidths: [1600, 2800, 4960] }),

    spacer(160),
    h2("10-2. 팀 소개"),
    makeTable([
      row(
        hCell("역할", { width: 1800 }),
        hCell("담당 영역", { width: 4000 }),
        hCell("주요 기여", { width: 3560 }),
      ),
      row(
        cell("AI 리드", { bg: C.lightest, bold: true, width: 1800, align: AlignmentType.CENTER }),
        cell("YOLO 모델 파인튜닝, TFLite 변환, 추론 파이프라인 설계", { width: 4000 }),
        cell("VoiceGuide82 82클래스 모델 훈련, 3프레임 필터 설계", { width: 3560 }),
      ),
      row(
        cell("Android 리드", { bg: "F0FFF4", bold: true, width: 1800, align: AlignmentType.CENTER }),
        cell("Kotlin 앱 개발, CameraX 연동, TTS/진동 파이프라인", { width: 4000 }),
        cell("MvpPipeline, SentenceBuilder, VoicePolicy 구현", { width: 3560 }),
      ),
      row(
        cell("백엔드 리드", { bg: "FFF8F0", bold: true, width: 1800, align: AlignmentType.CENTER }),
        cell("FastAPI 서버, DB 설계, GCP Cloud Run 배포", { width: 4000 }),
        cell("SSE 스트림, Tracker, 공공데이터 파이프라인", { width: 3560 }),
      ),
      row(
        cell("데이터 리드", { bg: "F5EEF8", bold: true, width: 1800, align: AlignmentType.CENTER }),
        cell("공공데이터 수집·정제·시나리오 설계, 대시보드 시각화", { width: 4000 }),
        cell("횡단보도 접근성 점수화, GeoJSON 산출, 데모 시나리오", { width: 3560 }),
      ),
    ], { width: 9360, colWidths: [1800, 4000, 3560] }),

    spacer(160),
    h2("10-3. 추진 일정 및 현재 개발 완료 현황"),
    makeTable([
      row(
        hCell("구분", { width: 1200 }),
        hCell("항목", { width: 4160 }),
        hCell("완료 여부", { width: 1600 }),
        hCell("비고", { width: 2400 }),
      ),
      ...[
        ["핵심 기술", "YOLO11n 온디바이스 추론", "완료 ✔", "yolo11n_320.tflite"],
        ["핵심 기술", "3프레임 투표 + IoU 추적 + EMA", "완료 ✔", "MvpPipeline.kt"],
        ["핵심 기술", "4단계 위험도 진동 패턴", "완료 ✔", "VoiceGuideConstants.kt"],
        ["핵심 기술", "한국어 TTS 음성 안내", "완료 ✔", "SentenceBuilder.kt"],
        ["앱 기능", "완전 핸즈프리 4가지 모드", "완료 ✔", "VoicePolicy.kt"],
        ["앱 기능", "오프라인 독립 운용", "완료 ✔", "서버 없이 TTS+진동"],
        ["서버", "FastAPI + SQLite + SSE 대시보드", "완료 ✔", "GCP Cloud Run 배포"],
        ["공공데이터", "횡단보도 접근성 점수화", "완료 ✔", "voiceguide_final/"],
        ["공공데이터", "A/B 경로 시나리오", "완료 ✔", "보라매역 데모"],
        ["공공데이터", "사고다발구역 지도 레이어", "완료 ✔", "대시보드 표시"],
      ].map(([cat, item, status, note]) =>
        row(
          cell(cat, { width: 1200, bg: C.light, bold: true, align: AlignmentType.CENTER }),
          cell(item, { width: 4160 }),
          cell(status, { width: 1600, align: AlignmentType.CENTER, bold: true, color: C.safe, bg: "F0FFF4" }),
          cell(note, { width: 2400, color: C.darkgray }),
        )
      ),
    ], { width: 9360, colWidths: [1200, 4160, 1600, 2400] }),
    spacer(200),
    pageBreak(),
  ];
}

// ─── API 참고 ─────────────────────────────────────────────────
function apiSection() {
  return [
    h1("주요 API 및 기술 스택"),

    h2("11-1. API 엔드포인트"),
    makeTable([
      row(
        hCell("메서드", { width: 1000 }),
        hCell("경로", { width: 3200 }),
        hCell("설명", { width: 5160 }),
      ),
      ...[
        ["POST", "/detect", "탐지 결과 JSON 수신, DB 저장, Tracker 업데이트"],
        ["POST", "/gps", "Android 위치 업데이트 수신"],
        ["POST", "/question", "최근 Tracker/DB 상태 기반 주변 확인 응답"],
        ["GET",  "/api/policy", "Android 정책 동기화, ETag 캐싱 지원"],
        ["GET",  "/events/{session_id}", "SSE 실시간 스트림 (대시보드 연결)"],
        ["GET",  "/status/{session_id}", "세션 현재 상태 조회"],
        ["GET",  "/history/{session_id}", "세션별 탐지 이력"],
        ["GET",  "/heatmap/{session_id}", "위험 히트맵 데이터"],
        ["GET",  "/routes/{session_id}", "저장된 GPS 경로"],
        ["GET",  "/pedestrian-hotspots/nearby", "GPS 기반 보행자 사고다발구역"],
        ["GET",  "/voiceguide-final/summary", "최종 공공데이터 시나리오 요약"],
        ["GET",  "/voiceguide-final/crosswalks.geojson", "횡단보도 접근성 GeoJSON"],
        ["GET",  "/dashboard", "실시간 대시보드 HTML"],
      ].map(([method, path, desc]) =>
        row(
          cell(method, { width: 1000, align: AlignmentType.CENTER, bold: true,
            color: method === "POST" ? C.accent : C.secondary,
            bg: method === "POST" ? "FFF8F0" : C.lightest }),
          cell(path, { width: 3200, color: C.darkgray }),
          cell(desc, { width: 5160 }),
        )
      ),
    ], { width: 9360, colWidths: [1000, 3200, 5160] }),

    spacer(160),
    h2("11-2. 기술 스택"),
    makeTable([
      row(
        hCell("계층", { width: 1600 }),
        hCell("기술", { width: 3160 }),
        hCell("버전/상세", { width: 4600 }),
      ),
      ...[
        ["AI 모델", "YOLO11n + TFLite", "yolo11n_320.tflite / yolo26n_float32.tflite"],
        ["Android", "Kotlin + CameraX", "Android Studio, USB 디버깅, Gradle"],
        ["추론", "TensorFlow Lite", "온디바이스 추론, 카메라 프레임 서버 미전송"],
        ["백엔드", "FastAPI (Python)", "Python 3.10+, SQLite, uvicorn"],
        ["실시간", "SSE (Server-Sent Events)", "대시보드 실시간 탐지 스트림"],
        ["인프라", "GCP Cloud Run", "asia-northeast3 (서울 리전), 서버리스 자동 스케일"],
        ["데이터", "SQLite / GeoJSON / CSV", "SQLAlchemy, 공공데이터 처리 pandas"],
        ["테스트", "pytest", "단위/통합 테스트, 공공데이터 검증"],
      ].map(([layer, tech, detail]) =>
        row(
          cell(layer, { width: 1600, bg: C.light, bold: true, align: AlignmentType.CENTER }),
          cell(tech, { width: 3160, bold: true, color: C.primary }),
          cell(detail, { width: 4600, color: C.darkgray }),
        )
      ),
    ], { width: 9360, colWidths: [1600, 3160, 4600] }),
    spacer(200),
    pageBreak(),
  ];
}

// ─── 마무리 ────────────────────────────────────────────────────
function closingSection() {
  return [
    h1("결론 및 향후 계획"),

    h2("12-1. VoiceGuide가 만드는 변화"),
    makeTable([
      row(
        hCell("Before VoiceGuide", { bg: C.danger, width: 4680 }),
        hCell("After VoiceGuide", { bg: C.safe, width: 4680 }),
      ),
      row(
        cell("흰지팡이로 감지 불가한 상체 높이 장애물 — 매 외출이 위험", { width: 4680 }),
        cell("82종 장애물 실시간 감지 — 방향별 한국어 음성 즉시 안내", { width: 4680, bold: true }),
      ),
      row(
        cell("음향신호기 없는 교차로 45.3% — 안전한 횡단 불가", { width: 4680 }),
        cell("공공데이터 기반 접근성 우수 경로 추천", { width: 4680, bold: true }),
      ),
      row(
        cell("보조 인력 동행 필수 — 독립 보행 어려움", { width: 4680 }),
        cell("완전 핸즈프리 + 오프라인 동작 — 진정한 자립 보행", { width: 4680, bold: true }),
      ),
      row(
        cell("보행 위험 데이터 미집계 — 인프라 개선 근거 부재", { width: 4680 }),
        cell("익명 집계 보행 데이터 → 지자체 정책 근거 제공", { width: 4680, bold: true }),
      ),
      row(
        cell("전용 보조기기 200만원+ — 경제적 접근 장벽", { width: 4680 }),
        cell("스마트폰 앱 무료 기본 제공 — 누구나 접근 가능", { width: 4680, bold: true }),
      ),
    ], { width: 9360, colWidths: [4680, 4680] }),

    spacer(200),
    h2("12-2. 핵심 요약"),
    makeTable([
      row(
        cell([
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 200, after: 100 }, children: [
            new TextRun({ text: "VoiceGuide", bold: true, size: 48, color: C.primary, font: "Arial" }),
          ]}),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 60, after: 60 }, children: [
            new TextRun({ text: "스마트폰 하나로, 시각장애인의 안전한 독립 보행을 실현합니다.", size: 24, color: C.darkgray, font: "Arial" }),
          ]}),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 80, after: 80 }, children: [
            new TextRun({ text: "온디바이스 AI · 한국어 특화 · 공공데이터 연동 · 완전 핸즈프리", bold: true, size: 22, color: C.secondary, font: "Arial" }),
          ]}),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 60, after: 200 }, children: [
            new TextRun({ text: "https://voiceguide-1063164560758.asia-northeast3.run.app", size: 18, color: C.midgray, font: "Arial", italics: true }),
          ]}),
        ], { bg: C.lightest, span: 1 }),
      ),
    ], { width: 9360, colWidths: [9360] }),

    spacer(120),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 80, after: 40 },
      children: [new TextRun({ text: "AI HUMAN 4기 3팀  |  2026", color: C.midgray, size: 20, font: "Arial" })]
    }),
  ];
}

// ─── 문서 조립 ────────────────────────────────────────────────
async function buildDoc() {
  const allChildren = [
    ...coverPage(),
    ...summarySection(),
    ...backgroundSection(),
    ...serviceSection(),
    ...aiModelSection(),
    ...riskSection(),
    ...featuresSection(),
    ...publicDataSection(),
    ...marketSection(),
    ...businessSection(),
    ...roadmapSection(),
    ...impactAndTeamSection(),
    ...apiSection(),
    ...closingSection(),
  ];

  const doc = new Document({
    numbering: { config: [] },
    styles: {
      default: {
        document: { run: { font: "Arial", size: 20, color: C.black } }
      }
    },
    sections: [{
      properties: {
        page: {
          size: { width: 11906, height: 16838 },
          margin: { top: 1134, right: 1134, bottom: 1134, left: 1134 }
        }
      },
      headers: {
        default: new Header({
          children: [new Paragraph({
            alignment: AlignmentType.RIGHT,
            border: { bottom: { style: BorderStyle.SINGLE, size: 2, color: C.secondary, space: 4 } },
            children: [
              new TextRun({ text: "VoiceGuide  |  시각장애인 온디바이스 AI 보행 보조 서비스", size: 16, color: C.midgray, font: "Arial" }),
            ]
          })]
        })
      },
      footers: {
        default: new Footer({
          children: [new Paragraph({
            alignment: AlignmentType.CENTER,
            children: [
              new TextRun({ text: "AI HUMAN 4기 3팀  |  2026  |  ", size: 16, color: C.midgray, font: "Arial" }),
              new TextRun({ children: [PageNumber.CURRENT], size: 16, color: C.midgray, font: "Arial" }),
              new TextRun({ text: " / ", size: 16, color: C.midgray, font: "Arial" }),
              new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 16, color: C.midgray, font: "Arial" }),
            ]
          })]
        })
      },
      children: allChildren,
    }]
  });

  const buffer = await Packer.toBuffer(doc);
  const outPath = "C:\\Users\\ghksw\\Downloads\\VoiceGuide_사업계획서_최종.docx";
  fs.writeFileSync(outPath, buffer);
  console.log("생성 완료:", outPath);
}

buildDoc().catch(e => { console.error(e); process.exit(1); });
