import gradio as gr
import cv2
import numpy as np
from src.depth.depth import detect_and_depth
from src.nlg.sentence import build_sentence
from src.voice.tts import speak


def process_image(image):
    if image is None:
        return "이미지를 업로드해주세요."

    _, encoded = cv2.imencode(".jpg", np.array(image))
    image_bytes = encoded.tobytes()

    # camera_orientation은 Android에서 나침반+가속도계로 자동 감지 후 API에 전달
    # Gradio MVP에서는 정면(front) 고정
    objects = detect_and_depth(image_bytes)
    sentence = build_sentence(objects, [], camera_orientation="front")

    speak(sentence)

    result = sentence + "\n\n"
    for obj in objects:
        result += (
            f"- {obj['class_ko']}: "
            f"{DIRECTION_KO_UI.get(obj['direction'], obj['direction'])}, "
            f"약 {obj['distance_m']}m, "
            f"위험도={obj['risk_score']}\n"
        )

    return result


DIRECTION_KO_UI = {
    "far_left":  "왼쪽 끝",
    "left":      "왼쪽",
    "center":    "정면",
    "right":     "오른쪽",
    "far_right": "오른쪽 끝",
}

demo = gr.Interface(
    fn=process_image,
    inputs=gr.Image(label="카메라 이미지"),
    outputs=gr.Textbox(label="음성 안내 결과"),
    title="VoiceGuide MVP",
    description="이미지를 업로드하면 주변 장애물을 음성으로 안내합니다.",
)

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860, show_api=False, inbrowser=True)
