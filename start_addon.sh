#!/usr/bin/env bash
# Arranca SOLO el add-on CardioAlert AP: la API (puerto 8000) y su interfaz (puerto 5173).
# No arranca la estación clínica simulada (para eso: ./start_simulador.sh).
set -e
cd "$(dirname "$0")"

# --- Python (>= 3.10): el del entorno virtual .venv si existe; si no, el del PATH ---
# Se prueba cada candidato: en Windows, "python3" puede ser el acceso directo vacío de la Microsoft Store.
PY=""
for candidato in "$PWD/.venv/bin/python" "$PWD/.venv/Scripts/python.exe" python3 python; do
  if "$candidato" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >/dev/null 2>&1; then
    PY="$candidato"
    break
  fi
done
if [ -z "$PY" ]; then
  echo "[ERROR] Hace falta Python 3.10 o superior. Instálelo, o cree un entorno virtual: python3 -m venv .venv" >&2
  exit 1
fi
if ! "$PY" -c "import fastapi, uvicorn, yaml, ruamel.yaml, openpyxl" 2>/dev/null; then
  echo "Instalando las dependencias de Python (requirements.txt)..."
  "$PY" -m pip install -r requirements.txt
fi

# --- Node.js (>= 20) ---
if ! command -v npm >/dev/null 2>&1; then
  echo "[ERROR] No se encuentra npm. Instale Node.js 20 o superior: https://nodejs.org" >&2
  exit 1
fi
if [ ! -d frontend/node_modules/vite ]; then
  echo "Instalando las dependencias de la interfaz (frontend)..."
  (cd frontend && npm install)
fi

# --- El puerto 8000 tiene que estar libre ---
if ! "$PY" -c "import socket, sys; s = socket.socket(); sys.exit(0 if s.connect_ex(('127.0.0.1', 8000)) else 1)"; then
  echo "[ERROR] El puerto 8000 ya está en uso: el add-on ya está arrancado, o lo ocupa otro programa." >&2
  exit 1
fi

# La API anuncia esta URL a la estación clínica (discovery de CDS Hooks)
export CARDIOALERT_UI_URL="http://localhost:5173"

cat <<'EOF'

 ============================================================
  CardioAlert AP - ADD-ON
 ============================================================
  Interfaz:              http://localhost:5173
  API (documentación):   http://localhost:8000/docs
  CDS Hooks (discovery): http://localhost:8000/cds-services
 ------------------------------------------------------------
  URL para instalar el add-on en la estación clínica:
                         http://localhost:8000
  Para parar: Ctrl+C.
 ============================================================

EOF

# La API en segundo plano; la interfaz en primer plano. Al salir se para también la API.
"$PY" -m uvicorn api.main:app --port 8000 &
API_PID=$!
trap 'kill "$API_PID" 2>/dev/null || true' EXIT INT TERM
cd frontend
npm run dev
