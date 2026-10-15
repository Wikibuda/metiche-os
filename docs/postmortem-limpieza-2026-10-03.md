# Post-mortem: Limpieza masiva de sesiones OpenClaw + Codex
**Fecha:** 3 de octubre, 2026
**Máquina:** raquel (Mac, aarch64-apple-darwin)
**Usuario:** gusluna
**Ejecutado por:** Gus + Claude (asistencia técnica)

---

## 1. Problema reportado

El dashboard "Inventario de sesiones — Mac + Ubuntu 2026" mostraba:

- **2 máquinas, $166.28 USD** de gasto estimado (DeepSeek)
- **23,010 sesiones · 8.44 B tokens**
- **Mac: $141.67 / 22,422 sesiones / 6.93 B tokens**
- **Ubuntu: $24.61 / 588 sesiones / 1.51 B tokens**
- Top-10 sesiones = 41% del gasto total

**Hallazgo principal:** el hilo de Codex `01a0c483` se había reabierto 17 veces
y producía sesiones-monstruo de >1,500 M tokens porque **el contexto completo
se reenviaba en cada turno**.

El directorio `~/.openclaw/agents/main/` acumulaba 22,298 sesiones (3.7 GB) —
"explosión de sesiones" por falta de recolección de basura.

---

## 2. Diagnóstico

### 2.1 OpenClaw

- El comando oficial `openclaw sessions cleanup` corre en modo `enforce` pero
  **la política de retención estaba demasiado laxa** (mantenía sesiones de 190
  días).
- Había **60,797 artefactos huérfanos** en `agents/main/agent/` (transcripts
  `.jsonl` sin referencia en la DB). El dry-run los detectaba pero no los
  borraba.
- El `codex-home/` (HOME aislado del agente codex) tenía 88 MB en
  `.tmp/plugins/` (clone git temporal huérfano) + 26 MB en `cache/`.

### 2.2 Codex Desktop + CLI (parcheado para DeepSeek)

- **1.9 GB totales** en `~/.codex/`, sin mantenimiento automático.
- 3 versiones del `app-server-daemon` instaladas (950 MB; solo 1 activa).
- Bundle `CodexCLI.app` duplicado dentro de `plugins/.plugin-appserver/`
  (317 MB, md5 idéntico al de `/Applications`).
- `logs_2.sqlite` con 43,447 filas: 60% DEBUG/TRACE (telemetría descartable).
- WAL de 50 MB sin checkpoint (proceso vivo bloqueaba el truncado).
- WAL huérfano de `sqlite/logs_2.sqlite-wal` del 12 de agosto (5 MB).
- El hilo `01a0c483` (34 MB de transcript) presente en:
  - `sessions/2026/09/21/rollout-...-01a0c483-....jsonl`
  - `thread-writer-locks/01a0c483-....lock`
  - `visualizations/2026/09/21/01a0c483-.../`
  - `shell_snapshots/01a0c483-*.sh` (x3)

---

## 3. Decisiones tomadas

| Decisión | Razonamiento |
|---|---|
| **NO tocar el parche DeepSeek** | Verificamos contra la documentación oficial: el parche solo modifica `config.toml` y `models.json`. No toca binarios. Confirmado por logs (`model=deepseek-v4-flash`). |
| **Borrar versiones viejas del daemon** | El parche DeepSeek no vive en binarios. `current` apunta a `0.160.0`. |
| **Borrar `CodexCLI.app` duplicado** | md5 idéntico a `/Applications`. Redundante. |
| **Podar logs por nivel** | DEBUG/TRACE son telemetría; INFO/WARN/ERROR se conservan. |
| **Conservar `computer-use/Codex Computer Use.app`** | Es una app instalada, no basura. |
| **Solo VACUUM en `thread_history_1.sqlite`** | 18,557 filas = historial real de hilos. No borrar. |
| **Sesiones: borrar >14 días** | Transcripts de conversaciones terminadas. No config. |
| **No borrar `packages/app-server-daemon/current/`** | Es el daemon activo. |

### Regla de oro aplicada

**NUNCA tocar:** `config.toml`, `models.json`, `backup-deepseek/`,
`.codex-global-state.json`, `state_5.sqlite`, `thread_history_1.sqlite`,
`packages/app-server-daemon/current/`, `computer-use/*.app`.

---

## 4. Acciones ejecutadas (con resultados)

