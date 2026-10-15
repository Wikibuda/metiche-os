# 📐 DOCUMENTO MAESTRO — Arquitectura de Masa Madre Monterrey

**Fecha:** 05-oct-2026 · **Autor:** Metiche ➰ (verificado en vivo, no copiado de memoria)
**Propósito:** ser la **foto real** de cómo está armado el sistema **hoy**, para que Gus pueda
solicitar (con base firme) la **modificación del War Room** y la propagación de la nomenclatura de 4 pilas.

> **Regla de oro:** las dos máquinas cambian de IP por DHCP → **usa los nombres**
> (`ubuntu-imac`, `raquel.local`), **nunca** una IP fija.

---

## 1. Las dos máquinas

| | **Ubuntu (`ubuntu-imac`)** | **Mac (`raquel.local`)** |
|---|---|---|
| Rol | **el único nodo 7×24** (producción) | estación de datos + escritorio de Gus |
| IP al 29-sep-2026 | `192.168.0.3` | `192.168.0.9` |
| Cómo referirse | `ubuntu-imac` | `raquel.local` |

---

## 2. Qué corre en cada una (verificado 05-oct-2026)

### 🍎 Mac — `raquel.local`
| Servicio | Detalle | Cómo se comprueba |
|---|---|---|
| 🐘 **Plane (PostgreSQL)** | Docker `plane-selfhost-plane-db-1` | `docker ps --format "{{.Names}}"` |
| 🎛️ **Plane web** | `:8080` | `https://plane.masamadremonterrey.com` |
| 💬 **Gateway OpenClaw — Metiche** | `:18797` (Telegram) | `openclaw channels status` |
| ⚙️ **MOTOR** (el cerebro de la cola) | `scripts/runner.py` vía launchd `com.masamadre.runner`, cada 30 min — **PAUSADO desde 3-oct** | `launchctl list \| grep masamadre` · `logs/runner_mac.log` |
| 🖥️ **War Room** | `:5063` (`operativo.html`) + API `:8091` | `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5063/` |
| 🖨️ **Impresora EPSON L1110** | USB | — |
| 🛠️ **Codex Mac** | nodo de desarrollo local | — |
| 🐳 Docker Desktop | `Docker.raw` (~21 GB) | — |

### 🐧 Ubuntu — `ubuntu-imac`
| Servicio | Detalle |
|---|---|
| 🤖 **Gateway OpenClaw** `:18797` | bot WhatsApp de clientes **+ Orquestador 🧭 (@MasamPlaneBot)** |
| 📊 **Dashboard ROI v2** `:5055` | `roi-dashboard.service` (migrado el 26-sep-2026) |
| 🗄️ `masamadre.db` | datos del ROI |
| ⚙️ **Director + crons** | `director.py`, `salud_nodos.py`, guardián de contrato, espejo |
| 🪞 **Espejo `plane-local/`** | copia de issues + páginas (refresco cada 20 min) |
| 🌐 **cloudflared-tunnel.service** | el túnel de Cloudflare vive aquí |
| 🛠️ **Codex Ubuntu** | nodo de desarrollo remoto |

**Punto clave de red:** Ubuntu es el único nodo 7×24. La Mac aporta Plane (el cerebro de datos),
el **motor**, y la impresora.

---

## 3. ⚙️ EL MOTOR — corre en la **Mac** (corrección clave)

> Este fue el dato que se nos había quedado mal («motor en Ubuntu»). **Verificado 05-oct-2026.**

- **Dónde corre:** en `raquel.local`, no en Ubuntu.
- **Cómo:** `~/Library/LaunchAgents/com.masamadre.runner.plist`
  → cada **30 min** (`StartInterval 1800`) ejecuta:
  `/opt/homebrew/bin/python3 /Users/gusluna/.openclaw/workspace/scripts/runner.py --max 4 --max-dia 6 --paralelo 4 --execute`
