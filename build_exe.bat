@echo off
rem ============================================================================
rem  Pedal Steel Master - single-file Windows build with Nuitka (onefile).
rem
rem  Output : dist\PedalSteelMaster.exe
rem  Needs  : .venv with the app's requirements, and Visual Studio (or Build
rem           Tools) with "Desktop development with C++" (Nuitka needs MSVC on
rem           Python 3.13+). Nuitka itself is installed into .venv if missing.
rem
rem  Usage  : build_exe.bat            build (runs the tests first)
rem           build_exe.bat notest     build without running the tests
rem           build_exe.bat clean      delete previous build output, then build
rem ============================================================================
setlocal EnableExtensions
cd /d "%~dp0"

set "APP_NAME=PedalSteelMaster"
set "APP_TITLE=Pedal Steel Master"
set "APP_VERSION=1.0.0.0"
set "PY=.venv\Scripts\python.exe"
set "BUILD_DIR=build_nuitka"
set "DIST_DIR=dist"
set "RUN_TESTS=1"

for %%A in (%*) do (
    if /i "%%~A"=="notest" set "RUN_TESTS=0"
    if /i "%%~A"=="clean" (
        echo Removing %BUILD_DIR% and %DIST_DIR% ...
        if exist "%BUILD_DIR%" rmdir /s /q "%BUILD_DIR%"
        if exist "%DIST_DIR%" rmdir /s /q "%DIST_DIR%"
    )
)

if not exist "%PY%" (
    echo ERROR: %PY% not found. Create the virtual environment first:
    echo        py -m venv .venv ^&^& .venv\Scripts\python.exe -m pip install -r requirements.txt
    exit /b 1
)

echo.
echo [1/4] Build tools (Nuitka, zstandard for onefile compression)
"%PY%" -m pip install --disable-pip-version-check --quiet --upgrade nuitka ordered-set zstandard
if errorlevel 1 goto :fail

if "%RUN_TESTS%"=="1" (
    echo.
    echo [2/4] Tests
    set "QT_QPA_PLATFORM=offscreen"
    "%PY%" -m unittest discover -s tests -q
    if errorlevel 1 (
        echo Tests failed: not building. Use "build_exe.bat notest" to build anyway.
        goto :fail
    )
    set "QT_QPA_PLATFORM="
) else (
    echo.
    echo [2/4] Tests skipped
)

echo.
echo [3/4] App icon (assets\icons\app_icon.ico)
"%PY%" -m ui.app_icon
if errorlevel 1 goto :fail

echo.
echo [4/4] Nuitka onefile build (the first build takes several minutes)
"%PY%" -m nuitka ^
    --onefile ^
    --msvc=latest ^
    --assume-yes-for-downloads ^
    --enable-plugin=pyside6 ^
    --include-qt-plugins=multimedia ^
    --include-package-data=reportlab ^
    --include-data-dir=assets=assets ^
    --nofollow-import-to=tests ^
    --windows-console-mode=attach ^
    --windows-icon-from-ico=assets\icons\app_icon.ico ^
    --product-name="%APP_TITLE%" ^
    --file-description="%APP_TITLE%" ^
    --file-version=%APP_VERSION% ^
    --product-version=%APP_VERSION% ^
    --onefile-tempdir-spec="{CACHE_DIR}/%APP_NAME%/{VERSION}" ^
    --output-dir="%BUILD_DIR%" ^
    --output-filename=%APP_NAME%.exe ^
    --report="%BUILD_DIR%\compilation-report.xml" ^
    main.py
if errorlevel 1 goto :fail

if not exist "%DIST_DIR%" mkdir "%DIST_DIR%"
copy /y "%BUILD_DIR%\%APP_NAME%.exe" "%DIST_DIR%\%APP_NAME%.exe" >nul
if errorlevel 1 goto :fail

echo.
echo Done: %DIST_DIR%\%APP_NAME%.exe
echo (First start unpacks into %%LOCALAPPDATA%%\%APP_NAME%; later starts reuse it.)
exit /b 0

:fail
echo.
echo BUILD FAILED (see the messages above).
exit /b 1
