#!/bin/bash
PID="$HOME/.openclaw/sakura.pid"

if [ ! -f "$PID" ]; then
    echo "⚠️  No hay PID guardado"
    exit 1
fi

SAKURA_PID=$(cat "$PID")

if ps -p "$SAKURA_PID" > /dev/null 2>&1; then
    kill "$SAKURA_PID"
    echo "🌸 Sakura Gateway detenido (PID: $SAKURA_PID)"
    rm "$PID"
else
    echo "⚠️  Proceso no encontrado (PID: $SAKURA_PID)"
    rm "$PID"
fi