- **Log:** `~/.openclaw/workspace/logs/runner_mac.log`
- **Qué hace:** mueve la cola de Plane, **una tarea por nodo a la vez** (con lotes de 4 y balanceo),
  con tope diario y lista de bloqueos. Determinista, 0 tokens de LLM.
- **Apagador de emergencia:** existe `~/.openclaw/workspace/.runner_pausado` (o `config.pausado`).
- **Estado ahora:** ⏸️ **PAUSADO desde el 3-oct-2026 13:16** («alto al desarrollo de Codex»).
- **Perillas:** `~/.openclaw/workspace/.runner_config.json`
  (`max_por_corrida`, `max_dia`, `ventana`, `bloqueos`, `pausado`, `max_por_nodo`, `paralelo`, `pilas`).

---

## 4. 🖥️ EL WAR ROOM — cómo está armado hoy

**Path del proyecto:**
```
/Users/gusluna/.openclaw/workspace/metiche-os-migrated-20260408/
```

### 4.1 Arquitectura (dos piezas)

| Pieza | Qué es | Dónde |
|---|---|---|
| **UI / server del tablero** | `dashboard-server.mjs` (Node) sirve `operativo.html` en **`:5063`**; hace **proxy de `/dashboard/*`** a la API | `dashboard/dashboard-server.mjs` |
| **API metiche-os** (`app/`) | consulta la DB local y expone lo que pinta la página | `app/` (FastAPI) · **`:8091`** |
| **Base de datos** | SQLite local | `data/db/metiche_os.db` |

- Página servida en `/`, `/operativo.html` y `/lab`.
- ⚠️ **No confundir** con el Dashboard de Masa Madre del **:5055** (esa es la de ROI, en Ubuntu).

### 4.2 Panel «Catálogo Plane»
- La página llama `GET /dashboard/plane/issues?limit=40`.
- **NO** consulta la API de Plane: lee la tabla local **`plane_sync`**.
- Por issue pinta: `issue_id`, `issue_url`, `task_id/task_title`, `labels`, `issue_state`, `sync_status`, `last_synced_at`, `last_swarm_id`.
- Estado actual: `issue_state` vacíos en `labels` (**por eso el carril NO se ve**).

### 4.3 Tablero de tareas
- Columnas: `queued · running · retrying · failed · done`.

### 4.4 Endpoints vivos del API (`:8091`)
`/stats` · `/tasks` · `/tasks/{id}` · **`/tasks/run`** (Lanzar Tarea Rápida) · `/tasks/{id}/action`
· `/validators` · `/recent-narratives` · `/channels/status` · `/channels/events`
· `/plane/issues` · `/conversations`
· `/fifo-queue` · `/fifo-queue/lengths` · **`/fifo-queue/enqueue`** · **`/fifo-queue/process-next`**

➡️ **Existe tubería para «lanzar»** (formulario + cola FIFO), **pero no hay botón por issue**.

### 4.5 Estado (05-oct 10:48)
✅ `:5063` → **200** · ✅ `:8091/health` → `{"ok":true}` · panel con `total ≥ 1`.

---

## 5. 🧱 LAS 4 PILAS (nomenclatura nueva) — **EN VEREMOS**

- **Qué es:** el tablero deja de ser una sola cola y se vuelve **cuatro carriles**, cada uno con su
  lógica; dentro de cada pila, el issue **más nuevo va primero (LIFO)**.
- **Issue:** **#528**.
- **Carriles y precedencia:** `negocio → roi → operacion → archivo`
- **Clasificación:** determinista (sin LLM) en `scripts/pilas.py`:
  etiqueta `carril:<x>` explícita gana → retorno `roi:*` (ingreso→negocio, ahorro→roi, higiene→operacion)
  → señales duras (`agent:masa-madre`→negocio, `machine:*`→operacion, `era:*`/`archivo`→archivo) → palabras → default `operacion`.
