"""
pip install -r requirements.txt 후 1회 실행하세요.
사용법: python tools/patch_gradio_client.py

gradio_client가 pydantic 생성 JSON Schema의 bool 값
(additionalProperties: true/false)을 처리 못하는 버그 패치.
"""
import importlib.util
import sys

spec = importlib.util.find_spec("gradio_client")
if spec is None:
    print("gradio_client가 설치되어 있지 않습니다. 먼저 pip install -r requirements.txt 실행하세요.")
    sys.exit(1)

utils_path = spec.submodule_search_locations[0] + "/utils.py"

print('\n', utils_path)

with open(utils_path, encoding="utf-8") as f:
    src = f.read()

MARKER = "# [VoiceGuide patch applied]"
if MARKER in src:
    print("이미 패치가 적용되어 있습니다.")
    sys.exit(0)

OLD1   = 'def get_type(schema: dict) -> str:'
OLD1_1 = 'def get_type(schema: dict):'
NEW1_BODY = f'\n    if not isinstance(schema, dict):  {MARKER}\n        return "Any"'

OLD2   = 'def _json_schema_to_python_type(schema: dict, defs: dict | None = None) -> str:'
OLD2_2 = 'def _json_schema_to_python_type(schema: Any, defs) -> str:'
NEW2_BODY = f'\n    if isinstance(schema, bool):  {MARKER}\n        return "Any"'

found1 = OLD1 if OLD1 in src else (OLD1_1 if OLD1_1 in src else None)
if found1 is None:
    print("패치 1 대상 코드를 찾지 못했습니다. gradio_client 버전을 확인하세요.")
    sys.exit(1)

found2 = OLD2 if OLD2 in src else (OLD2_2 if OLD2_2 in src else None)
if found2 is None:
    print("패치 2 대상 코드를 찾지 못했습니다. gradio_client 버전을 확인하세요.")
    sys.exit(1)

src = src.replace(found1, found1 + NEW1_BODY, 1)
src = src.replace(found2, found2 + NEW2_BODY, 1)

with open(utils_path, "w", encoding="utf-8") as f:
    f.write(src)

print(f"패치 완료: {utils_path}")
