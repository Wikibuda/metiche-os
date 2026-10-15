# 📋 Hallazgos — War Room y Consola de Enjambres

**Para:** Metiche ➰
**Fecha:** 05-oct-2026
**Alcance:** las dos superficies operativas del proyecto `metiche-os-migrated-20260408/`
**Método:** lectura directa de código + verificación en vivo (no copiado de memoria).

> Este documento complementa a `DOCUMENTO-MAESTRO-ARQUITECTURA-2026-10-05.md`. Aquel describe
> la arquitectura de las dos máquinas; este se enfoca en el **War Room** y en la **Consola de
> Enjambres**, que son piezas distintas y conviene no confundir.

---

## 0. Estado verificado en vivo (05-oct-2026)

| Chequeo | Resultado |
|---|---|
| `http://127.0.0.1:5063/` | **200** |
| `http://127.0.0.1:8091/health` | `{"ok":true,"service":"metiche-os","environment":"development"}` |
| `/dashboard/plane/issues?limit=3` | `total: 3`, todos `linked`, `issue_state: queued` |

Los issues visibles: `plane-529` (test), `plane-528` (4 pilas), `plane-527` (acción desde el aviso).
Los tres llegan con **`labels: []`** y con **`issue_url` en formato viejo**.

---

## 1. War Room

### 1.1 Arquitectura

- **UI/servidor:** `dashboard/dashboard-server.mjs` (Node) sirve `dashboard/operativo.html` en **:5063**
  y hace **proxy** de `/dashboard/*`, `/memory` y `/swarm*` hacia la API.
- **API:** FastAPI en **:8091** (`app/`).
- **Datos:** SQLite local `data/db/metiche_os.db`.
- Rutas: `/`, `/lab`, `/operativo.html` sirven la misma página.
- ⚠️ No confundir con el **Dashboard ROI :5055** (Masa Madre, en Ubuntu).

### 1.2 Paneles de `operativo.html` (1,300 líneas)

1. **KPIs** de cabecera: salud, fallas 10 m, latencia de ciclo, alertas críticas, último tick, memoria.
2. **Lanzar Tarea Rápida** (canal, título, contexto, casilla «Lanzar enjambre»).
3. **Registrar Memoria** + **Estado de Validadores**.
4. **Tablero de Tareas en Tiempo Real**: columnas `queued · running · retrying · failed · done`.
5. **Últimas Crónicas**, **Conversaciones WhatsApp**, **Issues Plane Relacionados**, **Memoria Reciente**.
6. **Detalle de Tarea** (timeline, payload, crónica, reintentar/cancelar/prioridad).
7. **Ajustes**: tema y umbrales de refresco.
8. Enlaces a la Consola de Enjambres y a `traje-iron-man`.

### 1.3 Hallazgos del War Room

1. **Catálogo Plane sin carril:** los `labels` llegan vacíos → la nomenclatura de 4 pilas no se puede
   pintar. Origen: el panel lee la tabla local `plane_sync`, no la API de Plane.
2. **Links de issue en formato viejo** (`/masa-madre-hq/projects/<uuid>/issues/<uuid>`) en lugar de
   `/masa-madre-hq/browse/MASAM-<seq>/`.
3. **Sin botón «Lanzar» por issue.** Existe «Lanzar Tarea Rápida» + cola FIFO, pero no se puede
   lanzar un issue puntual desde el catálogo.
4. **War Room = espejo por diseño.** El docstring de `scripts/warroom_espejo.py` lo confirma: el
   tablero *pinta* desde la tabla `task`; el bridge `run:enjambre` se apagó por ser un «segundo cerebro».
5. **El tablero agrupa por estado, no por carril** → hoy no hay forma visual de ver las 4 pilas.

---

## 2. Consola de Enjambres

### 2.1 Arquitectura

- **UI:** `dashboard/admin-dashboard-lab.html` (**2,119 líneas**, "Metiche OS Lab Dashboard").
- Se sirve en `/swarm-console.html`, `/admin-dashboard.html` y `/admin-dashboard-lab.html` (Node),
  y en `/dashboard/swarm-console.html` (FastAPI; `/admin-dashboard.html` redirige `307` ahí).
- Comparte tema con el War Room vía `localStorage["warroom_theme"]`.

### 2.2 Paneles de la consola

1. Cards de estado · 2. Estado operativo · 3. Tareas recientes · 4. Detalle de tarea ·
5. **Correr un issue (motor)** (select + `ssh ubuntu-imac` + `runner.py --seq` + vigía Telegram) ·
6. **Lanzar Enjambre** (name/goal/policy/agents/max_cycles → `POST /swarm` + `/swarm/{id}/run`) ·
7. Estado de Canales · 8. Enjambres Recientes + Historial · 9. **💰 Gastos** (alta/borrado en
`gastos.json` vía Node) · 10. Toggle de tema.

