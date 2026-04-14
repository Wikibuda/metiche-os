# OpenClaw -> Metiche (WhatsApp Inbound)

## Endpoint local

- Metodo: `POST`
- URL: `http://<metiche-host>:8091/webhooks/openclaw/whatsapp`
- Content-Type: `application/json`

Payload minimo soportado:

```json
{
  "channel": "whatsapp",
  "phone_number": "+5215512345678",
  "text": "Hola bot"
}
```

Tambien soporta variantes comunes en sobres `payload`, `event` y `data`, y campos `from`/`from_number` + `text`/`content`/`body`/`message`.

Payload usado actualmente por el hook `whatsapp-webhook-forwarder` de OpenClaw:

```json
{
  "timestamp": "2026-04-13T10:00:00Z",
  "from": "+521234567890",
  "content": "Texto del mensaje",
  "channel": "whatsapp",
  "metadata": {
    "message_id": "abc123",
    "type": "text",
    "sender_id": "...",
    "sender_name": "...",
    "group_id": "...",
    "is_group": false
  }
}
```

## Resultado esperado en Metiche

- Crea una `task` de traza para el flujo inbound.
- Registra evento `whatsapp_message_received` en `task_events`.
- Actualiza `channel_memory` con el ultimo mensaje entrante.
- El dashboard de canales mostrara actividad reciente en WhatsApp.

## Configuracion en OpenClaw

Configura un outgoing webhook para mensajes entrantes de WhatsApp apuntando a:

`http://<metiche-host>:8091/webhooks/openclaw/whatsapp`

## Alternativa si webhook no esta disponible

Si OpenClaw no puede emitir webhook saliente en tu despliegue actual, usa polling:

1. Consumir periodicamente (cada 5-15 s) el feed/API de mensajes entrantes de OpenClaw.
2. Por cada mensaje nuevo, reenviarlo al endpoint de Metiche con el payload minimo.
3. Guardar ultimo cursor/timestamp en el proceso de polling para evitar duplicados.
