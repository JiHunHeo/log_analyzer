@echo off
cd /d "%~dp0"

echo =================================================
echo  JEUS Log Analyzer - Starting...
echo =================================================
echo.

echo [1/3] Checking Python...
python --version
if %ERRORLEVEL% neq 0 (
    echo ERROR: Python not found. Please install Python first.
    pause
    exit /b 1
)

echo [2/3] Installing required packages...
if exist "packages" (
    echo     Installing from local packages folder (offline)...
    python -m pip install --no-index --find-links=packages openpyxl
) else (
    echo     Downloading from internet...
    python -m pip install openpyxl --quiet
)
if %ERRORLEVEL% neq 0 (
    echo ERROR: Package installation failed.
    pause
    exit /b 1
)

echo [3/3] Launching program...
echo.
python main.py
if %ERRORLEVEL% neq 0 (
    echo.
    echo ERROR: Program crashed. See message above.
    pause
    exit /b 1
)

pause
