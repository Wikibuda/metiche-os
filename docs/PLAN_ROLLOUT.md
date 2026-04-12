# PLAN_ROLLOUT - Semana 4

Este documento define el rollout operativo para pasar de modo sandbox a operación productiva por canal.

## 1) Desactivar Sandbox por Canal

### WhatsApp

1. Verifica que el número destino esté en safelist (`WHATSAPP_ALLOWED_NUMBERS`).
2. Configura `WHATSAPP_SANDBOX_MODE=false` en `.env` del entorno objetivo.
3. Reinicia API/worker:
   - `./scripts/run-api-8091.sh`
   - `./scripts/run-stack-consolidado.sh` (si aplica stack completo)
4. Valida estado:
   - `GET /dashboard/channels/status`
   - `GET /dashboard/channels/events?channel=whatsapp&limit=10`
5. Ejecuta smoke de canal:
   - `PYTHONPATH=. ./.venv/bin/python scripts/whatsapp_adapter_smoke.py`

### Telegram

1. Verifica que el `chat_id` destino esté en safelist (`TELEGRAM_ALLOWED_IDS`).
2. Configura `TELEGRAM_SANDBOX_MODE=false` en `.env` del entorno objetivo.
3. Reinicia API/worker.
4. Valida estado:
   - `GET /dashboard/channels/status`
   - `GET /dashboard/channels/events?channel=telegram&limit=10`
5. Ejecuta smoke de canal:
   - `PYTHONPATH=. ./.venv/bin/python scripts/telegram_adapter_smoke.py`

## 2) Ampliar Safelist a Nuevos Números

### WhatsApp

1. Edita `.env` y agrega número en `WHATSAPP_ALLOWED_NUMBERS` (CSV).
2. Formato recomendado: `+52XXXXXXXXXX` con código país.
3. Reinicia servicio para recargar configuración.
4. Valida enviando mensaje de prueba con smoke o flujo controlado.

### Telegram

1. Edita `.env` y agrega `chat_id` en `TELEGRAM_ALLOWED_IDS` (CSV).
2. Usa IDs numéricos exactos (sin alias ni username).
3. Reinicia servicio para recargar configuración.
4. Valida envío de prueba y revisa eventos del canal.

## 3) Consideraciones de Seguridad

- Mantén sandbox activo por defecto en entornos no productivos.
- Aplica principio de mínimo privilegio en safelists.
- Versiona cambios de `.env` mediante plantillas y no subas secretos al repo.
- Registra excepciones de envío y bloqueos de seguridad (`*_security_block`) para auditoría.
- Monitorea cambios de estado rojo en canales y define runbook de escalamiento.

## 4) Consideraciones de Monitorización

- Usa `GET /dashboard/channels/status` para health agregado por canal.
- Usa `GET /dashboard/channels/events` para inspección de eventos recientes.
- Revisa narrativa (`GET /narrative`) para trazabilidad de decisiones de swarm.
- Ejecuta batería mínima de smokes antes y después de cambios en config de canal:
  - `whatsapp_adapter_smoke.py`
  - `telegram_adapter_smoke.py`
  - `channels_dashboard_smoke.py`
  - `swarm_whatsapp_e2e_smoke.py`
  - `swarm_multichannel_e2e_smoke.py`

## 5) Criterio de Go/No-Go

- Go:
  - Todos los smokes pasan.
  - Dashboard muestra ambos canales coherentes.
  - No hay eventos críticos recurrentes en últimos 15 minutos.
- No-Go:
  - Fallas repetidas de dispatch.
  - Bloqueos de safelist inesperados.
  - Canal en rojo sin recuperación tras ventana de observación.
