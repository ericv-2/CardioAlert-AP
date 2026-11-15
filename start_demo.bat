@echo off
rem Arranca la demo completa: el add-on CardioAlert AP y la estacion clinica simulada, cada uno en su ventana.
chcp 65001 >nul
setlocal
cd /d "%~dp0"

start "CardioAlert AP - add-on (API 8000, interfaz 5173)" cmd /k call "%~dp0start_addon.bat"
start "Estacion clinica simulada (5174)" cmd /k call "%~dp0start_simulador.bat"

echo.
echo  ============================================================
echo   DEMO: add-on + estacion clinica simulada
echo  ============================================================
echo   Estacion clinica:      http://localhost:5174
echo   Add-on (interfaz):     http://localhost:5173
echo   Add-on (API):          http://localhost:8000/docs
echo   CDS Hooks (discovery): http://localhost:8000/cds-services
echo  ------------------------------------------------------------
echo   Cada aplicacion corre en su propia ventana: cierrela para pararla.
echo   En la estacion: Configuracion - Integraciones - Instalar
echo   (URL del add-on: http://localhost:8000).
echo  ============================================================
echo.

rem Abre la estacion clinica en el navegador cuando ya ha arrancado (DEMO_SIN_NAVEGADOR=1 para no abrirlo)
if not "%DEMO_SIN_NAVEGADOR%"=="1" (
  ping -n 7 127.0.0.1 >nul
  start "" "http://localhost:5174"
)
