from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_android_on_device_distance_calls_pass_class_name():
    sources = [
        _read("android/app/src/main/java/com/voiceguide/MvpPipeline.kt"),
        _read("android/app/src/main/java/com/voiceguide/SentenceBuilder.kt"),
        _read("android/app/src/main/java/com/voiceguide/MainActivity.kt"),
    ]

    joined = "\n".join(sources)
    assert "VoicePolicy.calcDistBboxM(det.classKo, det.w, det.h)" in joined
    assert "VoicePolicy.formatDistBbox(det.classKo, det.w, det.h)" in joined
    assert "VoicePolicy.calcDistBboxM(d.classKo, d.w, d.h)" in joined
    assert "VoicePolicy.calcDistBboxM(det.w, det.h)" not in joined
    assert "VoicePolicy.formatDistBbox(det.w, det.h)" not in joined
    assert "VoicePolicy.calcDistBboxM(d.w, d.h)" not in joined
