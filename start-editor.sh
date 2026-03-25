#!/bin/bash

# Directorio del editor
EDITOR_DIR="/Users/gusluna/.openclaw/workspace-personal/md-mermaid-editor"
PORT=8085

echo "====================================================="
echo "🚀 Iniciando Editor de Markdown y Mermaid"
echo "====================================================="
echo "📁 Directorio: $EDITOR_DIR"
echo "🔌 Puerto local: $PORT"
echo "🌐 URL Local: http://localhost:$PORT"
echo "🔗 Para Cloudflare: Apunta diagram.masamadremonterrey.com a localhost:$PORT"
echo "====================================================="
echo "Presiona Ctrl+C para detener el servidor"
echo ""

# Navegar al directorio y levantar el servidor
cd "$EDITOR_DIR" && python3 -m http.server $PORT
