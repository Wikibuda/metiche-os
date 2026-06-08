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
PLANE_SYNC_PULL_LABEL=run:enjambre
PLANE_COMMENT_WATCH_ENABLED=true
PLANE_COMMENT_WATCH_INTERVAL_SECONDS=20
PLANE_COMMENT_WATCH_LIMIT=20
PLANE_COMMAND_AUTHOR_ALLOWLIST=gglunar@gmail.com
PLANE_COMMAND_TIMEOUT_SECONDS=300
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

- El worker consulta issues con etiqueta configurable `PLANE_SYNC_PULL_LABEL` (default `run:enjambre`).
- Por cada issue elegible, asegura primero el vinculo `issue <-> task local` mediante `ensure_plane_issue_task_link(...)`.
- Esa task local funciona como recibo del bridge: nace en `queued` cuando el issue fue consumido por Metiche.
- Despues crea el swarm y ejecuta el ciclo real de trabajo.
- Cuando el bridge termina su procesamiento del issue, la task local pasa a `done`.
- Publica comentario en el issue con el `swarm_id`, la decision y el resultado consolidado del enjambre.

Adicionalmente, el worker de comentarios procesa comandos `/metiche ...` con allowlist de autor y registra idempotencia en `plane_processed_comments`.

### Modelo canonico: Task != Swarm

La separacion es intencional y debe mantenerse en codigo, dashboard y documentacion:

- `Task.status=queued/done` significa "Plane ya fue recibido y procesado por el bridge".
- `Swarm.status=pending/running/completed/failed` significa "estado real de ejecucion del enjambre".
- Una `Task` en `done` no implica que el trabajo ya termino; solo implica que la integracion Plane -> War Room ya se proceso.
- El War Room debe mostrar ambos estados sin mezclarlos para evitar falsos positivos de avance.

En terminos operativos:

- Plane define QUE hay que hacer.
- La task local confirma que el bridge ya tomo ese pedido.
- El swarm ejecuta el COMO y produce el resultado real.
- Los comentarios de vuelta a Plane deben apoyarse en la salida del swarm, no en el mero cambio de `Task.status`.

Etiquetas recomendadas al crear issue en Plane:

- Obligatoria para ejecucion: etiqueta definida en `PLANE_SYNC_PULL_LABEL` (por defecto `run:enjambre`).
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

Si un issue llega sin vinculo previo, el bridge debe crear automaticamente la task local y registrar la relacion para que el flujo bidireccional Plane <-> War Room no quede huerfano.

## 5) Retorno al jefe y CHANNEL_TARGETS

Cuando el swarm concluye:

- Se construye un `compiled_message` con los hallazgos consolidados de los agentes internos.
- Ese mensaje es la respuesta real del enjambre hacia afuera.
- El routing de salida usa `CHANNEL_TARGETS` como decision arquitectonica estable.
- El destino final puede ser distinto del `client_key` original si la politica del sistema exige centralizar la respuesta en el canal del jefe.

Esto permite que el mismo flujo operativo:

- deje trazabilidad en Plane,
- mantenga observabilidad en War Room,
- y entregue a Gus una salida consolidada y consistente.

## 6) Ejemplo practico completo

1. Crea issue en Plane con etiqueta `run:enjambre`.
2. Espera al intervalo de `run-worker` (por defecto ~20s para watch).
3. Verifica en Metiche:

```bash
curl -s http://127.0.0.1:8091/swarm | jq
curl -s "http://127.0.0.1:8091/dashboard/plane/issues?limit=30" | jq
```

4. Abre el issue en Plane y revisa comentario automatico con resultado.

## 7) Troubleshooting de integracion

### No aparecen issues de Plane

- Revisa `PLANE_SYNC_ENABLED=true`.
- Verifica conectividad a DB/API de Plane.
- Valida permisos del proyecto/workspace.

### No se lanzan enjambres

- Confirma etiqueta configurada en `PLANE_SYNC_PULL_LABEL`.
- Revisa logs del worker para `plane-watch lanzó enjambres`.
- Verifica que el worker este corriendo continuamente.

### El issue no muestra tareas vinculadas en orquestador

- Verifica que el bridge este ejecutando `ensure_plane_issue_task_link(...)` al consumir el issue.
- Revisa que exista registro en `plane_sync` para ese `issue_id`.
- Confirma que la task local se haya creado aunque el issue venga directo desde Plane.
- Recuerda: la vinculacion debe ser automatica; no debe depender de creacion manual previa en War Room.

### Errores de autenticacion API

- Revisa `PLANE_API_KEY` y/o `PLANE_BEARER_TOKEN`.
- Confirma `PLANE_WORKSPACE_SLUG` y `PLANE_PROJECT_ID`.

## 8) Referencias cruzadas

- [README](../README.md)
- [Operacion diaria](OPERACION.md)
- [Despliegue](DESPLIEGUE.md)
- [Diagramas](DIAGRAMAS.md)
