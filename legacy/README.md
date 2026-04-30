# Legacy 보관 폴더

이 폴더는 과거 실험 코드와 별도 서버 시도를 보관하는 곳입니다.

현재 발표/배포/Android 연동 기준 서버는 아래 하나입니다.

```text
src.api.main:app
```

현재 서버 실행:

```bat
cd /d C:\VoiceGuide\VoiceGuide
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

현재 GCP 배포:

```bat
gcloud run deploy voiceguide --source . --region asia-northeast3 --memory 2Gi --cpu 2 --timeout 120 --allow-unauthenticated --port 8080
```

## 보관 항목

| 폴더 | 의미 |
|---|---|
| `서버_DB/` | Supabase 연결 테스트용 과거 FastAPI 서버 |
| `서버_DB_수정/` | 블러/도로 관련 실험 서버 |

주의:

- 이 폴더의 `main.py`는 Android 앱이 호출하는 서버가 아닙니다.
- Cloud Run 배포도 이 폴더를 진입점으로 사용하지 않습니다.
- 참고가 끝나고 팀장이 승인하면 삭제하거나 별도 저장소로 분리할 수 있습니다.
