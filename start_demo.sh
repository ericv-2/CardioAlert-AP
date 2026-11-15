#!/usr/bin/env bash
# Arranca la demo completa: el add-on CardioAlert AP y la estación clínica simulada. Ctrl+C para los dos.
set -e
cd "$(dirname "$0")"

./start_addon.sh &
ADDON_PID=$!
./start_simulador.sh &
SIMULADOR_PID=$!
trap 'kill "$ADDON_PID" "$SIMULADOR_PID" 2>/dev/null || true' EXIT INT TERM

cat <<'EOF'

 ============================================================
  DEMO: add-on + estación clínica simulada
 ============================================================
  Estación clínica:      http://localhost:5174
  Add-on (interfaz):     http://localhost:5173
  Add-on (API):          http://localhost:8000/docs
  CDS Hooks (discovery): http://localhost:8000/cds-services
 ------------------------------------------------------------
  En la estación: Configuración → Integraciones → Instalar
  (URL del add-on: http://localhost:8000). Ctrl+C para parar los dos.
 ============================================================

EOF

wait
