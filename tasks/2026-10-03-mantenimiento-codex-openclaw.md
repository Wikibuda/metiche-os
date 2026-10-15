
---

# 📄 DOCUMENTO 2: Briefing para Metiche

**Este es el que le pasas a Metiche.** Guárdalo como:
`~/.openclaw/workspace/metiche-os-migrated-20260408/tasks/2026-10-03-mantenimiento-codex-openclaw.md`

```markdown
# Task para Metiche: Programar mantenimiento automático Codex + OpenClaw

**De:** Gus
**Para:** Metiche (agente principal, orquestador)
**Fecha:** 3 de octubre, 2026
**Prioridad:** Media-alta (evita recurrencia de un problema que costó ~$166 USD/mes)
**Contexto completo:** `docs/postmortem-limpieza-2026-10-03.md`

---

## TL;DR

Hoy limpiamos manualmente ~4.7 GB de basura acumulada en OpenClaw y Codex
(ver postmortem adjunto). El sistema quedó estable, pero **sin mantenimiento
automático vuelve a acumularse**. Necesito que diseñes, implementes y programes
la estrategia de mantenimiento recurrente.

Tú tienes el contexto del negocio y de la operación diaria. Yo tengo los
detalles técnicos del postmortem. Decide tú:

- Frecuencia y horarios óptimos (evitar solapamiento con crons existentes)
- Niveles de retención según criticidad de cada dato
- Si conviene un script único orquestador o crons independientes
- Si integrarlo al dashboard de inventario que ya existe
- Cómo alertar si algo falla

---

## Contexto técnico (lo que hay que saber)

### Rutas críticas

| Ruta | Qué es | Tamaño actual |
|---|---|---|
| `~/.openclaw/agents/*/agent/` | DBs y estado de cada agente OpenClaw | variable |
| `~/.openclaw/agents/*/agent/*/sessions/` | Transcripts de sesiones | variable |
| `~/.openclaw/agents/codex/agent/codex-home/` | HOME aislado del agente codex | ~15 MB |
| `~/.codex/` | Codex Desktop + CLI (parcheado DeepSeek) | 695 MB |
| `~/.codex/sessions/` | Transcripts de Codex | 172 MB |
| `~/.codex/thread_history_1.sqlite` | Historial real de hilos | 72 MB |
| `~/.codex/logs_2.sqlite` | Logs internos | 14 MB |
| `~/.codex/computer-use/Codex Computer Use.app` | App instalada | 72 MB |
| `~/.codex/packages/app-server-daemon/` | Daemon activo | 318 MB |

### 🚨 Restricciones CRÍTICAS (no negociar)

**NUNCA borrar ni modificar:**

1. **`~/.codex/config.toml`** — Config del parche DeepSeek (model_provider,
   model, [model_providers.deepseek], bearer token)
2. **`~/.codex/models.json`** — Catálogo de modelos DeepSeek declarados
3. **`~/.codex/backup-deepseek/`** — Backup oficial del parche (red de
   seguridad para restauración)
4. **`~/.codex/.codex-global-state.json`** — Estado global de la app
5. **`~/.codex/state_5.sqlite`, `thread_history_1.sqlite`, `memories_1.sqlite`,
   `goals_1.sqlite`** — Estado e historial real. Solo VACUUM.
6. **`~/.codex/packages/app-server-daemon/current/`** y la versión activa
   (hoy `0.160.0`) — Daemon en uso
7. **`~/.codex/computer-use/*.app`** — Aplicación instalada
8. **`~/.codex/plugins/.plugin-appserver/`** (excepto subcarpetas
   claramente temporales) — Plugins activos
9. **`~/.openclaw/agents/masa-madre*`** — Bot de atención a clientes (excluido
   por política)

**Contexto del parche DeepSeek:**
El parche fue aplicado siguiendo la documentación oficial de DeepSeek. Modifica
ÚNICAMENTE `config.toml` y `models.json`. NO toca binarios. Los logs confirman
que funciona (`model=deepseek-v4-flash` en cada turno). Cualquier script que
toque esos dos archivos DEBE ser rechazado.

---

## Lo que hay que construir

### 1. Script de mantenimiento OpenClaw

**Ubicación sugerida:** `~/.openclaw/workspace/metiche-os-migrated-20260408/scripts/maintenance-openclaw.sh`

Debe hacer:

- `openclaw sessions cleanup --all-agents --enforce` diario
- Borrar `*.jsonl` con >14 días en `agents/*/agent/*/sessions/`,
  **excluyendo** `*masa-madre*`
- Limpiar `~/.openclaw/agents/codex/agent/codex-home/.tmp/*` con >3 días
- Limpiar `~/.openclaw/agents/codex/agent/codex-home/cache/*`
- Log de salida a `~/.openclaw/logs/maintenance.log`
- Reportar tamaño antes/después por agente

### 2. Script de mantenimiento Codex

**Ubicación sugerida:** `~/.openclaw/workspace/metiche-os-migrated-20260408/scripts/maintenance-codex.sh`

Debe hacer:

- Borrar `~/.codex/.tmp/*` (con >3 días)
- Borrar `~/.codex/cache/*`
- Podar logs: `DELETE FROM logs WHERE level IN ('DEBUG','TRACE')` y
  `DELETE FROM logs WHERE level='INFO' AND ts < now()-7d`, seguido de
  `VACUUM` y `PRAGMA wal_checkpoint(TRUNCATE)`
- Borrar `~/.codex/sessions/**/*.jsonl` con >14 días
- Borrar WALs huérfanos (más de 30 días sin tocar, sin `.sqlite` base
  correspondiente activo)
- **Verificar** que `config.toml` y `models.json` sigan intactos al final
  (hash o grep de `deepseek`)
- Log de salida

### 3. Estrategia de retención (decide tú)

Mi sugerencia de partida (ajústala a la operación):

| Dato | Retención |
|---|---|
| `sessions/*.jsonl` OpenClaw (excepto masa-madre) | 14 días |
| `sessions/*.jsonl` Codex | 14 días |
| Logs Codex DEBUG/TRACE | 3 días |
| Logs Codex INFO | 7 días |
| Logs Codex WARN/ERROR | 30 días |
| `.tmp/` y `cache/` (ambos) | 3 días |
| DB `logs_2.sqlite` | VACUUM semanal |
| DB `thread_history_1.sqlite` | VACUUM mensual |

### 4. Programación (cron)

**Sugerencia inicial** — ajústala para no chocar con crons existentes:

```cron
# OpenClaw — diario 3:00 AM
0 3 * * * ~/.openclaw/workspace/metiche-os-migrated-20260408/scripts/maintenance-openclaw.sh >> ~/.openclaw/logs/maintenance.log 2>&1

# Codex — diario 3:30 AM
30 3 * * * ~/.openclaw/workspace/metiche-os-migrated-20260408/scripts/maintenance-codex.sh >> ~/.openclaw/logs/maintenance.log 2>&1