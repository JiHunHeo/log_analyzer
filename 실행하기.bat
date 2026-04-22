@echo off
cd /d "%~dp0"

echo =================================================
echo  JEUS Log Analyzer - Starting...
echo =================================================
echo.

if not exist "venv" (
    echo [Setup] First run: installing required packages...
    python -m venv venv
    call venv\Scripts\activate.bat

    if exist "packages" (
        echo [Setup] Installing from local packages folder (offline mode)...
        pip install --no-index --find-links=packages openpyxl
    ) else (
        echo [Setup] Downloading from internet...
        pip install openpyxl --quiet
    )

    echo [Setup] Done!
    echo.
) else (
    call venv\Scripts\activate.bat
)

echo [Run] Launching program...
python main.py

echo.
echo Program closed.
pause
