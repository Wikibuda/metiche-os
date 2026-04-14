#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:8091}"
TELEGRAM_REAL_TARGET="${TELEGRAM_REAL_TARGET:-}"
RUN_TELEGRAM_SMOKE="${RUN_TELEGRAM_SMOKE:-1}"
RUN_WHATSAPP_SMOKE="${RUN_WHATSAPP_SMOKE:-1}"
CLEANUP_RUNNING="${CLEANUP_RUNNING:-0}"
HTTP_TIMEOUT_SECONDS="${HTTP_TIMEOUT_SECONDS:-35}"
PYTHON_BIN="${PYTHON_BIN:-${ROOT_DIR}/.venv/bin/python}"

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

require_cmd curl
require_cmd python3
require_file "${PYTHON_BIN}"
require_file "${ROOT_DIR}/scripts/telegram_real_smoke.py"
require_file "${ROOT_DIR}/scripts/whatsapp_real_smoke.py"

echo "== Runbook Diario: Channels =="
echo "ROOT_DIR=${ROOT_DIR}"
echo "API_BASE_URL=${API_BASE_URL}"
echo ""

echo "1) Salud base"
curl -fsS "${API_BASE_URL}/health" >/dev/null
echo "OK health"
echo ""

echo "2) Estado de canales"
python3 - "${API_BASE_URL}" <<'PY'
import json
import sys
import urllib.request

base = sys.argv[1].rstrip("/")
with urllib.request.urlopen(base + "/dashboard/channels/status?event_preview_limit=5&inactivity_minutes=60", timeout=35) as r:
    data = json.loads(r.read().decode())

for item in data.get("channels", []):
    print(f"- {item.get('channel')}: {item.get('status')} (events={item.get('summary', {}).get('total_events')})")
PY
echo ""

if [[ "${RUN_TELEGRAM_SMOKE}" == "1" ]]; then
  echo "3) Smoke real Telegram"
  if [[ -z "${TELEGRAM_REAL_TARGET}" ]]; then
    echo "ERROR: Define TELEGRAM_REAL_TARGET para ejecutar telegram_real_smoke.py"
    exit 1
  fi
  (
    cd "${ROOT_DIR}"
    METICHE_API_BASE_URL="${API_BASE_URL}" \
    TELEGRAM_REAL_TARGET="${TELEGRAM_REAL_TARGET}" \
    SMOKE_HTTP_TIMEOUT_SECONDS="${HTTP_TIMEOUT_SECONDS}" \
    PYTHONPATH=. "${PYTHON_BIN}" scripts/telegram_real_smoke.py
  )
  echo ""
fi

if [[ "${RUN_WHATSAPP_SMOKE}" == "1" ]]; then
  echo "4) Smoke real WhatsApp"
  (
    cd "${ROOT_DIR}"
    PYTHONPATH=. "${PYTHON_BIN}" scripts/whatsapp_real_smoke.py
  )
  echo ""
fi

echo "5) Verificacion de eventos recientes"
python3 - "${API_BASE_URL}" <<'PY'
import json
import sys
import urllib.request

base = sys.argv[1].rstrip("/")
for channel in ("telegram", "whatsapp"):
    with urllib.request.urlopen(base + f"/dashboard/channels/events?channel={channel}&limit=8", timeout=35) as r:
        data = json.loads(r.read().decode())
    print(f"[{channel}] total={data.get('total')}")
    for item in data.get("items", [])[:3]:
        payload = item.get("payload") or {}
        print(
            "  ",
            item.get("event_type"),
            "success=" + str(payload.get("success")),
            "at=" + str(item.get("occurred_at")),
        )
PY
echo ""

echo "6) Running en tablero"
python3 - "${API_BASE_URL}" "${CLEANUP_RUNNING}" <<'PY'
import json
import sys
import urllib.request

base = sys.argv[1].rstrip("/")
cleanup = sys.argv[2] == "1"

with urllib.request.urlopen(base + "/dashboard/tasks?status=running&limit=200", timeout=35) as r:
    data = json.loads(r.read().decode())
tasks = data.get("tasks", [])
print("running_count=", len(tasks))

if cleanup and tasks:
    for task in tasks:
        task_id = task["task_id"]
        req = urllib.request.Request(
            base + f"/dashboard/tasks/{task_id}/action",
            method="POST",
            headers={"Content-Type": "application/json"},
            data=json.dumps({"action": "cancel"}).encode(),
        )
        with urllib.request.urlopen(req, timeout=35) as rr:
            payload = json.loads(rr.read().decode())
        print("cancelled=", payload.get("task_id"), "ok=", payload.get("ok"))
    with urllib.request.urlopen(base + "/dashboard/tasks?status=running&limit=200", timeout=35) as r2:
        after = json.loads(r2.read().decode()).get("tasks", [])
    print("remaining_running=", len(after))
elif cleanup:
    print("No hay tareas en running para cancelar.")
else:
    print("Cleanup desactivado. Usa CLEANUP_RUNNING=1 para cancelar running.")
PY
echo ""

echo "Runbook completado."
