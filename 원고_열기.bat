@echo off
chcp 65001 >nul
title CCUT 원고
echo ============================================
echo   CCUT 원고 화면을 엽니다. 창을 닫지 마세요.
echo   (닫으면 원고 화면이 꺼집니다)
echo ============================================
echo.

REM 이전에 열려있던 서버가 있으면 정리 (포트 8000 / 5199)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do taskkill /f /pid %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5199 ^| findstr LISTENING') do taskkill /f /pid %%a >nul 2>&1

REM 모든 영상이 재생되도록 원본 저장소를 연결 (읽기 전용 — 원본은 바꾸지 않음)
set CCUT_STORAGE_DIR=D:\CCUT1.0.4\storage

echo [1/3] 제작실(백엔드) 켜는 중...
start "CCUT backend" /min cmd /c "cd /d D:\CCUT1.0.4-text-core-b0\ccut_backend && set CCUT_STORAGE_DIR=D:\CCUT1.0.4\storage && python -m uvicorn main:app --host 127.0.0.1 --port 8000"

echo [2/3] 화면(프론트) 켜는 중...
start "CCUT frontend" /min cmd /c "cd /d D:\CCUT1.0.4-text-core-b0\ccut_frontend && npx vite --port 5199 --strictPort --host 127.0.0.1"

echo [3/3] 준비되면 브라우저가 자동으로 열립니다...
REM 백엔드가 응답할 때까지 대기 (최대 40초)
setlocal enabledelayedexpansion
set READY=0
for /l %%i in (1,1,40) do (
  >nul 2>&1 curl -s -o nul http://127.0.0.1:5199/ledger && set READY=1
  if "!READY!"=="1" goto :open
  timeout /t 1 >nul
)
:open
start "" http://127.0.0.1:5199/ledger
echo.
echo 열렸습니다. 이 창과 최소화된 두 창은 원고를 보는 동안 그대로 두세요.
echo 끝내려면 이 창에서 아무 키나 누르세요 (서버가 함께 꺼집니다).
pause >nul
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do taskkill /f /pid %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5199 ^| findstr LISTENING') do taskkill /f /pid %%a >nul 2>&1
