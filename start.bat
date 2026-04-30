@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo [VoiceGuide] Starting...

REM Activate conda ai_env in current shell first
if exist "%USERPROFILE%\anaconda3\Scripts\activate.bat" (
    call "%USERPROFILE%\anaconda3\Scripts\activate.bat" ai_env
) else if exist "%USERPROFILE%\miniconda3\Scripts\activate.bat" (
    call "%USERPROFILE%\miniconda3\Scripts\activate.bat" ai_env
)

REM Launch FastAPI server (inherits conda env from current shell)
start "VoiceGuide-Server" cmd /k "uvicorn src.api.main:app --host 0.0.0.0 --port 8000"
echo [1/2] FastAPI server started. Waiting 4 seconds...
timeout /t 4 /nobreak > nul

REM Launch ngrok tunnel
start "VoiceGuide-ngrok" cmd /k "ngrok http 8000"
echo [2/2] ngrok started.
echo.
echo ==========================================
echo  Local  : http://localhost:8000/health
echo  Dashboard : http://localhost:8000/dashboard
echo  ngrok  : Check Forwarding URL in ngrok window
echo  Android: Paste ngrok URL into app
echo  To stop: stop.bat
echo ==========================================
echo.
pause
