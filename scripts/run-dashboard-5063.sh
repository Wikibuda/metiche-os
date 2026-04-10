#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${DASHBOARD_PORT:-5063}"
API_BASE="${METICHE_OS_BASE:-http://127.0.0.1:8091}"

echo "Iniciando dashboard en http://127.0.0.1:${PORT}/"
echo "Conectando a API base: ${API_BASE}"
echo "UI operativo: http://127.0.0.1:${PORT}/"
echo "UI enjambres: http://127.0.0.1:${PORT}/swarm-console.html"

cd "${ROOT_DIR}"
exec env DASHBOARD_PORT="${PORT}" METICHE_OS_BASE="${API_BASE}" node dashboard/dashboard-server.mjs
