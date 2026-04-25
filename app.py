import time
import gradio as gr
import cv2
import numpy as np
from src.depth.depth import detect_and_depth
from src.nlg.sentence import build_sentence
from src.voice.tts import speak
from src.nlg.templates import CLOCK_TO_DIRECTION


def process_image(image, mode: str = "장애물"):
    if image is None:
        return None, "이미지를 업로드해주세요."

    t0 = time.time()
    img_np = np.array(image)
    _, encoded = cv2.imencode(".jpg", img_np)
    image_bytes = encoded.tobytes()

    objects = detect_and_depth(image_bytes)

    # 찾기/확인 모드: 가장 신뢰도 높은 단일 물체 안내
    if mode == "찾기" and objects:
        obj = max(objects, key=lambda o: o["conf"])
        from src.nlg.templates import CLOCK_TO_DIRECTION
        direction_ko = CLOCK_TO_DIRECTION.get(obj["direction"], obj["direction"])
        sentence = f"{obj['class_ko']}이 {direction_ko}에 있어요. 약 {obj['distance_m']}m."
    elif mode == "확인" and objects:
        # 화면 중앙에 가장 가까운 물체
        center_objs = sorted(objects, key=lambda o: abs(
            (o["bbox"][0] + o["bbox"][2]) / 2 / img_np.shape[1] - 0.5))
        obj = center_objs[0]
        sentence = f"카메라 중앙의 물체는 {obj['class_ko']}입니다."
    else:
        sentence = build_sentence(objects, [], camera_orientation="front")

    elapsed_ms = (time.time() - t0) * 1000
    speak(sentence)

    # 바운딩 박스 시각화
    annotated = img_np.copy()
    colors = [(30, 100, 255), (0, 200, 80), (255, 140, 0)]
    for i, obj in enumerate(objects):
        x1, y1, x2, y2 = obj["bbox"]
        color = colors[i % len(colors)]
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
        label = f"{obj['class_ko']}  {obj['distance_m']}m  위험도:{obj['risk_score']}"
        cv2.putText(annotated, label, (x1, max(y1 - 8, 20)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)

    lines = [
        f"[모드]      {mode}",
        f"[음성 안내]  {sentence}",
        f"[추론 시간]  {elapsed_ms:.0f}ms",
        f"[거리 추정]  {'Depth Anything V2' if objects and objects[0].get('depth_source') == 'v2' else 'bbox 면적 기반'}",
        "",
    ]
    if objects:
        lines.append("[탐지 목록]")
        for obj in objects:
            direction_ko = CLOCK_TO_DIRECTION.get(obj["direction"], obj["direction"])
            ground_tag = "  (바닥 장애물)" if obj.get("is_ground_level") else ""
            lines.append(
                f"  - {obj['class_ko']} | {direction_ko}{ground_tag} | "
                f"약 {obj['distance_m']}m | 신뢰도 {obj['conf']} | 위험도 {obj['risk_score']}"
            )
    else:
        lines.append("탐지된 장애물 없음")

    return annotated, "\n".join(lines)


demo = gr.Interface(
    fn=process_image,
    inputs=[
        gr.Image(label="카메라 이미지"),
        gr.Radio(
            choices=["장애물", "찾기", "확인"],
            value="장애물",
            label="분석 모드  (음성 명령: '주변 알려줘' / '찾아줘' / '이거 뭐야')",
        ),
    ],
    outputs=[
        gr.Image(label="탐지 결과 (바운딩 박스)"),
        gr.Textbox(label="음성 안내 / 상세 정보", lines=12),
    ],
    title="VoiceGuide — 시각장애인 실내 보행 음성 안내 시스템",
    description=(
        "이미지를 업로드하면 장애물의 위치·거리·위험도를 분석하여 한국어로 음성 안내합니다.\n"
        "Android 앱에서는 2초마다 자동 촬영 → 서버 전송 → 음성 출력이 실시간으로 이루어집니다.\n"
        "장애물 모드: 위험 장애물 안내 | 찾기 모드: 특정 물체 위치 | 확인 모드: 중앙 물체 식별"
    ),
)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--share", action="store_true",
                        help="실기기 테스트용 공개 URL 생성 (Gradio 터널링)")
    args = parser.parse_args()

    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        show_api=False,
        inbrowser=not args.share,
        share=args.share,
    )
