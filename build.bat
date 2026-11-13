@echo off
rem Arma MisterDescarga portatil en dist\. Requiere Python 3.11+ y Node.js 20+.
setlocal
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
  echo Creando entorno virtual...
  python -m venv .venv || goto :error
)

call .venv\Scripts\python -m pip install --upgrade pip >nul
call .venv\Scripts\python -m pip install -r requirements.txt -r requirements-dev.txt || goto :error
call .venv\Scripts\python scripts\build_portable.py %* || goto :error

echo.
echo Listo. Mira la carpeta dist\
exit /b 0

:error
echo.
echo Hubo un error al compilar.
exit /b 1
