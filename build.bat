@echo off
setlocal enabledelayedexpansion
echo ========================================
echo  Video DownloadErm v2.0 Build Script
echo ========================================
echo.

cd /d "%~dp0"

REM ---------------------------------------------------------------
REM  0. Prerequisites
REM ---------------------------------------------------------------
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.13 first.
    pause
    exit /b 1
)

if not exist "main.py" (
    echo [ERROR] main.py not found. Run build.bat from the source folder.
    pause
    exit /b 1
)

for %%F in (ffmpeg_strategy.py scrollable_table_frame.py Page1.py Page2.py) do (
    if not exist "%%F" (
        echo [ERROR] %%F not found. The source tree is incomplete.
        pause
        exit /b 1
    )
)

REM ---------------------------------------------------------------
REM  1. FFmpeg
REM
REM  Not stored in the repository: the binaries exceed GitHub file
REM  size limits and are GPL v3 licensed. Downloaded on demand from
REM  gyan.dev instead. See THIRD-PARTY-NOTICES.md
REM ---------------------------------------------------------------
if exist "ffmpeg\bin\ffmpeg.exe" (
    echo [1/4] FFmpeg already present, skipping download.
    goto :ffmpeg_ready
)

echo [1/4] FFmpeg not found. Downloading from gyan.dev ...
echo       (GPL v3 - see THIRD-PARTY-NOTICES.md)

where curl >nul 2>&1
if errorlevel 1 (
    echo [ERROR] curl.exe not found. Requires Windows 10 1803 or later.
    goto :ffmpeg_manual
)
where tar >nul 2>&1
if errorlevel 1 (
    echo [ERROR] tar.exe not found. Requires Windows 10 1803 or later.
    goto :ffmpeg_manual
)

if exist "_ffmpeg_tmp" rmdir /s /q "_ffmpeg_tmp"
mkdir "_ffmpeg_tmp"

curl -L --fail --progress-bar ^
     -o "_ffmpeg_tmp\ffmpeg.zip" ^
     "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
if errorlevel 1 (
    echo [ERROR] Download failed.
    goto :ffmpeg_manual
)

echo       Extracting ...
tar -xf "_ffmpeg_tmp\ffmpeg.zip" -C "_ffmpeg_tmp"
if errorlevel 1 (
    echo [ERROR] Extraction failed.
    goto :ffmpeg_manual
)

REM The archive expands to a versioned folder such as
REM   ffmpeg-7.1-essentials_build\bin\ffmpeg.exe
set "FFSRC="
for /d %%D in ("_ffmpeg_tmp\ffmpeg-*") do (
    if exist "%%~fD\bin\ffmpeg.exe" set "FFSRC=%%~fD\bin"
)
if not defined FFSRC (
    echo [ERROR] ffmpeg.exe not found inside the archive.
    goto :ffmpeg_manual
)

if not exist "ffmpeg\bin" mkdir "ffmpeg\bin"
copy /y "!FFSRC!\ffmpeg.exe"  "ffmpeg\bin\" >nul
copy /y "!FFSRC!\ffprobe.exe" "ffmpeg\bin\" >nul
rmdir /s /q "_ffmpeg_tmp"

if not exist "ffmpeg\bin\ffmpeg.exe" (
    echo [ERROR] Failed to place ffmpeg.exe.
    goto :ffmpeg_manual
)
echo       FFmpeg ready.
goto :ffmpeg_ready

:ffmpeg_manual
echo.
echo   Manual setup:
echo     1. Download https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip
echo     2. Extract it
echo     3. Copy ffmpeg.exe and ffprobe.exe into  ffmpeg\bin\
echo     4. Run build.bat again
echo.
if exist "_ffmpeg_tmp" rmdir /s /q "_ffmpeg_tmp"
pause
exit /b 1

:ffmpeg_ready

REM ---------------------------------------------------------------
REM  2. Python dependencies
REM ---------------------------------------------------------------
echo [2/4] Installing dependencies ...
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] pip install failed.
    pause
    exit /b 1
)

REM ---------------------------------------------------------------
REM  3. Clean previous output
REM ---------------------------------------------------------------
echo [3/4] Cleaning old build output ...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

REM ---------------------------------------------------------------
REM  4. Package
REM ---------------------------------------------------------------
echo [4/4] Running PyInstaller ...
python -m PyInstaller --noconfirm --onedir --windowed --name "Video Downloaderm" --icon "assets\icon\icon.ico" --add-data "assets;assets" --add-data "locale;locale" --add-data "ffmpeg;ffmpeg" --hidden-import yt_dlp --hidden-import pywinstyles --hidden-import CTkTable --hidden-import edge_tts --hidden-import customtkinter --hidden-import PIL --hidden-import requests --hidden-import ffmpeg_strategy --hidden-import scrollable_table_frame main.py
if errorlevel 1 (
    echo [ERROR] PyInstaller failed. See messages above.
    pause
    exit /b 1
)

echo.
echo ========================================
echo  BUILD OK
echo  Output: dist\Video Downloaderm\
echo.
echo  Note: the output bundles FFmpeg (GPL v3).
echo  If you redistribute it, see THIRD-PARTY-NOTICES.md
echo ========================================
pause
