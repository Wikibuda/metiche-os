#!/bin/bash
# Script para iniciar MD/Mermaid Editor en puerto 8081

cd "$(dirname "$0")/md-mermaid-editor"

# Verificar si Node.js está instalado
if ! command -v node &> /dev/null; then
    echo "❌ Node.js no está instalado"
    exit 1
fi

# Verificar si el archivo del servidor existe
if [ ! -f "server.mjs" ]; then
    echo "❌ server.mjs no encontrado"
    exit 1
fi

echo "🎨 Iniciando MD/Mermaid Editor en puerto 8081..."
echo "📝 Acceso: http://localhost:8081"
echo "🌐 Público: https://diagram.masamadremonterrey.com"

# Ejecutar servidor
node server.mjs