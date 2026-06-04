@echo off
setlocal

set "ROOT_PATH=%~dp0"
set "RUNNER_PYTHON=%ROOT_PATH%versions\19.0\venv\Scripts\python.exe"

if not exist "%RUNNER_PYTHON%" (
    echo Runner Python not found: "%RUNNER_PYTHON%"
    pause
    exit /b 1
)

"%RUNNER_PYTHON%" "%ROOT_PATH%scripts\dev_odoo.py" --odoo-version 19.0 -d odoo19_subscription_demo %*
pause
