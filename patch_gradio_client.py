"""
pip install -r requirements.txt 후 1회 실행하세요.

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

with open(utils_path, encoding="utf-8") as f:
    src = f.read()

MARKER = "# [VoiceGuide patch applied]"
if MARKER in src:
    print("이미 패치가 적용되어 있습니다.")
    sys.exit(0)

# 패치 1: get_type()에서 schema가 bool일 때 TypeError 방지
OLD1 = 'def get_type(schema: dict) -> str:'
NEW1 = '''def get_type(schema: dict) -> str:
    if not isinstance(schema, dict):  ''' + MARKER + '''
        return "Any"'''

# 패치 2: _json_schema_to_python_type()에서 bool 스키마 처리
OLD2 = 'def _json_schema_to_python_type(schema: dict, defs: dict | None = None) -> str:'
NEW2 = '''def _json_schema_to_python_type(schema: dict, defs: dict | None = None) -> str:
    if isinstance(schema, bool):  ''' + MARKER + '''
        return "Any"'''

if OLD1 not in src:
    print("패치 대상 코드를 찾지 못했습니다. gradio_client 버전을 확인하세요.")
    sys.exit(1)

src = src.replace(OLD1, NEW1, 1)
src = src.replace(OLD2, NEW2, 1)

with open(utils_path, "w", encoding="utf-8") as f:
    f.write(src)

print(f"패치 완료: {utils_path}")
