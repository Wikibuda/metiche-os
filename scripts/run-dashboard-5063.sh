#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${DASHBOARD_PORT:-5063}"

echo "Iniciando dashboard en http://127.0.0.1:${PORT}/admin-dashboard.html"

cd "${ROOT_DIR}"
exec env DASHBOARD_PORT="${PORT}" node dashboard/dashboard-static.mjs
