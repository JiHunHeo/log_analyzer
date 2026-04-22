@echo off
cd /d "%~dp0"

echo =================================================
echo  JEUS Log Analyzer
echo =================================================
echo.

python -m pip install --no-index --find-links=packages openpyxl --quiet --quiet
python main.py

pause
