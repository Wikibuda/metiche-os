#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_DIR="${ROOT_DIR}/data/db"
DB_FILE="${DB_DIR}/metiche_os.db"
PROJECTIONS_DIR="${ROOT_DIR}/projections"

mkdir -p "${DB_DIR}" "${PROJECTIONS_DIR}/bitacora" "${PROJECTIONS_DIR}/summaries"

export DATABASE_URL="${DATABASE_URL:-sqlite:////${DB_FILE}}"
export PROJECTIONS_ROOT="${PROJECTIONS_ROOT:-${PROJECTIONS_DIR}}"

PORT="${PORT:-8091}"
HOST="${HOST:-127.0.0.1}"

if [[ -x "${ROOT_DIR}/.venv311/bin/uvicorn" ]]; then
  UVICORN_BIN="${ROOT_DIR}/.venv311/bin/uvicorn"
elif [[ -x "${ROOT_DIR}/.venv/bin/uvicorn" ]]; then
  UVICORN_BIN="${ROOT_DIR}/.venv/bin/uvicorn"
else
  UVICORN_BIN="uvicorn"
fi

echo "Iniciando metiche-os API en http://${HOST}:${PORT}"
echo "DATABASE_URL=${DATABASE_URL}"
echo "PROJECTIONS_ROOT=${PROJECTIONS_ROOT}"

# Ensure environment variable does not override .env
unset SHOPIFY_ACCESS_TOKEN

exec "${UVICORN_BIN}" app.main:app --host "${HOST}" --port "${PORT}"
