# Metiche-OS

![Estado](https://img.shields.io/badge/status-active-success)
![Version estable](https://img.shields.io/badge/stable-v1.1.0-blue)
![Python](https://img.shields.io/badge/python-3.11+-informational)
![Docker](https://img.shields.io/badge/docker-compose-2496ED?logo=docker&logoColor=white)
![Licencia](https://img.shields.io/badge/license-MIT-green)

Metiche-OS es una capa operativa sobre OpenClaw para ejecutar trabajo diario con trazabilidad real: recibe eventos (especialmente WhatsApp), decide rutas de ejecucion, coordina enjambres, sincroniza con Plane y expone un dashboard para operacion.

## Capacidades principales

- Cronista de WhatsApp: registra inbound/outbound por webhook y construye historial por cliente.
- Integracion con Plane: crea/actualiza issues desde eventos de Metiche y procesa issues etiquetados para lanzar enjambres.
- Orquestacion de enjambres: ejecuta ciclos colaborativos con agentes especializados y deja evidencia historica.
- Dashboard operativo: vista de tareas, canales, conversaciones, validadores y enlaces a issues.

## Arquitectura

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
    P1[Adaptador DB/API]
    P2[Plane bridge]
    P3[Pull run:enjambre]
    P4[Issue y comentario]
  end

  B --> P1
  P1 --> P2 --> P3 --> P4
  H --> P4

  subgraph DASHBOARD[Dashboard]
    direction TB
    D1[operativo.html]
    D2[swarm-console.html]
  end

  B --> D1
  B --> D2
```

### Componentes (alto nivel)

- `webhooks`: entrada de eventos (`/webhooks/openclaw/whatsapp` y `/webhooks/openclaw/whatsapp/outbound`).
- `app` (FastAPI): APIs de tareas, dashboard, memoria y swarms.
- `worker`: procesamiento de cola, narrativa y polling de Plane (`run:enjambre`).
- `dashboard`: interfaz operativa (via FastAPI o servidor Node local en `:5063`).
- `SQLite`: base de Metiche (`data/db/metiche_os.db`) con eventos, tareas, narrativa e integracion Plane.

## Requisitos previos

- Docker y Docker Compose v2.
- Python `3.11+` (si correrás scripts/smokes fuera de Docker).
- Node.js (opcional, para `dashboard/dashboard-server.mjs`).
- Acceso a OpenClaw local y, si aplica, a Plane.

Variables de entorno minimas:

```bash
METICHE_ENV=development
DATABASE_URL=sqlite:////app/data/db/metiche_os.db
OPENCLAW_GATEWAY_URL=http://host.docker.internal:18797
OPENCLAW_GATEWAY_TOKEN=
WHATSAPP_ALLOWED_NUMBERS=+5210000000000,+5210000000001

PLANE_SYNC_ENABLED=true
PLANE_USE_DIRECT_DB=true
PLANE_DB_TYPE=postgres
PLANE_PG_HOST=plane-db
PLANE_PG_PORT=5432
PLANE_PG_USER=plane
PLANE_PG_PASSWORD=plane
PLANE_PG_DBNAME=plane
PLANE_ISSUES_BASE_URL=http://plane.local/issues
```

## Instalacion y despliegue rapido

1. Clonar repositorio:

```bash
git clone https://github.com/Wikibuda/metiche-os.git
cd metiche-os
```

2. Crear `.env` (desde un template propio o manualmente) con las variables anteriores.

3. Levantar stack base:

```bash
docker compose up -d --build app worker
```

4. Verificar salud:

```bash
curl -s http://127.0.0.1:8091/health
```

5. (Opcional) Levantar stack consolidado con dashboard local:

```bash
./scripts/run-stack-consolidado.sh
```

URLs comunes:

- API docs: `http://127.0.0.1:8091/docs`
- Dashboard operativo (FastAPI): `http://127.0.0.1:8091/dashboard/operativo`
- Consola de enjambres (FastAPI): `http://127.0.0.1:8091/dashboard/swarm-console.html`
- Dashboard Node local (si corre script): `http://127.0.0.1:5063/`

## Comandos basicos de operacion

```bash
# Logs
docker compose logs -f app
docker compose logs -f worker

# Reiniciar servicios
docker compose restart app
docker compose restart worker

# Estado de contenedores
docker compose ps

# Inicializar DB (si corres en host)
python -m app.cli.main init-db

# Ejecutar worker en host
python -m app.cli.main run-worker

# Smokes clave
PYTHONPATH=. python scripts/operational_validation.py
PYTHONPATH=. python scripts/swarm_dashboard_endpoints_smoke.py
PYTHONPATH=. python scripts/channel_memory_api_smoke.py
```

## Documentacion adicional

- [Guia de Operacion Diaria](docs/OPERACION.md)
- [Guia de Despliegue en Produccion](docs/DESPLIEGUE.md)
- [Guia de Integracion con Plane](docs/INTEGRACION_PLANE.md)
- [Diagramas de Arquitectura y Flujos](docs/DIAGRAMAS.md)
- [Rollout Operativo](docs/PLAN_ROLLOUT.md)

## Estado del proyecto

- Version objetivo estable: `v1.1.0`.
- Servicios principales activos en Compose: `app`, `worker`.
- Integracion Plane soporta modo DB directa (`postgres`) y modo API.

## Licencia

MIT.
