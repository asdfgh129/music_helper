@echo off
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python not found in PATH. Packaging needs Python 3.11+ on the build machine.
  echo         The generated dist\ package itself does NOT need Python.
  pause
  exit /b 1
)
python scripts\build_exe.py %*
if errorlevel 1 (
  echo.
  echo [FAILED] See the log above.
  pause
  exit /b 1
)
echo.
echo [OK] Package is ready in dist\
pause
