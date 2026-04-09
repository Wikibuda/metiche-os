# Manual de Usuario y Operacion - metiche-os

Este documento es la guia completa para operar, extender y mantener `metiche-os`.
Esta escrito para uso diario (operacion), onboarding (colaboradores) y evolucion tecnica (nuevos validadores).

## 1) Objetivo del sistema

`metiche-os` coordina cuatro capacidades:

- Ejecucion de tareas (`tasks`) con ruteo y validacion por canal.
- Sincronizacion de fallas de validacion hacia Plane (si esta habilitado).
- Narrativa operacional (cronicas, resumenes, momentos, candidatos).
- Proyeccion de bitacora en Markdown para lectura humana.

En la practica, el flujo principal es:

1. Se crea/ejecuta una tarea.
2. Se decide ruta (`decision`) y se registra ejecucion (`execution`).
3. Se valida por canal (`validation`, `validation_attempt` en `task_events`).
4. El selector narrativo promueve eventos relevantes a cronicas.
5. Se puede exportar la bitacora viva a archivo Markdown.

## 2) Arquitectura por modulos

### 2.1 Estructura principal

- `app/main.py`: inicializa FastAPI y registra routers.
- `app/api/`: endpoints HTTP (`/health`, `/tasks`, `/narrative`, etc).
- `app/cli/`: interfaz de linea de comandos (`run`, `validate`, `cuentame`, etc).
- `app/core/`: configuracion (`config.py`) y base de datos (`db.py`).
- `app/domain/tasks/`: modelos y flujo de tareas.
- `app/domain/validators/`: validadores por canal.
- `app/domain/narrative/`: selector y servicio narrativo.
- `app/integrations/plane.py`: cliente Plane.
- `app/projections/bitacora.py`: generador de bitacora Markdown.
- `app/sql/`: DDL aditivo narrativo.

### 2.2 Flujo de datos operativo

- Tabla/logica de tareas: `Task -> Decision -> Execution -> Validation`.
- Eventos clave: `task_events` (incluye `validation_attempt`).
- Curacion narrativa: `narrative_candidates -> narrativeentry`.
- Colecciones: `narrative_collections` y `narrative_collection_items`.

## 3) Configuracion y entorno

## 3.1 Prioridad de `.env`

Se cargan en este orden:

1. `/Users/gusluna/.openclaw/workspace/.env`
2. `.env` (directorio actual)
3. `/Users/gusluna/.openclaw/.env`

## 3.2 Variables clave

Base:

- `METICHE_ENV`
- `DATABASE_URL`
- `PROJECTIONS_ROOT`
- `WORKER_POLL_SECONDS`
- `PLANE_SYNC_ENABLED`

Plane:

- `PLANE_BASE_URL` o `PLANE_API_URL`
- `PLANE_WORKSPACE_SLUG`
- `PLANE_PROJECT_ID`
- `PLANE_ISSUES_BASE_URL` (opcional si no se usa build por slug/project)
- `PLANE_API_KEY` o `PLANE_API_TOKEN`
- `PLANE_BEARER_TOKEN` (opcional)

Validacion general:

- `VALIDATION_TIMEOUT_SECONDS`
- `VALIDATION_REQUIRED_CHANNELS` (lista separada por coma)

Canales:

- Telegram: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (o metadata fallback: `TELEGRAM_USER_ID`, `TELEGRAM_USERNAME`)
- WhatsApp: `OPENCLAW_GATEWAY_URL` (default `http://127.0.0.1:18797`)
- Dashboard: `DASHBOARD_HEALTH_URL` o `DASHBOARD_PORT`
- Shopify: `SHOPIFY_STORE_DOMAIN` o `SHOPIFY_STORE_URL`, `SHOPIFY_ACCESS_TOKEN`, `SHOPIFY_API_VERSION`
- Deepseek: `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`

## 4) Comandos CLI (operacion diaria)

Los comandos pueden correr como:

- `metiche <comando> ...` (si el alias/entrypoint esta disponible)
- `python -m app.cli.main <comando> ...`

Inicializacion:

- `metiche init-db`

Tareas:

- `metiche run --task "titulo" --task-type whatsapp --description "detalle"`
- `metiche validate --task-id <task_id>`
- `metiche run-worker`

Narrativa:

- `metiche --cuentame --limite 5`
- `metiche cuentame --dias 7 --limite 10`
- `metiche resumen-diario --dia 2026-04-08`
- `metiche momento "texto del momento" --narrador gus --asombro 4`
- `metiche narrator-tick --limite 100`

Semilla historica:

- `metiche seed-fundacional --source /ruta/input_history.json --limite 120`
- `metiche --cuentame --seed-input-history`

Bitacora:

- `metiche build-bitacora`

## 5) API HTTP (resumen rapido)

Health:

- `GET /health`

Tasks:

- `POST /tasks`
- `GET /tasks`
- `POST /tasks/run`
- `GET /tasks/{task_id}/flow`
- `POST /tasks/enqueue`
- `GET /tasks/queue`
- `POST /tasks/process-next`
- `GET /tasks/{task_id}/route`
- `GET /tasks/{task_id}/dispatch`
- `GET /tasks/overview`
- `GET /tasks/{task_id}/escalation`

