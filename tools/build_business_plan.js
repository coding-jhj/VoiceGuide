// VoiceGuide 사업계획서 업그레이드 — 원본 구조 동일, 내용 강화
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, BorderStyle, WidthType, ShadingType,
  VerticalAlign, PageNumber, PageBreak, LevelFormat, ExternalHyperlink,
  ImageRun,
} = require('docx');
const fs = require('fs');

// ─── SVG 차트 생성기 ──────────────────────────────────────────

// 1px PNG fallback (SVG 삽입 필수)
const PNG_FALLBACK = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
  "base64"
);

function svgImage(svgStr, widthPx, heightPx) {
  return new ImageRun({
    type: "svg",
    data: Buffer.from(svgStr),
    transformation: { width: widthPx, height: heightPx },
    fallback: { type: "png", data: PNG_FALLBACK },
  });
}

// ── 수평 그룹형 막대 차트 ─────────────────────────────────────
// bars: [{label, segments:[{val,color,label}]}]
function svgGroupedBarChart({ title, bars, width = 680, height = 280, xMax = 100 }) {
  const marginL = 210, marginR = 80, marginT = 50, marginB = 40;
  const chartW = width - marginL - marginR;
  const chartH = height - marginT - marginB;
  const rowH = Math.floor(chartH / bars.length);
  const barH = Math.min(26, rowH - 10);

  const xScale = v => (v / xMax) * chartW;

  let rects = "";
  let labels = "";

  bars.forEach((bar, i) => {
    const y = marginT + i * rowH + (rowH - barH) / 2;
    // row label
    labels += `<text x="${marginL - 8}" y="${y + barH / 2 + 5}" font-size="12" fill="#444" font-family="Arial" text-anchor="end">${bar.label}</text>`;
    // segments stacked horizontally
    let xCur = 0;
    bar.segments.forEach(seg => {
      const w = xScale(seg.val);
      if (w > 0) {
        rects += `<rect x="${marginL + xCur}" y="${y}" width="${w}" height="${barH}" fill="${seg.color}" rx="2"/>`;
        if (w > 28) {
          rects += `<text x="${marginL + xCur + w / 2}" y="${y + barH / 2 + 4}" font-size="11" fill="white" font-family="Arial" font-weight="bold" text-anchor="middle">${seg.val}%</text>`;
        }
      }
      xCur += w;
    });
    // total label at end (clamp to avoid overflow)
    const total = bar.segments.reduce((s, sg) => s + sg.val, 0);
    const labelX = Math.min(marginL + xScale(total) + 4, width - marginR - 2);
    labels += `<text x="${labelX}" y="${y + barH / 2 + 4}" font-size="11" fill="#333" font-family="Arial">${total}%</text>`;
  });

  // x-axis grid lines
  let grid = "";
  [0, 25, 50, 75, 100].forEach(v => {
    const x = marginL + xScale(v);
    grid += `<line x1="${x}" y1="${marginT - 8}" x2="${x}" y2="${marginT + chartH}" stroke="#DDD" stroke-width="1"/>`;
    grid += `<text x="${x}" y="${marginT - 12}" font-size="10" fill="#999" font-family="Arial" text-anchor="middle">${v}%</text>`;
  });

  // Legend
  const allSegs = [...new Set(bars.flatMap(b => b.segments.map(s => JSON.stringify({label:s.segLabel,color:s.color}))))].map(s=>JSON.parse(s));
  let legend = "";
  const legendItemW = Math.floor((width - marginL) / Math.max(allSegs.length, 1));
  allSegs.forEach((seg, i) => {
    const lx = marginL + i * legendItemW;
    const ly = height - 12;
    legend += `<rect x="${lx}" y="${ly - 10}" width="12" height="12" fill="${seg.color}" rx="2"/>`;
    legend += `<text x="${lx + 16}" y="${ly}" font-size="11" fill="#555" font-family="Arial">${seg.label}</text>`;
  });

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}">
  <rect width="${width}" height="${height}" fill="white" rx="8"/>
  <text x="${width/2}" y="28" font-size="14" font-weight="bold" fill="#1A3E6B" font-family="Arial" text-anchor="middle">${title}</text>
  ${grid}${rects}${labels}${legend}
</svg>`;
}

// ── 도넛 차트 ─────────────────────────────────────────────────
function svgDonutChart({ title, slices, size = 320 }) {
  // slices: [{label, value, color}]
  const cx = size / 2, cy = size / 2 + 20;
  const R = size * 0.32, r = size * 0.18;
  const total = slices.reduce((s, sl) => s + sl.value, 0);
  let paths = "";
  let legendItems = "";
  let angle = -Math.PI / 2;

  slices.forEach((sl, i) => {
    const sweep = (sl.value / total) * 2 * Math.PI;
    const x1 = cx + R * Math.cos(angle);
    const y1 = cy + R * Math.sin(angle);
    const x2 = cx + R * Math.cos(angle + sweep);
    const y2 = cy + R * Math.sin(angle + sweep);
    const ix1 = cx + r * Math.cos(angle);
    const iy1 = cy + r * Math.sin(angle);
    const ix2 = cx + r * Math.cos(angle + sweep);
    const iy2 = cy + r * Math.sin(angle + sweep);
    const lg = sweep > Math.PI ? 1 : 0;

    paths += `<path d="M${x1.toFixed(1)},${y1.toFixed(1)} A${R},${R} 0 ${lg},1 ${x2.toFixed(1)},${y2.toFixed(1)} L${ix2.toFixed(1)},${iy2.toFixed(1)} A${r},${r} 0 ${lg},0 ${ix1.toFixed(1)},${iy1.toFixed(1)} Z" fill="${sl.color}"/>`;

    // slice label
    const midAngle = angle + sweep / 2;
    const lx = cx + (R + r) / 2 * Math.cos(midAngle);
    const ly = cy + (R + r) / 2 * Math.sin(midAngle);
    const pct = Math.round(sl.value / total * 100);
    if (pct > 8) {
      paths += `<text x="${lx.toFixed(1)}" y="${(ly+4).toFixed(1)}" font-size="12" fill="white" font-family="Arial" font-weight="bold" text-anchor="middle">${pct}%</text>`;
    }
    angle += sweep;

    // legend
    const lrow = Math.floor(i / 2);
    const lcol = i % 2;
    const lbx = 20 + lcol * (size / 2 - 10);
    const lby = size + 10 + lrow * 20;
    legendItems += `<rect x="${lbx}" y="${lby - 10}" width="12" height="12" fill="${sl.color}" rx="2"/>`;
    legendItems += `<text x="${lbx + 16}" y="${lby}" font-size="11" fill="#444" font-family="Arial">${sl.label} (${sl.value})</text>`;
  });

  const legendH = Math.ceil(slices.length / 2) * 20 + 20;

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size + legendH + 20}">
  <rect width="${size}" height="${size + legendH + 20}" fill="white" rx="8"/>
  <text x="${size/2}" y="18" font-size="13" font-weight="bold" fill="#1A3E6B" font-family="Arial" text-anchor="middle">${title}</text>
  ${paths}
  <circle cx="${cx}" cy="${cy}" r="${r - 2}" fill="white"/>
  <text x="${cx}" y="${cy - 6}" font-size="11" fill="#666" font-family="Arial" text-anchor="middle">합계</text>
  <text x="${cx}" y="${cy + 12}" font-size="14" font-weight="bold" fill="#1A3E6B" font-family="Arial" text-anchor="middle">${total}</text>
  ${legendItems}
</svg>`;
}

// ── 수직 막대 차트 ────────────────────────────────────────────
function svgVerticalBar({ title, bars, width = 500, height = 300, yMax = 100, yLabel = "%" }) {
  // bars: [{label, value, color}]
  const marginL = 50, marginR = 20, marginT = 60, marginB = 60;
  const chartW = width - marginL - marginR;
  const chartH = height - marginT - marginB;
  const bw = Math.floor((chartW / bars.length) * 0.6);
  const gap = Math.floor(chartW / bars.length);
  const yScale = v => chartH - (v / yMax) * chartH;

  let rects = "";
  let xlabels = "";
  bars.forEach((b, i) => {
    const x = marginL + i * gap + (gap - bw) / 2;
    const y = marginT + yScale(b.value);
    const h = chartH - yScale(b.value);
    rects += `<rect x="${x}" y="${y}" width="${bw}" height="${h}" fill="${b.color}" rx="3"/>`;
    rects += `<text x="${x + bw/2}" y="${y - 5}" font-size="12" fill="${b.color}" font-family="Arial" font-weight="bold" text-anchor="middle">${b.value}${yLabel}</text>`;
    // x label (multi-line)
    const lines = b.label.split("\n");
    lines.forEach((ln, li) => {
      xlabels += `<text x="${x + bw/2}" y="${marginT + chartH + 16 + li * 14}" font-size="11" fill="#555" font-family="Arial" text-anchor="middle">${ln}</text>`;
    });
  });

  // y-axis grid
  let grid = "";
  [0, 25, 50, 75, 100].filter(v => v <= yMax).forEach(v => {
    const y = marginT + yScale(v);
    grid += `<line x1="${marginL}" y1="${y}" x2="${marginL + chartW}" y2="${y}" stroke="#EEE" stroke-width="1"/>`;
    grid += `<text x="${marginL - 4}" y="${y + 4}" font-size="10" fill="#999" font-family="Arial" text-anchor="end">${v}</text>`;
  });

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}">
  <rect width="${width}" height="${height}" fill="white" rx="8"/>
  <text x="${width/2}" y="28" font-size="13" font-weight="bold" fill="#1A3E6B" font-family="Arial" text-anchor="middle">${title}</text>
  <line x1="${marginL}" y1="${marginT}" x2="${marginL}" y2="${marginT + chartH}" stroke="#CCC" stroke-width="1.5"/>
  <line x1="${marginL}" y1="${marginT + chartH}" x2="${marginL + chartW}" y2="${marginT + chartH}" stroke="#CCC" stroke-width="1.5"/>
  ${grid}${rects}${xlabels}
</svg>`;
}

// ── SVG 아키텍처 플로우 다이어그램 ───────────────────────────
function svgArchDiagram() {
  const w = 700, h = 220;
  const boxes = [
    { x: 10,  y: 60, w: 110, h: 60, bg: "#1A3E6B", label: "카메라", sub: "CameraX" },
    { x: 165, y: 60, w: 110, h: 60, bg: "#2E75B6", label: "AI 추론", sub: "TFLite YOLO11n\n30ms 이내" },
    { x: 320, y: 60, w: 110, h: 60, bg: "#E67E22", label: "위험도 계산", sub: "IoU+EMA\n필터링" },
    { x: 475, y: 20, w: 110, h: 55, bg: "#27AE60", label: "음성 안내", sub: "TTS 한국어" },
    { x: 475, y: 90, w: 110, h: 55, bg: "#7D3C98", label: "진동 패턴", sub: "4단계 햅틱" },
    { x: 600, y: 150, w: 90, h: 50, bg: "#2C3E50", label: "서버/DB", sub: "FastAPI\nSSE 대시보드" },
  ];
  const arrows = [
    [120, 90, 165, 90],
    [275, 90, 320, 90],
    [430, 75, 475, 47],
    [430, 90, 475, 117],
    [475+55, 117, 600, 170],
  ];

  let svgBoxes = "", svgArrows = "", svgTexts = "";

  boxes.forEach(b => {
    svgBoxes += `<rect x="${b.x}" y="${b.y}" width="${b.w}" height="${b.h}" fill="${b.bg}" rx="6"/>`;
    svgTexts += `<text x="${b.x + b.w/2}" y="${b.y + b.h/2 - 6}" font-size="12" font-weight="bold" fill="white" font-family="Arial" text-anchor="middle">${b.label}</text>`;
    b.sub.split("\n").forEach((ln, i) => {
      svgTexts += `<text x="${b.x + b.w/2}" y="${b.y + b.h/2 + 8 + i*12}" font-size="9" fill="#EEE" font-family="Arial" text-anchor="middle">${ln}</text>`;
    });
  });

  arrows.forEach(([x1,y1,x2,y2]) => {
    svgArrows += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="#999" stroke-width="2" marker-end="url(#arrow)"/>`;
  });

  // 온디바이스 영역 표시
  const label1 = "온디바이스 (오프라인 완전 작동)";

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}">
  <defs>
    <marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
      <path d="M0,0 L0,6 L8,3 z" fill="#999"/>
    </marker>
  </defs>
  <rect width="${w}" height="${h}" fill="#FAFAFA" rx="8"/>
  <rect x="5" y="40" width="590" height="140" fill="none" stroke="#2E75B6" stroke-width="1.5" stroke-dasharray="6,3" rx="8"/>
  <text x="12" y="36" font-size="11" fill="#2E75B6" font-family="Arial" font-style="italic">${label1}</text>
  ${svgArrows}${svgBoxes}${svgTexts}
  <text x="${w/2}" y="208" font-size="11" fill="#888" font-family="Arial" text-anchor="middle">서버 연동은 선택적 — 네트워크 없이도 핵심 기능 100% 유지</text>
</svg>`;
}

// ── SVG 타임라인 ──────────────────────────────────────────────
function svgTimeline() {
  const w = 700, h = 220;
  const phases = [
    { label: "1단계 MVP", period: "현재~1개월", goal: "TFLite 추론 안정화\n위험도 규칙 완성", color: "#1A3E6B" },
    { label: "2단계 파일럿", period: "1~3개월", goal: "복지관 3곳 MOU\n사용자 20인 테스트", color: "#2E75B6" },
    { label: "3단계 조달", period: "3~6개월", goal: "NIA 보조기기\n보급사업 등록", color: "#E67E22" },
    { label: "4단계 확장", period: "6개월+", goal: "스마트 글래스\n해외시장 진출", color: "#27AE60" },
  ];
  const step = w / phases.length;
  const cy = 100;

  let items = "";
  phases.forEach((p, i) => {
    const cx = step * i + step / 2;
    // connector line
    if (i < phases.length - 1) {
      items += `<line x1="${cx + 24}" y1="${cy}" x2="${cx + step - 24}" y2="${cy}" stroke="#CCC" stroke-width="2" marker-end="url(#arrowTL)"/>`;
    }
    // circle
    items += `<circle cx="${cx}" cy="${cy}" r="22" fill="${p.color}"/>`;
    items += `<text x="${cx}" y="${cy + 6}" font-size="13" font-weight="bold" fill="white" font-family="Arial" text-anchor="middle">${i+1}</text>`;
    // phase label above
    items += `<text x="${cx}" y="${cy - 34}" font-size="13" font-weight="bold" fill="${p.color}" font-family="Arial" text-anchor="middle">${p.label}</text>`;
    items += `<text x="${cx}" y="${cy - 18}" font-size="11" fill="#999" font-family="Arial" text-anchor="middle">${p.period}</text>`;
    // goal below
    p.goal.split("\n").forEach((ln, li) => {
      items += `<text x="${cx}" y="${cy + 36 + li*15}" font-size="11" fill="#555" font-family="Arial" text-anchor="middle">${ln}</text>`;
    });
  });

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}">
  <defs>
    <marker id="arrowTL" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
      <path d="M0,0 L0,6 L8,3 z" fill="#CCC"/>
    </marker>
  </defs>
  <rect width="${w}" height="${h}" fill="white" rx="8"/>
  <text x="${w/2}" y="22" font-size="14" font-weight="bold" fill="#1A3E6B" font-family="Arial" text-anchor="middle">중장기 발전 로드맵</text>
  ${items}
</svg>`;
}

// ── SVG 포지셔닝 매트릭스 ─────────────────────────────────────
function svgPositioningMatrix() {
  const w = 500, h = 380;
  const cx = w/2, cy = h/2 + 20;

  const items = [
    { x: cx - 90, y: cy - 80, label: "VoiceGuide", sub: "자동+온디바이스", color: "#1A3E6B", r: 28, bold: true },
    { x: cx + 90, y: cy + 80, label: "Be My Eyes", sub: "수동+클라우드", color: "#CCC", r: 18 },
    { x: cx - 90, y: cy + 80, label: "흰지팡이", sub: "수동+아날로그", color: "#CCC", r: 16 },
    { x: cx + 90, y: cy - 60, label: "Seeing AI", sub: "수동+클라우드", color: "#CCC", r: 16 },
  ];

  let dots = "";
  items.forEach(it => {
    dots += `<circle cx="${it.x}" cy="${it.y}" r="${it.r}" fill="${it.color}" opacity="${it.bold ? 1 : 0.5}"/>`;
    dots += `<text x="${it.x}" y="${it.y + 4}" font-size="${it.bold ? 10 : 9}" font-weight="${it.bold ? 'bold' : 'normal'}" fill="${it.bold ? 'white' : '#555'}" font-family="Arial" text-anchor="middle">${it.label}</text>`;
    if (!it.bold) {
      dots += `<text x="${it.x}" y="${it.y + 16}" font-size="9" fill="#888" font-family="Arial" text-anchor="middle">${it.sub}</text>`;
    } else {
      dots += `<text x="${it.x}" y="${it.y + 16}" font-size="9" fill="#2E75B6" font-family="Arial" text-anchor="middle">${it.sub}</text>`;
    }
  });

  // 사각형 배경 4분면
  const quad = [
    { x: 40, y: 40, w: cx-40, h: cy-40, fill: "#FFF9F0", label: "자동/클라우드" },
    { x: cx, y: 40, w: cx-40, h: cy-40, fill: "#E8F4FF", label: "자동/온디바이스 ★" },
    { x: 40, y: cy, w: cx-40, h: cy-40, fill: "#F5F5F5", label: "수동/아날로그" },
    { x: cx, y: cy, w: cx-40, h: cy-40, fill: "#FFF5F5", label: "수동/클라우드" },
  ];

  let quadSvg = "";
  quad.forEach(q => {
    quadSvg += `<rect x="${q.x}" y="${q.y}" width="${q.w}" height="${q.h}" fill="${q.fill}" stroke="#DDD" stroke-width="0.5"/>`;
    quadSvg += `<text x="${q.x + q.w/2}" y="${q.y + 14}" font-size="10" fill="#AAA" font-family="Arial" text-anchor="middle">${q.label}</text>`;
  });

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}">
  <rect width="${w}" height="${h}" fill="white" rx="8"/>
  <text x="${w/2}" y="22" font-size="13" font-weight="bold" fill="#1A3E6B" font-family="Arial" text-anchor="middle">경쟁 포지셔닝 매트릭스</text>
  ${quadSvg}
  <line x1="${cx}" y1="40" x2="${cx}" y2="${h-40}" stroke="#BBB" stroke-width="1.5"/>
  <line x1="40" y1="${cy}" x2="${w-40}" y2="${cy}" stroke="#BBB" stroke-width="1.5"/>
  <text x="${w/2}" y="${h-8}" font-size="10" fill="#888" font-family="Arial" text-anchor="middle">← 수동 감지  |  자동 감지 →</text>
  <text x="14" y="${cy}" font-size="10" fill="#888" font-family="Arial" text-anchor="middle" transform="rotate(-90,14,${cy})">← 클라우드  |  온디바이스 →</text>
  ${dots}
