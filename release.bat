@echo off
setlocal enabledelayedexpansion
title pubcode release builder

set APPNAME=pubcode

REM 从 pubcode.py 自动读取版本号
set APPVERSION=
for /f "usebackq tokens=2 delims==" %%A in (`findstr /r /c:"^VERSION = " pubcode.py`) do (
    set APPVERSION=%%A
)
set APPVERSION=%APPVERSION: =%
set APPVERSION=%APPVERSION:'=%
if "%APPVERSION%"=="" (
    echo [ERROR] Failed to read VERSION from pubcode.py
    pause
    exit /b 1
)

set OUTZIP=%APPNAME%-v%APPVERSION%-win64.zip

echo ============================================
echo  pubcode v%APPVERSION% release builder
echo ============================================
echo.

echo [0/5] Checking prerequisites...
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] python not found in PATH.
    pause
    exit /b 1
)
if not exist "ffmpeg\ffmpeg.exe" (
    echo [ERROR] ffmpeg\ffmpeg.exe not found.
    pause
    exit /b 1
)
if not exist "ffmpeg\ffprobe.exe" (
    echo [ERROR] ffmpeg\ffprobe.exe not found.
    pause
    exit /b 1
)
if not exist "pubcode.py" (
    echo [ERROR] pubcode.py not found.
    pause
    exit /b 1
)
echo   OK

echo [1/5] Cleaning old artifacts...
if exist build    rmdir /s /q build
if exist dist     rmdir /s /q dist
if exist release  rmdir /s /q release
if exist "%OUTZIP%" del /q "%OUTZIP%"
echo   OK

echo [2/5] Building exe with PyInstaller...
python -m PyInstaller --onefile --name %APPNAME% --clean pubcode.py
if errorlevel 1 (
    echo [ERROR] PyInstaller failed.
    pause
    exit /b 1
)
if not exist "dist\%APPNAME%.exe" (
    echo [ERROR] dist\%APPNAME%.exe not produced.
    pause
    exit /b 1
)
echo   OK

echo [3/5] Assembling release folder...
mkdir release
copy /Y "dist\%APPNAME%.exe" "release\" >nul
mkdir "release\ffmpeg"
copy /Y "ffmpeg\ffmpeg.exe"  "release\ffmpeg\" >nul
copy /Y "ffmpeg\ffprobe.exe" "release\ffmpeg\" >nul
if exist "ffmpeg\ffplay.exe" (
    echo   ffplay.exe found, including...
    copy /Y "ffmpeg\ffplay.exe" "release\ffmpeg\" >nul
) else (
    echo   ffplay.exe not found, skipping.
)
if exist "README.md"          copy /Y "README.md"          "release\" >nul
if exist "LICENSE-ffmpeg.txt" copy /Y "LICENSE-ffmpeg.txt" "release\" >nul
if exist "CHANGELOG.md"       copy /Y "CHANGELOG.md"       "release\" >nul
echo   OK

echo [4/5] Zipping...
powershell -NoProfile -Command "Compress-Archive -Path 'release\*' -DestinationPath '%OUTZIP%' -Force"
if errorlevel 1 (
    echo [ERROR] zip failed.
    pause
    exit /b 1
)
echo   OK

echo [5/5] Verifying...
if not exist "%OUTZIP%" (
    echo [ERROR] %OUTZIP% not produced.
    pause
    exit /b 1
)
echo.
echo ============================================
echo  DONE: %OUTZIP%
echo ============================================
echo.
echo Release folder contents:
dir /b release
echo.
for %%F in ("%OUTZIP%") do set ZIP_SIZE=%%~zF
set /a ZIP_MB=!ZIP_SIZE! / 1048576
for %%F in ("release\%APPNAME%.exe") do set EXE_SIZE=%%~zF
set /a EXE_MB=!EXE_SIZE! / 1048576
echo Size summary:
echo   pubcode.exe : !EXE_MB! MB
echo   zip package : !ZIP_MB! MB
echo.
pause