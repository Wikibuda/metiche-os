# Release Checklist - Dashboard Lab metiche-os

## Objetivo

Validar que el dashboard lab está listo antes de crear tag de release.

## URLs clave

- Interfaz: `http://127.0.0.1:5063/lab`
- Alias: `http://127.0.0.1:5063/`
- Consola de enjambres: `http://127.0.0.1:5063/swarm-console.html`
- Swagger metiche-os: `http://127.0.0.1:8091/docs`
- OpenAPI: `http://127.0.0.1:8091/openapi.json`

## Checks HTTP obligatorios

1. `GET http://127.0.0.1:8091/health` -> `200`
2. `GET http://127.0.0.1:5063/health` -> `200`
3. `GET http://127.0.0.1:5063/api/labs/metiche-os/overview` -> `200`
4. `GET /api/labs/metiche-os/task-detail?taskId=<uuid-real>` -> `200`

## Checks UI obligatorios

1. El panel de métricas carga sin errores al abrir `/lab`.
2. El panel de detalle muestra vista amigable (cards), con JSON solo opcional.
3. Los botones de vista (`Completo`, `Flow`, `Route`, `Dispatch`, `Escalation`) funcionan.
4. Al fallar backend o timeout, se muestran alertas visibles sin romper toda la pantalla.
5. El `task_id` permanece después de recargar la página.
6. Auto-refresh:
   - cola activa (`queue_depth > 0`) refresca en ~5s,
   - cola vacía refresca en ~15s.

## Resultado release

- Si todos los checks pasan: ✅ autorizado para tag release.
- Si falla cualquier check: ❌ corregir antes del tag.
