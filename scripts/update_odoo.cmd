@echo off
setlocal

set "ROOT_PATH=%~dp0"
set "RUNNER_PYTHON=%ROOT_PATH%versions\17.0\venv\Scripts\python.exe"

if not exist "%RUNNER_PYTHON%" (
    echo Runner Python not found: "%RUNNER_PYTHON%"
    pause
    exit /b 1
)

"%RUNNER_PYTHON%" "%ROOT_PATH%scripts\update_odoo_version.py" --odoo-version 17.0 %*
pause
