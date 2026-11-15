@echo off
rem Arranca SOLO la estacion clinica simulada (puerto 5174). No necesita Python ni el add-on.
rem Los datos de los pacientes son de la estacion (simulador\datos) y los sirve su servidor FHIR.
chcp 65001 >nul
setlocal
cd /d "%~dp0"

rem --- Node.js (>= 20): se usa npm.cmd, no npm (PowerShell puede bloquear npm.ps1) ---
where npm.cmd >nul 2>nul
if errorlevel 1 (
  echo [ERROR] No se encuentra npm.cmd. Instale Node.js 20 o superior: https://nodejs.org
  exit /b 1
)
if not exist "simulador\datos\demo\fhir\P001.json" (
  echo [ERROR] Faltan los datos sinteticos ^(simulador\datos\demo\fhir^). Ejecute: python scripts\generate_patients.py
  exit /b 1
)
if not exist "simulador\node_modules\.bin\vite.cmd" (
  echo Instalando las dependencias del simulador...
  pushd simulador
  call npm.cmd install
  if errorlevel 1 (
    popd
    echo [ERROR] No se han podido instalar las dependencias del simulador.
    exit /b 1
  )
  popd
)

echo.
echo  ============================================================
echo   ESTACION CLINICA SIMULADA  (datos sinteticos)
echo  ============================================================
echo   Estacion clinica:      http://localhost:5174
echo   Su servidor FHIR:      http://localhost:5174/fhir/metadata
echo   Cupo activo:           Configuracion - Cupo / centro
echo                          ^(demo de 100 o realista de 1.500^)
echo  ------------------------------------------------------------
echo   Por defecto NO tiene ningun add-on instalado.
echo   Para instalar CardioAlert AP: Configuracion - Integraciones,
echo   URL del add-on http://localhost:8000 (arranquelo con start_addon.bat).
echo   Para parar: Ctrl+C o cierre esta ventana.
echo  ============================================================
echo.

cd simulador
call npm.cmd run dev
