@echo off
rem Arranca SOLO el add-on CardioAlert AP: la API (puerto 8000) y su interfaz (puerto 5173).
rem No arranca la estacion clinica simulada (para eso: start_simulador.bat).
chcp 65001 >nul
setlocal
cd /d "%~dp0"

rem --- Python (>= 3.10): el del entorno virtual .venv si existe; si no, el del PATH ---
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"
"%PY%" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>nul
if errorlevel 1 (
  echo [ERROR] Hace falta Python 3.10 o superior. Instalelo, o cree un entorno virtual: py -3 -m venv .venv
  exit /b 1
)
"%PY%" -c "import fastapi, uvicorn, yaml, ruamel.yaml, openpyxl" 2>nul
if errorlevel 1 (
  echo Instalando las dependencias de Python ^(requirements.txt^)...
  "%PY%" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo [ERROR] No se han podido instalar las dependencias de Python.
    exit /b 1
  )
)

rem --- Node.js (>= 20): se usa npm.cmd, no npm (PowerShell puede bloquear npm.ps1) ---
where npm.cmd >nul 2>nul
if errorlevel 1 (
  echo [ERROR] No se encuentra npm.cmd. Instale Node.js 20 o superior: https://nodejs.org
  exit /b 1
)
if not exist "frontend\node_modules\.bin\vite.cmd" (
  echo Instalando las dependencias de la interfaz ^(frontend^)...
  pushd frontend
  call npm.cmd install
  if errorlevel 1 (
    popd
    echo [ERROR] No se han podido instalar las dependencias de la interfaz.
    exit /b 1
  )
  popd
)

rem --- El puerto 8000 tiene que estar libre ---
"%PY%" -c "import socket, sys; s = socket.socket(); sys.exit(0 if s.connect_ex(('127.0.0.1', 8000)) else 1)"
if errorlevel 1 (
  echo [ERROR] El puerto 8000 ya esta en uso: el add-on ya esta arrancado, o lo ocupa otro programa.
  exit /b 1
)

rem La API anuncia esta URL a la estacion clinica (discovery de CDS Hooks)
set "CARDIOALERT_UI_URL=http://localhost:5173"

echo.
echo  ============================================================
echo   CardioAlert AP - ADD-ON
echo  ============================================================
echo   Interfaz:              http://localhost:5173
echo   API (documentacion):   http://localhost:8000/docs
echo   CDS Hooks (discovery): http://localhost:8000/cds-services
echo  ------------------------------------------------------------
echo   URL para instalar el add-on en la estacion clinica:
echo                          http://localhost:8000
echo   Para parar: Ctrl+C o cierre esta ventana.
echo  ============================================================
echo.

rem La API en segundo plano en esta misma ventana; la interfaz en primer plano
start "" /b "%PY%" -m uvicorn api.main:app --port 8000
cd frontend
call npm.cmd run dev
