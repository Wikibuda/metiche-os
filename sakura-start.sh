#!/bin/bash
# Script Zen para iniciar Sakura Gateway
CONFIG_DIR="$HOME/.openclaw-personal"
LOG_FILE="$CONFIG_DIR/sakura.log"
PID_FILE="$CONFIG_DIR/sakura.pid"

echo "🌸 Preparando entorno Sakura..."

# Verificar si ya está corriendo
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo "🍃 Sakura ya está floreciendo (PID: $OLD_PID)"
        echo "🌐 URL: http://localhost:18800"
        exit 0
    else
        echo "🍂 Proceso anterior terminó, limpiando..."
        rm -f "$PID_FILE"
    fi
fi

# Limpiar log anterior
> "$LOG_FILE"

echo "🌱 Iniciando Sakura Gateway..."

# Iniciar con datos separados
OPENCLAW_DATA="$CONFIG_DIR" openclaw gateway run >> "$LOG_FILE" 2>&1 &
SAKURA_PID=$!

# Esperar un momento para que inicie
sleep 2

# Verificar si está vivo
if ps -p "$SAKURA_PID" > /dev/null 2>&1; then
    echo "$SAKURA_PID" > "$PID_FILE"
    echo "🌸 Sakura Gateway floreciendo (PID: $SAKURA_PID)"
    echo "📝 Logs: $LOG_FILE"
    echo "🌐 URL: http://localhost:18800"
    echo "🛑 Para detener: ./sakura-stop.sh"
    
    # Mostrar primeras líneas del log
    echo ""
    echo "--- Últimas líneas del log ---"
    tail -10 "$LOG_FILE" | sed 's/\x1b\[[0-9;]*m//g'
else
    echo "❌ Error al iniciar Sakura"
    echo "Revisa el log: $LOG_FILE"
    exit 1
fi
