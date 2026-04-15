# Guia de Integracion con Plane

Esta guia detalla la integracion bidireccional entre Metiche-OS y Plane.

## 1) Configuracion de la conexion

Metiche soporta dos modos de integracion:

- DB directa (`PLANE_USE_DIRECT_DB=true`, recomendado para Plane self-host).
- API HTTP (`PLANE_USE_DIRECT_DB=false`).

### Variables principales

```bash
PLANE_SYNC_ENABLED=true
PLANE_USE_DIRECT_DB=true
PLANE_DB_TYPE=postgres
PLANE_PG_HOST=plane-db
PLANE_PG_PORT=5432
PLANE_PG_USER=plane
PLANE_PG_PASSWORD=plane
PLANE_PG_DBNAME=plane

PLANE_BASE_URL=https://api.plane.so
PLANE_WORKSPACE_SLUG=mi-workspace
PLANE_PROJECT_ID=<uuid>
PLANE_API_KEY=<api-key>
PLANE_BEARER_TOKEN=<bearer-token>
PLANE_ISSUES_BASE_URL=https://plane.midominio.com/issues

PLANE_WATCH_ENABLED=true
PLANE_WATCH_INTERVAL_SECONDS=20
PLANE_WATCH_LIMIT=20
```

## 2) Sincronizacion Metiche -> Plane

Cuando una tarea de Metiche falla validacion:

- Se crea issue en Plane (si no existe enlace previo).
- Se agregan etiquetas como `metiche`, `task:failed`, `task:<tipo>`.
- Se comenta automaticamente el detalle de la falla.
- Se actualiza estado del issue a `In Progress`.

Cuando la tarea se recupera y valida correctamente:

- Se actualiza el mismo issue vinculado.
- Se agrega comentario de cierre.
- Se intenta marcar el issue como `Done`.

Consulta de issues vinculados desde dashboard:

```bash
curl -s "http://127.0.0.1:8091/dashboard/plane/issues?limit=30" | jq
```

## 3) Sincronizacion Plane -> Metiche

Flujo activo en worker:

- El worker consulta issues con etiqueta `run:enjambre`.
- Por cada issue elegible, crea swarm y ejecuta un ciclo.
- Publica comentario en el issue con el `swarm_id` y decision.

Etiquetas recomendadas al crear issue en Plane:

- Obligatoria para ejecucion: `run:enjambre`.
- Opcional de clasificacion: `metiche:task`.

Ejemplo conceptual de issue:

```json
{
  "name": "Diagnosticar bloqueo de webhook WhatsApp",
  "labels": ["run:enjambre", "metiche:task"],
  "description_html": "<p>Analizar incidentes en recepcion de mensajes.</p>"
}
```

## 4) Idempotencia y control de duplicados

Metiche evita reprocesar issues de forma infinita con:

- Tabla `plane_processed_issues`.
- Comparacion por `issue_updated_at`.
- Regla anti-loop: si el ultimo `last_action` fue `swarm_launched`, no relanza automaticamente.

Ademas, el vinculo tarea-issue se guarda en `plane_sync` para actualizar el mismo issue sin duplicarlo.

## 5) Ejemplo practico completo

1. Crea issue en Plane con etiqueta `run:enjambre`.
2. Espera al intervalo de `run-worker` (por defecto ~20s para watch).
3. Verifica en Metiche:

```bash
curl -s http://127.0.0.1:8091/swarm | jq
curl -s "http://127.0.0.1:8091/dashboard/plane/issues?limit=30" | jq
```

4. Abre el issue en Plane y revisa comentario automatico con resultado.

## 6) Troubleshooting de integracion

### No aparecen issues de Plane

- Revisa `PLANE_SYNC_ENABLED=true`.
- Verifica conectividad a DB/API de Plane.
- Valida permisos del proyecto/workspace.

### No se lanzan enjambres

- Confirma etiqueta exacta `run:enjambre`.
- Revisa logs del worker para `plane-watch lanzó enjambres`.
- Verifica que el worker este corriendo continuamente.

### Errores de autenticacion API

- Revisa `PLANE_API_KEY` y/o `PLANE_BEARER_TOKEN`.
- Confirma `PLANE_WORKSPACE_SLUG` y `PLANE_PROJECT_ID`.

## 7) Referencias cruzadas

- [README](../README.md)
- [Operacion diaria](OPERACION.md)
- [Despliegue](DESPLIEGUE.md)
- [Diagramas](DIAGRAMAS.md)
