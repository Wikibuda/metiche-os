#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/docker-compose.yml"
COMPOSE_PROJECT="${COMPOSE_PROJECT:-metiche-os}"
API_URL="${API_URL:-http://127.0.0.1:8091/health}"
DASHBOARD_PORT="${DASHBOARD_PORT:-5063}"
DASHBOARD_URL="http://127.0.0.1:${DASHBOARD_PORT}/admin-dashboard.html"
DASHBOARD_OVERVIEW_URL="http://127.0.0.1:${DASHBOARD_PORT}/api/labs/metiche-os/overview"
DASHBOARD_PID_FILE="${ROOT_DIR}/.dashboard-5063.pid"
DASHBOARD_LOG_FILE="${ROOT_DIR}/data/dashboard-5063.log"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Falta dependencia requerida: $1"
    exit 1
  fi
}

wait_http_200() {
  local url="$1"
  local tries="${2:-30}"
  local wait_s="${3:-1}"
  local i
  for ((i=1; i<=tries; i++)); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep "$wait_s"
  done
  return 1
}

require_cmd docker
require_cmd node
require_cmd curl

mkdir -p "${ROOT_DIR}/data"

echo "1) Levantando app + worker (compose project: ${COMPOSE_PROJECT})..."
docker compose -p "${COMPOSE_PROJECT}" -f "${COMPOSE_FILE}" up -d --build app worker

echo "2) Reiniciando dashboard en puerto ${DASHBOARD_PORT}..."
if [[ -f "${DASHBOARD_PID_FILE}" ]]; then
  OLD_PID="$(cat "${DASHBOARD_PID_FILE}" 2>/dev/null || true)"
  if [[ -n "${OLD_PID}" ]] && kill -0 "${OLD_PID}" 2>/dev/null; then
    kill "${OLD_PID}" || true
    sleep 1
  fi
fi

PORT_PIDS="$(lsof -tiTCP:${DASHBOARD_PORT} -sTCP:LISTEN 2>/dev/null || true)"
if [[ -n "${PORT_PIDS}" ]]; then
  kill ${PORT_PIDS} || true
  sleep 1
fi

(
  cd "${ROOT_DIR}"
  nohup env DASHBOARD_PORT="${DASHBOARD_PORT}" node dashboard/dashboard-server.mjs \
    > "${DASHBOARD_LOG_FILE}" 2>&1 &
  echo $! > "${DASHBOARD_PID_FILE}"
)

echo "3) Validando salud de servicios..."
if ! wait_http_200 "${API_URL}" 45 1; then
  echo "API no respondió OK en ${API_URL}"
  exit 1
fi

if ! wait_http_200 "${DASHBOARD_OVERVIEW_URL}" 45 1; then
  echo "Dashboard/API bridge no respondió OK en ${DASHBOARD_OVERVIEW_URL}"
  exit 1
fi

echo ""
echo "Stack consolidado arriba:"
echo "- API:       http://127.0.0.1:8091/docs"
echo "- Dashboard: ${DASHBOARD_URL}"
echo "- Logs dash: ${DASHBOARD_LOG_FILE}"
echo "- PID dash:  ${DASHBOARD_PID_FILE}"
