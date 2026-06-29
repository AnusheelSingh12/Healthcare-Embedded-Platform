@echo off
setlocal

set "ROOT_DIR=%~dp0"
set "BACKEND_DIR=%ROOT_DIR%backend"
set "VENV_DIR=%BACKEND_DIR%\.venv"

if not exist "%BACKEND_DIR%" (
  echo Error: backend directory not found at %BACKEND_DIR%
  exit /b 1
)

where py >nul 2>&1
if %errorlevel%==0 (
  set "PYTHON_CMD=py -3"
) else (
  where python >nul 2>&1
  if %errorlevel%==0 (
    set "PYTHON_CMD=python"
  ) else (
    echo Error: Python is not installed. Install Python 3.10+ and retry.
    exit /b 1
  )
)

echo Using Python: %PYTHON_CMD%

if not exist "%VENV_DIR%" (
  echo Creating virtual environment in backend\.venv ...
  %PYTHON_CMD% -m venv "%VENV_DIR%"
)

call "%VENV_DIR%\Scripts\activate.bat"

python -m pip install --upgrade pip
python -m pip install -r "%BACKEND_DIR%\requirements.txt"

echo Setup complete.
echo Run the app with: run.bat

endlocal
