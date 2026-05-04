# Comandos Plane -> Metiche

Este documento describe el protocolo para ejecutar acciones de Metiche desde comentarios en issues de Plane.

## Formato de comando

Cada comando debe escribirse en `issue_comments.comment_stripped` con este formato:

```text
/metiche accion:nombre param1=valor1 param2=valor2
```

Ejemplos:

```text
/metiche accion:enjambre.run
/metiche accion:task.retry task_id=43387ae2-340d-4e1b-a955-d7ea142020f7 priority=high
/metiche accion:task.cancel task_id=43387ae2-340d-4e1b-a955-d7ea142020f7
/metiche accion:traje.archivar lote=30 dryrun=true
/metiche accion:traje.limpiar-low lote=20
/metiche accion:traje.status
/metiche accion:sync.pull limit=20
/metiche accion:info.health
```

## Seguridad y control

- Solo se procesan comentarios de autores en allowlist (`PLANE_COMMAND_AUTHOR_ALLOWLIST`).
- El comentario se procesa una sola vez (idempotencia) en tabla `plane_processed_comments`.
- Se agrega etiqueta `pending-command` al iniciar.
- Al terminar:
  - éxito: `last-action:ok`
  - error: `last-action:error`
- Timeout por comando: `PLANE_COMMAND_TIMEOUT_SECONDS` (default 300s).

## Variables de entorno

```bash
PLANE_SYNC_PULL_LABEL=run:enjambre
PLANE_WATCH_ENABLED=true
PLANE_WATCH_INTERVAL_SECONDS=20
PLANE_WATCH_LIMIT=20

PLANE_COMMENT_WATCH_ENABLED=true
PLANE_COMMENT_WATCH_INTERVAL_SECONDS=20
PLANE_COMMENT_WATCH_LIMIT=20
PLANE_COMMAND_AUTHOR_ALLOWLIST=gglunar@gmail.com
PLANE_COMMAND_TIMEOUT_SECONDS=300
```

## Acciones soportadas (MVP)

- `accion:enjambre.run`
  - Crea swarm desde el issue origen y ejecuta 1 ciclo.
  - Parámetros opcionales: `parent_issue_id`, `task_id`, `max_cycles`.
- `accion:task.retry task_id=<uuid>`
  - Reencola la tarea (prioridad por defecto `high`).
  - Parámetro opcional: `priority`.
- `accion:task.cancel task_id=<uuid>`
  - Cancela la tarea y sus entradas en cola.
- `accion:traje.archivar lote=30 dryrun=true|false`
  - Ejecuta operación mensual de archivado.
- `accion:traje.limpiar-low lote=20 dryrun=true|false`
  - Ejecuta limpieza de issues low obsoletos.
- `accion:traje.status`
  - Devuelve estado actual del Traje Iron Man.
- `accion:sync.pull limit=20`
  - Fuerza sincronización Plane -> Metiche con la etiqueta configurada.
- `accion:info.health`
  - Devuelve salud operativa resumida.

## Observabilidad

- Historial API: `GET /api/plane-commands/history?limit=50`
- Campos clave por comando:
  - `status` (`processing`, `done`, `error`)
  - `result_json`
  - `error_text`
  - `started_at`, `finished_at`
