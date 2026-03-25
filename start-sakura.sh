#!/bin/bash
# Script para iniciar gateway Sakura (personal)
CONFIG="$HOME/.openclaw/personal-config.json"
LOG="$HOME/.openclaw/sakura.log"
PID="$HOME/.openclaw/sakura.pid"

echo "🌸 Iniciando Sakura Gateway (puerto 18800)..."

# Verificar si ya está corriendo
if [ -f "$PID" ]; then
    OLD_PID=$(cat "$PID")
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo "⚠️  Ya está corriendo (PID: $OLD_PID)"
        exit 1
    fi
fi

# Iniciar gateway en background
OPENCLAW_CONFIG="$CONFIG" openclaw gateway run >> "$LOG" 2>&1 &
NEW_PID=$!

# Guardar PID
echo $NEW_PID > "$PID"

echo "✅ Gateway iniciado (PID: $NEW_PID)"
echo "📝 Logs: $LOG"
echo "🌐 URL: http://localhost:18800"
echo "🛑 Para detener: kill $NEW_PID"
