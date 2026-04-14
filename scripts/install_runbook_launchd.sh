#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNBOOK_SCRIPT="${ROOT_DIR}/scripts/runbook_daily_channels.sh"
PYTHON_BIN_DEFAULT="${ROOT_DIR}/.venv/bin/python"

LABEL="${LABEL:-com.metiche.runbook.daily}"
HOUR="${HOUR:-9}"
MINUTE="${MINUTE:-0}"
API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:8091}"
TELEGRAM_REAL_TARGET="${TELEGRAM_REAL_TARGET:-}"
RUN_TELEGRAM_SMOKE="${RUN_TELEGRAM_SMOKE:-1}"
RUN_WHATSAPP_SMOKE="${RUN_WHATSAPP_SMOKE:-1}"
CLEANUP_RUNNING="${CLEANUP_RUNNING:-1}"
PYTHON_BIN="${PYTHON_BIN:-${PYTHON_BIN_DEFAULT}}"
LOAD_NOW="${LOAD_NOW:-1}"

PLIST_PATH="${HOME}/Library/LaunchAgents/${LABEL}.plist"
LOG_DIR="${ROOT_DIR}/data"
STDOUT_LOG="${LOG_DIR}/runbook_daily_channels.launchd.out.log"
STDERR_LOG="${LOG_DIR}/runbook_daily_channels.launchd.err.log"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Falta dependencia requerida: $1"
    exit 1
  fi
}

require_file() {
  if [[ ! -f "$1" ]]; then
    echo "No existe archivo requerido: $1"
    exit 1
  fi
}

validate_int_range() {
  local value="$1"
  local min="$2"
  local max="$3"
  local label="$4"
  if ! [[ "$value" =~ ^[0-9]+$ ]]; then
    echo "Valor invalido para ${label}: ${value}"
    exit 1
  fi
  if (( value < min || value > max )); then
    echo "Rango invalido para ${label}: ${value} (esperado ${min}-${max})"
    exit 1
  fi
}

require_cmd launchctl
require_cmd plutil
require_file "${RUNBOOK_SCRIPT}"
require_file "${PYTHON_BIN}"
validate_int_range "${HOUR}" 0 23 "HOUR"
validate_int_range "${MINUTE}" 0 59 "MINUTE"

if [[ "${RUN_TELEGRAM_SMOKE}" == "1" && -z "${TELEGRAM_REAL_TARGET}" ]]; then
  echo "ERROR: define TELEGRAM_REAL_TARGET para RUN_TELEGRAM_SMOKE=1"
  exit 1
fi

mkdir -p "${HOME}/Library/LaunchAgents"
mkdir -p "${LOG_DIR}"

cat > "${PLIST_PATH}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${RUNBOOK_SCRIPT}</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${ROOT_DIR}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>API_BASE_URL</key>
    <string>${API_BASE_URL}</string>
    <key>TELEGRAM_REAL_TARGET</key>
    <string>${TELEGRAM_REAL_TARGET}</string>
    <key>RUN_TELEGRAM_SMOKE</key>
    <string>${RUN_TELEGRAM_SMOKE}</string>
    <key>RUN_WHATSAPP_SMOKE</key>
    <string>${RUN_WHATSAPP_SMOKE}</string>
    <key>CLEANUP_RUNNING</key>
    <string>${CLEANUP_RUNNING}</string>
    <key>PYTHON_BIN</key>
    <string>${PYTHON_BIN}</string>
  </dict>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>${HOUR}</integer>
    <key>Minute</key>
    <integer>${MINUTE}</integer>
  </dict>
  <key>RunAtLoad</key>
  <false/>
  <key>StandardOutPath</key>
  <string>${STDOUT_LOG}</string>
  <key>StandardErrorPath</key>
  <string>${STDERR_LOG}</string>
</dict>
</plist>
EOF

plutil -lint "${PLIST_PATH}" >/dev/null

if [[ "${LOAD_NOW}" == "1" ]]; then
  launchctl bootout "gui/$(id -u)/${LABEL}" >/dev/null 2>&1 || true
  launchctl bootstrap "gui/$(id -u)" "${PLIST_PATH}"
  launchctl enable "gui/$(id -u)/${LABEL}" || true
fi

echo "LaunchAgent instalado."
echo "LABEL=${LABEL}"
echo "PLIST_PATH=${PLIST_PATH}"
echo "Hora diaria: $(printf "%02d:%02d" "${HOUR}" "${MINUTE}")"
echo "Logs:"
echo "- ${STDOUT_LOG}"
echo "- ${STDERR_LOG}"
echo "Probar manual:"
echo "launchctl kickstart -k gui/$(id -u)/${LABEL}"
