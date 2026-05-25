from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "build_voiceguide_final_dataset.py"


def load_module():
    spec = importlib.util.spec_from_file_location("build_voiceguide_final_dataset", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_final_score_uses_all_accessibility_evidence():
    module = load_module()

    row = {
        "has_pedestrian_light": "Y",
        "has_audio_signal": "Y",
        "has_push_button": "Y",
        "is_raised_crosswalk": "Y",
        "has_traffic_safety_detail": "Y",
    }

    assert module.accessibility_score(row) == 8
    assert module.route_tier(8) == "preferred"
    assert module.support_evidence(row) == "보행등, 음향신호기, 보행자작동신호기, 고원식횡단보도, 교통안전시설 상세"


def test_build_final_dataset_outputs_scenario_ready_files(tmp_path):
    module = load_module()

    output_dir = tmp_path / "voiceguide_final"
    module.build(output_dir=output_dir)

    expected = {
        "final_crosswalk_accessibility.csv",
        "final_crosswalk_accessibility.geojson",
        "final_route_comparison.csv",
        "final_scenario_dataset.json",
        "final_tts_guidance.csv",
        "final_data_usage.html",
        "README.md",
    }
    assert expected.issubset({p.name for p in output_dir.iterdir()})

    crosswalks = pd.read_csv(output_dir / "final_crosswalk_accessibility.csv", encoding="utf-8-sig")
    assert len(crosswalks) == 1025
    assert {
        "crosswalk_id",
        "district",
        "latitude",
        "longitude",
        "has_traffic_safety_detail",
        "accessibility_score",
        "route_recommendation_tier",
        "support_evidence",
    }.issubset(crosswalks.columns)

    route = pd.read_csv(output_dir / "final_route_comparison.csv", encoding="utf-8-sig")
    assert set(route["route_id"]) == {"A", "B"}
    assert bool(route.loc[route["route_id"].eq("B"), "selected"].iloc[0])
    assert route.loc[route["route_id"].eq("B"), "accessibility_score"].iloc[0] > route.loc[
        route["route_id"].eq("A"), "accessibility_score"
    ].iloc[0]

    geojson = json.loads((output_dir / "final_crosswalk_accessibility.geojson").read_text(encoding="utf-8"))
    assert geojson["type"] == "FeatureCollection"
    assert len(geojson["features"]) == 1025

    dataset = json.loads((output_dir / "final_scenario_dataset.json").read_text(encoding="utf-8"))
    assert {"metadata", "destination_candidates", "preferred_crosswalk_candidates", "demo_crosswalk_pair"}.issubset(
        dataset
    )
