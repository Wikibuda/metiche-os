#!/bin/bash
# Script para iniciar Dashboard Admin en puerto 5050

cd "$(dirname "$0")"
export DASHBOARD_PORT=5050

# Verificar si Node.js está instalado
if ! command -v node &> /dev/null; then
    echo "❌ Node.js no está instalado"
    exit 1
fi

# Verificar si el archivo del servidor existe
if [ ! -f "dashboard-server.mjs" ]; then
    echo "❌ dashboard-server.mjs no encontrado"
    exit 1
fi

echo "🚀 Iniciando Dashboard Admin en puerto 5050..."
echo "📊 Acceso: http://localhost:5050"
echo "🌐 Público: https://dashboard.masamadremonterrey.com"

# Ejecutar servidor
node dashboard-server.mjs