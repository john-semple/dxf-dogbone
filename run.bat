@echo off
setlocal EnableDelayedExpansion
set "PYTHON="

where py >nul 2>nul && (
    py -3.11 -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" 2>nul && set "PYTHON=py -3.11"
    if not defined PYTHON ( py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" 2>nul && set "PYTHON=py -3" )
)

if not defined PYTHON (
    where python >nul 2>nul && (
        python -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" 2>nul && set "PYTHON=python"
    )
)

if not defined PYTHON (
    echo ERROR: Python 3.11+ not found.
    echo Install from python.org - check "Add python.exe to PATH" during install.
    echo If a Microsoft Store window opened, disable the Store PATH stub:
    echo Settings ^> Apps ^> Advanced app settings ^> App execution aliases ^> turn OFF python.exe
    exit /b 1
)

echo Using Python via: !PYTHON!
!PYTHON! -c "import sys; assert sys.version_info >= (3,11); print('Python OK:', sys.version.split()[0])" || (echo ERROR: resolved interpreter failed version check & exit /b 1)

if exist ".venv\Scripts\python.exe" (
    echo Reusing existing venv:
    .venv\Scripts\python.exe -c "import sys; print('  venv Python:', sys.version.split()[0])"
) else (
    !PYTHON! -m venv .venv || (echo ERROR: venv creation failed & exit /b 1)
    .venv\Scripts\python.exe -m pip install -r requirements.txt --quiet || (echo ERROR: pip install failed - delete the .venv folder and re-run run.bat & exit /b 1)
)

if not exist app.py (
    echo.
    echo No app.py yet - environment check only. App ships with milestone M1.
    exit /b 0
)

.venv\Scripts\python.exe app.py %*
if errorlevel 1 (
    echo Launch failed - attempting one dependency repair...
    .venv\Scripts\python.exe -m pip install -r requirements.txt --quiet
    .venv\Scripts\python.exe app.py %*
)