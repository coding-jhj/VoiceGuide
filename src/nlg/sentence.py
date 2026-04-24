from src.nlg.templates import TEMPLATES, CHANGE_TEMPLATES, FALLBACK_TEMPLATE, DIRECTION_KO


def build_sentence(objects: list[dict], changes: list[str]) -> str:
    """
    Args:
        objects: detect_and_depth() 반환값 (위험도 내림차순, 최대 2개)
        changes: ["가방이 1개 더 있어요"] 형식 (없으면 빈 리스트)
    Returns:
        "왼쪽 바로 앞에 의자가 있어요. 오른쪽으로 비켜보세요."

    규칙:
    1. objects가 비어있으면 → "주변에 장애물이 없어요."
    2. risk_score 가장 높은 것을 먼저 안내
    3. changes가 있으면 마지막에 추가
    4. 문장은 최대 2문장
    """
    if not objects:
        base = "주변에 장애물이 없어요."
    else:
        parts = []
        for obj in objects[:2]:
            key = (obj["direction"], obj["distance"])
            tmpl = TEMPLATES.get(key)
            if tmpl:
                parts.append(tmpl.format(obj=obj["class_ko"]))
            else:
                parts.append(
                    FALLBACK_TEMPLATE.format(
                        obj=obj["class_ko"],
                        direction_ko=DIRECTION_KO.get(obj["direction"], obj["direction"]),
                        distance=obj["distance"],
                    )
                )
        base = " ".join(parts)

    change_text = " ".join(changes[:1]) if changes else ""
    return f"{base} {change_text}".strip()
