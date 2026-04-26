# 설치 후 이 파일을 실행해서 확인해
# 사용법: python tools/verify.py

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

libs = [
    ("torch",              "2.4.1"),
    ("numpy",              "1.26.4"),
    ("ultralytics",        "8.3.2"),
    ("cv2",                "4.10.0"),
    ("gradio",             "4.44.1"),
    ("fastapi",            "0.115.5"),
    ("speech_recognition", "3.10.4"),
    ("gtts",               "2.5.3"),
]

print(f"Python: {sys.version}\n")

for lib_name, expected in libs:
    try:
        lib = __import__(lib_name)
        version = getattr(lib, "__version__",
                  getattr(lib, "version", "확인불가"))
        status = "OK  " if expected in str(version) else "WARN"
        print(f"{status}  {lib_name}: {version} (권장: {expected})")
    except ImportError:
        print(f"FAIL  {lib_name}: 설치 안됨!")

try:
    import torch, numpy as np
    t = torch.tensor(np.array([1.0, 2.0]))
    print(f"\ntorch + numpy 호환성: OK ({t})")
except Exception as e:
    print(f"\ntorch + numpy 호환성: FAIL → {e}")

try:
    import cv2, numpy as np
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    print("opencv + numpy 호환성: OK")
except Exception as e:
    print(f"opencv + numpy 호환성: FAIL → {e}")
