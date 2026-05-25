import pandas as pd

from tools import preprocess_voiceguide_scenario_data as scenario


def _row(crosswalk_id: str, score: int, lat: float, lon: float, **flags):
    return {
        "crosswalk_id": crosswalk_id,
        "address": flags.pop("address", "동작구 신대방동 테스트"),
        "latitude": lat,
        "longitude": lon,
        "accessibility_score": score,
        "support_evidence": flags.pop("support_evidence", "교통안전시설 상세"),
        "route_recommendation_tier": flags.pop("tier", "basic"),
        "has_pedestrian_light": flags.pop("has_pedestrian_light", "N"),
        "has_audio_signal": flags.pop("has_audio_signal", "N"),
        "has_push_button": flags.pop("has_push_button", "N"),
        "has_traffic_safety_detail": flags.pop("has_traffic_safety_detail", "Y"),
    }


def test_apply_final_tier_labels_uses_presentation_labels():
    scores = pd.Series([7, 4, 1, 0])

    tiers = scenario.apply_final_tier_labels(scores)

    assert tiers.tolist() == ["preferred", "recommended", "basic", "insufficient"]


def test_pick_demo_pair_prefers_final_scenario_ids_and_detour():
    crosswalks = pd.DataFrame(
        [
            _row(
                "06-0000016344",
                1,
                37.49774746,
                126.9240174,
                address="동작구 신대방동 349-35도",
            ),
            _row(
                "06-0000032157",
                7,
                37.49503545,
                126.9274009,
                address="동작구 신대방동 산112-5도",
                support_evidence="음향신호기, 보행등, 교통안전시설 상세",
                tier="preferred",
                has_pedestrian_light="Y",
                has_audio_signal="Y",
            ),
            _row("06-0000003950", 1, 37.48188507, 126.9666438),
            _row(
                "06-0000003951",
                10,
                37.48126427,
                126.9659855,
                tier="preferred",
                has_pedestrian_light="Y",
                has_audio_signal="Y",
                has_push_button="Y",
            ),
        ]
    )

    pair = scenario.pick_demo_pair(crosswalks)

    assert pair["shortest_route_crosswalk_a"]["crosswalk_id"] == "06-0000016344"
    assert pair["safer_route_crosswalk_b"]["crosswalk_id"] == "06-0000032157"
    assert pair["estimated_route_detour_m"] == 8
    assert "약 8m" in pair["tts_example"]
