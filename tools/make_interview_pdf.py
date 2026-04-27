"""
시각장애인 인터뷰 질문지 PDF 생성 스크립트
실행: python tools/make_interview_pdf.py
출력: docs/interview_questions.pdf
"""

from fpdf import FPDF, XPos, YPos
import os

FONT_PATH = r"C:\Windows\Fonts\malgun.ttf"
FONT_BOLD = r"C:\Windows\Fonts\malgunbd.ttf"
OUTPUT    = os.path.join(os.path.dirname(__file__), "..", "docs", "interview_questions.pdf")


class PDF(FPDF):
    def header(self):
        self.set_font("KR", "B", 11)
        self.set_fill_color(235, 240, 250)
        self.cell(0, 10, "VoiceGuide 사용자 인터뷰 질문지",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C", fill=True)
        self.set_font("KR", "", 9)
        self.set_text_color(100, 100, 100)
        self.cell(0, 6, "KDT AI Human 3팀  |  2026-04-27  |  비공개 내부 자료",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
        self.set_text_color(0, 0, 0)
        self.ln(4)

    def footer(self):
        self.set_y(-12)
        self.set_font("KR", "", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 8, f"- {self.page_no()} -", align="C")
        self.set_text_color(0, 0, 0)


def section(pdf, title, r=30, g=80, b=160):
    pdf.set_font("KR", "B", 11)
    pdf.set_fill_color(r, g, b)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 9, f"  {title}",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)


def intro(pdf, text):
    pdf.set_font("KR", "", 9)
    pdf.set_text_color(70, 70, 70)
    pdf.set_fill_color(248, 248, 248)
    pdf.multi_cell(0, 6, text, fill=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)


def question(pdf, num, q, note=None):
    pdf.set_font("KR", "B", 10)
    pdf.set_text_color(30, 80, 160)
    pdf.multi_cell(0, 7, f"Q{num}. {q[:1]}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("KR", "", 10)
    # 첫 글자는 번호 셀에서 썼으니 나머지만 이어씀
    # → 사실 아래처럼 전부 한 multi_cell로 쓰는 게 더 안전
    # 번호 + 질문을 한 줄로 합쳐서 bold 처리
    pdf.set_y(pdf.get_y() - 7)  # 위로 올려서 덮어쓰기
    pdf.set_font("KR", "B", 10)
    pdf.set_text_color(30, 80, 160)
    pdf.cell(12, 7, f"Q{num}.", new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.set_font("KR", "", 10)
    pdf.set_text_color(0, 0, 0)
    w = pdf.epw - 12  # 남은 너비
    pdf.multi_cell(w, 7, q, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if note:
        pdf.set_x(pdf.l_margin + 4)
        pdf.set_font("KR", "", 8)
        pdf.set_text_color(110, 110, 110)
        pdf.multi_cell(pdf.epw - 4, 5.5, f"* {note}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0, 0, 0)
    pdf.ln(2)


# ── PDF 생성 ────────────────────────────────────────────────────────────────
pdf = PDF()
pdf.add_font("KR",  "", FONT_PATH)
pdf.add_font("KR", "B", FONT_BOLD)
pdf.set_auto_page_break(auto=True, margin=15)
pdf.add_page()
pdf.set_margins(18, 20, 18)

# ── 인사말 ──────────────────────────────────────────────────────────────────
pdf.set_font("KR", "", 10)
pdf.multi_cell(0, 7,
    "안녕하세요. 저희는 시각장애인의 보행을 돕는 AI 앱 VoiceGuide를 개발 중인 팀입니다.\n"
    "귀중한 시간을 내어 주셔서 진심으로 감사드립니다.\n\n"
    "불편하시거나 답하기 어려운 질문은 언제든지 건너뛰셔도 됩니다.\n"
    "정답이 없는 질문들이며, 솔직한 경험과 의견이 저희에게 가장 큰 도움이 됩니다."
)
pdf.ln(5)

# ── 1부: 일상 이동 ───────────────────────────────────────────────────────────
section(pdf, "1부. 일상적인 이동 경험에 대해")
intro(pdf, "평소 혼자 이동하실 때의 경험을 여쭤보겠습니다. 편하게 말씀해 주세요.")

question(pdf, 1,
    "혼자 외출하실 때 가장 자주 이용하시는 이동 수단은 무엇인가요?",
    "도보, 대중교통, 택시 등. 특별히 선호하거나 피하는 수단이 있으신지도 궁금합니다.")

question(pdf, 2,
    "길을 걸으실 때 가장 불안하거나 긴장되는 순간은 언제인가요?",
    "특정 장소나 상황 (횡단보도, 혼잡한 곳, 처음 가는 곳 등)이 있으시면 말씀해 주세요.")

question(pdf, 3,
    "점자 블록(노란 유도 블록)이 도움이 되신다고 느끼시나요? 반대로 불편하신 경험도 있으셨나요?",
    "자전거나 킥보드가 블록 위에 있었던 경우 등, 어떻게 대처하시는지도 궁금합니다.")

question(pdf, 4,
    "버스나 지하철을 이용하실 때 가장 어려운 점은 무엇인가요?",
    "버스 번호 확인, 하차 위치 파악 등 구체적인 상황을 말씀해 주시면 감사하겠습니다.")

question(pdf, 5,
    "키오스크(무인 주문기, ATM 등)를 혼자 사용해 보신 적 있으신가요? 어떠셨나요?",
    "어떤 방법으로 대처하시는지도 여쭤봐도 될까요?")

pdf.ln(3)

# ── 2부: 현재 사용 도구 ──────────────────────────────────────────────────────
section(pdf, "2부. 현재 사용하시는 보조 도구에 대해", r=50, g=130, b=80)
intro(pdf, "지금 사용하고 계신 앱이나 기기에 대해 여쭤보겠습니다.")

question(pdf, 6,
    "현재 스마트폰을 이용하시나요? 주로 어떤 기능을 사용하시나요?",
    "스크린리더, 음성 안내, 특정 앱 등. 폰 사용이 어려우신 부분도 말씀해 주세요.")

question(pdf, 7,
    "보행 중 도움을 받기 위해 사용해 보신 앱이 있으신가요? (예: Be My Eyes, Seeing AI 등)",
    "좋았던 점과 아쉬웠던 점, 사용하지 않으신다면 그 이유도 궁금합니다.")

question(pdf, 8,
    "신호등 앞에서 언제 건너도 되는지 어떻게 확인하시나요?",
    "음향 신호기가 없는 곳에서는 어떻게 하시는지도 여쭤봐도 될까요?")

question(pdf, 9,
    "보행 중 주변 상황(장애물, 차량 등)을 파악하기 위해 주로 어떤 방법을 쓰시나요?",
    "흰 지팡이 사용 방식, 소리로 판단하는 방법 등 평소 습관이 있으시면 말씀해 주세요.")

pdf.ln(3)

# ── 3부: 앱 기능 피드백 ──────────────────────────────────────────────────────
section(pdf, "3부. 저희 앱 기능에 대한 의견", r=140, g=60, b=60)
intro(pdf,
    "저희가 개발 중인 기능들을 간단히 설명드리고 솔직한 의견을 여쭤보겠습니다.\n"
    "어떤 의견이든 매우 소중합니다.")

question(pdf, 10,
    "카메라로 앞을 비추면 '왼쪽 앞에 의자가 있어요. 오른쪽으로 피해가세요.' 처럼 "
    "방향과 행동을 알려주는 기능이 실제로 유용할 것 같으신가요?",
    "1초마다 자동으로 분석하며 음성으로 알려줍니다. 너무 자주 말해서 오히려 불편할 수 있을까요?")

question(pdf, 11,
    "위험한 것(차량, 계단 등)은 음성으로, 덜 중요한 것(멀리 있는 의자 등)은 짧은 "
    "비프음으로만 알려주는 방식은 어떻게 생각하시나요?",
    "경고가 너무 많으면 오히려 혼란스러울 수 있어 이런 방식을 생각했습니다.")

question(pdf, 12,
    "'여기 저장해줘 편의점'이라고 말하면 그 위치를 기억했다가, "
    "나중에 '편의점 찾아줘'라고 하면 안내해 주는 기능은 도움이 될 것 같으신가요?",
    "자주 가시는 장소를 이름으로 저장하는 개인 내비게이션 기능입니다.")

question(pdf, 13,
    "카메라로 신호등을 비추면 '초록불이에요. 건너도 돼요.' 처럼 신호 상태를 알려주는 "
    "기능은 어떻게 생각하시나요?",
    "음향 신호기가 없는 곳에서 도움이 될 수 있을지 의견이 궁금합니다.")

question(pdf, 14,
    "'글자 읽어줘'라고 말하면 카메라 속 텍스트(간판, 메뉴판, 처방전 등)를 읽어주는 "
    "기능은 필요하신가요?",
    "어떤 상황에서 가장 유용할 것 같으신지 말씀해 주시면 도움이 됩니다.")

pdf.ln(3)

# ── 4부: 자유 의견 ───────────────────────────────────────────────────────────
section(pdf, "4부. 자유롭게 말씀해 주세요", r=100, g=60, b=140)
intro(pdf, "형식 없이 편하게 말씀해 주시는 내용이 저희에게 가장 큰 도움이 됩니다.")

question(pdf, 15,
    "보행 중 스마트폰 앱이 도움이 되려면 가장 중요한 것이 무엇이라고 생각하시나요?",
    "속도, 정확도, 말하는 방식, 배터리 등 어떤 것이 가장 우선순위인지 궁금합니다.")

question(pdf, 16,
    "저희 앱에 꼭 들어갔으면 하는 기능이 있으시다면 무엇인가요?",
    "아무리 작은 것이라도 괜찮습니다.")

question(pdf, 17,
    "반대로 이런 앱에 절대 있으면 안 되는 것이 있다면 무엇일까요?",
    "예: '말이 너무 많으면 안 된다', '화면을 봐야 하는 기능이 있으면 안 된다' 등")

question(pdf, 18,
    "마지막으로 저희 같은 개발자들이 시각장애인을 위한 앱을 만들 때 "
    "가장 주의해야 할 점을 한 가지만 말씀해 주신다면 무엇일까요?")

# ── 감사 인사 ────────────────────────────────────────────────────────────────
pdf.ln(5)
pdf.set_font("KR", "", 9)
pdf.set_fill_color(245, 245, 245)
pdf.multi_cell(0, 7,
    "소중한 시간과 경험을 나눠주셔서 진심으로 감사드립니다.\n"
    "말씀해 주신 내용은 저희 앱 개발에 반드시 반영하겠습니다.\n"
    "혹시 추가로 전하고 싶으신 말씀이 있으시면 언제든지 연락 주세요.",
    fill=True
)

output_path = os.path.abspath(OUTPUT)
os.makedirs(os.path.dirname(output_path), exist_ok=True)
pdf.output(output_path)
print(f"PDF 생성 완료: {output_path}")
