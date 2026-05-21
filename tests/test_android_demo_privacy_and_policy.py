from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _map_block(source: str, name: str) -> str:
    start = source.index(f"val {name} = mapOf(")
    end = source.index("\n)", start)
    return source[start:end]


def test_android_gps_upload_is_disabled_for_demo_privacy():
    source = _read("android/app/src/main/java/com/voiceguide/MainActivity.kt")
    manifest = _read("android/app/src/main/AndroidManifest.xml")

    assert "private const val ENABLE_ANDROID_GPS_UPLOAD = false" in source
    assert "ENABLE_ANDROID_GPS_UPLOAD &&" in source[source.index("private fun hasValidLocation()") :]
    assert "if (!ENABLE_ANDROID_GPS_UPLOAD)" in source[source.index("private fun startGpsUpdates()") :]
    assert "android.permission.ACCESS_FINE_LOCATION" not in manifest
    assert "android.permission.ACCESS_COARSE_LOCATION" not in manifest


def test_android_clock_direction_and_action_cover_server_12_hour_outputs():
    constants = _read("android/app/src/main/java/com/voiceguide/VoiceGuideConstants.kt")
    direction_block = _map_block(constants, "CLOCK_TO_DIRECTION")
    action_block = _map_block(constants, "DIRECTION_ACTION")

    for clock in ["5시", "6시", "7시"]:
        assert f'"{clock}"' in direction_block
        assert f'"{clock}"' in action_block


def test_policy_files_include_class_specific_bbox_calibration():
    for path in [
        "src/config/policy.json",
        "android/app/src/main/assets/policy_default.json",
    ]:
        policy = _read(path)
        assert '"bbox_calib_area_by_class"' in policy
        assert '"사람"' in policy
        assert '"버스"' in policy
