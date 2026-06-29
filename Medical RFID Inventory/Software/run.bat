@echo off
setlocal

set "ROOT_DIR=%~dp0"
set "BACKEND_DIR=%ROOT_DIR%backend"
set "VENV_DIR=%BACKEND_DIR%\.venv"

if not exist "%BACKEND_DIR%" (
  echo Error: backend directory not found at %BACKEND_DIR%
  exit /b 1
)

if not exist "%VENV_DIR%\Scripts\activate.bat" (
  echo Virtual environment not found. Running setup first ...
  call "%ROOT_DIR%setup.bat"
)

call "%VENV_DIR%\Scripts\activate.bat"

cd /d "%BACKEND_DIR%"

echo Starting server at http://localhost:8000 ...
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

endlocal