Narrative:

- `POST /narrative`
- `GET /narrative`

## 6) Validadores por canal

Implementados:

- `telegram_validator.py`
- `whatsapp_validator.py`
- `dashboard_validator.py`
- `shopify_validator.py`
- `deepseek_validator.py`

Reglas actuales:

- Se determina lista de canales requeridos por `task_type`, por anotacion en descripcion (`[channels=a,b]`) y por `VALIDATION_REQUIRED_CHANNELS`.
- Cada validador devuelve `ValidationResult(channel, passed, detail, critical, metadata)`.
- Cada resultado emite un `task_event` tipo `validation_attempt`.

### 6.1 Caso WhatsApp (Fase 4)

`WhatsAppValidator` exige DOS checks:

1. Gateway unificado activo:
- `GET {OPENCLAW_GATEWAY_URL}/health` con timeout 5s.
- Exito si `status=200` y payload con `ok=true` o `status=live`.

2. Canal habilitado:
- Ejecuta:
  - `openclaw channels list 2>/dev/null | grep -q "WhatsApp default: linked, enabled"`
- Exito si el comando retorna `0`.

Optimizacion:

- Cache TTL 60s para evitar ejecutar el comando en cada validacion consecutiva.

## 7) Como agregar un nuevo validador (paso a paso)

Ejemplo: `MiCanalValidator`.

1. Crear archivo en `app/domain/validators/mi_canal_validator.py`.
2. Implementar clase que herede de `BaseValidator` y su `validate(...)`.
3. Retornar siempre `ValidationResult` consistente (con `critical=True` cuando aplique).
4. Exportar clase en `app/domain/validators/__init__.py`.
5. Registrar instancia en `_validator_registry()` en `app/domain/tasks/service.py`.
6. Mapear `task_type -> canal` en `_resolve_required_channels(...)` si corresponde.
7. Probar:
- `metiche run --task "..."`
- `metiche validate --task-id <id>`
- `metiche narrator-tick --limite 100`
- `metiche --cuentame --limite 5`
8. Documentar variables nuevas en `README.md` y en este manual.

Buenas practicas:

- Mantener cambios aditivos (sin romper otros validadores).
- Incluir metadatos utiles para debug (`status_code`, `endpoint`, `error`).
- Diferenciar bien errores criticos vs informativos para impactar asombro narrativo correctamente.

## 8) Mantenimiento de bitacora y narrativa

Objetivo:

- Que los eventos importantes queden en memoria util, legible y recuperable.

Operacion recomendada:

1. Ejecutar tareas (`run` o cola/worker).
2. Correr selector:
- `metiche narrator-tick --limite 100`
3. Revisar:
- `metiche --cuentame --limite 10`
- `metiche resumen-diario --dia YYYY-MM-DD`
4. Exportar:
- `metiche build-bitacora`

Rutas de salida:

- Bitacora Markdown: `projections/bitacora/bitacora_de_asombros.md`

Escala de asombro usada por validaciones:

- `5`: falla critica
- `4`: validacion exitosa
- `3`: falla no critica / informativo

## 9) Integracion con Plane

Si `PLANE_SYNC_ENABLED=true`, cuando hay canales fallidos:

- se crea issue de validacion fallida.
- se agrega comentario con resumen.

Punto de integracion:

- `app/integrations/plane.py`

Uso actual:

- `_sync_plane_validation(...)` en `app/domain/tasks/service.py`.

## 10) Runbook de troubleshooting

Problema: `validate` falla por credenciales faltantes.

- Revisar variables del canal en `~/.openclaw/workspace/.env`.

Problema: WhatsApp falla por conectividad.

- Verificar `OPENCLAW_GATEWAY_URL`.
- Probar manual:
  - `curl http://127.0.0.1:18797/health`
- Confirmar canal:
  - `openclaw channels list`

Problema: no aparecen cronicas nuevas.

- Ejecutar `metiche narrator-tick --limite 100`.
- Revisar que existan `task_events` relevantes (importancia/wonder).

Problema: DB inaccesible.

- Confirmar `DATABASE_URL` absoluta y permisos de escritura.

## 11) Checklist operativo rapido

Diario:

1. `metiche run ...` o proceso de cola.
2. `metiche validate --task-id ...` cuando se requiera validacion manual.
3. `metiche narrator-tick --limite 100`.
4. `metiche --cuentame --limite 5`.
5. `metiche build-bitacora`.

Semanal:

1. Revisar resumenes diarios.
2. Verificar salud de validadores por canal.
3. Confirmar sincronizacion Plane ante fallas reales.

---

## 12) Plantilla para copiar en Plane

Si quieres subir este manual a Plane como documento interno, usa este archivo completo como fuente:

- `MANUAL_USUARIO.md`

Recomendacion:

- Crear item tipo "Ops Manual / User Guide" y pegar secciones 1-12.
- Mantener un owner tecnico para actualizar comandos y variables cuando cambie el runtime.
