#!/usr/bin/env bash
set -euo pipefail

LABEL="${LABEL:-com.metiche.runbook.daily}"
PLIST_PATH="${HOME}/Library/LaunchAgents/${LABEL}.plist"

if command -v launchctl >/dev/null 2>&1; then
  launchctl bootout "gui/$(id -u)/${LABEL}" >/dev/null 2>&1 || true
  launchctl disable "gui/$(id -u)/${LABEL}" >/dev/null 2>&1 || true
fi

if [[ -f "${PLIST_PATH}" ]]; then
  rm -f "${PLIST_PATH}"
fi

echo "LaunchAgent removido:"
echo "- LABEL=${LABEL}"
echo "- PLIST_PATH=${PLIST_PATH}"
