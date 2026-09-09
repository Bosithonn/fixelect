@echo off
REM Run Fixelect (Python AI Engine)
cd /d "%~dp0"

echo ===================================================
echo   Fixelect - AI Grammar and Spelling Desktop Engine
echo   Hotkey: Ctrl+Alt+F to fix selection
echo   Quit:   Ctrl+Alt+Q
echo ===================================================
echo.

python fixelect.py %*
if errorlevel 1 (
  echo.
  echo Process exited with an error.
  pause
)