</svg>`;
}

// ── SVG 데이터 파이프라인 ─────────────────────────────────────
function svgDataPipeline() {
  const w = 700, h = 160;
  const steps = [
    { label: "공공데이터\n수집", sub: "사회보장정보원\n보건복지부", color: "#1A3E6B" },
    { label: "정규화\n점수화", sub: "WGS84 좌표\n접근성 0~5점", color: "#2E75B6" },
    { label: "경로\n최적화", sub: "안전경로 선택\n접근성 우선", color: "#E67E22" },
    { label: "서비스\n연동", sub: "TTS 안내문\nSSE 대시보드", color: "#27AE60" },
    { label: "정책\n환류", sub: "비식별 위험로그\n지자체 제공", color: "#7D3C98" },
  ];
  const bw = 100, bh = 70, gap = (w - 40 - steps.length * bw) / (steps.length - 1);
  let items = "";
  steps.forEach((s, i) => {
    const x = 20 + i * (bw + gap);
    const y = (h - bh) / 2;
    items += `<rect x="${x}" y="${y}" width="${bw}" height="${bh}" fill="${s.color}" rx="6"/>`;
    s.label.split("\n").forEach((ln, li) => {
      items += `<text x="${x+bw/2}" y="${y+20+li*14}" font-size="12" font-weight="bold" fill="white" font-family="Arial" text-anchor="middle">${ln}</text>`;
    });
    s.sub.split("\n").forEach((ln, li) => {
      items += `<text x="${x+bw/2}" y="${y+bh+12+li*12}" font-size="9" fill="#666" font-family="Arial" text-anchor="middle">${ln}</text>`;
    });
    if (i < steps.length - 1) {
      items += `<line x1="${x+bw+2}" y1="${h/2}" x2="${x+bw+gap-2}" y2="${h/2}" stroke="#BBB" stroke-width="2" marker-end="url(#arrowDP)"/>`;
    }
  });
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h+40}">
  <defs>
    <marker id="arrowDP" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
      <path d="M0,0 L0,6 L8,3 z" fill="#BBB"/>
    </marker>
  </defs>
  <rect width="${w}" height="${h+40}" fill="white" rx="8"/>
  ${items}
</svg>`;
}

// ── SVG 팀 스택 가로 막대 ─────────────────────────────────────
function svgTeamStack() {
  const w = 680, h = 200;
  const skills = [
    { label: "Android / Kotlin", val: 90, color: "#1A3E6B", member: "정환주" },
    { label: "TFLite / YOLO AI", val: 88, color: "#2E75B6", member: "임명광" },
    { label: "FastAPI / GCP",    val: 82, color: "#E67E22", member: "임명광" },
    { label: "UX / 공공데이터",  val: 85, color: "#7D3C98", member: "김재현" },
    { label: "사업기획 / 문서화", val: 88, color: "#27AE60", member: "김재현" },
  ];
  const marginL = 160, marginR = 80, marginT = 30, marginB = 20;
  const chartW = w - marginL - marginR;
  const rowH = Math.floor((h - marginT - marginB) / skills.length);
  const barH = Math.min(22, rowH - 8);

  let items = "";
  skills.forEach((s, i) => {
    const y = marginT + i * rowH + (rowH - barH) / 2;
    const bw = (s.val / 100) * chartW;
    items += `<rect x="${marginL}" y="${y}" width="${bw}" height="${barH}" fill="${s.color}" rx="3" opacity="0.85"/>`;
    items += `<text x="${marginL - 8}" y="${y + barH/2 + 4}" font-size="11" fill="#444" font-family="Arial" text-anchor="end">${s.label}</text>`;
    items += `<text x="${marginL + bw + 6}" y="${y + barH/2 + 4}" font-size="10" fill="${s.color}" font-family="Arial" font-weight="bold">${s.val}%</text>`;
    items += `<text x="${w - marginR + 4}" y="${y + barH/2 + 4}" font-size="9" fill="#AAA" font-family="Arial">${s.member}</text>`;
  });

  // grid
  let grid = "";
  [25, 50, 75, 100].forEach(v => {
    const x = marginL + (v / 100) * chartW;
    grid += `<line x1="${x}" y1="${marginT - 5}" x2="${x}" y2="${h - marginB}" stroke="#EEE" stroke-width="1"/>`;
    grid += `<text x="${x}" y="${marginT - 8}" font-size="9" fill="#CCC" font-family="Arial" text-anchor="middle">${v}%</text>`;
  });

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}">
  <rect width="${w}" height="${h}" fill="white" rx="8"/>
  <text x="${w/2}" y="18" font-size="13" font-weight="bold" fill="#1A3E6B" font-family="Arial" text-anchor="middle">팀 핵심 기술 역량 커버리지</text>
  ${grid}${items}
</svg>`;
}

// ── SVG 성능 검증 KPI 바 차트 ────────────────────────────────
function svgPerfBar() {
  const w = 680, h = 200;
  const metrics = [
    { label: "응답지연\n0.5초 이하", value: 90, unit: "목표달성", color: "#2E75B6" },
    { label: "탐지정확도\n85% 이상", value: 85, unit: "85%", color: "#27AE60" },
    { label: "배터리·발열\n문제 없음", value: 78, unit: "기준 만족", color: "#E67E22" },
    { label: "음성피로도\n20% 감소", value: 80, unit: "20%↓", color: "#7D3C98" },
    { label: "오프라인\n100% 유지", value: 100, unit: "100%", color: "#1A3E6B" },
  ];
  const marginL = 20, marginR = 20, marginT = 60, marginB = 50;
  const chartW = w - marginL - marginR;
  const chartH = h - marginT - marginB;
  const n = metrics.length;
  const bw = Math.floor(chartW / n * 0.55);
  const gap = chartW / n;
  const yScale = v => chartH - (v / 100) * chartH;

  let bars = "", xlabels = "", grid = "";

  [25, 50, 75, 100].forEach(v => {
    const y = marginT + yScale(v);
    grid += `<line x1="${marginL}" y1="${y}" x2="${marginL + chartW}" y2="${y}" stroke="#EEE" stroke-width="1"/>`;
    grid += `<text x="${marginL - 4}" y="${y + 4}" font-size="9" fill="#BBB" font-family="Arial" text-anchor="end">${v}</text>`;
  });

  metrics.forEach((m, i) => {
    const x = marginL + i * gap + (gap - bw) / 2;
    const barY = marginT + yScale(m.value);
    const barH = chartH - yScale(m.value);
    bars += `<rect x="${x}" y="${barY}" width="${bw}" height="${barH}" fill="${m.color}" rx="3" opacity="0.85"/>`;
    // value label above bar — clamp so it doesn't go above chart top
    const labelY = Math.max(marginT - 6, barY - 5);
    bars += `<text x="${x + bw/2}" y="${labelY}" font-size="10" font-weight="bold" fill="${m.color}" font-family="Arial" text-anchor="middle">${m.unit}</text>`;
    m.label.split("\n").forEach((ln, li) => {
      xlabels += `<text x="${x + bw/2}" y="${marginT + chartH + 14 + li * 13}" font-size="10" fill="#555" font-family="Arial" text-anchor="middle">${ln}</text>`;
    });
  });

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}">
  <rect width="${w}" height="${h}" fill="white" rx="8"/>
  <text x="${w/2}" y="22" font-size="13" font-weight="bold" fill="#1A3E6B" font-family="Arial" text-anchor="middle">성능 검증 목표 시각화</text>
  <line x1="${marginL}" y1="${marginT}" x2="${marginL}" y2="${marginT+chartH}" stroke="#CCC" stroke-width="1.5"/>
  <line x1="${marginL}" y1="${marginT+chartH}" x2="${marginL+chartW}" y2="${marginT+chartH}" stroke="#CCC" stroke-width="1.5"/>
  ${grid}${bars}${xlabels}
</svg>`;
}

// ── SVG 사용자 여정 플로우 (Before/After VoiceGuide) ──────────
function svgUserJourney() {
  const w = 700, h = 200;
  const stages = ["출발 전", "보행 중", "위험 회피", "도착 후"];
  const before = ["경로 정보\n흩어져 있음", "흰지팡이만\n의존", "위험 원인\n불명확", "복지서비스\n정보 부족"];
  const after =  ["복지기관\n데이터 안내", "전방 객체\n음성 경고", "방향+객체\n즉시 안내", "복지서비스\n연계 안내"];
  const n = stages.length;
  const colW = w / n;
  const rowH = 60;
  const y0 = 30, y1 = 90, y2 = 155;

  let items = "";
  stages.forEach((s, i) => {
    const cx = colW * i + colW / 2;
    // Stage header
    items += `<rect x="${colW*i+4}" y="${y0-4}" width="${colW-8}" height="24" fill="#1A3E6B" rx="4"/>`;
    items += `<text x="${cx}" y="${y0+13}" font-size="12" font-weight="bold" fill="white" font-family="Arial" text-anchor="middle">${s}</text>`;
    // Arrow between stages
    if (i < n - 1) {
      items += `<line x1="${colW*(i+1)-10}" y1="${y0+8}" x2="${colW*(i+1)+4}" y2="${y0+8}" stroke="#CCC" stroke-width="1.5" marker-end="url(#arrowUJ)"/>`;
    }
    // Before row
    items += `<rect x="${colW*i+4}" y="${y1-4}" width="${colW-8}" height="${rowH}" fill="#FFEAEA" rx="4" stroke="#C0392B" stroke-width="0.5"/>`;
    before[i].split("\n").forEach((ln, li) => {
      items += `<text x="${cx}" y="${y1+18+li*14}" font-size="10" fill="#C0392B" font-family="Arial" text-anchor="middle">${ln}</text>`;
    });
    // After row
    items += `<rect x="${colW*i+4}" y="${y2-4}" width="${colW-8}" height="${rowH}" fill="#E8F8F0" rx="4" stroke="#27AE60" stroke-width="0.5"/>`;
    after[i].split("\n").forEach((ln, li) => {
      items += `<text x="${cx}" y="${y2+18+li*14}" font-size="10" fill="#1A5A40" font-family="Arial" text-anchor="middle">${ln}</text>`;
    });
  });

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h+20}">
  <defs>
    <marker id="arrowUJ" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
      <path d="M0,0 L0,6 L8,3 z" fill="#CCC"/>
    </marker>
  </defs>
  <rect width="${w}" height="${h+20}" fill="white" rx="8"/>
  <text x="4" y="${y1+14}" font-size="10" fill="#C0392B" font-family="Arial" font-weight="bold" transform="rotate(-90,8,${y1+rowH/2})">Before</text>
  <text x="4" y="${y2+14}" font-size="10" fill="#27AE60" font-family="Arial" font-weight="bold" transform="rotate(-90,8,${y2+rowH/2})">After</text>
  ${items}
</svg>`;
}

// ── SVG 사회적 가치 Before/After ─────────────────────────────
function svgSocialImpact() {
  const w = 680, h = 280;
  const cols = [
    { label: "흰지팡이만\n사용 시", items: ["상체 장애물 감지 불가", "돌발 상황 대처 어려움", "반복 경로만 이동 가능", "보조인 없이 장거리 불안", "인프라 부재 시 위험 노출"], color: "#C0392B", icon: "✗" },
    { label: "VoiceGuide\n도입 후",  items: ["82종 장애물 실시간 안내", "방향·거리 음성 경고 즉시", "안전 최적 경로 자동 추천", "완전 핸즈프리 독립 보행", "오프라인 100% 기능 유지"], color: "#27AE60", icon: "✓" },
  ];
  const colW = (w - 60) / 2;
  let svg = "";
  cols.forEach((col, ci) => {
    const x = 20 + ci * (colW + 20);
    svg += `<rect x="${x}" y="40" width="${colW}" height="${h - 50}" fill="${col.color}" fill-opacity="0.06" stroke="${col.color}" stroke-width="2" rx="8"/>`;
    const lines = col.label.split("\n");
    lines.forEach((ln, li) => {
      svg += `<text x="${x + colW/2}" y="${52 + li * 18}" font-size="13" font-weight="bold" fill="${col.color}" font-family="Arial" text-anchor="middle">${ln}</text>`;
    });
    col.items.forEach((item, ii) => {
      const iy = 96 + ii * 36;
      svg += `<rect x="${x + 10}" y="${iy - 14}" width="${colW - 20}" height="28" fill="${col.color}" fill-opacity="0.10" rx="4"/>`;
      svg += `<text x="${x + 28}" y="${iy + 5}" font-size="11" fill="${col.color}" font-family="Arial" font-weight="bold">${col.icon}</text>`;
      svg += `<text x="${x + 44}" y="${iy + 5}" font-size="11" fill="#333" font-family="Arial">${item}</text>`;
    });
  });
  // center arrow
  const cx = w / 2;
  svg += `<rect x="${cx - 22}" y="${h/2 - 22}" width="44" height="44" fill="white" stroke="#CCC" stroke-width="1" rx="22"/>`;
  svg += `<text x="${cx}" y="${h/2 + 7}" font-size="20" fill="#1A3E6B" font-family="Arial" text-anchor="middle">→</text>`;

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}">
  <rect width="${w}" height="${h}" fill="white" rx="8"/>
  <text x="${w/2}" y="22" font-size="14" font-weight="bold" fill="#1A3E6B" font-family="Arial" text-anchor="middle">VoiceGuide 도입 전후 보행 환경 변화</text>
  ${svg}
</svg>`;
}

// ── SVG KPI 행 (숫자 + 라벨 카드, 인포카드 대체) ──────────────
function svgKpiRow({ stats, width = 680, height = 130 }) {
  const n = stats.length;
  const pad = 10;
  const cardW = Math.floor((width - (n + 1) * pad) / n);
  let cards = "";
  stats.forEach((s, i) => {
    const x = pad + i * (cardW + pad);
    const lines = s.label.split("\n");
    cards += `<rect x="${x}" y="6" width="${cardW}" height="${height - 12}" fill="#F8FAFB" rx="6" stroke="${s.color}" stroke-width="2"/>`;
    cards += `<rect x="${x}" y="6" width="5" height="${height - 12}" fill="${s.color}" rx="3"/>`;
    cards += `<text x="${x + cardW / 2 + 2}" y="${Math.round(height * 0.48)}" font-size="26" font-weight="bold" fill="${s.color}" font-family="Arial" text-anchor="middle">${s.value}</text>`;
    lines.forEach((ln, li) => {
      cards += `<text x="${x + cardW / 2 + 2}" y="${Math.round(height * 0.48 + 20 + li * 14)}" font-size="10" fill="#555" font-family="Arial" text-anchor="middle">${ln}</text>`;
    });
  });
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}">
  <rect width="${width}" height="${height}" fill="white"/>
  ${cards}
