#!/bin/bash
# Script Zen para detener Sakura Gateway
CONFIG_DIR="$HOME/.openclaw-personal"
PID_FILE="$CONFIG_DIR/sakura.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "🍂 No hay registro de Sakura Gateway corriendo"
    exit 0
fi

SAKURA_PID=$(cat "$PID_FILE")

if ps -p "$SAKURA_PID" > /dev/null 2>&1; then
    echo "🍃 Deteniendo Sakura Gateway (PID: $SAKURA_PID)..."
    kill "$SAKURA_PID"
    sleep 1
    
    if ps -p "$SAKURA_PID" > /dev/null 2>&1; then
        echo "⚠️  Forzando terminación..."
        kill -9 "$SAKURA_PID"
    fi
    
    echo "🌸 Sakura Gateway se ha marchitado"
else
    echo "🍂 El proceso ya no existe (PID: $SAKURA_PID)"
fi

rm -f "$PID_FILE"
