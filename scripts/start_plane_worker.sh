#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! command -v docker >/dev/null 2>&1; then
  echo "Falta dependencia requerida: docker"
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "Falta dependencia requerida: python3"
  exit 1
fi

if ! docker ps >/dev/null 2>&1; then
  echo "Docker no esta corriendo. Abrelo primero."
  exit 1
fi

cd "${ROOT_DIR}"

echo "Docker activo"
echo "Arrancando worker de Plane..."
exec python3 -m app.cli.main run-worker