</svg>`;
}

// ─── 색상 ─────────────────────────────────────────────────────
const C = {
  primary:   "1A3E6B",
  secondary: "2E75B6",
  accent:    "F2913D",
  light:     "D6E4F7",
  lightest:  "EBF4FF",
  white:     "FFFFFF",
  black:     "1A1A1A",
  gray:      "F5F5F5",
  midgray:   "888888",
  dark:      "444444",
  danger:    "C0392B",
  warning:   "E67E22",
  safe:      "27AE60",
  yellow:    "F5F5F5",
  orange:    "F5F5F5",
  green:     "EBF5FB",
  blue:      "F5F5F5",
  purple:    "F5F5F5",
};

// ─── 테두리 ────────────────────────────────────────────────────
const b1 = (c = "CCCCCC") => ({ style: BorderStyle.SINGLE, size: 1, color: c });
const bAll = (c = "CCCCCC") => ({ top: b1(c), bottom: b1(c), left: b1(c), right: b1(c) });
const bNone = () => ({ top: { style: BorderStyle.NONE }, bottom: { style: BorderStyle.NONE }, left: { style: BorderStyle.NONE }, right: { style: BorderStyle.NONE } });

// ─── 셀 생성 ──────────────────────────────────────────────────
function cell(content, {
  bg = C.white, bold = false, align = AlignmentType.LEFT,
  vAlign = VerticalAlign.CENTER, w = null, color = C.black,
  sz = 19, bdr = null, span = 1, italic = false,
  indent = 0, before = 80, after = 80,
} = {}) {
  let children;
  if (Array.isArray(content)) {
    children = content;
  } else {
    const lines = String(content).split('\n');
    children = lines.map((line, i) =>
      new Paragraph({
        alignment: align,
        spacing: { before: i === 0 ? before : 40, after: i === lines.length - 1 ? after : 40 },
        indent: indent ? { left: indent } : undefined,
        children: [new TextRun({ text: line, bold, color, size: sz, font: "Malgun Gothic", italics: italic })],
      })
    );
  }
  const opts = {
    borders: bdr || bAll(),
    shading: { fill: bg, type: ShadingType.CLEAR },
    margins: { top: 90, bottom: 90, left: 120, right: 120 },
    verticalAlign: vAlign,
    columnSpan: span,
    children,
  };
  if (w) opts.width = { size: w, type: WidthType.DXA };
  return new TableCell(opts);
}

// 헤더 셀
function hc(text, { bg = C.primary, color = C.white, w = null, align = AlignmentType.CENTER, sz = 19, span = 1 } = {}) {
  return cell([new Paragraph({
    alignment: align,
    spacing: { before: 100, after: 100 },
    children: [new TextRun({ text, bold: true, color, size: sz, font: "Malgun Gothic" })],
  })], { bg, bdr: bAll("888888"), w, span });
}

// 테이블 생성
function tbl(rows, { w = 9072, cols = [] } = {}) {
  return new Table({
    width: { size: w, type: WidthType.DXA },
    columnWidths: cols.length ? cols : undefined,
    rows,
  });
}

function row(...cells) { return new TableRow({ children: cells }); }

// ─── 텍스트 요소 ──────────────────────────────────────────────
function sectionTitle(num, text) {
  return new Paragraph({
    pageBreakBefore: num !== "cover",
    spacing: { before: 0, after: 200 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: C.primary, space: 4 } },
    children: [
      new TextRun({ text: `${num}. `, bold: true, color: C.secondary, size: 30, font: "Malgun Gothic" }),
      new TextRun({ text, bold: true, color: C.primary, size: 30, font: "Malgun Gothic" }),
    ],
  });
}

function subTitle(text) {
  return new Paragraph({
    spacing: { before: 200, after: 120 },
    children: [
      new TextRun({ text: "※ ", bold: true, color: C.accent, size: 23, font: "Malgun Gothic" }),
      new TextRun({ text, bold: true, color: C.primary, size: 23, font: "Malgun Gothic" }),
    ],
  });
}

function bullet(text, { indent = 360, sz = 19, color = C.black, bold = false } = {}) {
  return new Paragraph({
    spacing: { before: 60, after: 60 },
    indent: { left: indent, hanging: 240 },
    children: [
      new TextRun({ text: "◦ ", color: C.secondary, size: sz, font: "Malgun Gothic", bold: true }),
      new TextRun({ text, size: sz, color, font: "Malgun Gothic", bold }),
    ],
  });
}

function note(text) {
  return new Paragraph({
    spacing: { before: 80, after: 80 },
    indent: { left: 240 },
    children: [new TextRun({ text, size: 17, color: C.dark, font: "Malgun Gothic", italics: true })],
  });
}

function sp(n = 120) {
  return new Paragraph({ spacing: { before: n, after: 0 }, children: [new TextRun("")] });
}

function pb() {
  return new Paragraph({ children: [new PageBreak()] });
}

function p(text, { sz = 19, color = C.black, bold = false, indent = 0 } = {}) {
  return new Paragraph({
    spacing: { before: 60, after: 80 },
    indent: indent ? { left: indent } : undefined,
    children: [new TextRun({ text, size: sz, color, font: "Malgun Gothic", bold })],
  });
}

// ─── 시각화 헬퍼 ─────────────────────────────────────────────

// 인포그래픽 카드 박스 (큰 숫자 + 설명)
function infoCard(value, label, bg, borderColor, w = 2268) {
  return cell([
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120, after: 30 }, children: [
      new TextRun({ text: value, bold: true, size: 64, color: bg === C.white ? C.primary : C.white, font: "Malgun Gothic" }),
    ]}),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 120 }, children: [
      new TextRun({ text: label, size: 18, color: bg === C.white ? C.dark : "EEEEEE", font: "Malgun Gothic" }),
    ]}),
  ], { bg, bdr: bAll(borderColor), w });
}

// 화살표 셀 (플로우차트 연결)
function arrowCell(w = 400, vertical = false) {
  return cell(
    vertical ? "▼" : "▶",
    { bg: C.white, bdr: bNone(), w, align: AlignmentType.CENTER, bold: true, color: C.secondary, sz: 28 }
  );
}

// 플로우 박스 (시스템 아키텍처 등)
function flowBox(title, desc, bg, borderColor, w = 1400) {
  return cell([
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 80, after: 20 }, children: [
      new TextRun({ text: title, bold: true, size: 20, color: C.white, font: "Malgun Gothic" }),
    ]}),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 80 }, children: [
      new TextRun({ text: desc, size: 15, color: "EEEEEE", font: "Malgun Gothic" }),
    ]}),
  ], { bg, bdr: bAll(borderColor), w });
}

// 바 차트 행 (테이블 셀 기반)
function barChartRow(label, pct, total, color, bg = C.white) {
  const filled = Math.round(pct / 100 * 40);
  const bar = "█".repeat(filled) + "░".repeat(40 - filled);
  return row(
    cell(label, { w: 2400, bold: true, bg }),
    cell([new Paragraph({ spacing: { before: 60, after: 60 }, children: [
      new TextRun({ text: bar, font: "Malgun Gothic", size: 14, color }),
      new TextRun({ text: `  ${pct}%`, font: "Malgun Gothic", size: 18, bold: true, color }),
    ]})], { w: 5272, bg }),
    cell(total, { w: 1400, align: AlignmentType.CENTER, bold: true, color, bg }),
  );
}

// 타임라인 단계 셀
function timelineStep(phase, period, goal, color, w = 2200) {
  return cell([
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 80, after: 20 }, children: [
      new TextRun({ text: phase, bold: true, size: 22, color: C.white, font: "Malgun Gothic" }),
    ]}),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 20 }, children: [
      new TextRun({ text: period, size: 16, color: "CCCCCC", font: "Malgun Gothic" }),
    ]}),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 10, after: 80 }, children: [
      new TextRun({ text: goal, size: 17, color: "FFFFFF", font: "Malgun Gothic", bold: true }),
    ]}),
  ], { bg: color, bdr: bAll(color), w });
}

// 아이콘 + 텍스트 행 (체크리스트 스타일)
function iconRow(icon, text, color = C.primary) {
  return new Paragraph({
    spacing: { before: 60, after: 60 },
    indent: { left: 240, hanging: 360 },
    children: [
      new TextRun({ text: `${icon}  `, bold: true, color, size: 22, font: "Malgun Gothic" }),
      new TextRun({ text, size: 19, color: C.black, font: "Malgun Gothic" }),
    ],
  });
}

// ─── 표지 ─────────────────────────────────────────────────────
function coverPage() {
  return [
    sp(300),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 0, after: 80 },
      children: [new TextRun({ text: "「2026 국민행복 서비스 발굴 · 창업경진대회」 사업계획서", size: 22, color: C.midgray, font: "Malgun Gothic" })],
    }),
    tbl([
      row(
        cell([
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120, after: 60 }, children: [new TextRun({ text: "VoiceGuide", bold: true, size: 80, color: C.primary, font: "Malgun Gothic" })] }),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 60 }, children: [new TextRun({ text: "보이스가이드", bold: true, size: 30, color: C.secondary, font: "Malgun Gothic" })] }),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 40, after: 160 }, children: [new TextRun({ text: "시각장애인을 위한 온디바이스 AI 스마트폰 보행 보조 서비스", size: 24, color: C.dark, font: "Malgun Gothic" })] }),
        ], { bg: C.lightest, bdr: bAll(C.secondary), span: 3 }),
      ),
      row(
        cell([
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 100, after: 40 }, children: [new TextRun({ text: "25만+", bold: true, size: 52, color: C.primary, font: "Malgun Gothic" })] }),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 100 }, children: [new TextRun({ text: "국내 등록 시각장애인", size: 18, color: C.dark, font: "Malgun Gothic" })] }),
        ], { bg: C.blue, bdr: bAll(C.secondary), w: 3024 }),
        cell([
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 100, after: 40 }, children: [new TextRun({ text: "82종", bold: true, size: 52, color: C.accent, font: "Malgun Gothic" })] }),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 100 }, children: [new TextRun({ text: "장애물 탐지 클래스", size: 18, color: C.dark, font: "Malgun Gothic" })] }),
        ], { bg: C.orange, bdr: bAll("E67E22"), w: 3024 }),
        cell([
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 100, after: 40 }, children: [new TextRun({ text: "100%", bold: true, size: 52, color: C.safe, font: "Malgun Gothic" })] }),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 100 }, children: [new TextRun({ text: "온디바이스 프라이버시 보호", size: 18, color: C.dark, font: "Malgun Gothic" })] }),
        ], { bg: C.green, bdr: bAll("27AE60"), w: 3024 }),
      ),
    ], { w: 9072, cols: [3024, 3024, 3024] }),
    sp(160),
    tbl([
      row(
        hc("아이디어 주제(팀명)", { w: 2200, bg: C.primary }),
        cell("VoiceGuide (보이스가이드)   /   AI Human 4기 3팀", { w: 6872, bold: true, color: C.primary }),
      ),
    ], { w: 9072, cols: [2200, 6872] }),
    sp(80),
    tbl([
      row(
        hc("아이디어 요약\n(5줄 이내)", { w: 2200, bg: C.secondary }),
        cell([
          bullet("국내 등록 시각장애인 25만 명의 독립 보행을 위한 온디바이스 AI 기반 스마트폰 보행 보조 서비스"),
          bullet("YOLO11n-Nano + TFLite 온디바이스 추론으로 전방 장애물을 실시간 감지하고 방향별 한국어 음성 경고 제공"),
          bullet("흰지팡이가 탐지하지 못하는 상체 높이 장애물(킥보드, 볼라드, 공사 표지판 등)을 선제적으로 인식·안내"),
          bullet("완전 핸즈프리 음성 명령 지원 및 네트워크 없이도 구동되는 오프라인 온디바이스 처리 구조로 프라이버시 보호"),
          bullet("공공데이터(한국사회보장정보원, 보건복지부)를 활용한 실증 코스 설계 및 복지기관 파트너십 추진"),
        ], { w: 6872 }),
      ),
    ], { w: 9072, cols: [2200, 6872] }),
    sp(200),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [new TextRun({ text: "AI HUMAN 4기 3팀  |  2026", color: C.midgray, size: 19, font: "Malgun Gothic" })],
    }),
    pb(),
  ];
}

// ─── 사업계획서 요약 ──────────────────────────────────────────
function planSummary() {
  return [
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 0, after: 160 },
      children: [new TextRun({ text: "【 사업계획서 요약 】", bold: true, size: 28, color: C.primary, font: "Malgun Gothic" })],
      border: {
        top: { style: BorderStyle.SINGLE, size: 6, color: C.primary },
        bottom: { style: BorderStyle.SINGLE, size: 2, color: C.primary },
      },
    }),
    tbl([
      row(
        hc("제안배경 및\n출품작 소개", { w: 2000, bg: C.primary }),
        cell([
          bullet("국내 시각장애인 25만 명은 흰지팡이만으로는 상체 높이 장애물 탐지가 불가능해 보행 사고 위험에 상시 노출"),
          bullet("음향신호기 미설치율 45.3%, 볼라드 부적정 설치율 96% 등 도보 인프라 구조적 부실이 심각"),
          bullet("VoiceGuide는 스마트폰 카메라를 활용한 온디바이스 AI로 이 사각지대를 실시간 음성 안내로 보완하는 능동형 보행 보조 앱"),
        ], { w: 7072 }),
      ),
      row(
        hc("아이디어\n핵심내용", { w: 2000, bg: C.secondary }),
        cell([
          bullet("YOLO11n-Nano 320/TFLite 온디바이스 추론 (레이턴시 30ms 이내)"),
          bullet("바운딩박스 크기 기반 기하학적 거리 추정 공식 D = (F × H) / h"),
          bullet("화면 3분할 방향 판별 및 위험도 우선순위 매트릭스"),
          bullet("음성 출력 중복 필터(Audio Fatigue 방지)"),
          bullet("핸즈프리 STT 음성 명령 지원 — 4가지 모드(장애물/찾기/주변확인/물건확인)"),
        ], { w: 7072 }),
      ),
      row(
        hc("기존 서비스와의\n차별성", { w: 2000, bg: C.primary }),
        cell([
          bullet("수동 캡처 방식(Be My Eyes 등)과 달리 앱 실행만으로 자동 실시간 감지"),
          bullet("클라우드 전송 없이 온디바이스 100% 로컬 처리 → 즉각 반응 + 프라이버시 보호"),
          bullet("흰지팡이(하단 지면)와 AI 카메라(상단·정면)의 상호보완 구조"),
        ], { w: 7072 }),
      ),
      row(
        hc("창업(사업화)\n가능성", { w: 2000, bg: C.secondary }),
        cell([
          bullet("B2G(지자체 스마트시티·정보통신보조기기 조달)"),
          bullet("B2B(AI 엔진 SDK 라이선스)"),
          bullet("B2C(기본 무료 + 유료 팩)"),
          bullet("B2G2C(복지관 훈련 라이선스) — 4원 수익 구조"),
          bullet("정보통신보조기기 보급사업 등록 시 정부가 비용의 80~90% 지원 → 빠른 보급 채널 확보"),
        ], { w: 7072 }),
      ),
      row(
        hc("파급효과", { w: 2000, bg: C.primary }),
        cell([
          bullet("보행 돌발 사고율 40% 이상 경감 목표"),
          bullet("수천억 규모 물리 인프라 재설치 비용 절감"),
          bullet("경량 Edge AI 복지 실용 모델 선도 — ESG: UN SDGs '모두를 위한 포용적 도시' 기여"),
          bullet("온디바이스 처리로 개인정보보호법 리스크 원천 차단"),
        ], { w: 7072 }),
      ),
      row(
        hc("활용 공공데이터\n(제공기관명)", { w: 2000, bg: C.secondary }),
        cell([
          bullet("사회서비스 제공기관 정보 검색 (한국사회보장정보원) → 실증 복지관 매핑"),
          bullet("장애인편의시설 현황 (한국사회보장정보원) → 필드 테스트 코스 설계"),
          bullet("중앙부처복지서비스 (한국사회보장정보원) → 정보통신보조기기 정책 기획"),
          bullet("등록장애인 수 (보건복지부) → 지역별 잠재 고객 규모 분석"),
          bullet("보행자 사고다발구역 (경찰청) / 횡단보도 접근성 (서울시) → 경로 추천·위험지도"),
        ], { w: 7072 }),
      ),
    ], { w: 9072, cols: [2000, 7072] }),
  ];
}

// ─── 섹션 1. 팀 역량 ──────────────────────────────────────────
function section1() {
  return [
    sectionTitle("1", "참가자(팀) 주요 역량"),

    subTitle("팀원 구성 및 역할 분담"),
    tbl([
      row(
        hc("역할", { w: 1800 }),
        hc("이름", { w: 1200 }),
        hc("주요 역량 및 담당 업무", { w: 6072 }),
      ),
      row(
        cell("팀장 / Android 개발", { bg: C.blue, bold: true, w: 1800, align: AlignmentType.CENTER }),
        cell("정환주", { bg: C.blue, bold: true, w: 1200, align: AlignmentType.CENTER }),
        cell([
          bullet("Android(Kotlin) 개발 총괄, Git 브랜치 전략 수립 및 협업 아키텍처 설계", { indent: 240 }),
          bullet("MVP 앱 인터페이스 및 CameraX 프레임 파이프라인 구축", { indent: 240 }),
          bullet("외부 서버(GCP Cloud Run) 연동 및 오디오 제어 로직 구현", { indent: 240 }),
          bullet("MvpPipeline.kt, SentenceBuilder.kt, VoicePolicy.kt 구현", { indent: 240 }),
        ], { w: 6072 }),
      ),
      row(
        cell("AI 모델 연동\n및 서버", { bg: C.orange, bold: true, w: 1800, align: AlignmentType.CENTER }),
        cell("임명광", { bg: C.orange, bold: true, w: 1200, align: AlignmentType.CENTER }),
        cell([
          bullet("YOLO 객체 감지 모델 최적화 및 한국어 클래스 매핑, TFLite 형식 변환", { indent: 240 }),
          bullet("온디바이스 추론 파이프라인 개발 (yolo11n_320.tflite)", { indent: 240 }),
          bullet("규칙 기반 객체 거리·방향 판별 알고리즘 설계 (D=F×H/h)", { indent: 240 }),
          bullet("GCP Cloud Run 인프라 배포, FastAPI 서버 구축", { indent: 240 }),
        ], { w: 6072 }),
      ),
      row(
        cell("UX / 기획\n사업계획서", { bg: C.purple, bold: true, w: 1800, align: AlignmentType.CENTER }),
        cell("김재현", { bg: C.purple, bold: true, w: 1200, align: AlignmentType.CENTER }),
        cell([
          bullet("시각장애인 접근성 가이드라인 분석 및 인터뷰 기반 UX 기획", { indent: 240 }),
          bullet("활용 공공데이터 수집 및 정제, 횡단보도 접근성 점수화 시나리오 설계", { indent: 240 }),
          bullet("사업성/시장성 분석 및 사업계획서/발표 자료 작성", { indent: 240 }),
          bullet("사용자 피드백 분석 및 보라매역 → 복지관 데모 시나리오 구성", { indent: 240 }),
        ], { w: 6072 }),
      ),
      row(
        cell("지도강사", { bg: C.gray, bold: true, w: 1800, align: AlignmentType.CENTER }),
        cell("이석창", { bg: C.gray, bold: true, w: 1200, align: AlignmentType.CENTER }),
        cell("AI Human 4기 지도강사", { w: 6072, color: C.dark }),
      ),
    ], { w: 9072, cols: [1800, 1200, 6072] }),

    sp(160),
    subTitle("팀 역량 요약 및 협업 체계"),
    p("본 팀은 전문 AI 교육과정(AI Human 4기)을 통해 AI 알고리즘, 컴퓨터 비전, 자연어 처리, 그리고 이를 최종 배포하기 위한 모바일·클라우드 개발 전반에 걸친 실무 역량을 함양하였습니다. 단순히 고성능의 AI 모델을 만드는 것에 그치지 않고, 스마트폰 하드웨어 성능 한계를 고려한 온디바이스 경량화 모델링(TFLite)과 시각장애인 대상 접근성(Accessibility)에 맞춘 UX 기획을 결합하여, 실제 사용 가능한 '프로덕트 중심의 사고'로 협업을 진행하고 있습니다."),
    sp(80),
    tbl([
      row(
        hc("협업 방식", { w: 2000, bg: C.secondary }),
        hc("내용", { w: 7072 }),
      ),
      row(
        cell("개발 병렬화", { bg: C.blue, bold: true, w: 2000 }),
        cell("기술팀은 Android 실시간 추론, 모델 경량화, JSON/서버 연동을 분리해 병렬 개발", { w: 7072 }),
      ),
      row(
        cell("기획·UX 검증", { bg: C.purple, bold: true, w: 2000 }),
        cell("기획·UX 담당은 보행 상황, 경고 피로도, 공공데이터 시나리오를 독립 검증", { w: 7072 }),
      ),
      row(
        cell("스프린트", { bg: C.orange, bold: true, w: 2000 }),
        cell("주 2회 스크럼으로 기능 단위 이슈 관리 — 데모 영상·대시보드·사업계획서를 같은 메시지로 정렬", { w: 7072 }),
      ),
    ], { w: 9072, cols: [2000, 7072] }),

    sp(160),
    subTitle("역량과 심사기준 연결 표"),
    tbl([
      row(
        hc("심사기준", { w: 2200 }),
        hc("팀 보유 역량", { w: 3600 }),
        hc("제출서류에서 보여줄 증거", { w: 3272 }),
      ),
      row(
        cell("AI 기술 활용", { bg: C.blue, bold: true, w: 2200 }),
        cell("모바일 객체감지, TFLite 변환, 위험도 로직 설계", { w: 3600 }),
        cell("모델 구조도, 성능 목표, 위험도 매트릭스", { w: 3272 }),
      ),
      row(
        cell("AI 서비스", { bg: C.orange, bold: true, w: 2200 }),
        cell("Android 카메라 파이프라인, STT/TTS UX", { w: 3600 }),
        cell("데모 시나리오, 음성 경고 예시", { w: 3272 }),
      ),
      row(
        cell("공공데이터 활용", { bg: C.green, bold: true, w: 2200 }),
        cell("데이터셋 조사·정제, 기관 매핑, 접근성 점수화", { w: 3600 }),
        cell("데이터 활용표, 실증기관 발굴 계획", { w: 3272 }),
      ),
      row(
        cell("발전 가능성", { bg: C.purple, bold: true, w: 2200 }),
        cell("Cloud Run 배포 완료, 대시보드, 사업계획서 작성", { w: 3600 }),
        cell("6개월 로드맵, PoC 제안 구조", { w: 3272 }),
      ),
    ], { w: 9072, cols: [2200, 3600, 3272] }),

    sp(120),
    subTitle("팀 개발 스택 및 기술 커버리지"),
    new Paragraph({
      spacing: { before: 60, after: 80 },
      children: [svgImage(svgTeamStack(), 572, 168)],
    }),
    pb(),
  ];
}

// ─── 섹션 2. 제안배경 ────────────────────────────────────────
function section2() {
  return [
    sectionTitle("2", "제안배경 및 출품작 소개"),

    subTitle("제안 배경 및 문제 정의"),
    p("국내 등록 시각장애인은 2023년 보건복지부 기준 약 25만 명에 달하며, 이들의 실외 독립 보행은 일상 자율성과 사회 참여를 위한 필수 조건입니다. 하지만 도심 보행 환경은 시각장애인에게 여전히 수많은 충돌 위험을 야기하고 있습니다."),
    p("기존의 대표적 보행 보조 기구인 '흰지팡이(White Cane)'는 지면 근처 장애물 탐지에는 훌륭하지만, 지면에서 50cm 이상 떠 있는 돌출 장애물(차량 사이드미러, 건설 표지판, 현수막 줄, 나뭇가지)이나 갑자기 빠른 속도로 진입하는 전동 킥보드 등 상체 높이의 위험 요소 감지에는 명확한 한계를 지닙니다."),

    sp(120),
    subTitle("핵심 문제 현황 인포그래픽"),
    new Paragraph({
      spacing: { before: 60, after: 80 },
      children: [svgImage(svgKpiRow({
        stats: [
          { value: "25만 명", label: "국내 등록 시각장애인\n(2023, 보건복지부)", color: "#1A3E6B" },
          { value: "96%",    label: "볼라드 부적정 설치율\n(위험 장애물화)",    color: "#C0392B" },
          { value: "45.3%",  label: "음향신호기 미설치율\n(청각 안내 공백)",   color: "#E67E22" },
          { value: "4.0%",   label: "볼라드 적정 설치율\n(사실상 모두 위험)",  color: "#27AE60" },
        ],
        width: 680, height: 130,
      }), 572, 109)],
    }),

    sp(120),
    subTitle("전국 시각장애인 보행 편의시설 설치 실태 (정량 데이터)"),
    p("한국시각장애인연합회 시각장애인편의시설지원센터 2023년 전국 주요 공공/교통시설 주변 반경 300m 보행로(총 7,019개 조사 지점) 실태조사 결과:", { sz: 18, color: C.dark }),
    sp(60),
    tbl([
      row(
        hc("편의시설 구분", { w: 2600 }),
        hc("적정 설치율\n(안전)", { bg: C.safe, w: 1600 }),
        hc("부적정 설치율\n(위험)", { bg: C.warning, w: 1600 }),
        hc("미설치율\n(위험)", { bg: C.danger, w: 1600 }),
        hc("VoiceGuide 보완 방식", { w: 1672 }),
      ),
      row(
        cell("인도 점자블록", { w: 2600, bold: true }),
        cell("4.0%", { w: 1600, align: AlignmentType.CENTER, color: C.safe, bold: true }),
        cell("77.3%", { w: 1600, align: AlignmentType.CENTER, color: C.warning, bold: true }),
        cell("18.7%", { w: 1600, align: AlignmentType.CENTER, color: C.danger, bold: true }),
        cell("경로 위험 객체 음성 안내", { w: 1672, sz: 17 }),
      ),
      row(
        cell("볼라드(차량 진입 억제용 말뚝)", { w: 2600, bold: true }),
        cell("4.0%", { w: 1600, align: AlignmentType.CENTER, color: C.safe, bold: true }),
        cell("96.0%", { w: 1600, align: AlignmentType.CENTER, color: C.danger, bold: true, bg: "FFEAEA" }),
        cell("—", { w: 1600, align: AlignmentType.CENTER, color: C.midgray }),
        cell("볼라드 객체 선제 감지", { w: 1672, sz: 17 }),
      ),
      row(
        cell("신호등 음향신호기", { w: 2600, bold: true }),
        cell("28.0%", { w: 1600, align: AlignmentType.CENTER, color: C.safe, bold: true }),
        cell("26.7%", { w: 1600, align: AlignmentType.CENTER, color: C.warning, bold: true }),
        cell("45.3%", { w: 1600, align: AlignmentType.CENTER, color: C.danger, bold: true, bg: "FFEAEA" }),
        cell("접근성 우수 경로 추천", { w: 1672, sz: 17 }),
      ),
      row(
        cell("교통시설 점자블록 연계성", { w: 2600, bold: true }),
        cell("7.8%", { w: 1600, align: AlignmentType.CENTER, color: C.safe, bold: true }),
        cell("37.5%", { w: 1600, align: AlignmentType.CENTER, color: C.warning, bold: true }),
        cell("54.7%", { w: 1600, align: AlignmentType.CENTER, color: C.danger, bold: true }),
        cell("공공데이터 연계 안내", { w: 1672, sz: 17 }),
      ),
    ], { w: 9072, cols: [2600, 1600, 1600, 1600, 1672] }),
    note("VoiceGuide는 점자블록·음향신호기·볼라드를 대체하는 앱이 아니라, 설치 품질과 관리 공백을 보완하는 저비용 디지털 안전망입니다."),

    sp(120),
    subTitle("편의시설 설치 실태 그래프 (적정/부적정/미설치 비율)"),
    new Paragraph({
      spacing: { before: 60, after: 80 },
      children: [svgImage(svgGroupedBarChart({
        title: "전국 시각장애인 보행 편의시설 설치 실태 (2023, 7,019개 지점 조사)",
        bars: [
          { label: "인도 점자블록", segments: [
            { val: 4.0,  color: "#27AE60", segLabel: "적정 (안전)" },
            { val: 77.3, color: "#E67E22", segLabel: "부적정 (위험)" },
            { val: 18.7, color: "#C0392B", segLabel: "미설치 (위험)" },
          ]},
          { label: "볼라드 (차량 억제용)", segments: [
            { val: 4.0,  color: "#27AE60", segLabel: "적정 (안전)" },
            { val: 96.0, color: "#E67E22", segLabel: "부적정 (위험)" },
          ]},
          { label: "신호등 음향신호기", segments: [
            { val: 28.0, color: "#27AE60", segLabel: "적정 (안전)" },
            { val: 26.7, color: "#E67E22", segLabel: "부적정 (위험)" },
            { val: 45.3, color: "#C0392B", segLabel: "미설치 (위험)" },
          ]},
          { label: "교통시설 점자블록 연계", segments: [
            { val: 7.8,  color: "#27AE60", segLabel: "적정 (안전)" },
            { val: 37.5, color: "#E67E22", segLabel: "부적정 (위험)" },
            { val: 54.7, color: "#C0392B", segLabel: "미설치 (위험)" },
          ]},
        ],
        width: 680, height: 280,
      }), 572, 236)],
    }),

    sp(140),
    subTitle("신문보도 사례 — VoiceGuide 적용 필요성"),
    tbl([
      row(
        cell([
          new Paragraph({ spacing: { before: 60, after: 40 }, children: [
            new TextRun({ text: "■ 사례 1: 점자블록 위 무단 방치된 공유 킥보드 — 시각장애인에겐 사실상 '지뢰밭'", bold: true, size: 20, color: C.primary, font: "Malgun Gothic" }),
          ]}),
          new Paragraph({ spacing: { before: 0, after: 60 }, children: [
            new TextRun({ text: "공유 모빌리티 활성화로 인도 위 전동 킥보드 방치가 사회적 문제로 대두되고 있다. 시각장애인이 보행 중 방치된 킥보드 핸들에 부딪혀 안면부 골절상을 입거나, 킥보드에 걸려 차도로 튕겨 나가는 사고가 빈번하게 보도되고 있다. 지자체의 강제 견인 제도 등 사후 조치만으로는 실시간 보행 중 충돌 위협을 원천 예방할 수 없다.", size: 18, color: C.black, font: "Malgun Gothic" }),
          ]}),
          new Paragraph({ spacing: { before: 0, after: 40 }, children: [
            new TextRun({ text: "📰 출처: 한겨레신문 (hani.co.kr)", size: 16, color: C.midgray, font: "Malgun Gothic", italics: true }),
          ]}),
          new Paragraph({ spacing: { before: 0, after: 60 }, children: [
            new TextRun({ text: "→ VoiceGuide 적용 시: 카메라가 전방 킥보드·자전거·적재물을 감지하고 즉시 안내 — 핵심은 사후 신고가 아니라 보행 순간의 사전 회피", bold: true, size: 18, color: C.safe, font: "Malgun Gothic" }),
          ]}),
        ], { bg: "FFF9F0", bdr: bAll("E67E22") }),
      ),
    ], { w: 9072, cols: [9072] }),
    sp(80),
    tbl([
      row(
        cell([
          new Paragraph({ spacing: { before: 60, after: 40 }, children: [
            new TextRun({ text: "■ 사례 2: 인도 위 설치 규격 어긴 볼라드(Bollard) — 충돌로 정강이 부상 속출", bold: true, size: 20, color: C.danger, font: "Malgun Gothic" }),
          ]}),
          new Paragraph({ spacing: { before: 0, after: 60 }, children: [
            new TextRun({ text: "보행자 안전을 위해 설치된 볼라드가 규정(충격흡수용 우레탄 재질, 높이 80~100cm, 전면 30cm 점자블록)을 지키지 않고 단단한 석재나 철재로 잘못 설치된 경우가 허다하다. 시각장애인이 단단한 돌 볼라드에 직접 부딪혀 다리쪽 찰과상 및 신체부위의 부상이 지속 발생하고 있다.", size: 18, color: C.black, font: "Malgun Gothic" }),
          ]}),
          new Paragraph({ spacing: { before: 0, after: 40 }, children: [
            new TextRun({ text: "📰 출처: 전북장애인신문 / 중앙일보 / 고양신문 / JTV뉴스", size: 16, color: C.midgray, font: "Malgun Gothic", italics: true }),
          ]}),
          new Paragraph({ spacing: { before: 0, after: 60 }, children: [
            new TextRun({ text: "→ VoiceGuide 적용 시: 볼라드를 '시설'이 아닌 보행 경로상 객체로 인식하여 흰지팡이 접촉 전 방향·거리 정보를 제공", bold: true, size: 18, color: C.safe, font: "Malgun Gothic" }),
          ]}),
        ], { bg: "FFF0F0", bdr: bAll(C.danger) }),
      ),
    ], { w: 9072, cols: [9072] }),

    sp(140),
    subTitle("문제의 3중 구조"),
    tbl([
      row(
        hc("구조", { w: 1600, bg: C.primary }),
        hc("내용", { w: 3600 }),
        hc("VoiceGuide 해결 방향", { w: 3872 }),
      ),
      row(
        cell("개인 차원", { bg: C.blue, bold: true, w: 1600, align: AlignmentType.CENTER }),
        cell("보행 중 위험을 바로 파악하지 못하면 외출 자체가 불안해짐 → 이동권과 생활 자립의 문제", { w: 3600 }),
        cell("실시간 음성 경고로 보행 중 즉각적 위험 인지 → 외출 자신감 회복", { w: 3872, color: C.safe, bold: true }),
      ),
      row(
        cell("지역 차원", { bg: C.orange, bold: true, w: 1600, align: AlignmentType.CENTER }),
        cell("편의시설 설치·관리 수준이 지역별로 다르고 실시간 위험은 계속 변함", { w: 3600 }),
        cell("시설정보 + 위험로그를 결합한 지역 맞춤 개선 → 비식별 히트맵 제공", { w: 3872, color: C.safe, bold: true }),
      ),
      row(
        cell("행정 차원", { bg: C.purple, bold: true, w: 1600, align: AlignmentType.CENTER }),
        cell("복지정보는 제공되지만 실제 목적지까지 안전하게 이동하는 과정은 별도 과제", { w: 3600 }),
        cell("복지정보 접근성 + 물리적 이동 접근성 연결 → 공공데이터 순환형 활용 모델", { w: 3872, color: C.safe, bold: true }),
      ),
    ], { w: 9072, cols: [1600, 3600, 3872] }),

    sp(140),
    subTitle("현장 위험 객체 분류"),
    tbl([
      row(
        hc("객체군", { w: 2000 }),
        hc("주요 예시", { w: 3000 }),
        hc("VoiceGuide 경고 예시", { w: 4072 }),
      ),
      row(
        cell("방치형 장애물", { bg: C.orange, bold: true, w: 2000, align: AlignmentType.CENTER }),
        cell("전동킥보드, 자전거, 적재물, 입간판", { w: 3000 }),
        cell("\"정면 1.5미터 앞 전동 킥보드 주의, 오른쪽으로 비껴가세요\"", { w: 4072, color: C.primary, bold: true }),
      ),
      row(
        cell("고정 시설물", { bg: C.yellow, bold: true, w: 2000, align: AlignmentType.CENTER }),
        cell("볼라드, 기둥, 공사 표지판, 나무 지지대", { w: 3000 }),
        cell("\"왼쪽 앞에 볼라드가 있어요. 오른쪽으로 피해가세요\"", { w: 4072, color: C.primary, bold: true }),
      ),
      row(
        cell("이동 객체", { bg: "FFEAEA", bold: true, w: 2000, align: AlignmentType.CENTER }),
        cell("사람, 자전거, 차량 진입", { w: 3000 }),
        cell("\"위험! 바로 앞 자전거. 조심! 멈추세요!\"", { w: 4072, color: C.danger, bold: true }),
      ),
      row(
        cell("환경 위험", { bg: C.gray, bold: true, w: 2000, align: AlignmentType.CENTER }),
        cell("공사구간, 횡단보도 진입부, 출입구 혼잡", { w: 3000 }),
        cell("\"왼쪽 앞에 공사 표지판이 있어요\"", { w: 4072, color: C.dark }),
      ),
    ], { w: 9072, cols: [2000, 3000, 4072] }),

    sp(140),
    subTitle("핵심 문제 구조"),
    tbl([
      row(
        hc("문제 영역", { w: 2000 }),
        hc("현재 한계", { w: 3500 }),
        hc("VoiceGuide가 보완할 지점", { w: 3572 }),
      ),
      row(
        cell("흰지팡이", { bg: C.orange, bold: true, w: 2000 }),
        cell("지면 근처 장애물 인지는 강하지만 상체 높이 장애물, 접근 물체, 돌발 상황에는 취약", { w: 3500 }),
        cell("스마트폰 카메라가 전방·상단 위험을 보조 감지 (82클래스 YOLO 모델)", { w: 3572 }),
      ),
      row(
        cell("도로 인프라", { bg: C.yellow, bold: true, w: 2000 }),
        cell("볼라드·음향신호기 품질·연계성 문제로 실제 보행 안정성이 낮음", { w: 3500 }),
        cell("개인 단말 기반 실시간 위험 안내로 인프라 공백 보완", { w: 3572 }),
      ),
      row(
        cell("정보 접근", { bg: C.blue, bold: true, w: 2000 }),
        cell("복지기관·편의시설 정보는 존재하지만 보행 중 위험 회피와 직접 연결되지 않음", { w: 3500 }),
        cell("복지기관/편의시설/복지서비스 데이터를 사용자 상황에 맞게 연결", { w: 3572 }),
      ),
    ], { w: 9072, cols: [2000, 3500, 3572] }),

    sp(140),
    subTitle("사용자 페르소나 및 고객여정지도"),
    tbl([
      row(
        hc("항목", { w: 2000, bg: C.secondary }),
        hc("내용", { w: 7072 }),
      ),
      row(
        cell("페르소나", { bg: C.blue, bold: true, w: 2000 }),
        cell("지민 씨(가명, 32세) — 출퇴근과 복지관 방문을 혼자 수행하는 시각장애인", { w: 7072 }),
      ),
      row(
        cell("현재 도구", { bg: C.blue, bold: true, w: 2000 }),
        cell("흰지팡이, 이어폰, 스마트폰 지도 앱, 주변 사람의 도움", { w: 7072 }),
      ),
      row(
        cell("주요 불안", { bg: "FFEAEA", bold: true, w: 2000 }),
        cell("방치 킥보드, 볼라드, 공사 표지판, 사람·자전거 접근, 음향신호기 없는 횡단보도", { w: 7072 }),
      ),
      row(
        cell("기대 가치", { bg: C.green, bold: true, w: 2000 }),
        cell("보행 중 손 조작 없이 \"무엇이 어느 방향에 얼마나 가까운지\"를 짧게 듣는 것", { w: 7072, bold: true }),
      ),
    ], { w: 9072, cols: [2000, 7072] }),
    sp(80),
    tbl([
      row(
        hc("여정 단계", { w: 1600 }),
        hc("사용자 행동", { w: 2200 }),
        hc("Pain Point", { w: 2200 }),
        hc("VoiceGuide 개입", { w: 3072 }),
      ),
      ...[
        ["출발 전", "목적지·이동 경로 확인", "복지기관·편의시설 정보가 흩어져 있음", "복지기관/편의시설 데이터 기반 주변 정보 안내"],
        ["보행 중", "흰지팡이로 바닥 확인", "상체 높이 장애물과 빠른 접근 물체 인지 어려움", "전방 객체 감지, 거리·방향 음성 경고"],
        ["위험 회피", "멈추거나 방향 조정", "위험 원인을 모르면 불안감 증가", "방향+객체 행동 단위 안내"],
        ["도착 후", "복지관·기관 방문", "이용 가능한 복지서비스 정보 부족", "중앙부처복지서비스 데이터와 연결해 제도 안내"],
        ["피드백", "불편지점 공유", "위험구간 정보가 행정 개선으로 이어지기 어려움", "비식별 위험 로그를 기관용 리포트로 환류"],
      ].map(([stage, action, pain, fix]) =>
        row(
          cell(stage, { bg: C.lightest, bold: true, w: 1600, align: AlignmentType.CENTER }),
          cell(action, { w: 2200 }),
          cell(pain, { w: 2200, color: C.danger }),
          cell(fix, { w: 3072, color: C.primary }),
        )
      ),
    ], { w: 9072, cols: [1600, 2200, 2200, 3072] }),

    sp(120),
    subTitle("사용자 여정 Before / After VoiceGuide"),
    new Paragraph({
      spacing: { before: 60, after: 80 },
      children: [svgImage(svgUserJourney(), 589, 185)],
    }),
    pb(),
  ];
}

// ─── 섹션 3. 아이디어 핵심 내용 ──────────────────────────────
function section3() {
  return [
    sectionTitle("3", "아이디어 핵심 내용 (공공데이터 활용 적정성, AI 기술 활용, 실현 가능성, 기술성)"),

    subTitle("MVP 기능 현황 (현재 구현 완료)"),
    tbl([
      row(
        hc("기능 모듈", { w: 2200 }),
        hc("상태", { w: 900 }),
        hc("구현 상세", { w: 5972 }),
      ),
      ...[
        ["장애물 탐지", "완료 ✔", "CameraX + TFLite YOLO11n 온디바이스 추론 — 82클래스(COCO80 + 계단 + 문)"],
        ["위험도 진동 패턴", "완료 ✔", "NONE/SHORT/DOUBLE/URGENT 4단계 햅틱 패턴 — 초근접(1m 이내) 시 URGENT 자동 발동"],
        ["한국어 TTS 음성 안내", "완료 ✔", "SentenceBuilder — 방향·거리·객체 정보 포함 한국어 짧은 경고문 동적 생성"],
        ["완전 핸즈프리 음성 명령", "완료 ✔", "STT 기반 4가지 모드(장애물/찾기/주변확인/물건확인) — 화면 조작 불필요"],
        ["3프레임 투표 필터", "완료 ✔", "3연속 프레임 2회 이상 탐지 시만 경보 확정 — 카메라 흔들림 오탐 방지"],
        ["IoU 추적 & EMA 평활화", "완료 ✔", "동적 객체 궤적 추적 + 지수이동평균 기반 접근 위험도 가중"],
        ["서버 전송 / DB 저장", "완료 ✔", "탐지 JSON + GPS POST → FastAPI + SQLite 영구 저장"],
        ["실시간 대시보드", "완료 ✔", "SSE 스트림 — 탐지 현황·이동 경로·24시간 내역·사고다발구역"],
        ["오프라인 동작", "완료 ✔", "서버 없이 Android 내장 TTS + 진동 완전 유지"],
        ["공공데이터 시나리오", "완료 ✔", "보라매역 → 서울시남부장애인종합복지관 A/B 경로 접근성 비교"],
      ].map(([feat, status, detail]) =>
        row(
          cell(feat, { w: 2200, bold: true }),
          cell(status, { w: 900, align: AlignmentType.CENTER, bold: true, color: C.safe, bg: C.green }),
          cell(detail, { w: 5972, sz: 18 }),
        )
      ),
    ], { w: 9072, cols: [2200, 900, 5972] }),

    sp(160),
    subTitle("시스템 아키텍처 다이어그램"),
    new Paragraph({
      spacing: { before: 60, after: 80 },
      children: [svgImage(svgArchDiagram(), 589, 185)],
    }),

    sp(160),
    subTitle("서비스 처리 흐름도 (상세)"),
    tbl([
      row(
        hc("단계", { w: 600, bg: C.primary }),
        hc("처리 내용", { w: 4272, bg: C.primary }),
        hc("기술 요소", { w: 4200, bg: C.secondary }),
      ),
      ...[
        ["①", "앱 실행 및 카메라 시작 → CameraX 실시간 프레임 캡처", "Android CameraX API"],
        ["②", "전방 객체 실시간 탐지 → TFLite YOLO11n 온디바이스 추론 (30ms 이내)", "yolo11n_320.tflite / yolo26n_float32.tflite"],
        ["③", "3프레임 투표 필터 → 오탐 방지 후 유효 객체 확정", "긴급 클래스(차량·동물·계단)는 우회 즉시 경보"],
        ["④", "위험도 계산 → IoU 추적 + EMA 위험도 산정", "바운딩박스 면적 × 클래스별 캘리브레이션 상수"],
        ["⑤", "진동 + 음성 안내 → 햅틱 4단계 + 한국어 TTS 즉시 출력", "SentenceBuilder.kt — 서버 응답 불필요"],
        ["⑥", "대시보드 기록 → 탐지 이력 및 GPS 경로 서버 저장·시각화", "FastAPI POST /detect, /gps → SSE → 대시보드"],
      ].map(([step, proc, tech], i) =>
        row(
          cell(step, { w: 600, bold: true, align: AlignmentType.CENTER, bg: i % 2 === 0 ? C.lightest : C.blue }),
          cell(proc, { w: 4272 }),
          cell(tech, { w: 4200, color: C.dark, sz: 17 }),
        )
      ),
    ], { w: 9072, cols: [600, 4272, 4200] }),

    sp(160),
    subTitle("거리 추정 알고리즘 시각화"),
    tbl([
      row(
        cell([
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 60, after: 20 }, children: [
            new TextRun({ text: "D = (F × H) / h", bold: true, size: 40, color: C.primary, font: "Malgun Gothic" }),
          ]}),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 60 }, children: [
            new TextRun({ text: "단일 카메라 기하학적 거리 추정 공식", size: 17, color: C.dark, font: "Malgun Gothic" }),
          ]}),
        ], { bg: C.lightest, bdr: bAll(C.secondary), w: 3000 }),
        arrowCell(400),
        cell([
          new Paragraph({ spacing: { before: 40, after: 20 }, children: [
            new TextRun({ text: "D", bold: true, color: C.danger, size: 22, font: "Malgun Gothic" }),
            new TextRun({ text: " = 추정 거리 (미터)", size: 19, color: C.black, font: "Malgun Gothic" }),
          ]}),
          new Paragraph({ spacing: { before: 10, after: 10 }, children: [
            new TextRun({ text: "F", bold: true, color: C.secondary, size: 22, font: "Malgun Gothic" }),
            new TextRun({ text: " = 카메라 초점거리 팩터 (보정 상수)", size: 19, color: C.black, font: "Malgun Gothic" }),
          ]}),
          new Paragraph({ spacing: { before: 10, after: 10 }, children: [
            new TextRun({ text: "H", bold: true, color: C.safe, size: 22, font: "Malgun Gothic" }),
            new TextRun({ text: " = 클래스 객체 실물 평균 높이", size: 19, color: C.black, font: "Malgun Gothic" }),
          ]}),
          new Paragraph({ spacing: { before: 10, after: 40 }, children: [
            new TextRun({ text: "h", bold: true, color: C.accent, size: 22, font: "Malgun Gothic" }),
            new TextRun({ text: " = 탐지된 바운딩박스 픽셀 높이", size: 19, color: C.black, font: "Malgun Gothic" }),
          ]}),
        ], { w: 5272 }),
      ),
    ], { w: 9072, cols: [3000, 400, 5272] }),
    sp(80),
    subTitle("방향 판별 구역 다이어그램 (화면 3분할)"),
    tbl([
      row(
        cell([
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 60, after: 10 }, children: [
            new TextRun({ text: "◀ 왼쪽", bold: true, size: 24, color: C.white, font: "Malgun Gothic" }),
          ]}),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 60 }, children: [
            new TextRun({ text: "0.0 ~ 0.33", size: 17, color: "CCCCCC", font: "Malgun Gothic" }),
          ]}),
        ], { bg: C.secondary, bdr: bAll(C.primary), w: 2800 }),
        cell([
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 60, after: 10 }, children: [
            new TextRun({ text: "▶ 정면 ◀", bold: true, size: 24, color: C.white, font: "Malgun Gothic" }),
          ]}),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 60 }, children: [
            new TextRun({ text: "0.33 ~ 0.66  ★ 최우선 위험", size: 17, color: "FFD700", font: "Malgun Gothic", bold: true }),
          ]}),
        ], { bg: C.danger, bdr: bAll("8B0000"), w: 3472 }),
        cell([
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 60, after: 10 }, children: [
            new TextRun({ text: "오른쪽 ▶", bold: true, size: 24, color: C.white, font: "Malgun Gothic" }),
          ]}),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 60 }, children: [
            new TextRun({ text: "0.66 ~ 1.0", size: 17, color: "CCCCCC", font: "Malgun Gothic" }),
          ]}),
        ], { bg: C.secondary, bdr: bAll(C.primary), w: 2800 }),
      ),
      row(
        cell("2순위: 방향 회피 안내\n(DOUBLE 진동)", { w: 2800, align: AlignmentType.CENTER, bg: C.blue, color: C.secondary, bold: true }),
        cell("1순위: 즉시 정지 경고\n(URGENT 진동)", { w: 3472, align: AlignmentType.CENTER, bg: "FFEAEA", color: C.danger, bold: true }),
        cell("2순위: 방향 회피 안내\n(DOUBLE 진동)", { w: 2800, align: AlignmentType.CENTER, bg: C.blue, color: C.secondary, bold: true }),
      ),
    ], { w: 9072, cols: [2800, 3472, 2800] }),

    sp(160),
    subTitle("AI 기술 활용 및 구체적 알고리즘"),
    p("VoiceGuide는 고비용의 클라우드 서버 통신이나 LTE/5G 음영 지역에서의 먹통 현상을 배제하기 위해 스마트폰 디바이스 내부에서 추론이 끝나는 '온디바이스(On-device) AI' 핵심 아키텍처를 지향합니다."),
    sp(80),
    tbl([
      row(
        hc("기술 요소", { w: 2200 }),
        hc("적용 방식", { w: 4272 }),
        hc("성능 목표", { w: 2600 }),
      ),
      row(
        cell("객체감지 모델", { bg: C.blue, bold: true, w: 2200 }),
        cell("YOLO11n-Nano를 TFLite로 변환해 모바일에서 온디바이스 추론 — FP32 기반", { w: 4272 }),
        cell("레이턴시 30ms 이내, mAP 39.5%", { w: 2600, bold: true }),
      ),
      row(
        cell("거리 추정\nD = (F × H) / h", { bg: C.orange, bold: true, w: 2200, align: AlignmentType.CENTER }),
        cell("단일 카메라 환경에서 바운딩박스 크기와 클래스 평균 실물 높이를 이용한 기하학적 거리 추정\nD: 추정거리 | F: 초점거리 팩터 | H: 클래스 실물 평균 높이 | h: 바운딩박스 픽셀 높이", { w: 4272 }),
        cell("클래스별 캘리브레이션 상수 개별 설정 (50종 이상)", { w: 2600, bold: true }),
      ),
      row(
        cell("방향 판별\n(3분할)", { bg: C.purple, bold: true, w: 2200, align: AlignmentType.CENTER }),
        cell("바운딩박스 중심점 X 좌표 기준\n• 0.0 ~ 0.33: 왼쪽\n• 0.33 ~ 0.66: 정면\n• 0.66 ~ 1.0: 오른쪽", { w: 4272 }),
        cell("화면 위치 기반 즉시 계산 (추가 연산 없음)", { w: 2600, bold: true }),
      ),
      row(
        cell("모델 최적화\n계획", { bg: C.gray, bold: true, w: 2200, align: AlignmentType.CENTER }),
        cell("현재 FP32 → 추후 FP16 또는 INT8 양자화로 발열·배터리·FPS 문제 완화", { w: 4272 }),
        cell("FPS 20 이상 목표 (저사양 기기)", { w: 2600, bold: true }),
      ),
    ], { w: 9072, cols: [2200, 4272, 2600] }),

    sp(140),
    subTitle("위험도 우선순위 매트릭스"),
    tbl([
      row(
        hc("구분(거리)", { w: 1800, bg: C.primary }),
        hc("정면 영역\n(0.33 ~ 0.66)", { bg: C.danger, w: 2424 }),
        hc("왼쪽 영역\n(0.0 ~ 0.33)", { bg: C.warning, w: 2424 }),
        hc("오른쪽 영역\n(0.66 ~ 1.0)", { bg: C.warning, w: 2424 }),
      ),
      row(
        cell("초근접\n(1.0m 이내)", { bg: "FFEAEA", bold: true, w: 1800, align: AlignmentType.CENTER }),
        cell("위험 1순위\n즉시 정지 경고 (URGENT)", { bg: "FFEAEA", w: 2424, align: AlignmentType.CENTER, bold: true, color: C.danger }),
        cell("위험 2순위\n방향 회피 안내 (DOUBLE)", { bg: "FFF3E0", w: 2424, align: AlignmentType.CENTER }),
        cell("위험 2순위\n방향 회피 안내 (DOUBLE)", { bg: "FFF3E0", w: 2424, align: AlignmentType.CENTER }),
      ),
      row(
        cell("근접\n(1.0m ~ 2.0m)", { bg: C.yellow, bold: true, w: 1800, align: AlignmentType.CENTER }),
        cell("주의 3순위\n진행 방향 주의 (SHORT)", { bg: C.yellow, w: 2424, align: AlignmentType.CENTER }),
        cell("주의 4순위\n접근 인지 알림 (SHORT)", { bg: C.yellow, w: 2424, align: AlignmentType.CENTER }),
        cell("주의 4순위\n접근 인지 알림 (SHORT)", { bg: C.yellow, w: 2424, align: AlignmentType.CENTER }),
      ),
      row(
        cell("원거리\n(2.0m 초과)", { bg: C.gray, bold: true, w: 1800, align: AlignmentType.CENTER }),
        cell("모니터링\n(안내 미출력)", { bg: C.gray, w: 2424, align: AlignmentType.CENTER, color: C.midgray }),
        cell("필터링\n(안내 제외)", { bg: C.gray, w: 2424, align: AlignmentType.CENTER, color: C.midgray }),
        cell("필터링\n(안내 제외)", { bg: C.gray, w: 2424, align: AlignmentType.CENTER, color: C.midgray }),
      ),
    ], { w: 9072, cols: [1800, 2424, 2424, 2424] }),

    sp(140),
    subTitle("성능 검증 계획"),
    tbl([
      row(
        hc("검증 항목", { w: 2200 }),
        hc("검증 방법", { w: 4000 }),
        hc("목표치", { w: 2872 }),
      ),
      ...[
        ["응답 지연", "카메라 입력부터 TTS 시작까지 시간 측정", "평균 0.5초 이하"],
        ["탐지 안정성", "동일 코스 반복 주행 영상 라벨링 비교", "핵심 객체 경고 정확도 85% 이상"],
        ["배터리/발열", "20분 연속 사용 시 온도·배터리 감소율 측정", "발열 경고 없이 사용 가능"],
        ["음성 피로도", "반복경고 빈도와 사용자 불편도 설문", "불편도 20% 이상 감소"],
        ["오프라인 안정성", "Wi-Fi 차단 상태에서 TTS·진동 동작 확인", "100% 기본 기능 유지"],
      ].map(([item, method, goal]) =>
        row(
          cell(item, { bg: C.lightest, bold: true, w: 2200 }),
          cell(method, { w: 4000 }),
          cell(goal, { w: 2872, bold: true, color: C.primary }),
        )
      ),
    ], { w: 9072, cols: [2200, 4000, 2872] }),

    sp(120),
    subTitle("성능 목표 시각화"),
    new Paragraph({
      spacing: { before: 60, after: 80 },
      children: [svgImage(svgPerfBar(), 572, 168)],
    }),
    pb(),
  ];
}

// ─── 섹션 4. 차별성 ──────────────────────────────────────────
function section4() {
  return [
    sectionTitle("4", "기존 서비스와의 차별성 (독창성)"),

    subTitle("국내외 유관 서비스와의 세부 성능 비교"),
    tbl([
      row(
        hc("비교 항목", { w: 2200, bg: C.primary }),
        hc("흰지팡이\n(기본)", { bg: C.midgray, w: 1468 }),
        hc("Be My Eyes\n(수동 캡처)", { bg: "888888", w: 1468 }),
        hc("Microsoft\nSeeing AI", { bg: "888888", w: 1468 }),
        hc("VoiceGuide", { bg: C.secondary, w: 2468 }),
      ),
      ...[
        ["주요 감지 대상", "바닥 30cm 이내 장애물", "텍스트·이미지 묘사", "텍스트·바코드·장면 설명", "정면/상체 높이 장애물 82클래스 ✔"],
        ["위험 즉시 알림", "접촉 시에만(사후)", "불가(수동 캡처)", "수동 캡처 필요", "자동 실시간 음성 경고(사전) ✔"],
        ["구동 방식", "완전 아날로그", "클라우드 서버 의존", "클라우드 서버 의존", "온디바이스 AI (오프라인 가능) ✔"],
        ["보행 중 조작성", "물리적 조작 필수", "화면 터치 조작 필요", "화면 터치 조작 필요", "음성 명령 완전 핸즈프리 ✔"],
        ["한국어 특화", "해당 없음", "미흡", "미흡", "완전 한국어 특화 (SentenceBuilder) ✔"],
        ["공공데이터 연동", "없음", "없음", "없음", "국내 공공데이터 접근성 분석 ✔"],
        ["실시간 대시보드", "없음", "없음", "없음", "보호자/기관용 SSE 대시보드 ✔"],
        ["4단계 진동 피드백", "없음", "없음", "없음", "NONE/SHORT/DOUBLE/URGENT ✔"],
        ["프라이버시", "해당 없음", "영상 서버 전송", "영상 서버 전송", "온디바이스 처리, 영상 미전송 ✔"],
      ].map(([item, wc, bme, ms, vg]) =>
        row(
          cell(item, { bg: C.light, bold: true, w: 2200 }),
          cell(wc, { w: 1468, align: AlignmentType.CENTER, color: C.midgray }),
          cell(bme, { w: 1468, align: AlignmentType.CENTER, color: C.midgray }),
          cell(ms, { w: 1468, align: AlignmentType.CENTER, color: C.midgray }),
          cell(vg, { w: 2468, align: AlignmentType.CENTER, bold: true, color: C.safe, bg: C.green }),
        )
      ),
    ], { w: 9072, cols: [2200, 1468, 1468, 1468, 2468] }),

    sp(160),
    subTitle("독창성 핵심 차별점 요약"),
    tbl([
      row(
        hc("차별점", { w: 2400, bg: C.secondary }),
        hc("설명", { w: 6672 }),
      ),
      row(
        cell("① 보행 위험 감지 자동화", { bg: C.blue, bold: true, w: 2400 }),
        cell("기존 앱들은 사용자가 직접 카메라로 찍어야 대답하는 방식인 반면, VoiceGuide는 앱 실행만으로 전방의 충돌 위협을 '자동' 감지하여 실시간 선제 안내를 제공합니다.", { w: 6672 }),
      ),
      row(
        cell("② 네트워크 독립 & 프라이버시", { bg: C.green, bold: true, w: 2400 }),
        cell("온디바이스에서 100% 로컬 처리하므로 즉시 반응이 가능하며, 카메라 프레임을 서버로 전송하지 않아 사용자의 시선 프라이버시를 안전하게 보호합니다.", { w: 6672 }),
      ),
      row(
        cell("③ 흰지팡이 상호보완 구조", { bg: C.purple, bold: true, w: 2400 }),
        cell("흰지팡이를 전면 부정하는 것이 아니라, 흰지팡이의 탐지 범위(하단 지면) 바깥의 사각지대(상단·정면 1.5m 공간)를 AI 카메라가 백업하는 형태로 연계합니다.", { w: 6672 }),
      ),
      row(
        cell("④ 공공데이터 경로 최적화", { bg: C.orange, bold: true, w: 2400 }),
        cell("단순 최단 경로가 아닌 음향신호기·볼라드·횡단보도 접근성 점수를 반영한 '시각장애인 안전 최적 경로'를 추천하는 차별화된 시나리오를 제공합니다.", { w: 6672 }),
      ),
    ], { w: 9072, cols: [2400, 6672] }),

    sp(140),
    subTitle("경쟁 포지셔닝 매트릭스"),
    new Paragraph({
      spacing: { before: 60, after: 80 },
      children: [svgImage(svgPositioningMatrix(), 420, 320)],
    }),

    sp(140),
    subTitle("서비스 포지셔닝 분석"),
    tbl([
      row(
        hc("포지셔닝 축", { w: 2000 }),
        hc("낮은 쪽", { w: 2500 }),
        hc("높은 쪽", { w: 2500 }),
        hc("VoiceGuide 위치", { bg: C.secondary, w: 2072 }),
      ),
      ...[
        ["즉시성", "사후 신고·사후 설명", "보행 중 자동 경고", "보행 중 자동 위험 경고 ✔"],
        ["데이터 활용", "단순 정보 조회", "실증·운영·환류", "공공데이터 + 비식별 위험로그 ✔"],
        ["보급 장벽", "고가 전용 장비", "스마트폰 앱", "스마트폰 기반 저마찰 도입 ✔"],
        ["프라이버시", "영상 서버 전송", "로컬 처리", "온디바이스 우선 처리 ✔"],
      ].map(([axis, low, high, pos]) =>
        row(
          cell(axis, { bg: C.light, bold: true, w: 2000 }),
          cell(low, { w: 2500, color: C.midgray }),
          cell(high, { w: 2500 }),
          cell(pos, { w: 2072, bold: true, color: C.safe, bg: C.green }),
        )
      ),
    ], { w: 9072, cols: [2000, 2500, 2500, 2072] }),
    pb(),
  ];
}

// ─── 섹션 5. 사업화 ──────────────────────────────────────────
function section5() {
  return [
    sectionTitle("5", "아이디어의 창업(사업화, 시장성), 매출 발생 및 투자 가능성"),

    subTitle("비즈니스 모델 캔버스 (4원 수익 구조)"),
    tbl([
      row(
        cell([
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 80, after: 20 }, children: [
            new TextRun({ text: "B2G", bold: true, size: 32, color: C.white, font: "Malgun Gothic" }),
          ]}),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 20 }, children: [
            new TextRun({ text: "정부 · 지자체", bold: true, size: 20, color: "EEEEEE", font: "Malgun Gothic" }),
          ]}),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 10, after: 80 }, children: [
            new TextRun({ text: "스마트시티 시범사업\n정보통신보조기기 조달\n→ 연 500만원/기관", size: 17, color: "FFFFFF", font: "Malgun Gothic" }),
          ]}),
        ], { bg: "1A3E6B", bdr: bAll("0D2240"), w: 2200 }),
        cell([
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 80, after: 20 }, children: [
            new TextRun({ text: "B2B", bold: true, size: 32, color: C.white, font: "Malgun Gothic" }),
          ]}),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 20 }, children: [
            new TextRun({ text: "보조기기 · 웨어러블", bold: true, size: 20, color: "EEEEEE", font: "Malgun Gothic" }),
          ]}),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 10, after: 80 }, children: [
            new TextRun({ text: "AI 감지 엔진\nSDK 라이선스\n→ 연 2,000만원~", size: 17, color: "FFFFFF", font: "Malgun Gothic" }),
          ]}),
        ], { bg: "E67E22", bdr: bAll("CC6600"), w: 2236 }),
        cell([
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 80, after: 20 }, children: [
            new TextRun({ text: "B2C", bold: true, size: 32, color: C.white, font: "Malgun Gothic" }),
          ]}),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 20 }, children: [
            new TextRun({ text: "시각장애인 개인", bold: true, size: 20, color: "EEEEEE", font: "Malgun Gothic" }),
          ]}),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 10, after: 80 }, children: [
            new TextRun({ text: "기본 무료 + 유료 팩\n→ 월 3,900원\n(3만 명 목표)", size: 17, color: "FFFFFF", font: "Malgun Gothic" }),
          ]}),
        ], { bg: "7D3C98", bdr: bAll("5B2780"), w: 2236 }),
        cell([
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 80, after: 20 }, children: [
            new TextRun({ text: "B2G2C", bold: true, size: 28, color: C.white, font: "Malgun Gothic" }),
          ]}),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 20 }, children: [
            new TextRun({ text: "복지관 라이선스", bold: true, size: 20, color: "EEEEEE", font: "Malgun Gothic" }),
          ]}),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 10, after: 80 }, children: [
            new TextRun({ text: "보행 훈련 라이선스\n대면 검증 프로그램\n→ 복지관 20곳 목표", size: 17, color: "FFFFFF", font: "Malgun Gothic" }),
          ]}),
        ], { bg: "27AE60", bdr: bAll("1A7A40"), w: 2400 }),
      ),
    ], { w: 9072, cols: [2200, 2236, 2236, 2400] }),
    sp(80),
    tbl([
      row(
        cell([
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 80, after: 80 }, children: [
            new TextRun({ text: "★ 정보통신보조기기 보급사업 등록 시 정부가 비용의 80~90% 지원 → 빠른 보급 채널 확보 가능", bold: true, size: 19, color: C.primary, font: "Malgun Gothic" }),
          ]}),
        ], { bg: C.lightest, bdr: bAll(C.secondary) }),
      ),
    ], { w: 9072, cols: [9072] }),

    sp(120),
    subTitle("수익 구조 도넛 차트 (중장기 목표 비중)"),
    new Paragraph({
      spacing: { before: 60, after: 80 },
      children: [svgImage(svgDonutChart({
        title: "VoiceGuide 수익 구조 (중장기 목표)",
        slices: [
          { label: "B2G 정부·지자체 조달", value: 40, color: "#1A3E6B" },
          { label: "B2B SDK 라이선스",   value: 25, color: "#E67E22" },
          { label: "B2C 개인 구독",       value: 20, color: "#7D3C98" },
          { label: "B2G2C 복지관",       value: 15, color: "#27AE60" },
        ],
        size: 300,
      }), 252, 320)],
    }),

    sp(140),
    subTitle("다각적 비즈니스 모델 (BM) 상세"),
    tbl([
      row(
        hc("비즈니스\n타겟", { w: 1400, bg: C.primary }),
        hc("제공 가치 (Value Proposition)", { w: 3600 }),
        hc("수익 창출 방식", { w: 4072 }),
      ),
      row(
        cell("B2G\n정부·지자체", { bg: C.blue, bold: true, w: 1400, align: AlignmentType.CENTER }),
        cell("교통약자 안전 보행 인프라 확충, 공공데이터 연계 복지 서비스 제공 실적", { w: 3600 }),
        cell("지자체 스마트시티 보행 안전 시범 사업 계약, 정보통신보조기기 조달 납품\n→ 연 500만원/기관 (50개소 목표)", { w: 4072 }),
      ),
      row(
        cell("B2B\n보조기기·웨어러블", { bg: C.orange, bold: true, w: 1400, align: AlignmentType.CENTER }),
        cell("기존 아날로그 안경, 목걸이형 스마트 기기에 AI 핵심 객체 감지 모듈 탑재 지원", { w: 3600 }),
        cell("AI 감지/거리판단 알고리즘 엔진 API/SDK 라이선스 수수료\n→ 연 2,000만원~", { w: 4072 }),
      ),
      row(
        cell("B2C\n개인 사용자", { bg: C.purple, bold: true, w: 1400, align: AlignmentType.CENTER }),
        cell("이동 안전 및 자율 보행감 증진, 삶의 질 향상", { w: 3600 }),
        cell("기본 자동 안내 영구 무료 + 고화질 정밀 탐지·음성 팩 유료 구독\n→ 월 3,900원 (3만 명 목표)", { w: 4072 }),
      ),
      row(
        cell("B2G2C\n복지관", { bg: C.green, bold: true, w: 1400, align: AlignmentType.CENTER }),
        cell("기관 이용자 보행 자립 훈련 프로그램 보완", { w: 3600 }),
        cell("기관용 보행 훈련 라이선스 판매 및 대면 검증 프로그램 공동 수행\n→ 복지관 20곳 목표 (2년차)", { w: 4072 }),
      ),
    ], { w: 9072, cols: [1400, 3600, 4072] }),

    sp(140),
    subTitle("초기 고객 가설 및 검증 방법"),
    tbl([
      row(
        hc("우선\n순위", { w: 600, bg: C.primary }),
        hc("고객군", { w: 2200 }),
        hc("도입 이유", { w: 3272 }),
        hc("검증 방법", { w: 3000 }),
      ),
      row(
        cell("1", { bg: C.blue, bold: true, w: 600, align: AlignmentType.CENTER }),
        cell("시각장애인 복지관", { w: 2200, bold: true }),
        cell("보행훈련 프로그램 보조와 사용자 피드백 확보", { w: 3272 }),
        cell("20명 내외 파일럿 테스트 — 현장 코스 운영", { w: 3000 }),
      ),
      row(
        cell("2", { bg: C.orange, bold: true, w: 600, align: AlignmentType.CENTER }),
        cell("지자체 장애인복지/교통약자 부서", { w: 2200, bold: true }),
        cell("지역 보행 위험 분석 및 스마트복지 성과", { w: 3272 }),
        cell("위험구간 리포트와 PoC 제안", { w: 3000 }),
      ),
      row(
        cell("3", { bg: C.purple, bold: true, w: 600, align: AlignmentType.CENTER }),
        cell("보조기기 기업", { w: 2200, bold: true }),
        cell("기존 하드웨어에 AI 감지 엔진 탑재 가능", { w: 3272 }),
        cell("SDK 데모와 공동사업 제안", { w: 3000 }),
      ),
    ], { w: 9072, cols: [600, 2200, 3272, 3000] }),

    sp(140),
    subTitle("도입 패키지 예시"),
    tbl([
      row(
        hc("패키지", { w: 1400, bg: C.primary }),
        hc("대상", { w: 2200 }),
        hc("구성", { w: 3472 }),
        hc("목표", { w: 2000 }),
      ),
      row(
        cell("실증형", { bg: C.blue, bold: true, w: 1400, align: AlignmentType.CENTER }),
        cell("복지관 / 교육기관", { w: 2200 }),
        cell("앱, 테스트 코스, 설문지, 위험로그 리포트", { w: 3472 }),
        cell("사용성 검증", { w: 2000, bold: true, color: C.safe }),
      ),
      row(
        cell("기관형", { bg: C.orange, bold: true, w: 1400, align: AlignmentType.CENTER }),
        cell("지자체 / 공공기관", { w: 2200 }),
        cell("앱 라이선스, 대시보드, 월간 리포트", { w: 3472 }),
        cell("교통약자 안전정책 자료화", { w: 2000, bold: true, color: C.primary }),
      ),
      row(
        cell("SDK형", { bg: C.purple, bold: true, w: 1400, align: AlignmentType.CENTER }),
        cell("보조기기 기업", { w: 2200 }),
        cell("객체감지·위험도 엔진, 음성 안내 모듈", { w: 3472 }),
        cell("기존 장비와 결합", { w: 2000, bold: true, color: C.dark }),
      ),
    ], { w: 9072, cols: [1400, 2200, 3472, 2000] }),

    sp(80),
    subTitle("중장기 발전 로드맵 타임라인"),
    new Paragraph({
      spacing: { before: 40, after: 60 },
      children: [svgImage(svgTimeline(), 589, 200)],
    }),

    sp(80),
    subTitle("중장기 발전 단계 로드맵 (상세)"),
    tbl([
      row(
        hc("단계", { w: 1000, bg: C.primary }),
        hc("기간", { w: 1400 }),
        hc("목표", { w: 3272 }),
        hc("주요 산출물", { w: 3400 }),
      ),
      ...[
        ["1단계\nMVP", "현재 ~ 1개월", "TFLite 추론 구조화, 위험도 규칙 정리, MVP 기능 완성·검증", "Android MVP, 테스트 체크리스트, 대시보드"],
        ["2단계\n파일럿", "1 ~ 3개월", "복지관 3곳과 실증 MOU 체결, 시각장애인 20인 대상 실외 필드 주행 테스트", "실증 리포트 1차, 인터뷰 요약, 공공데이터 매핑표"],
        ["3단계\n조달", "3 ~ 6개월", "NIA 정보통신보조기기 보급사업 소프트웨어 부문 신규 품목 등록 추진", "사업화 로드맵, 개인정보·윤리 체크리스트"],
        ["4단계\n확장", "6개월~", "안경형/웨어러블 디바이스 제휴 — 스마트 글래스 시장 진출", "SDK 패키징, 해외 시장 진출 기획서"],
      ].map(([phase, period, goal, output]) =>
        row(
          cell(phase, { bg: C.lightest, bold: true, w: 1000, align: AlignmentType.CENTER }),
          cell(period, { w: 1400, align: AlignmentType.CENTER, color: C.dark }),
          cell(goal, { w: 3272 }),
          cell(output, { w: 3400, color: C.dark, sz: 17 }),
        )
      ),
    ], { w: 9072, cols: [1000, 1400, 3272, 3400] }),

    sp(140),
    subTitle("월별 실행계획"),
    tbl([
      row(
        hc("기간", { w: 1200 }),
        hc("목표", { w: 2200 }),
        hc("주요 작업", { w: 3272 }),
        hc("산출물", { w: 2400 }),
      ),
      ...[
        ["1개월차", "MVP 안정화", "모델 클래스 통일, TFLite 추론 안정화, 위험도 규칙 정리, 음성 안내문 개선", "Android MVP, 테스트 체크리스트"],
        ["2개월차", "공공데이터 연계", "사회서비스 제공기관/편의시설/복지서비스 API 매핑, 실증기관 후보 도출", "기관 후보 리스트, 데이터 매핑표"],
        ["3개월차", "1차 파일럿", "복지관 테스트 코스 운영, 사용자 인터뷰, 위험객체 클래스 보정", "실증 리포트 1차, 인터뷰 요약"],
        ["4개월차", "AI·UX 고도화", "오탐/미탐 개선, 반복 경고 억제, 음성 명령 개선, 배터리·발열 측정", "모델/UX 개선본, 성능표"],
        ["5개월차", "기관 제안", "지자체/복지기관용 대시보드, 위험구간 리포트, 도입 제안서 작성", "PoC 제안서, 대시보드 캡처"],
        ["6개월차", "확산 준비", "후속지원사업 신청, 보조기기 연계 검토, 개인정보 문서화", "사업화 로드맵, 윤리 체크리스트"],
      ].map(([period, goal, work, output]) =>
        row(
          cell(period, { bg: C.lightest, bold: true, w: 1200, align: AlignmentType.CENTER }),
          cell(goal, { w: 2200, bold: true, color: C.primary }),
          cell(work, { w: 3272, sz: 18 }),
          cell(output, { w: 2400, sz: 17, color: C.dark }),
        )
      ),
    ], { w: 9072, cols: [1200, 2200, 3272, 2400] }),

    sp(140),
    subTitle("성과지표 (KPI)"),
    tbl([
      row(
        hc("구분", { w: 1400 }),
        hc("1차 목표", { w: 4000 }),
        hc("측정 방법", { w: 3672 }),
      ),
      ...[
        ["기술 성능", "핵심 위험객체 경고 정확도 85% 이상, 평균 응답지연 0.5초 이하", "테스트 영상·현장 코스 기준 라벨링 검증"],
        ["사용자 경험", "음성 경고 이해도 80점 이상, 경고 피로도 20% 감소", "실증 후 설문 및 인터뷰"],
        ["실증 확산", "복지기관 3곳 이상 협의, 파일럿 사용자 20~100명 단계 확대", "협력기관 미팅록, 참여자 수"],
        ["공공데이터 활용", "데이터셋 3종 이상 실제 기능/운영에 반영", "API 매핑표, 기관·시설·서비스 안내 로그"],
        ["사업화", "기관 PoC 제안 2건 이상, 후속지원사업 1건 이상 신청", "제안서, 신청서, 미팅 결과"],
      ].map(([cat, goal, measure]) =>
        row(
          cell(cat, { bg: C.light, bold: true, w: 1400, align: AlignmentType.CENTER }),
          cell(goal, { w: 4000, bold: true }),
          cell(measure, { w: 3672, color: C.dark }),
        )
      ),
    ], { w: 9072, cols: [1400, 4000, 3672] }),
    pb(),
  ];
}

// ─── 섹션 6. 파급효과 ────────────────────────────────────────
function section6() {
  return [
    sectionTitle("6", "아이디어 상용화에 따른 파급효과 (기대효과, ESG 경영 실현 가능성)"),

    subTitle("파급효과 한눈에 보기 (인포그래픽)"),
    new Paragraph({
      spacing: { before: 60, after: 80 },
      children: [svgImage(svgKpiRow({
        stats: [
          { value: "40%↓",    label: "보행 돌발\n사고율 경감 목표",     color: "#C0392B" },
          { value: "30%↑",    label: "자립 보행\n비율 향상",            color: "#27AE60" },
          { value: "수천억",  label: "물리 인프라\n절감 (재설치 대비)", color: "#7D3C98" },
          { value: "UN SDGs", label: "포용적 도시\nESG 기여",           color: "#2E75B6" },
        ],
        width: 680, height: 130,
      }), 572, 109)],
    }),

    sp(120),
    subTitle("ESG 경영 실현 다이어그램"),
    tbl([
      row(
        cell([
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 60, after: 20 }, children: [
            new TextRun({ text: "E  환경(Environment)", bold: true, size: 22, color: C.white, font: "Malgun Gothic" }),
          ]}),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 60 }, children: [
            new TextRun({ text: "온디바이스 처리로\n서버 전력 소비 최소화\n(Green AI)", size: 17, color: "EEEEEE", font: "Malgun Gothic" }),
          ]}),
        ], { bg: "2ECC71", bdr: bAll("1A7A40"), w: 2924 }),
        cell([
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 60, after: 20 }, children: [
            new TextRun({ text: "S  사회(Social)", bold: true, size: 22, color: C.white, font: "Malgun Gothic" }),
          ]}),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 60 }, children: [
            new TextRun({ text: "시각장애인 이동권 보장\nUN SDGs 포용적 도시\n디지털 소외계층 지원", size: 17, color: "EEEEEE", font: "Malgun Gothic" }),
          ]}),
        ], { bg: "3498DB", bdr: bAll("1A5A9A"), w: 3124 }),
        cell([
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 60, after: 20 }, children: [
            new TextRun({ text: "G  거버넌스(Governance)", bold: true, size: 22, color: C.white, font: "Malgun Gothic" }),
          ]}),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 60 }, children: [
            new TextRun({ text: "영상 원본 미저장\n개인정보보호법 완전 준수\n비식별 데이터만 활용", size: 17, color: "EEEEEE", font: "Malgun Gothic" }),
          ]}),
        ], { bg: "8E44AD", bdr: bAll("5B2780"), w: 3024 }),
      ),
    ], { w: 9072, cols: [2924, 3124, 3024] }),

    sp(140),
    subTitle("상용화 기대효과 상세"),
    tbl([
      row(
        hc("영역", { w: 1600, bg: C.primary }),
        hc("기대효과", { w: 5000 }),
        hc("정량 목표", { w: 2472 }),
      ),
      row(
        cell("보행 안전성\n향상", { bg: C.green, bold: true, w: 1600, align: AlignmentType.CENTER }),
        cell("82종 장애물 실시간 감지로 충돌 전 사전 인지 — 흰지팡이 사각지대 완전 보완", { w: 5000 }),
        cell("보행 돌발 사고율 40% 이상 경감", { w: 2472, bold: true, color: C.safe }),
      ),
      row(
        cell("독립 보행\n실현", { bg: C.blue, bold: true, w: 1600, align: AlignmentType.CENTER }),
        cell("완전 핸즈프리 + 오프라인 동작으로 보조 인력 동행 없이 단독 보행 가능 경우 확대", { w: 5000 }),
        cell("자립 보행 비율 30% 이상 향상", { w: 2472, bold: true, color: C.safe }),
      ),
      row(
        cell("인프라 비용\n절감", { bg: C.orange, bold: true, w: 1600, align: AlignmentType.CENTER }),
        cell("물리적 점자블록·음향신호기 전면 재설치 비용 대비 모바일 앱으로 즉각적·전국적 보완 솔루션 제공", { w: 5000 }),
        cell("수천억 규모 인프라 보완 효과", { w: 2472, bold: true, color: C.safe }),
      ),
      row(
        cell("Edge AI\n모범 사례", { bg: C.purple, bold: true, w: 1600, align: AlignmentType.CENTER }),
        cell("고성능 클라우드 서버 의존 없이 사회 복지 분야에서 경량 엣지 컴퓨팅 실용 사례를 정립", { w: 5000 }),
        cell("온디바이스 AI 복지 모델 선도", { w: 2472, bold: true }),
      ),
      row(
        cell("보행 데이터\n정책 환류", { bg: C.light, bold: true, w: 1600, align: AlignmentType.CENTER }),
        cell("익명 집계 보행 위험 로그를 지자체에 제공 → 도보 인프라 개선 근거 및 정책 자료화", { w: 5000 }),
        cell("연 2건 이상 지자체 정책 제안", { w: 2472, bold: true }),
      ),
    ], { w: 9072, cols: [1600, 5000, 2472] }),

    sp(140),
    subTitle("리스크 대응 표"),
    tbl([
      row(
        hc("리스크", { w: 1800 }),
        hc("영향", { w: 3000 }),
        hc("대응 방안", { w: 4272 }),
      ),
      ...[
        ["오탐·미탐", "불필요한 경고 또는 위험 미인지로 사용자 신뢰 저하", "핵심 객체군부터 제한 운영, 3프레임 안정화, 위험도 임계값 튜닝, 사용자 피드백 기반 보정"],
        ["배터리·발열", "장시간 보행 시 사용성 저하", "FPS 동적 조절, 화면 꺼짐 백그라운드 안내, 저전력 모드"],
        ["음성 마스킹", "경고음이 차량 경적·사이렌 등 외부 소리를 가릴 위험", "골전도 이어폰 가이드, 안내 길이 최소화, 주변 소음 기준 볼륨 조절"],
        ["개인정보", "카메라 영상에 타인 얼굴·차량 번호가 포함될 수 있음", "영상 원본 미저장, 온디바이스 처리, 비식별 최소 로그, 명확한 동의서"],
        ["과신 위험", "앱이 모든 위험을 감지한다고 오해할 가능성", "\"보행 보조 도구\" 고지, 흰지팡이 병행 사용, 위험 상황별 주의 문구"],
        ["공공데이터 최신성", "기관 정보·복지서비스 정보 오류 가능성", "정기 동기화, 공식 링크 연결, 중요 정보는 전화/홈페이지 재확인 안내"],
      ].map(([risk, impact, response]) =>
        row(
          cell(risk, { bg: "FFEAEA", bold: true, w: 1800, align: AlignmentType.CENTER }),
          cell(impact, { w: 3000, color: C.danger }),
          cell(response, { w: 4272 }),
        )
      ),
    ], { w: 9072, cols: [1800, 3000, 4272] }),

    sp(140),
    subTitle("ESG 경영 실현 방안"),
    tbl([
      row(
        hc("ESG 항목", { w: 1600, bg: C.primary }),
        hc("실현 방안", { w: 7472 }),
      ),
      row(
        cell("S\nSocial", { bg: C.green, bold: true, w: 1600, align: AlignmentType.CENTER }),
        cell("디지털 소외계층이자 교통약자인 시각장애인의 정보 및 이동 접근성을 극대화하여 UN 지속가능발전목표(SDGs) '모두를 위한 포용적이고 안전한 도시 구축'에 기여합니다.", { w: 7472 }),
      ),
      row(
        cell("G\nGovernance", { bg: C.blue, bold: true, w: 1600, align: AlignmentType.CENTER }),
        cell("시각장애인이 이동하는 모든 영상 데이터는 중앙 서버에 수집되지 않고 온디바이스에서 즉시 소멸되므로, 타인의 얼굴이나 차량 번호판 불법 수집 관련 개인정보보호법 리스크를 원천 차단합니다.", { w: 7472 }),
      ),
    ], { w: 9072, cols: [1600, 7472] }),

    sp(140),
    subTitle("윤리·법적 체크리스트"),
    tbl([
      row(
        hc("항목", { w: 1600 }),
        hc("체크 내용", { w: 5000 }),
        hc("현재 상태", { w: 2472 }),
      ),
      ...[
        ["동의", "실증 참여자에게 수집 항목, 보관기간, 철회 방법을 안내했는가", "서식 준비 중"],
        ["최소수집", "영상·음성 원본 없이도 검증 가능한 통계만 저장하는가", "완료 ✔ (탐지 JSON만 저장)"],
        ["안전고지", "앱이 흰지팡이와 보행훈련을 대체하지 않음을 명시했는가", "앱 내 고지 문구 포함"],
        ["접근성", "화면을 보지 않아도 앱 시작·중지·도움 요청이 가능한가", "완료 ✔ (핸즈프리 완전 지원)"],
        ["오류 대응", "오탐/미탐 신고와 모델 개선 루프가 준비되어 있는가", "피드백 채널 설계 중"],
      ].map(([item, check, status]) =>
        row(
          cell(item, { bg: C.light, bold: true, w: 1600, align: AlignmentType.CENTER }),
          cell(check, { w: 5000 }),
          cell(status, { w: 2472, bold: true, color: status.includes("✔") ? C.safe : C.warning, align: AlignmentType.CENTER }),
        )
      ),
    ], { w: 9072, cols: [1600, 5000, 2472] }),

    sp(160),
    subTitle("VoiceGuide 도입 전후 보행 환경 변화"),
    new Paragraph({
      spacing: { before: 60, after: 80 },
      children: [svgImage(svgSocialImpact(), 572, 235)],
    }),
    pb(),
  ];
}

// ─── 섹션 7. 공공데이터 ──────────────────────────────────────
function section7() {
  return [
    sectionTitle("7", "출품작에 활용한 공공데이터 및 국가중점데이터 적용 계획 세부 내용"),

    p("VoiceGuide는 공공데이터를 단순한 시장 조사 목적에 그치지 않고 서비스의 실행, 실증, 보급 확장 단계에 입체적으로 활용합니다. 특히 서울시 동작구를 중심으로 횡단보도 접근성 점수화 시나리오를 구현하여, 최단 경로가 아닌 '시각장애인 안전 최적 경로'를 추천하는 데모를 완성하였습니다.", { sz: 18, color: C.dark }),

    sp(120),
    subTitle("공공데이터 활용 흐름도"),
    new Paragraph({
      spacing: { before: 60, after: 80 },
      children: [svgImage(svgDataPipeline(), 589, 168)],
    }),

    sp(140),
    subTitle("활용 공공데이터 목록"),
    tbl([
      row(
        hc("데이터셋명", { w: 2800 }),
        hc("제공 기관", { w: 2000 }),
        hc("구체적 연계 방식 및 서비스 기여점", { w: 4272 }),
      ),
      ...[
        ["횡단보도 위치 데이터", "서울 열린데이터 광장", "동작구 횡단보도 후보 지도 포인트 및 경로 비교 기준점 — 보라매역 데모 시나리오 구성"],
        ["보행등·교통신호 정보", "서울 열린데이터 광장", "횡단 가능 신호 안내 근거, 접근성 점수 가중치 (보행등 유무 +1점)"],
        ["음향신호기 정보", "한국사회보장정보원", "시각장애인 필수 시설 여부 점수화 (음향신호기 유무 +1점)"],
        ["보행자작동신호기 정보", "보건복지부", "사용자 직접 신호 요청 가능 여부 점수화 (+1점)"],
        ["고원식 횡단보도 정보", "국토교통부", "차량 감속·보행자 보호 가능성 보조 점수 (+1점)"],
        ["교통안전시설 상세정보", "서울시", "횡단보도별 설명 가능 안전 근거 텍스트"],
        ["보행자 사고다발구역", "경찰청", "대시보드 지도 주의 구역 레이어 표시"],
        ["장애인 복지시설 정보", "한국사회보장정보원", "데모 목적지(서울시남부장애인종합복지관) 및 접근성 시나리오 구성"],
        ["사회서비스 제공기관 정보 검색", "한국사회보장정보원", "실증 복지관 매핑 및 파일럿 기관 섭외"],
        ["중앙부처복지서비스", "한국사회보장정보원", "정보통신보조기기 보급사업 정책 단가 및 BM 프레임 설계"],
        ["등록장애인 수", "보건복지부", "지역별 잠재 고객 규모 도출 및 마케팅 전략 수립"],
      ].map(([name, src, usage]) =>
        row(
          cell(name, { w: 2800, bold: true }),
          cell(src, { w: 2000, align: AlignmentType.CENTER, color: C.dark }),
          cell(usage, { w: 4272, sz: 17 }),
        )
      ),
    ], { w: 9072, cols: [2800, 2000, 4272] }),

    sp(140),
    subTitle("데이터 처리 파이프라인"),
    tbl([
      row(
        hc("단계", { w: 600 }),
        hc("처리 내용", { w: 3400 }),
        hc("산출물", { w: 5072 }),
      ),
      ...[
        ["①", "원본 공공데이터 수집 및 분류", "목적지 / 횡단보도 / 보행지원시설 / 이동지원센터 분리"],
        ["②", "좌표 정규화 및 위경도 변환", "WGS84 좌표계 통일, 횡단보도 주변 30m 반경 시설 매칭"],
        ["③", "접근성 점수화 (0~5점)", "보행등·음향신호기·작동신호기·고원식·상세정보 각 1점씩 가산"],
        ["④", "등급 분류", "preferred(5점) / recommended(3-4점) / basic(1-2점) / insufficient(0점)"],
        ["⑤", "대시보드용 파일 산출", "CSV / GeoJSON / JSON / HTML — build_voiceguide_final_dataset.py"],
      ].map(([step, proc, output]) =>
        row(
          cell(step, { bg: C.lightest, bold: true, w: 600, align: AlignmentType.CENTER }),
          cell(proc, { w: 3400, bold: true }),
          cell(output, { w: 5072, color: C.dark }),
        )
      ),
    ], { w: 9072, cols: [600, 3400, 5072] }),

    sp(140),
    subTitle("대표 데모 시나리오: 보라매역 → 서울시남부장애인종합복지관"),
    tbl([
      row(
        hc("항목", { w: 2000 }),
        hc("경로 A — 최단 직선", { bg: C.warning, w: 3536 }),
        hc("경로 B — 접근성 우선 ✔ 채택", { bg: C.safe, w: 3536 }),
      ),
      ...[
        ["횡단보도 ID", "06-0000016344", "06-0000032157"],
        ["접근성 점수", "1점 (basic)", "4점 (recommended)"],
        ["음향신호기", "없음 ✗", "있음 ✔"],
        ["보행자작동신호기", "없음 ✗", "있음 ✔"],
        ["고원식 횡단보도", "없음 ✗", "있음 ✔"],
        ["보행등", "있음 ✔", "있음 ✔"],
      ].map(([item, a, b]) =>
        row(
          cell(item, { bg: C.light, bold: true, w: 2000 }),
          cell(a, { w: 3536, align: AlignmentType.CENTER, color: a.includes("✗") ? C.danger : C.dark }),
          cell(b, { w: 3536, align: AlignmentType.CENTER, bold: true, color: b.includes("✔") ? C.safe : C.dark }),
        )
      ),
      row(
        cell("선택 이유", { bg: C.light, bold: true, w: 2000 }),
        cell("최단 거리지만 시각장애인 필수 시설(음향신호기·작동신호기·고원식) 미비", { w: 3536, color: C.warning }),
        cell("거리 약간 길지만 보행 안전시설 3종 완비 → 시각장애인 안전 최적 경로로 선택", { w: 3536, bold: true, color: C.safe }),
      ),
    ], { w: 9072, cols: [2000, 3536, 3536] }),

    sp(140),
    subTitle("데이터 연계 흐름"),
    tbl([
      row(
        hc("단계", { w: 1200, bg: C.secondary }),
        hc("데이터 활용", { w: 3400 }),
        hc("산출물", { w: 4472 }),
      ),
      ...[
        ["1. 실증 전", "사회서비스 제공기관/편의시설 데이터로 실증기관과 테스트 코스 후보 선정", "실증 지도, 기관 후보 리스트"],
        ["2. 실증 중", "앱 감지 로그와 공공데이터 위치정보를 대조", "위험구간별 객체 유형 통계"],
        ["3. 실증 후", "복지서비스 데이터와 사용자 니즈를 연결", "복지서비스 안내 시나리오, 정책 제안서"],
        ["4. 확산", "지역별 등록장애인 수 기반 단계별 마케팅 전략 수립", "지역별 타겟 고객 분석 리포트"],
      ].map(([stage, usage, output]) =>
        row(
          cell(stage, { bg: C.lightest, bold: true, w: 1200, align: AlignmentType.CENTER }),
          cell(usage, { w: 3400 }),
          cell(output, { w: 4472, color: C.dark }),
        )
      ),
    ], { w: 9072, cols: [1200, 3400, 4472] }),

    sp(140),
    subTitle("데이터 필드 설계 및 개인정보 최소화"),
    tbl([
      row(
        hc("구분", { w: 1800, bg: C.primary }),
        hc("저장/활용 필드", { w: 3800 }),
        hc("개인정보 최소화 방식", { w: 3472 }),
      ),
      row(
        cell("공공데이터", { bg: C.blue, bold: true, w: 1800, align: AlignmentType.CENTER }),
        cell("기관명, 주소, 시설유형, 복지서비스명, 신청방법", { w: 3800 }),
        cell("공개 데이터만 사용 — 개인정보 미포함", { w: 3472, color: C.safe, bold: true }),
      ),
      row(
        cell("앱 위험로그", { bg: C.orange, bold: true, w: 1800, align: AlignmentType.CENTER }),
        cell("객체유형, 위험도, 시간대, 격자화 위치, 앱 버전", { w: 3800 }),
        cell("영상·음성 원본 저장 금지 — 탐지 JSON만 저장", { w: 3472, color: C.safe, bold: true }),
      ),
      row(
        cell("실증 설문", { bg: C.purple, bold: true, w: 1800, align: AlignmentType.CENTER }),
        cell("만족도, 경고 이해도, 피로도, 개선의견", { w: 3800 }),
        cell("이름 대신 참여자 코드 사용", { w: 3472, color: C.safe, bold: true }),
      ),
      row(
        cell("기관 리포트", { bg: C.gray, bold: true, w: 1800, align: AlignmentType.CENTER }),
        cell("위험구간 유형, 반복 감지 객체, 개선 제안", { w: 3800 }),
        cell("개별 사용자 이동경로 노출 방지", { w: 3472, color: C.safe, bold: true }),
      ),
    ], { w: 9072, cols: [1800, 3800, 3472] }),

    sp(140),
    subTitle("한국사회보장정보원 관점 강조"),
    tbl([
      row(
        hc("한국사회보장정보원 관점", { w: 3200, bg: C.secondary }),
        hc("VoiceGuide 반영 내용", { w: 5872 }),
      ),
      ...[
        ["공공데이터 활용 강화", "OpenAPI를 단순 조회가 아니라 실증기관 선정, 편의시설 취약구간 분석, 복지서비스 안내에 사용"],
        ["복지 사각지대 해소", "이동이 어려워 복지기관·서비스 접근이 제한되는 시각장애인의 첫 관문을 보행안전으로 지원"],
        ["AI 기술의 실서비스화", "온디바이스 AI로 보행 중 즉시 반응하는 피지컬 AI 성격의 안전 서비스를 구현"],
        ["데이터 환류 가능성", "영상이 아닌 비식별 위험 로그를 활용해 지역별 보행위험 히트맵과 시설 개선 우선순위 도출"],
        ["기관 협업 가능성", "복지관·자립생활센터·지자체와 파일럿을 수행해 실제 사용자 기반 검증 가능"],
        ["복지로 연계성", "복지로 위치정보 서비스와 달리 '시설 탐색 후 실제 이동 중 위험'을 보완하는 서비스로 포지셔닝"],
      ].map(([view, content]) =>
        row(
          cell(view, { bg: C.lightest, bold: true, w: 3200 }),
          cell(content, { w: 5872 }),
        )
      ),
    ], { w: 9072, cols: [3200, 5872] }),
    sp(80),
    tbl([
      row(
        cell([
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 100, after: 60 }, children: [
            new TextRun({ text: "VoiceGuide는 사회보장정보가 '어디에 무엇이 있는지'를 알려주는 것을 넘어,", size: 19, color: C.primary, font: "Malgun Gothic", bold: true }),
          ]}),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 100 }, children: [
            new TextRun({ text: "사용자가 그 서비스에 실제로 도달하도록 돕는 이동 안전 서비스를 제안합니다.", size: 19, color: C.dark, font: "Malgun Gothic", bold: true }),
          ]}),
        ], { bg: C.blue, bdr: bAll(C.secondary) }),
      ),
    ], { w: 9072, cols: [9072] }),

    sp(200),
    tbl([
      row(
        cell([
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120, after: 60 }, children: [
            new TextRun({ text: "VoiceGuide", bold: true, size: 48, color: C.primary, font: "Malgun Gothic" }),
          ]}),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 60 }, children: [
            new TextRun({ text: "스마트폰 하나로, 시각장애인의 안전한 독립 보행을 실현합니다.", size: 22, color: C.dark, font: "Malgun Gothic" }),
          ]}),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 40, after: 60 }, children: [
            new TextRun({ text: "온디바이스 AI  ·  한국어 특화  ·  공공데이터 연동  ·  완전 핸즈프리", bold: true, size: 20, color: C.secondary, font: "Malgun Gothic" }),
          ]}),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 40, after: 120 }, children: [
            new TextRun({ text: "https://voiceguide-1063164560758.asia-northeast3.run.app", size: 17, color: C.midgray, font: "Malgun Gothic", italics: true }),
          ]}),
        ], { bg: C.lightest, bdr: bAll(C.secondary), span: 1 }),
      ),
    ], { w: 9072, cols: [9072] }),
  ];
}

// ─── 부록. 데이터 기반 실증·사업성 보강 ───────────────────────
function appendixSection() {
  return [
    pb(),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 0, after: 160 },
      children: [new TextRun({ text: "【 부록 】 데이터 기반 실증·사업성 보강", bold: true, size: 28, color: C.primary, font: "Malgun Gothic" })],
      border: {
        top: { style: BorderStyle.SINGLE, size: 6, color: C.primary },
        bottom: { style: BorderStyle.SINGLE, size: 2, color: C.primary },
      },
    }),
    p("final_* 데이터셋을 바탕으로 공공데이터 활용성, 실증 코스 설계, 안전 경로 추천 근거를 시각화했습니다.", { sz: 18, color: C.dark }),
    sp(80),

    // 핵심 통계 요약 박스
    tbl([
      row(
        cell([
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 100, after: 40 }, children: [new TextRun({ text: "1,025건", bold: true, size: 52, color: C.primary, font: "Malgun Gothic" })] }),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 100 }, children: [new TextRun({ text: "횡단보도 분석 (동작구)", size: 18, color: C.dark, font: "Malgun Gothic" })] }),
        ], { bg: C.blue, bdr: bAll(C.secondary), w: 2268 }),
        cell([
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 100, after: 40 }, children: [new TextRun({ text: "368건 (35.9%)", bold: true, size: 52, color: C.safe, font: "Malgun Gothic" })] }),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 100 }, children: [new TextRun({ text: "우선/권장 횡단보도 후보", size: 18, color: C.dark, font: "Malgun Gothic" })] }),
        ], { bg: C.green, bdr: bAll("27AE60"), w: 2268 }),
        cell([
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 100, after: 40 }, children: [new TextRun({ text: "4개", bold: true, size: 52, color: C.accent, font: "Malgun Gothic" })] }),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 100 }, children: [new TextRun({ text: "복지 목적지", size: 18, color: C.dark, font: "Malgun Gothic" })] }),
        ], { bg: C.orange, bdr: bAll("E67E22"), w: 2268 }),
        cell([
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 100, after: 40 }, children: [new TextRun({ text: "+8m 안전", bold: true, size: 52, color: C.safe, font: "Malgun Gothic" })] }),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 100 }, children: [new TextRun({ text: "경로 안전 근거 확보", size: 18, color: C.dark, font: "Malgun Gothic" })] }),
        ], { bg: C.green, bdr: bAll("27AE60"), w: 2268 }),
      ),
    ], { w: 9072, cols: [2268, 2268, 2268, 2268] }),

    sp(120),
    subTitle("경로 A/B 안전성 비교 시각화"),
    tbl([
      row(
        cell([
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 60, after: 20 }, children: [
            new TextRun({ text: "경로 A  (최단 거리)", bold: true, size: 24, color: C.white, font: "Malgun Gothic" }),
          ]}),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 60 }, children: [
            new TextRun({ text: "817m", bold: true, size: 40, color: "FFFFFF", font: "Malgun Gothic" }),
          ]}),
        ], { bg: C.danger, bdr: bAll("8B0000"), w: 3000 }),
        cell([
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 60, after: 20 }, children: [
            new TextRun({ text: "VS", bold: true, size: 32, color: C.primary, font: "Malgun Gothic" }),
          ]}),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 60 }, children: [
            new TextRun({ text: "+8m", bold: true, size: 22, color: C.dark, font: "Malgun Gothic" }),
          ]}),
        ], { bg: C.gray, bdr: bNone(), w: 1072 }),
        cell([
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 60, after: 20 }, children: [
            new TextRun({ text: "경로 B  ★ 채택 (안전 우선)", bold: true, size: 24, color: C.white, font: "Malgun Gothic" }),
          ]}),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 60 }, children: [
            new TextRun({ text: "825m", bold: true, size: 40, color: "FFFFFF", font: "Malgun Gothic" }),
          ]}),
        ], { bg: C.safe, bdr: bAll("1A7A40"), w: 3000 }),
      ),
      row(
        cell([
          iconRow("✗", "음향신호기 없음", C.danger),
          iconRow("✗", "보행자작동신호기 없음", C.danger),
          iconRow("✗", "고원식 횡단보도 없음", C.danger),
          iconRow("✓", "보행등 있음", C.safe),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 40, after: 40 }, children: [
            new TextRun({ text: "접근성 점수: 1점 (basic)", bold: true, size: 18, color: C.danger, font: "Malgun Gothic" }),
          ]}),
        ], { w: 3000, bg: "FFF0F0" }),
        cell("", { w: 1072, bdr: bNone() }),
        cell([
          iconRow("✓", "음향신호기 있음", C.safe),
          iconRow("✓", "보행자작동신호기 있음", C.safe),
          iconRow("✓", "고원식 횡단보도 있음", C.safe),
          iconRow("✓", "보행등 있음", C.safe),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 40, after: 40 }, children: [
            new TextRun({ text: "접근성 점수: 4점 (recommended)", bold: true, size: 18, color: C.safe, font: "Malgun Gothic" }),
          ]}),
        ], { w: 3000, bg: C.green }),
      ),
    ], { w: 9072, cols: [3000, 1072, 3000] }),

    sp(120),
    subTitle("성능 목표 KPI 차트"),
    new Paragraph({
      spacing: { before: 60, after: 80 },
      children: [svgImage(svgVerticalBar({
        title: "VoiceGuide 핵심 성능 목표 KPI",
        bars: [
          { label: "탐지 정확도\n목표 85%+",   value: 85, color: "#27AE60" },
          { label: "사고율 감소\n목표 40%+",   value: 40, color: "#C0392B" },
          { label: "보행 자립\n향상 30%+",     value: 30, color: "#2E75B6" },
          { label: "경고 이해도\n80점 이상",   value: 80, color: "#E67E22" },
          { label: "피로도 감소\n20%+",        value: 20, color: "#7D3C98" },
        ],
        width: 500, height: 280, yMax: 100,
      }), 420, 235)],
    }),

    sp(160),
    subTitle("표 1. 데이터 활용 구조와 사업계획서 반영 포인트"),
    tbl([
      row(
        hc("활용 데이터", { w: 2200, bg: C.primary }),
        hc("반영 내용", { w: 3472 }),
        hc("서비스/사업 효과", { w: 3400 }),
      ),
      ...[
        ["복지시설 정보", "동작구 장애인복지관 후보 추출", "실증기관 발굴·복지관 방문 시나리오 구성"],
        ["횡단보도 접근성", "보행등·음향신호기·작동신호기·고원식 여부 점수화", "최단거리보다 설명 가능한 안전 경로 추천"],
        ["경로 A/B 비교", "817m 최단 후보와 825m 안전 경로 비교", "\"왜 8m를 더 이동하는지\" 사용자에게 설명"],
        ["TTS 안내 문구", "경로 선택·횡단보도 접근·실시간 감지 안내 분리", "화면 조작 없이 짧고 행동 가능한 음성 UX 제공"],
      ].map(([data, content, effect]) =>
        row(
          cell(data, { bg: C.lightest, bold: true, w: 2200 }),
          cell(content, { w: 3472 }),
          cell(effect, { w: 3400, color: C.primary }),
        )
      ),
    ], { w: 9072, cols: [2200, 3472, 3400] }),

    sp(140),
    subTitle("표 2. 사용자 음성 안내(TTS) 및 진동 패턴 예시"),
    tbl([
      row(
        hc("순서", { w: 600, bg: C.primary }),
        hc("상황", { w: 1800, bg: C.secondary }),
        hc("안내 문구 (TTS)", { w: 4600 }),
        hc("진동", { w: 2072 }),
      ),
      row(
        cell("1", { bg: C.lightest, bold: true, w: 600, align: AlignmentType.CENTER }),
        cell("경로 선택", { w: 1800, bold: true }),
        cell("\"최단 후보보다 약 8미터 더 이동하지만, 보행등과 음향신호기, 보행자작동신호기 정보가 있는 횡단보도로 안내합니다.\"", { w: 4600, color: C.primary, bold: true }),
        cell("짧은 진동 (SHORT)", { w: 2072, align: AlignmentType.CENTER, color: C.dark }),
      ),
      row(
        cell("2", { bg: C.lightest, bold: true, w: 600, align: AlignmentType.CENTER }),
        cell("횡단보도 접근", { w: 1800, bold: true }),
        cell("\"전방에 보행지원시설 정보가 있는 횡단보도가 있습니다. 신호 안내를 확인하며 건너세요.\"", { w: 4600, color: C.primary, bold: true }),
        cell("중간 진동 (DOUBLE)", { w: 2072, align: AlignmentType.CENTER, color: C.warning }),
      ),
      row(
        cell("3", { bg: "FFEAEA", bold: true, w: 600, align: AlignmentType.CENTER }),
        cell("실시간 장애물\n감지", { w: 1800, bold: true }),
        cell("\"이동 중 전방 장애물은 카메라로 계속 확인합니다.\" (+ 실시간 객체 감지 즉시 안내)", { w: 4600, color: C.danger, bold: true }),
        cell("URGENT (4단계)", { w: 2072, align: AlignmentType.CENTER, bold: true, color: C.white, bg: C.danger }),
      ),
    ], { w: 9072, cols: [600, 1800, 4600, 2072] }),

    sp(140),
    subTitle("표 3. 사업화·실증 보강 포인트"),
    tbl([
      row(
        hc("구분", { w: 1600, bg: C.primary }),
        hc("보강 내용", { w: 4400 }),
        hc("사업계획서 활용", { w: 3072 }),
      ),
      ...[
        ["실증 설득력", "보라매역 → 서울시남부장애인종합복지관 실제 방문 흐름", "복지관 PoC 제안서·데모 영상에 바로 활용"],
        ["심사 대응", "공공데이터를 단순 조회가 아니라 안전 경로 판단 근거로 전환", "공공데이터 활용 적정성 및 AI 서비스성 강화"],
        ["개인정보 보호", "영상은 온디바이스 처리, 서버에는 비식별 위험 이벤트만 축적", "개인정보보호법 리스크 및 운영 부담 최소화"],
        ["보완 계획", "지도 경로 API·현장 좌표 검증·사용자 피드백 로그 결합", "대표 직선거리 데모값을 실제 보행 네트워크로 고도화"],
      ].map(([cat, content, usage]) =>
        row(
          cell(cat, { bg: C.lightest, bold: true, w: 1600, align: AlignmentType.CENTER }),
          cell(content, { w: 4400 }),
          cell(usage, { w: 3072, color: C.primary }),
        )
      ),
    ], { w: 9072, cols: [1600, 4400, 3072] }),

    sp(80),
    tbl([
      row(
        cell([
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 80, after: 40 }, children: [
            new TextRun({ text: "자료 기준: final_scenario_dataset.json(2026-05-24T17:38:31), final_crosswalk_accessibility.csv,", size: 15, color: C.midgray, font: "Malgun Gothic", italics: true }),
          ]}),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 80 }, children: [
            new TextRun({ text: "final_route_comparison.csv, final_tts_guidance.csv", size: 15, color: C.midgray, font: "Malgun Gothic", italics: true }),
          ]}),
        ], { bg: C.gray, bdr: bNone() }),
      ),
    ], { w: 9072, cols: [9072] }),
  ];
}

// ─── 문서 조립 ────────────────────────────────────────────────
async function buildDoc() {
  const children = [
    ...coverPage(),
    ...planSummary(),
    ...section1(),
    ...section2(),
    ...section3(),
    ...section4(),
    ...section5(),
    ...section6(),
    ...section7(),
    ...appendixSection(),
  ];

  const doc = new Document({
    styles: {
      default: { document: { run: { font: "Malgun Gothic", size: 19, color: C.black } } },
    },
    sections: [{
      properties: {
        page: {
          size: { width: 11906, height: 16838 },
          margin: { top: 1000, right: 1000, bottom: 1000, left: 1000 },
        },
      },
      headers: {
        default: new Header({ children: [new Paragraph({
          alignment: AlignmentType.RIGHT,
          border: { bottom: { style: BorderStyle.SINGLE, size: 2, color: C.secondary, space: 3 } },
          spacing: { before: 0, after: 100 },
          children: [new TextRun({ text: "VoiceGuide 사업계획서  |  AI Human 4기 3팀  |  2026 국민행복 서비스 발굴·창업경진대회", size: 15, color: C.midgray, font: "Malgun Gothic" })],
        })] }),
      },
      footers: {
        default: new Footer({ children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          border: { top: { style: BorderStyle.SINGLE, size: 2, color: C.midgray, space: 3 } },
          children: [
            new TextRun({ text: "- ", size: 15, color: C.midgray, font: "Malgun Gothic" }),
            new TextRun({ children: [PageNumber.CURRENT], size: 15, color: C.midgray, font: "Malgun Gothic" }),
            new TextRun({ text: " -", size: 15, color: C.midgray, font: "Malgun Gothic" }),
          ],
        })] }),
      },
      children,
    }],
  });

  const buf = await Packer.toBuffer(doc);
  const out = "C:\\Users\\ghksw\\Downloads\\VoiceGuide_사업계획서_최종_업그레이드.docx";
  fs.writeFileSync(out, buf);
  console.log("완료:", out);
}

buildDoc().catch(e => { console.error(e); process.exit(1); });