### 2.3 Backend de swarm

- **Rutas:** `app/api/routes_swarm.py` → `POST /swarm`, `GET /swarm`, `GET /swarm/{id}`,
  `POST /swarm/{id}/run`, `GET /swarm/{id}/history`.
- **Ciclo:** `app/domain/swarm/service.py` (857 líneas) recorre **plan → dispatch → validate → adjust**.
  Decisión por policy (`majority`, `leader-follower`, `narrative-consensus`). Se detiene por consenso
  aceptado, por `reject_streak ≥ 2`, o por `max_cycles`. Al cerrar, **comenta en Plane** y notifica Telegram.
- **Dispatch:** `app/services/dispatcher.py` (669 líneas). Agentes internos `deepseek→narrative`,
  `plane→data_query`, `dashboard→narrative`, `knowledge_agent→semantic_search`; canales externos
  `whatsapp`/`telegram→send_message`. Reintentos con backoff (1, 2, 4 s; máx. 3). DeepSeek llama a la
  API real y guarda reportes en `/app/projections/reportes/`. El agente `plane` consulta el Postgres
  real de Plane (con fallback `psql`).
- **Modelos:** `Swarm`, `SwarmAgent`, `SwarmCycle`, `SwarmVote`; 13 agentes permitidos, 3 policies.
  Escribe en `task_events`, `memory_entries` y narrativa (`chronicle`).

### 2.4 Hallazgos de la consola

1. **Doble ruta de ejecución.** «Correr issue» delega al MOTOR (correcto); «Lanzar Enjambre» **ejecuta
   aquí mismo**, síncrono dentro del request FastAPI. Contradice el principio «un solo cerebro / espejo».
2. **Consenso parcialmente sintético.** Si un agente no despacha, `_simulate_vote` decide por palabras
   clave («riesgo» → reject). No todo voto es evidencia real.
3. **Bug latente.** `_dispatch_code_execution` y `_dispatch_batch_sql` leen `task.task_data`, atributo
   que **no existe** en `UnifiedTask` → siempre devuelven `no_code` / `no_queries`.
4. **ids de sección desalineados:** «Detalle de tarea» = `swarm-launch-panel`; «Lanzar Enjambre» =
   `swarm-history-panel`; «Enjambres Recientes» = `legacy-detail-panel`.
5. **Hardcodes operativos:** `CHANNEL_TARGETS` en `service.py` y `DEEPSEEK_API_KEY` en `docker-compose.yml`
   (este último debería moverse a `.env` y rotarse).
6. **La consola no ve el catálogo Plane ni las 4 pilas** — viven solo en `operativo.html`.

---

## 3. Hallazgos transversales (afectan ambos frentes)

1. **Contradicción del MOTOR: Mac vs Ubuntu.** El Documento Maestro (05-oct) afirma que el motor corre
   en la **Mac** y marca como falso el «motor en Ubuntu». Pero `dashboard-server.mjs` (`runIssueOnMotor`,
   que hace `ssh ubuntu-imac`) y `warroom_espejo.py` siguen diciendo **Ubuntu**. Decisión pendiente.
2. **Dos superficies separadas** (War Room y Consola) con backend y datos distintos → duplican estado
   y confunden al operar.
3. **Deuda de documentación:** páginas `plane-local/pages/arquitectura-*` marcadas «verificado 29-sep»
   quedaron anteriores a cambios del motor.

---

## 4. Decisiones que necesito de ti / de Gus

1. ¿El MOTOR corre en la **Mac** o en **Ubuntu**? (define todo lo demás).
2. ¿La Consola de Enjambres **ejecuta** o solo **observa** como el War Room?
3. ¿Las 4 pilas se pintan en el **War Room** (agrupar columnas) o en la **Consola**?
4. ¿Se unifican ambas superficies o se mantienen separadas por diseño?

---

## 5. Cómo verificar cada línea

```bash
# War Room y consola (Mac)
curl -s -o /dev/null -w "5063 -> %{http_code}\n" http://127.0.0.1:5063/
curl -s http://127.0.0.1:8091/health
curl -s 'http://127.0.0.1:5063/dashboard/plane/issues?limit=5'

# Enjambres
curl -s 'http://127.0.0.1:5063/swarm?limit=5'

# 4 pilas
cd ~/.openclaw/workspace && python3 scripts/pilas.py tablero
```

---
*Documento de hallazgos. No propone cambios todavía: primero alinea las decisiones de la sección 4.*
