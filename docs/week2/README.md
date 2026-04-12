# Semana 2 - Baseline Operativa (Cierre)

Estado: **Cerrada**
Fecha de cierre: **2026-04-10**

## 1) Alcance cerrado

- Control de enjambres operativo (`swarm_controller`) con ejecución por ciclos, consenso y razón de parada.
- Integración War Room + consola de enjambres para crear, ejecutar y monitorear swarms.
- Compatibilidad de rutas para acceso estable desde API y dashboard Node.
- Consola de enjambres alineada al look & feel operativo con soporte de tema oscuro/claro.

## 2) Rutas oficiales

- War Room: `http://127.0.0.1:5063/operativo.html`
- Consola de enjambres: `http://127.0.0.1:5063/swarm-console.html`
- War Room (FastAPI): `http://127.0.0.1:8091/dashboard/operativo`
- Enjambres (FastAPI): `http://127.0.0.1:8091/dashboard/swarm-console.html`

Compatibilidad:

- `http://127.0.0.1:8091/admin-dashboard.html` -> `307` a `/dashboard/swarm-console.html`.
- `http://127.0.0.1:5063/admin-dashboard.html` mantiene acceso al mismo HTML de consola (modo swarm).

## 3) Evidencia técnica de validación

### Stack consolidado

Comando:

```bash
./scripts/run-stack-consolidado.sh
```

Resultado esperado:

- App + worker levantados por Docker Compose.
- Dashboard Node activo en `5063`.
- Salud OK en API (`8091`) y consola swarm (`5063`).

### Flujo E2E de enjambre (real)

Comandos validados:

```bash
PYTHONPATH=. ./.venv/bin/python scripts/swarm_dashboard_endpoints_smoke.py
PYTHONPATH=. ./.venv/bin/python scripts/war_room_swarm_e2e_smoke.py
```

Evidencia de ejecución:

- `swarm_dashboard_endpoints_smoke.py`: OK con `swarm_id=bd0b1923-1bae-42b8-8c97-6ab54900e349`.
- `war_room_swarm_e2e_smoke.py`: OK con `swarm_id=209ddc24-3c20-44ac-b035-f306501b5155`, `decision=accept`, `stop_reason=accepted_consensus`, `cycles=1`.

## 4) Tema oscuro/claro

- La consola swarm usa clave compartida `localStorage["warroom_theme"]`.
- Hay toggle explícito en la cabecera (`Tema: Oscuro/Claro`).
- El estado persiste al navegar entre War Room y consola de enjambres.

## 5) Archivos clave de baseline Semana 2

- `dashboard/admin-dashboard-lab.html`
- `dashboard/dashboard-server.mjs`
- `dashboard/operativo.html`
- `app/api/routes_dashboard.py`
- `app/main.py`
- `scripts/run-stack-consolidado.sh`
- `scripts/war_room_swarm_e2e_smoke.py`

## 6) Siguiente fase

- Semana 3: dashboard de negocio en puerto separado y sin mezclar con la consola swarm.
