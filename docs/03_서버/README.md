# 서버 문서 안내

현재 발표/배포/Android 연동 기준 서버는 아래 하나입니다.

```text
src.api.main:app
```

먼저 볼 문서:

| 문서 | 용도 |
|---|---|
| `../00_실행/CMD_RUNBOOK.md` | CMD 실행/배포/검증 순서 |
| `../PROJECT_STRUCTURE.md` | 현재 폴더 구조와 실행 진입점 |
| `../04_팀/SERVER_AND_LEAD_ACTIONS.md` | 서버 담당 + 팀장 체크리스트 |
| `GCP_DEPLOY_NOW.md` | GCP Cloud Run 배포 |
| `NGROK_GUIDE.md` | 로컬 서버 외부 연결 |

주의할 문서:

| 문서 | 현재 의미 |
|---|---|
| `SERVER_GUIDE.md` | `legacy/서버_DB*` 실험 서버 이해용 참고 |
| `SERVER_ARCHITECTURE.md` | 과거 다중 서버 연결 아이디어 참고 |
| `SUPABASE_QNA.md` | Supabase 연결 Q&A 참고 |

현재 실행 명령:

```bat
cd /d C:\VoiceGuide\VoiceGuide
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

현재 GCP 배포 명령:

```bat
cd /d C:\VoiceGuide\VoiceGuide
gcloud run deploy voiceguide --source . --region asia-northeast3 --memory 2Gi --cpu 2 --timeout 120 --allow-unauthenticated --port 8080
```
