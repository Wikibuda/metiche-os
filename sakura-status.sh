#!/bin/bash
CONFIG_DIR="$HOME/.openclaw-personal"
PID_FILE="$CONFIG_DIR/sakura.pid"
LOG_FILE="$CONFIG_DIR/sakura.log"

echo "🌸 Estado de Sakura Gateway"
echo "---------------------------"

if [ -f "$PID_FILE" ]; then
    SAKURA_PID=$(cat "$PID_FILE")
    if ps -p "$SAKURA_PID" > /dev/null 2>&1; then
        echo "✅ **Corriendo** (PID: $SAKURA_PID)"
        echo "🌐 URL: http://localhost:18800"
        echo "📊 Puertos:"
        lsof -p "$SAKURA_PID" -a -iTCP -sTCP:LISTEN 2>/dev/null | grep LISTEN || echo "   No se pudieron obtener puertos"
        
        echo ""
        echo "--- Últimas líneas del log ---"
        tail -5 "$LOG_FILE" 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g' || echo "   Log vacío o no accesible"
    else
        echo "❌ **PID existe pero proceso no encontrado**"
        echo "   Limpiando PID obsoleto..."
        rm -f "$PID_FILE"
    fi
else
    echo "🔄 **No está corriendo**"
    echo "   Para iniciar: ./sakura-start.sh"
fi
