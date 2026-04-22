@echo off
echo =================================================
echo  JEUS Log Analyzer - Build Start
echo =================================================
echo.

echo [Step 1] Installing required packages...
pip install pyinstaller openpyxl
echo.

echo [Step 2] Building .exe file... (may take a few minutes)
pyinstaller ^
    --onefile ^
    --windowed ^
    --name "JEUS_Log_Analyzer" ^
    --hidden-import=openpyxl ^
    --hidden-import=openpyxl.styles ^
    --hidden-import=openpyxl.utils ^
    main.py

echo.
if %ERRORLEVEL% == 0 (
    echo =================================================
    echo  Build SUCCESS!
    echo  Check dist\JEUS_Log_Analyzer.exe
    echo =================================================
) else (
    echo =================================================
    echo  Build FAILED. Check error messages above.
    echo =================================================
)

pause
