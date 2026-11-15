#!/usr/bin/env bash
# Arranca SOLO la estación clínica simulada (puerto 5174). No necesita Python ni el add-on.
# Los datos de los pacientes son de la estación (simulador/datos) y los sirve su servidor FHIR.
set -e
cd "$(dirname "$0")"

# --- Node.js (>= 20) ---
if ! command -v npm >/dev/null 2>&1; then
  echo "[ERROR] No se encuentra npm. Instale Node.js 20 o superior: https://nodejs.org" >&2
  exit 1
fi
if [ ! -f simulador/datos/demo/fhir/P001.json ]; then
  echo "[ERROR] Faltan los datos sintéticos (simulador/datos/demo/fhir). Ejecute: python scripts/generate_patients.py" >&2
  exit 1
fi
if [ ! -d simulador/node_modules/vite ]; then
  echo "Instalando las dependencias del simulador..."
  (cd simulador && npm install)
fi

cat <<'EOF'

 ============================================================
  ESTACIÓN CLÍNICA SIMULADA  (datos sintéticos)
 ============================================================
  Estación clínica:      http://localhost:5174
  Su servidor FHIR:      http://localhost:5174/fhir/metadata
  Cupo activo:           Configuración → Cupo / centro
                         (demo de 100 o realista de 1.500)
 ------------------------------------------------------------
  Por defecto NO tiene ningún add-on instalado.
  Para instalar CardioAlert AP: Configuración → Integraciones,
  URL del add-on http://localhost:8000 (arránquelo con ./start_addon.sh).
  Para parar: Ctrl+C.
 ============================================================

EOF

cd simulador
npm run dev
