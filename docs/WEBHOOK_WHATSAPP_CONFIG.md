# Configuracion de Webhook WhatsApp para Metiche

## Resumen

OpenClaw reenvia automaticamente los mensajes entrantes de WhatsApp al webhook de Metiche:

`http://localhost:8091/webhooks/openclaw/whatsapp`

## Detalles tecnicos

- Hook: `whatsapp-webhook-forwarder`
- Evento: `message:received`
- Filtro: solo canal `whatsapp`
- Ubicacion en host OpenClaw: `~/.openclaw/hooks/whatsapp-webhook-forwarder/`

Payload esperado:

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

## Verificacion operativa

1. Verificar hook activo:

```bash
openclaw hooks list
```

2. Probar endpoint de Metiche:

```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"timestamp":"2026-04-13T10:30:00Z","from":"+521234567890","content":"Test","channel":"whatsapp","metadata":{"message_id":"test123","type":"text"}}' \
  http://localhost:8091/webhooks/openclaw/whatsapp
```

3. Probar mensaje real:
- Enviar mensaje al WhatsApp Business.
- Revisar logs de OpenClaw:

```bash
tail -f /tmp/openclaw/openclaw-*.log | grep WhatsAppWebhook
```

- Confirmar evento en dashboard de Metiche.

## Troubleshooting

- Si el hook no aparece:

```bash
ls -la ~/.openclaw/hooks/whatsapp-webhook-forwarder/
grep -A5 "whatsapp-webhook-forwarder" ~/.openclaw/openclaw.json
openclaw gateway restart
```

- Si el webhook no llega:

```bash
curl -I http://localhost:8091
tail -f /tmp/openclaw/openclaw-*.log | grep -E "WhatsAppWebhook|webhook"
```

## Notas

- No requiere autenticacion para entorno localhost.
- Incluye mensajes individuales y grupales.
- Errores de red del hook se registran sin bloquear el flujo normal.
