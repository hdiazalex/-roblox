@echo off
rem Windows: haz doble clic en este archivo para abrir el convertidor.
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 biblioteca_a_mp3.py %*
    exit /b
)
where python >nul 2>nul
if %errorlevel%==0 (
    python biblioteca_a_mp3.py %*
    exit /b
)
echo Necesitas Python 3: https://www.python.org/downloads/
pause