### 4.1 OpenClaw

| Acción | Antes | Después | Recuperado |
|---|---|---|---|
| `openclaw sessions cleanup --all-agents --enforce` (main) | ~4.05 GB | 675 MB | **3.4 GB** |
| Limpieza codex-home (`.tmp/plugins` + `cache/`) | 144 MB | ~15 MB | **130 MB** |
| Limpieza logs_2.sqlite | 24 MB | ~14 MB | **10 MB** |
| VACUUM thread_history | 79 MB | 72 MB | **7 MB** |

### 4.2 Codex

| Acción | Antes | Después | Recuperado |
|---|---|---|---|
| `.tmp/*` completo | 138 MB | 0 | **138 MB** |
| `cache/*` | 15 MB | 0 | **15 MB** |
| Daemon viejo (0.159.2, 0.159.3) | 634 MB | 0 | **634 MB** |
| `plugins/.plugin-appserver/codex-cli/CodexCLI.app` | 317 MB | 0 | **317 MB** |
| WAL de `logs_2.sqlite` (checkpoint) | 50 MB | 0 | **50 MB** |
| `logs_2.sqlite` DEBUG/TRACE | 49 MB | 14 MB | **35 MB** |
| Hilo `01a0c483` (transcript + artefactos) | 34 MB | 0 | **34 MB** |
| WAL huérfano `sqlite/logs_2.sqlite-wal` | 5 MB | 0 | **5 MB** |
| Sessions >14d | ~20 MB | 0 | **~20 MB** |
| VACUUM state_5.sqlite | 5.4 MB | 800 KB | **4.6 MB** |

### 4.3 Totales

| Sistema | Antes | Ahora | Recuperado |
|---|---|---|---|
| OpenClaw `main` | ~4.05 GB | 675 MB | 3.4 GB |
| OpenClaw `codex-home` | 144 MB | ~15 MB | 130 MB |
| Codex global | 1.9 GB | 695 MB | 1.2 GB |
| **TOTAL** | **~6.1 GB** | **~1.4 GB** | **✅ ~4.7 GB** |

---

## 5. Verificación post-limpieza

- ✅ `config.toml` intacto: `model = "deepseek-flash"`, `model_provider = "deepseek"`,
  `[model_providers.deepseek]` presente.
- ✅ `models.json` intacto.
- ✅ `backup-deepseek/` intacto.
- ✅ Prueba funcional: `codex exec --skip-git-repo-check "responde solo: ok"` →
  arranca con `model: deepseek-flash` y `provider: deepseek`.

---

## 6. Causa raíz

1. **OpenClaw:** política de retención sin límites de edad ni cap por agente.
   El cleanup oficial detecta huérfanos pero requiere `--enforce` para actuar.
2. **Codex:** sin mantenimiento automático de logs, WALs, daemon versions,
   bundles duplicados ni `.tmp/`.
3. **Hilo `01a0c483`:** reapertura cíclica en cada turno → reenvío completo de
   contexto → >1,500 M tokens por sesión.
4. **Sin cron:** ambos sistemas acumulaban basura indefinidamente.

---

## 7. Acciones pendientes

Ver "Briefing para Metiche" (Documento 2).

---

## 8. Anexos

### A. Comandos clave usados

```bash
# OpenClaw
openclaw sessions cleanup --all-agents --dry-run     # diagnóstico
openclaw sessions cleanup --all-agents --enforce     # limpieza real

# Codex — VACUUM selectivo
sqlite3 ~/.codex/logs_2.sqlite "DELETE FROM logs WHERE level IN ('DEBUG','TRACE');"
sqlite3 ~/.codex/logs_2.sqlite "DELETE FROM logs WHERE level='INFO' AND ts < strftime('%s','now','-7 days');"
sqlite3 ~/.codex/logs_2.sqlite "VACUUM;"
sqlite3 ~/.codex/logs_2.sqlite "PRAGMA wal_checkpoint(TRUNCATE);"

# Codex — limpieza de archivos
rm -rf ~/.codex/.tmp/*
rm -rf ~/.codex/cache/*
rm -rf ~/.codex/packages/app-server-daemon/releases/0.159.{2,3}-aarch64-apple-darwin
rm -rf ~/.codex/plugins/.plugin-appserver/codex-cli
find ~/.codex/sessions -name "*.jsonl" -type f -mtime +14 -delete