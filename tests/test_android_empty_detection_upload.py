from pathlib import Path


def test_empty_detection_branch_does_not_upload_to_server():
    source = Path("android/app/src/main/java/com/voiceguide/MainActivity.kt").read_text(
        encoding="utf-8"
    )
    branch_start = source.index("if (voted.isEmpty())")
    branch_end = source.index("return@Runnable", branch_start)
    empty_branch = source[branch_start:branch_end]

    assert "sendDetectionJsonToServer" not in empty_branch
    assert "handleSuccess(" in empty_branch
