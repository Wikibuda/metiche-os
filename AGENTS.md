# Guías del Repositorio

## Estructura del Proyecto y Organización de Módulos

- `app/` — aplicación FastAPI. Subpaquetes: `api/` (routers), `services/` (lógica de negocio), `domain/` (entidades SQLModel y servicios), `integrations/` (adaptadores de Plane, WhatsApp, Telegram y OpenClaw), `core/` (config, db, roles), más `cli/`, `agents/`, `bootstrap/` y `sql/` (migraciones).
- `dashboard/` — vistas HTML operativas y el servidor Node opcional (`dashboard-server.mjs`).
- `tests/` — suites de `unittest`; `scripts/*_smoke.py` — pruebas de humo operativas y end-to-end.
- `docs/` — guías de operación, despliegue e integración con Plane; `contracts/v1alpha1/` — contratos JSON compartidos.
- `data/` y `projections/` — artefactos de ejecución generados, no fuente.

## Comandos de Compilación, Pruebas y Desarrollo

- `docker compose up -d --build app worker` — construye y levanta la API y el worker.
- `curl -s http://127.0.0.1:8091/health` — verifica la salud del servicio.
- `python -m app.cli.main init-db` / `run-worker` — inicializa la base de datos o ejecuta el worker en el host.
- `pytest` — ejecuta las pruebas unitarias de `tests/`.
- `PYTHONPATH=. python scripts/operational_validation.py` — ejecuta la validación operativa principal.

## Estilo de Código y Convenciones de Nombres

- Python 3.11+ (la imagen del contenedor usa 3.12), alineado con `requirements.txt`.
- Indentación de 4 espacios; `snake_case` para funciones y variables, `PascalCase` para clases SQLModel.
- Prefiere `from __future__ import annotations` y anotaciones de tipo completas (ver `app/main.py`).
- No hay linter ni formateador configurado — imita el código existente y mantén los diffs mínimos.
- Nombra los routers `routes_*.py` y los scripts de humo `*_smoke.py`.

## Guías de Pruebas

- Framework: `unittest` (compatible con pytest). Archivos `tests/test_*.py`, clases `*Test`, métodos `test_*`.
- Usa SQLite en memoria por prueba (`create_engine("sqlite://")`), como en `tests/test_channel_memory_service.py`.
- Agrega una prueba enfocada por cada servicio o comportamiento nuevo, y ejecuta `pytest` antes de abrir un PR.

## Guías de Commits y Pull Requests

- Los commits siguen Conventional Commits: `feat:`, `fix:`, `chore:`, `docs:`; se acepta español o inglés (p. ej. `fix: robustecer bridge de plane`). Los releases usan `release snapshot vX.Y.Z (sanitized)`.
- Mantén los commits acotados e imperativos.
- Los PR deben incluir un resumen, módulos afectados, evidencia de validación (salida de humo) y el issue de Plane enlazado. Agrega capturas para cambios en el dashboard.

## Seguridad y Configuración

- Nunca hagas commit de `.env`, secretos o estado de ejecución; `.gitignore` los cubre.
- Copia `.env.example` a `.env` y define `DATABASE_URL`, `OPENCLAW_GATEWAY_*`, `WHATSAPP_ALLOWED_NUMBERS` y las variables de Plane.
