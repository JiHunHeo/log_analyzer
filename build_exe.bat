@echo off
chcp 65001 > nul
echo =================================================
echo  JEUS 로그 분석기 .exe 파일 빌드 시작
echo =================================================
echo.

:: 필요한 라이브러리 설치
echo [1단계] 필요한 라이브러리 설치 중...
pip install pyinstaller openpyxl
echo.

:: PyInstaller로 단일 .exe 파일 빌드
:: --onefile   : 모든 파일을 하나의 .exe로 합칩니다
:: --windowed  : 콘솔 창 없이 GUI만 보이게 합니다
:: --name      : 생성될 .exe 파일 이름
:: --add-data  : 추가 데이터 파일 포함 (없으면 생략)
echo [2단계] .exe 파일 빌드 중... (수 분 소요될 수 있습니다)
pyinstaller ^
    --onefile ^
    --windowed ^
    --name "JEUS로그분석기" ^
    --hidden-import=openpyxl ^
    --hidden-import=openpyxl.styles ^
    --hidden-import=openpyxl.utils ^
    main.py

echo.
if %ERRORLEVEL% == 0 (
    echo =================================================
    echo  빌드 성공!
    echo  dist 폴더에서 JEUS로그분석기.exe 파일을 확인하세요.
    echo =================================================
) else (
    echo =================================================
    echo  빌드 실패! 위의 오류 메시지를 확인해주세요.
    echo =================================================
)

pause
