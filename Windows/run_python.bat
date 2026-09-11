@echo off
REM Run Fixelect (Python AI Engine)
cd /d "%~dp0"

echo ===================================================
echo   Fixelect - AI Grammar & Executive Polish
echo   Fix Text:    Alt Alt  (or Ctrl+Alt+F)
echo   Polish Text: Ctrl Ctrl (or Ctrl+Alt+P)
echo   Quit:        Ctrl+Alt+Q
echo ===================================================
echo.

python fixelect.py %*
if errorlevel 1 (
  echo.
  echo Process exited with an error.
  pause
)
