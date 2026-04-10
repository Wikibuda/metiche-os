# metiche-os

![Estado](https://img.shields.io/badge/status-active-success)
![Version](https://img.shields.io/badge/version-0.1.0-blue)
![Licencia](https://img.shields.io/badge/license-MIT-green)

Sistema operativo de coordinación para la IA personal de Gus: tareas, decisiones, validación multicanal, narrativa operativa y proyecciones vivas de bitácora.

`metiche-os` se integra con OpenClaw como capa de orquestación y memoria operacional: recibe intención del Jefe Adoptivo, decide ruta, ejecuta, valida y deja huella narrativa.

## Tabla de Contenido

- [Visión General](#visión-general)
- [Arquitectura Completa](#arquitectura-completa)
- [Características Principales](#características-principales)
- [Requisitos del Sistema](#requisitos-del-sistema)
- [Instalación y Configuración](#instalación-y-configuración)
- [Guía de Uso Rápida](#guía-de-uso-rápida)
- [Demo Visual](#demo-visual)
- [Validadores por Canal](#validadores-por-canal)
- [Narrativa y Bitácora](#narrativa-y-bitácora)
- [Semana 1 Ready Pack](#semana-1-ready-pack)
- [Arranque Consolidado](#arranque-consolidado)
- [API HTTP](#api-http)
- [API `/memory`](#api-memory)
- [Integración con Plane](#integración-con-plane)
- [Estructura del Proyecto](#estructura-del-proyecto)
- [Contribución](#contribución)
- [FAQ](#faq)
- [Licencia](#licencia)
- [Agradecimientos e Historia](#agradecimientos-e-historia)

## Visión General

`metiche-os` existe para operar la misión completa:

- Convertir solicitudes en ejecución real con criterio (`Task -> Decision -> Execution -> Validation`).
- Reducir fricción operativa con CLI y API.
- Verificar salud por canal con validadores reales (no mocks).
- Sincronizar fallas relevantes con Plane.
- Transformar eventos operativos en narrativa útil (asombro, crónicas, colecciones, bitácora).

Relación con OpenClaw:

- OpenClaw aporta el entorno operativo y los canales.
- `metiche-os` aporta el sistema de decisión, validación, memoria narrativa y proyección.

## Arquitectura Completa

El siguiente diagrama representa la arquitectura de referencia (visión operativa + estratégica del proyecto):

```mermaid
graph TD
  A[Jefe Gus] --> B[Metiche Coordinador]
  A --> C[Plane Notifier Bot]
  C --> B

  B --> D{Ejecucion inmediata}
  D --> E[Lanzar Enjambres]
  D --> F[Cola FIFO Ejecutiva]
  F --> D

  subgraph COLA[Cola FIFO Ejecutiva]
    direction TB
    F1[En progreso]
    F2[Blocking]
    F3[Urgent]
    F4[High]
    F5[Medium]
    F6[Low]
    F1 --> F2 --> F3 --> F4 --> F5 --> F6
  end

  F --> F1
  E --> G[Trabajo Background]

  subgraph ENJAMBRES[Enjambres Especializados]
    direction LR
    G1[Dashboard]
    G2[WhatsApp]
    G3[Shopify]
    G4[DeepSeek]
    G5[Plane]
    G6[Control Ingresos Egresos]
  end

  G --> G1
  G --> G2
  G --> G3
  G --> G4
  G --> G5
  G --> G6

  G1 --> H[Validacion automatica]
  G2 --> H
  G3 --> H
  G4 --> H
  G5 --> H
  G6 --> H

  H --> I[Reporte unico final]
  I --> J[Entrega al jefe]

  subgraph NARRATIVA[Sistema Narrativo]
    direction TB
    N1[task_events]
    N2[narrative_candidates]
    N3[narrative_entries]
  end

  B --> N1
  N1 --> N2 --> N3
  N3 --> I

  subgraph PLANE[Integracion Plane]
    direction TB
    P1[plane_db_helper.py]
    P2[plane_keeper.py]
    P3[plane_monitor.py]
    P4[Issue y comentario]
  end

  B --> P1
  P1 --> P2 --> P3 --> P4
  H --> P4

  subgraph DASHBOARD[Dashboard]
    direction TB
    D1[dashboard/admin-dashboard-lab.html (modo swarm)]
    D2[dashboard/dashboard-server.mjs]
  end

  B --> D1
  D1 --> D2

  K[Bitacora Markdown] --> I
  B --> K
```

### Capas arquitectónicas (estado actual)

- Operativa: flujo de tareas, decisiones, ejecución, cola y validación (`app/domain/tasks`).
- Memoria narrativa: eventos, candidatos y crónicas (`app/domain/narrative` + tablas narrativas).
- Validación multicanal real: Telegram, WhatsApp, Shopify, Dashboard, DeepSeek (`app/domain/validators`).
- Proyecciones: bitácora Markdown exportable (`app/projections/bitacora.py`).
- Integración externa: Plane para registrar fallas de validación (`app/integrations/plane.py`).

### Componentes de visión (estado)

- API `/memory`: implementada (Fase 5).
- Plane-Keeper completo: implementado (Fase 6).
- Automatización total de Plane por polling: implementada (Fase 7).

## Características Principales

- Gestión de tareas y rutas de decisión (`run`, cola, procesamiento siguiente).
- Cola de prioridad con buckets operativos (`blocking`, `urgent`, `high`, `medium`, `low`).
- Validación real por canal y validación manual por `task_id`.
- Emisión de `validation_attempt` como eventos operativos.
- Narrativa automática con nivel de asombro (3, 4, 5 según resultado).
- CLI de operación (`run`, `validate`, `narrator-tick`, `--cuentame`, `build-bitacora`).
- API HTTP para tareas, narrativa, memoria y salud.
- Sincronía con Plane ante validaciones fallidas.
- Manual completo para operación y extensión en `MANUAL_USUARIO.md`.

## Requisitos del Sistema

- Python `3.10+` (recomendado 3.11+).
- Entorno macOS/Linux (probado en macOS para este workspace).
- Dependencias Python en `requirements.txt`.
- SQLite habilitado (viene por defecto con Python).
- Variables de entorno configuradas para canales que quieras validar.

Espacio en disco:

- Depende del crecimiento de `metiche_os.db`, crónicas y proyecciones Markdown.
- Recomendación práctica: reservar espacio para crecimiento continuo de la base.

## Instalación y Configuración

### 1) Clonar y entrar al proyecto

```bash
git clone https://github.com/Wikibuda/metiche-os.git
cd metiche-os
```

### 2) Crear entorno virtual

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3) Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4) Configurar variables de entorno

Crear/editar `.env` o usar `~/.openclaw/workspace/.env` (prioridad más alta en runtime actual).

Variables clave recomendadas:

```bash
METICHE_ENV=development
DATABASE_URL=sqlite:////ruta/absoluta/metiche_os.db
PLANE_SYNC_ENABLED=true
OPENCLAW_GATEWAY_URL=http://127.0.0.1:18797

PLANE_SYNC_ENABLED=true
PLANE_USE_DIRECT_DB=true
PLANE_DB_TYPE=postgres
PLANE_LOCAL_ENABLED=true
PLANE_DB_PATH=/ruta/absoluta/plane.db
PLANE_PG_HOST=localhost
PLANE_PG_PORT=5432
PLANE_PG_USER=plane
PLANE_PG_PASSWORD=plane
PLANE_PG_DBNAME=plane
PLANE_SYNC_PULL_LABEL=metiche:task
```

### 5) Inicializar base de datos

```bash
python -m app.cli.main init-db
```

## Guía de Uso Rápida

### Ejecutar tarea

```bash
metiche run --task "validar whatsapp gateway" --task-type whatsapp --description "usando gateway unificado"
```

### Validación manual por task_id

```bash
metiche validate --task-id <task_id>
```

### Selección narrativa y promoción

```bash
metiche narrator-tick --limite 100
```

### Leer crónicas recientes

```bash
metiche --cuentame --limite 5
```

### Proyectar bitácora a Markdown

```bash
metiche build-bitacora
```

## Demo Visual

Sección pensada para material de onboarding visual en GitHub.

- Demo CLI (GIF): **próximamente**
- Demo flujo narrativo (GIF): **próximamente**
- Demo validación multicanal (GIF): **próximamente**

Mientras tanto, puedes validar el flujo completo con los comandos de la sección de uso rápido.

## Validadores por Canal

| Canal | Estado | Verificación actual | Variables clave |
|---|---|---|---|
| Telegram | Implementado | Envía mensaje con Bot API o usa fallback metadata (`user_id` + `username`) | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` o `TELEGRAM_USER_ID`, `TELEGRAM_USERNAME` |
| WhatsApp | Implementado (Fase 4) | `GET /health` en gateway OpenClaw + check de canal linked/enabled en `openclaw channels list` | `OPENCLAW_GATEWAY_URL` |
| Shopify | Implementado | Ping a `shop.json` de Admin API | `SHOPIFY_STORE_DOMAIN` o `SHOPIFY_STORE_URL`, `SHOPIFY_ACCESS_TOKEN`, `SHOPIFY_API_VERSION` |
| Dashboard | Implementado | Health endpoint directo o por puerto local | `DASHBOARD_HEALTH_URL` o `DASHBOARD_PORT` |
| DeepSeek | Implementado | Validación básica de disponibilidad por credenciales/base URL | `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL` |

### Cómo añadir un nuevo validador

1. Crear archivo en `app/domain/validators/mi_canal_validator.py`.
2. Heredar de `BaseValidator` e implementar `validate(...)`.
3. Retornar `ValidationResult` consistente (`passed`, `detail`, `critical`, `metadata`).
4. Exportar en `app/domain/validators/__init__.py`.
5. Registrar en `_validator_registry()` en `app/domain/tasks/service.py`.
6. Mapear canal en `_resolve_required_channels(...)`.
7. Probar con `run`, `validate`, `narrator-tick`, `--cuentame`.

## Narrativa y Bitácora

Conceptos principales:

- `task_events`: eventos operativos (incluye `validation_attempt`).
- `narrative_candidates`: candidatos seleccionados por importancia/asombro.
- `narrativeentry`: crónicas publicadas.
- `narrative_collections`: agrupación diaria de crónicas.

Escala de asombro para validación:

- `5`: falla crítica.
- `4`: validación exitosa.
- `3`: informativo/no crítico.

Proyección de bitácora:

- Archivo generado en `projections/bitacora/bitacora_de_asombros.md`.

## Semana 1 Ready Pack

Para cerrar la fase de diseño tecnico antes de implementar control de enjambres (Semana 2), este repo incluye un paquete versionado en:

- Migraciones: `app/sql/migrations/week1/`
  - `up_postgres.sql`, `up_sqlite.sql`
  - `down_postgres.sql`, `down_sqlite.sql`
  - `seed_week1.sql`
- Contratos JSON v1alpha1: `contracts/v1alpha1/`
  - `UnifiedTask.json`
  - `Swarm.json`
  - `task_events.json`
- Checklist DoD y guia de ejecucion: `docs/week1/README.md`
- Baseline de cierre Semana 2: `docs/week2/README.md`

Cobertura del pack:

- Tablas de enjambre (`swarms`, `swarm_agents`, `swarm_cycles`, `swarm_votes`).
- Extension `memory_entries` Opcion B (`source`, `related_channel`, `client_key`, `correlation_id`).
- Indices de trazabilidad y continuidad multicanal.
- Catalogo de eventos de enjambre (`task_events`) con severidad y campos requeridos.

## Semana 2 Baseline

Estado de cierre documentado en:

- `docs/week2/README.md`

Incluye:

- Alcance operativo cerrado de `swarm_controller`.
- Evidencia E2E (`create -> run -> history`) con consola de enjambres.
- Compatibilidad de rutas (`/admin-dashboard.html` y `/swarm-console.html`).
- Persistencia de tema compartido (`warroom_theme`) entre War Room y consola.

## Arranque Consolidado

Script recomendado para levantar todo el entorno local consolidado (API + worker + dashboard):

```bash
./scripts/run-stack-consolidado.sh
```

El script realiza:

- `docker compose up -d --build app worker` bajo proyecto `metiche-os`.
- Reinicio limpio del dashboard en `5063` con `dashboard/dashboard-server.mjs`.
- Validación de salud en API (`8091`) y consola de enjambres (`5063`).

URLs:

- API docs: `http://127.0.0.1:8091/docs`
- Consola de enjambres: `http://127.0.0.1:5063/swarm-console.html`
- War Room: `http://127.0.0.1:5063/operativo.html`
- War Room (FastAPI): `http://127.0.0.1:8091/dashboard/operativo`
- Enjambres (FastAPI): `http://127.0.0.1:8091/dashboard/swarm-console.html`

Artefactos generados:

- Log del dashboard: `data/dashboard-5063.log`
- PID del dashboard: `.dashboard-5063.pid`

Opcionales por entorno:

```bash
COMPOSE_PROJECT=metiche-os DASHBOARD_PORT=5063 ./scripts/run-stack-consolidado.sh
```

## API HTTP

### Levantar API

```bash
./scripts/run-api-8091.sh
```

Documentacion Swagger:

- `http://127.0.0.1:8091/docs`
- `http://127.0.0.1:8091/openapi.json`

### Endpoints principales

- `GET /health`
- `POST /tasks/run`
- `GET /tasks`
- `GET /tasks/{task_id}/flow`
- `POST /tasks/enqueue`
- `GET /tasks/queue`
- `POST /tasks/process-next`
- `GET /tasks/overview`
- `POST /narrative`
- `GET /narrative`
- `POST /memory`
- `GET /memory`
- `GET /memory/{entry_id}`
- `GET /memory/stats`
- `GET /dashboard/operativo`
- `GET /dashboard/stats`
- `GET /dashboard/tasks`
- `GET /dashboard/tasks/{task_id}`
- `POST /dashboard/tasks/run`
- `POST /dashboard/tasks/{task_id}/action`
- `GET /dashboard/validators`
- `GET /dashboard/recent-narratives`

### Ejemplos curl

```bash
curl -s http://127.0.0.1:8091/health | jq
```

```bash
curl -s -X POST http://127.0.0.1:8091/tasks/run \
  -H "Content-Type: application/json" \
  -d '{
    "title": "probar validador shopify",
    "description": "prueba técnica",
    "task_type": "shopify",
    "execution_mode": "immediate"
  }' | jq
```

```bash
curl -s http://127.0.0.1:8091/tasks/<task_id>/flow | jq
```

```bash
curl -s -X POST http://127.0.0.1:8091/memory \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Decision de enrutamiento",
    "content": "Se priorizó canal whatsapp por urgencia operativa",
    "event_type": "decision",
    "importance_level": "high",
    "wonder_level": 4,
    "source": "metiche"
  }' | jq
```

```bash
curl -s "http://127.0.0.1:8091/memory?event_type=decision&limit=10" | jq
```

```bash
curl -s http://127.0.0.1:8091/memory/stats | jq
```

## API `/memory`

La API de memoria expone un pool de eventos durables para decisiones, errores, éxitos y aprendizajes.

Campos de entrada principales:

- `title`: titulo breve de la memoria.
- `content`: detalle de la memoria.
- `event_type`: `decision` | `error` | `success` | `learning`.
- `importance_level`: `low` | `medium` | `high`.
- `wonder_level`: escala 1-5.
- `source`: origen (ej. `metiche`, `enjambre_shopify`).
- `related_task_id`: referencia opcional a `task.id`.

Endpoints:

- `POST /memory` crea una entrada.
- `GET /memory` lista con filtros/paginación (`event_type`, `importance_level`, `wonder_level`, `source`, `start_date`, `end_date`, `limit`, `offset`).
- `GET /memory/{entry_id}` recupera una entrada por ID.
- `GET /memory/stats` resume totales por tipo/importancia y promedio de asombro.

## Dashboard Local

### Levantar dashboard

```bash
./scripts/run-dashboard-5063.sh
```

URLs principales:

- `http://127.0.0.1:5063/swarm-console.html`
- `http://127.0.0.1:5063/operativo.html`
- `http://127.0.0.1:8091/dashboard/operativo`

### War Room operativo

Vista unica para operacion diaria:

- Lanzamiento rapido de tareas por canal en 2 clics.
- Tablero en tiempo real por estados `queued`, `running`, `retrying`, `failed`, `done`.
- Acciones directas por tarea: reintentar, cancelar, ver log y abrir en Plane.
- Detalle lateral con timeline de `task_events`, payload y validacion.
- Estado real de validadores (ultimo `validation_attempt`) y cronicas recientes.
- Alertas proactivas por retrying estancado y cola `blocking`.

## Integración con Plane

En Fase 6, la integración soporta tres modos:

- `PLANE_USE_DIRECT_DB=true` + `PLANE_DB_TYPE=postgres`: acceso directo a PostgreSQL de Plane (Docker/self-host).
- `PLANE_USE_DIRECT_DB=true` + `PLANE_DB_TYPE=sqlite`: acceso local a `plane.db` (SQLite).
- `PLANE_USE_DIRECT_DB=false`: integración por API HTTP (`app/integrations/plane.py`).

Flujo principal:

- Al cerrar validaciones (`validated` o `failed`), Metiche sincroniza estado en Plane local.
- Si no existe issue asociado y hay falla, se crea issue con etiquetas de tarea.
- Se actualiza estado del issue (`completed` en éxito, `in_progress` en falla por defecto).
- Se agrega comentario con resumen de validación y trazabilidad de crónica.
- Todo intento de sincronía queda registrado en `task_events` con tipo `plane_sync_attempt`.
- La relación tarea↔issue se guarda en tabla `plane_sync` (BD de Metiche).

Sincronización inversa (issues -> tareas):

```bash
metiche plane-sync --process-issues --limit 20
```

- Busca issues por etiqueta `metiche:task` (configurable con `PLANE_SYNC_PULL_LABEL`).
- Crea tareas en Metiche y guarda la relación en `plane_sync`.
- Marca el issue con etiqueta `in_progress` y añade comentario de trazabilidad.

Worker de automatización continua (polling):

```bash
metiche plane-watch
```

```bash
metiche plane-watch --once --dry-run --limit 30
```

- Respeta `PLANE_DB_TYPE` (`postgres`/`sqlite`) usando el mismo adaptador dinámico de Fase 6.
- Intervalo configurable por `.env` con `PLANE_WATCH_INTERVAL` (o `--interval` por CLI).
- Etiquetas observadas por defecto: `PLANE_WATCH_LABELS` (`metiche:task,run:whatsapp,run:shopify,run:enjambre,run:operational,schedule:cron`).
- Emite logs JSON por tick (`plane_watch_tick`) para ingestión en monitorización.
- Guarda idempotencia en `plane_processed_issues` para evitar reprocesar issues.

Mejora futura sugerida:

- Alternativa webhook/event-driven para evitar polling (por ejemplo `pg_notify` o `plane-webhook`).

Cliente de integración local:

- `app/integrations/plane_local.py`
- `app/integrations/plane_postgres.py`

Notas para PostgreSQL:

- Requiere `psycopg2-binary` instalado.
- Variables mínimas: `PLANE_PG_HOST`, `PLANE_PG_PORT`, `PLANE_PG_USER`, `PLANE_PG_PASSWORD`, `PLANE_PG_DBNAME`.
- El módulo adapta estados por nombre (`Todo`, `In Progress`, `Done`) usando la tabla real `states`.

## Estructura del Proyecto

```text
metiche-os/
├─ app/
│  ├─ api/                  # Endpoints FastAPI (health, tasks, narrative, rules, soul)
│  ├─ bootstrap/            # Semillas iniciales
│  ├─ cli/                  # Comandos Typer (run, validate, narrator, bitacora)
│  ├─ core/                 # Configuración y DB engine
│  ├─ domain/
│  │  ├─ tasks/             # Modelos y flujo operativo de tareas
│  │  ├─ validators/        # Validadores reales por canal
│  │  ├─ narrative/         # Selector y servicios narrativos
│  │  └─ soul/              # Perfil/actor y piezas de contexto
│  ├─ integrations/         # Integraciones externas (Plane, readonly_openclaw)
│  ├─ projections/          # Exportadores (bitácora)
│  └─ sql/                  # DDL narrativo aditivo
├─ data/                    # SQLite y exportables
├─ dashboard/               # Dashboard web y utilidades de release lab
├─ projections/             # Salidas proyectadas
├─ MANUAL_USUARIO.md        # Manual técnico-operativo extenso
├─ MANUAL_USUARIO_FULL.html # Manual HTML completo
├─ MANUAL_USUARIO_EXEC.html # Manual HTML ejecutivo
├─ requirements.txt
└─ README.md
```

## Contribución

Guía rápida para colaborar:

1. Crear branch por feature/fix.
2. Mantener cambios aditivos y compatibles.
3. Verificar flujo CLI/API después de tocar `tasks`, `validators` o `narrative`.
4. Documentar variables nuevas en README y manual.
5. Si agregas validador, incluir prueba end-to-end mínima con `run` + `validate`.

Áreas comunes de extensión:

- Nuevos validadores por canal.
- Mejora de selección narrativa y curación de colecciones.
- Nuevas proyecciones (reportes/markdown/json).
- Mejoras de sincronía y enriquecimiento de Plane.

## FAQ

### ¿Por qué una tarea puede quedar en `failed` aunque se ejecutó?

Porque el estado final depende también de validación por canal. Si la ejecución completa pero la validación falla, la tarea cierra en `failed`.

### ¿Qué significa el asombro narrativo?

Es una señal de relevancia operacional:

- `5`: falla crítica
- `4`: éxito validado
- `3`: informativo/no crítico

### ¿Dónde está la bitácora exportada?

En `projections/bitacora/bitacora_de_asombros.md`, generada con `metiche build-bitacora`.

### ¿Cómo forzar validación manual?

Con `metiche validate --task-id <task_id>`.

### ¿El sistema ya tiene API de memoria `/memory`?

Sí. Está disponible en la API HTTP y también vía CLI con `metiche memory add|list|stats`.

## Licencia

Este proyecto se distribuye bajo licencia **MIT**.

Nota: si el repositorio aún no incluye `LICENSE`, agregar el archivo MIT estándar como siguiente paso de hardening legal.

## Agradecimientos e Historia

Metiche nace de una conversación operativa continua iniciada el **28 de febrero**, con una visión clara:

- Gus como **Jefe Adoptivo**.
- Metiche como coordinador técnico con criterio.
- OpenClaw como base operativa de la IA personal.
- Narrativa y bitácora como memoria viva del sistema.

Gracias a quienes colaboran manteniendo este enfoque: técnico, práctico y humano.
