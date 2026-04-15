# Guia de Despliegue para Produccion

Esta guia describe un despliegue estable de Metiche-OS para entornos productivos o pre-productivos.

## 1) Requisitos de hardware y software

Minimo recomendado:

- CPU: 2 vCPU
- RAM: 4 GB
- Disco: 20 GB SSD
- SO: Linux x86_64 (Ubuntu 22.04+ recomendado)
- Docker Engine + Docker Compose v2

Recomendado para carga media:

- CPU: 4 vCPU
- RAM: 8 GB
- Disco: 50+ GB SSD

## 2) Variables de entorno (con ejemplos)

Archivo sugerido: `.env` en la raiz del repo.

### Core Metiche

```bash
METICHE_ENV=production
DATABASE_URL=sqlite:////app/data/db/metiche_os.db
PROJECTIONS_ROOT=/app/projections
WORKER_POLL_SECONDS=5
```

### OpenClaw / WhatsApp

```bash
OPENCLAW_GATEWAY_URL=http://host.docker.internal:18797
OPENCLAW_GATEWAY_TOKEN=tu_token
OPENCLAW_CONFIG_PATH=/mnt/openclaw-state/openclaw.json
OPENCLAW_STATE_DIR=/mnt/openclaw-state
WHATSAPP_SANDBOX_MODE=false
WHATSAPP_ALLOWED_NUMBERS=+5215512345678,+5215599998888
```

### Plane (DB directa PostgreSQL)

```bash
PLANE_SYNC_ENABLED=true
PLANE_USE_DIRECT_DB=true
PLANE_DB_TYPE=postgres
PLANE_PG_HOST=plane-db
PLANE_PG_PORT=5432
PLANE_PG_USER=plane
PLANE_PG_PASSWORD=plane
PLANE_PG_DBNAME=plane
PLANE_ISSUES_BASE_URL=https://plane.midominio.com/issues
PLANE_WATCH_ENABLED=true
PLANE_WATCH_INTERVAL_SECONDS=20
PLANE_WATCH_LIMIT=20
```

### Plane (modo API HTTP)

```bash
PLANE_SYNC_ENABLED=true
PLANE_USE_DIRECT_DB=false
PLANE_BASE_URL=https://api.plane.so
PLANE_WORKSPACE_SLUG=mi-workspace
PLANE_PROJECT_ID=<uuid-proyecto>
PLANE_API_KEY=<api-key>
PLANE_BEARER_TOKEN=<bearer-token>
PLANE_TIMEOUT_SECONDS=15
```

## 3) Despliegue con Docker Compose

Levantar servicios:

```bash
docker compose up -d --build app worker
```

Servicios en `docker-compose.yml`:

- `app`: API FastAPI en puerto `8091`.
- `worker`: consumo de cola, narrativa y polling de Plane.

Puertos:

- `8091/tcp`: API y dashboard via FastAPI.

Volumenes relevantes:

- `./data:/app/data`: base de datos y estado local.
- `./projections:/app/projections`: bitacora y proyecciones.
- `openclaw_state:/mnt/openclaw-state`: estado de OpenClaw compartido.

## 4) Configuracion de red

### Metiche <-> OpenClaw

- `OPENCLAW_GATEWAY_URL` debe ser accesible desde contenedor `app` y `worker`.
- Si OpenClaw corre en host local, usar `host.docker.internal` (como en compose).
- Configura OpenClaw para enviar webhook inbound a:
  - `POST http://<metiche-host>:8091/webhooks/openclaw/whatsapp`
- Opcional webhook outbound:
  - `POST http://<metiche-host>:8091/webhooks/openclaw/whatsapp/outbound`

### Metiche <-> Plane

- Compose ya conecta a red externa `plane-selfhost_default` como `plane_selfhost`.
- Si Plane corre fuera de Docker local, ajusta `PLANE_PG_HOST` o modo API.
- Verifica conectividad de red antes de habilitar sincronizacion automatica.

## 5) Backup y restauracion

### Backup de base de datos Metiche

```bash
mkdir -p backups
cp data/db/metiche_os.db backups/metiche_os_$(date +%Y%m%d_%H%M%S).db
```

### Backup de configuracion

```bash
cp .env backups/env_$(date +%Y%m%d_%H%M%S).bak
```

### Restauracion

1. Detener servicios:

```bash
docker compose stop app worker
```

2. Restaurar archivo:

```bash
cp backups/metiche_os_YYYYMMDD_HHMMSS.db data/db/metiche_os.db
```

3. Levantar servicios:

```bash
docker compose up -d app worker
```

## 6) Actualizacion del sistema

Procedimiento recomendado:

1. Respaldar DB y `.env`.
2. Actualizar codigo:

```bash
git pull origin main
```

3. Reconstruir e iniciar:

```bash
docker compose up -d --build app worker
```

4. Verificar salud y dashboard:

```bash
curl -s http://127.0.0.1:8091/health
curl -s http://127.0.0.1:8091/dashboard/stats
```

5. Ejecutar smoke minimo:

```bash
PYTHONPATH=. python scripts/operational_validation.py
```

## 7) Seguridad recomendada

- Activar safelist en canales:
  - `WHATSAPP_ALLOWED_NUMBERS`
  - `TELEGRAM_ALLOWED_IDS`
- Mantener sandbox en ambientes no productivos:
  - `WHATSAPP_SANDBOX_MODE=true`
  - `TELEGRAM_SANDBOX_MODE=true`
- No exponer `8091` publicamente sin reverse proxy y auth.
- No publicar tokens (`OPENCLAW_GATEWAY_TOKEN`, `PLANE_API_KEY`) en repositorio.
- Restringir red de base de datos Plane a hosts autorizados.

## 8) Ejemplo completo de despliegue (entorno de pruebas)

```bash
# 1) Variables base
cat > .env <<'EOF'
METICHE_ENV=production
DATABASE_URL=sqlite:////app/data/db/metiche_os.db
OPENCLAW_GATEWAY_URL=http://host.docker.internal:18797
PLANE_SYNC_ENABLED=true
PLANE_USE_DIRECT_DB=true
PLANE_DB_TYPE=postgres
PLANE_PG_HOST=plane-db
PLANE_PG_PORT=5432
PLANE_PG_USER=plane
PLANE_PG_PASSWORD=plane
PLANE_PG_DBNAME=plane
EOF

# 2) Ajustar al menos OPENCLAW_GATEWAY_URL y credenciales Plane

# 3) Levantar stack
docker compose up -d --build app worker

# 4) Levantar dashboard local opcional
./scripts/run-stack-consolidado.sh

# 5) Validar endpoints
curl -s http://127.0.0.1:8091/health
curl -s http://127.0.0.1:8091/dashboard/plane/issues
```

## 9) Referencias cruzadas

- [README](../README.md)
- [Operacion diaria](OPERACION.md)
- [Integracion Plane](INTEGRACION_PLANE.md)
- [Diagramas](DIAGRAMAS.md)
