@echo off
rem AI-SUMMARY: 64-bit calendar/notification runner using portable Python discovery
setlocal
set "ROOT=%~dp0.."
set "LOG_DIR=%ROOT%\runtime_data\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1

py -3.12 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)" >nul 2>&1
if %errorlevel%==0 (
  py -3.12 -u "%ROOT%\run.py" %* >> "%LOG_DIR%\%1.log" 2>&1
) else (
  python -u "%ROOT%\run.py" %* >> "%LOG_DIR%\%1.log" 2>&1
)
exit /b %errorlevel%
