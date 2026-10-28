@echo off
rem AI-SUMMARY: 32-bit execution runner using project-local .venv32
setlocal
set "ROOT=%~dp0.."
set "LOG_DIR=%ROOT%\runtime_data\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1
if not exist "%ROOT%\.venv32\Scripts\python.exe" (
  echo [ENV32_MISSING] .venv32 missing, run scheduler\setup.ps1 first 1>&2
  exit /b 2
)
"%ROOT%\.venv32\Scripts\python.exe" -u "%ROOT%\run.py" %* >> "%LOG_DIR%\%1.log" 2>&1
exit /b %errorlevel%