- **Quién lo consume:** `scripts/runner.py` (motor) y `scripts/plane_orquestador.py` (Orquestador 🧭).
- **Estado:** **apagado por default** (opt-in: `CODEX_PILAS=1` o `.runner_config.json` → `"pilas": true`).
- **CLI:** `python3 scripts/pilas.py tablero | cola | clasificar | carril <seq> | validar`.

---

## 6. 👥 Cómo trabajamos (roles y flujo)

| Actor | Dónde | Qué hace |
|---|---|---|
| **Gus** | Telegram | decide, aprueba, cierra ventanas |
| **Metiche** ➰ | Mac | conversa, construye/arregla sistemas, escribe en Plane |
| **Orquestador** 🧭 (@MasamPlaneBot) | Ubuntu | cola, prioridades, asignación a nodos, verifica y **cierra** issues |
| **MOTOR** (`runner.py`) | Mac | mueve la cola solo (hoy **pausado**) |
| **Codex** | Mac + Ubuntu | **desarrollo** (todo lo que requiera código) |
| **Plane** | Mac (Postgres) | base de datos/verdad operativa · espejo `plane-local/` |

**Flujo:** Gus pide → issue en Plane (Regla #24) → Orquestador prioriza/asigna → Codex ejecuta →
Motor/Orquestador mueven la cola → Orquestador verifica y cierra.

---

## 7. 🐛 Desactualizado / deuda técnica (lo que encontré)

1. **War Room:** su `warroom_espejo.py` (docstring, 30-sep) dice **«motor en Ubuntu»** → **falso** (es la Mac).
2. **Links:** el `issue_url` del panel usa el formato viejo
   (`/masa-madre-hq/projects/<uuid>/issues/<uuid>`); el bueno es
   **`/masa-madre-hq/browse/MASAM-<seq>/`**.
3. **Panel sin carril:** los `labels` llegan vacíos → la nomenclatura de 4 pilas no se ve.
4. **Sin botón por issue:** hay «Lanzar Tarea Rápida» + cola FIFO, pero no se puede lanzar **un issue puntual** desde el panel.
5. **Páginas de arquitectura** (`plane-local/pages/arquitectura-*`) marcadas **«verificado 29-sep»**: son anteriores a cambios del motor; **no mencionan el motor**.
6. **Motor pausado** desde el 3-oct (nada se mueve solo).

---

## 8. 🎯 Qué hay que modificar (semilla para el documento de solicitud)

1. **Nomenclatura visible:** etiquetar issues con `carril:negocio|roi|operacion|archivo` (las genera `pilas.py`) y/o **agrupar el panel en 4 columnas**.
2. **Botón «Lanzar» por issue:** endpoint `POST /dashboard/plane/issues/{seq}/launch` que **encola** (reusa la cola FIFO) → lo toma el **MOTOR en la Mac**. **El War Room no ejecuta** (un solo cerebro).
3. **Fix de links** a `/masa-madre-hq/browse/MASAM-<seq>/`.
4. **Refrescar** las páginas de arquitectura y el docstring del War Room (motor en la Mac, 4 pilas, estado real).
5. **Encender las pilas** cuando Gus/Orquestador lo decidan (`"pilas": true`).

---

## 9. 🔬 Cómo comprobar cada línea

```bash
# War Room (Mac)
curl -s -o /dev/null -w "5063 -> %{http_code}\n" http://127.0.0.1:5063/
curl -s http://127.0.0.1:8091/health
curl -s 'http://127.0.0.1:5063/dashboard/plane/issues?limit=5'

# Motor (Mac)
launchctl list | grep masamadre
cat ~/.openclaw/workspace/.runner_config.json
tail -5 ~/.openclaw/workspace/logs/runner_mac.log

# Plane / Docker (Mac)
docker ps --format "{{.Names}} {{.Status}}"

# 4 pilas
cd ~/.openclaw/workspace && python3 scripts/pilas.py tablero
```

---
*Documento vivo. Si algo aquí no cuadra con otra página, esta manda — y se corrige la otra.*
