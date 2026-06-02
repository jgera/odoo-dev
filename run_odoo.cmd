@echo off
setlocal

set "ROOT_PATH=%~dp0"
set "VENV_PATH=%ROOT_PATH%venv"

if not exist "%VENV_PATH%\Scripts\python.exe" (
    echo Python virtual environment not found: "%VENV_PATH%\Scripts\python.exe"
    pause
    exit /b 1
)

"%VENV_PATH%\Scripts\python.exe" "%ROOT_PATH%scripts\dev_odoo.py" %*
pause
