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
- [API HTTP](#api-http)
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
 %% === PALETA DE COLORES PRINCIPAL === 
 classDef jefe fill:#FF6B9D,stroke:#333,stroke-width:3px,color:#fff,font-weight:bold 
 classDef metiche fill:#4A90E2,stroke:#333,stroke-width:3px,color:#fff,font-weight:bold 
 classDef bot fill:#FFD166,stroke:#333,stroke-width:2px,color:#333 
 classDef decision fill:#06D6A0,stroke:#333,stroke-width:3px,color:#fff,font-weight:bold 
 classDef enjambre fill:#118AB2,stroke:#333,stroke-width:2px,color:#fff 
 classDef proyecto fill:#EF476F,stroke:#333,stroke-width:2px,color:#fff 
 classDef regla fill:#7209B7,stroke:#333,stroke-width:2px,color:#fff 
 classDef sistema fill:#073B4C,stroke:#333,stroke-width:2px,color:#fff 
 classDef entrega fill:#FF9E00,stroke:#333,stroke-width:3px,color:#fff,font-weight:bold 
 classDef cola fill:#FFA726,stroke:#333,stroke-width:3px,color:#fff,font-weight:bold 
 classDef monticulo fill:#8AC926,stroke:#333,stroke-width:2px,color:#fff 
 classDef memoria fill:#9C27B0,stroke:#333,stroke-width:2px,color:#fff 
 classDef optimizacion fill:#FF5722,stroke:#333,stroke-width:2px,color:#fff 
 
 %% === NODOS PRINCIPALES === 
 A["🏢 JEFE ADOPTIVO Gus"] -->|📨 Solicitud prioritaria| B["🤖 METICHE Coordinador"] 
 A -->|💬 Comenta en Plane| N["🤖 PLANE NOTIFIER BOT"] 
 
 %% === DECISIÓN DE COLA === 
 B --> D0{"🎯 ¿Orden explícita ejecución inmediata?"} 
D0 -->|Si Gus ordena ejecucion inmediata| C{"🎯 Decisión METICHE"} 
 D0 -->|📋 No (por defecto)| COLA_FIFO["📋 COLA FIFO-EJECUTIVA"] 
 
 %% === COLA FIFO CON MONTÍCULOS === 
 COLA_FIFO -->|🔁 Procesar siguiente| D0 
 
 subgraph COLA["📋 COLA FIFO-EJECUTIVA (MONTÍCULOS)"] 
    direction LR 
    MONTICULO_EN_PROGRESO["⚡ MONTÍCULO EN PROGRESO"] 
    MONTICULO_BLOQUEANTES["⛰️ MONTÍCULO BLOQUEANTES"] 
    MONTICULO_URGENTES["🔥 MONTÍCULO URGENTES"] 
    MONTICULO_HIGH["🚀 MONTÍCULO HIGH"] 
    MONTICULO_MEDIUM["📊 MONTÍCULO MEDIUM"] 
    MONTICULO_LOW["🐌 MONTÍCULO LOW"] 
    
    MONTICULO_EN_PROGRESO -->|Primero| MONTICULO_BLOQUEANTES 
    MONTICULO_BLOQUEANTES -->|Segundo| MONTICULO_URGENTES 
    MONTICULO_URGENTES -->|Tercero| MONTICULO_HIGH 
    MONTICULO_HIGH -->|Cuarto| MONTICULO_MEDIUM 
    MONTICULO_MEDIUM -->|Quinto| MONTICULO_LOW 
 end 
 
 %% Contenido de los montículos (como nodos independientes para mantener información) 
 PROG_217["#217 Ideas Brillantes (Pool Memoria)"] --> MONTICULO_EN_PROGRESO 
 PROG_218["#218 Optimización DeepSeek + TRAE IDE"] --> MONTICULO_EN_PROGRESO 
 PROG_219["#219 Integración TRAE IDE"] --> MONTICULO_EN_PROGRESO 
 
 BLOQ_208["#208 Bomberazo #001"] --> MONTICULO_BLOQUEANTES 
 BLOQ_204["#204 Presupuesto DeepSeek"] --> MONTICULO_BLOQUEANTES 
 BLOQ_203["#203 Regla #10 JOY"] --> MONTICULO_BLOQUEANTES 
 
 URG_91["#91 Telegram Polling Loops"] --> MONTICULO_URGENTES 
 URG_93["#93 Errores WhatsApp"] --> MONTICULO_URGENTES 
 URG_94["#94 Fermentación IA"] --> MONTICULO_URGENTES 
 
 HIGH_89["#89 Configurar SMTP"] --> MONTICULO_HIGH 
 HIGH_90["#90 Recuperar voz TTS"] --> MONTICULO_HIGH 
 HIGH_92["#92 Monitor Telegram"] --> MONTICULO_HIGH 
 
 MED_206["#206 Árbol Decisiones"] --> MONTICULO_MEDIUM 
 MED_210["#210 Permisos device-auth"] --> MONTICULO_MEDIUM 
 MED_212["#212 Actualizar diagrama"] --> MONTICULO_MEDIUM 
 
 LOW_201["#201 Git cleanup"] --> MONTICULO_LOW 
 LOW_202["#202 Test BD"] --> MONTICULO_LOW 
 LOW_211["#211 Limpieza demo"] --> MONTICULO_LOW 
 
 %% === DECISIONES METICHE === 
 C -->|🤖 Tarea automatizable| D["🚀 LANZAR ENJAMBRE"] 
 C -->|🧠 Planificación estratégica| E["💡 METICHE DIRECTAMENTE"] 
 C -->|📝 Respuesta a comentario| P["✍️ Responder en Plane"] 
 C -->|💰 Análisis financiero| ROI["📊 PROYECTO ROI"] 
 C -->|⚡ Automatización total| ATP["🚀 AUTOMATIZACIÓN TOTAL PLANE"] 
 
 N -->|📨 Notificación Telegram| B 
 N -->|🗃️ BD Polling cada 2min| O["🗃️ Base de Datos Plane"] 
 
 %% === SISTEMA HÍBRIDO DEEPSEEK === 
 subgraph SISTEMA_HIBRIDO["🤖 SISTEMA HÍBRIDO DEEPSEEK (Optimización costos)"] 
    direction LR 
    ROUTER["🎯 Router Clasificador"] -->|Tarea simple| CHAT["💬 DeepSeek Chat ($0.14/1M)"] 
    ROUTER -->|Tarea compleja| REASONER["🧠 DeepSeek Reasoner ($0.27/1M)"] 
    ROUTER -->|WhatsApp Business| REASONER_WA["📱 WhatsApp (Siempre Reasoner)"] 
    ROUTER -->|Duda| REASONER 
    
    CHAT -->|Ahorro 48%| METRICAS["📊 Métricas Ahorro"] 
    REASONER -->|Calidad garantizada| METRICAS 
    REASONER_WA -->|Regla #3| METRICAS 
 end 
 
 B -->|Tareas internas| ROUTER 
 E -->|Planificación| REASONER 
 
 %% === POOL DE MEMORIA INTELIGENTE === 
 subgraph POOL_MEMORIA["🧠 POOL DE MEMORIA INTELIGENTE (Idea #1)"] 
    direction TB 
    MEM_API["📡 API REST /memory"] -->|POST| MEM_DB["🗃️ SQLite + JSON"] 
    MEM_API -->|GET query| MEM_DB 
    MEM_DB -->|Reglas| MEM_RULES["📜 Reglas #1-#11"] 
    MEM_DB -->|Decisiones| MEM_DECISIONS["💡 Decisiones históricas"] 
    MEM_DB -->|Errores| MEM_ERRORS["⚠️ Errores aprendidos"] 
    MEM_DB -->|Éxitos| MEM_SUCCESS["✅ Éxitos replicables"] 
 end 
 
 B -->|Aprendizajes| MEM_API 
 G -->|Datos enjambres| MEM_API 
 H -->|Interacciones WhatsApp| MEM_API 
 
 %% === ENJAMBRES === 
 D --> F["🔄 TRABAJO EN BACKGROUND"] 
 
 subgraph Enjambres ["🌈 ENJAMBRES ESPECIALIZADOS"] 
   G["📊 Enjambre Dashboard"] 
   H["💬 Enjambre WhatsApp"] 
   I["🛒 Enjambre Shopify"] 
   J["🤖 Enjambre DeepSeek"] 
   K["📋 Enjambre Plane"] 
   CIE["💰 CONTROL INGRESOS/EGRESOS"] 
 end 
 
 F --> G 
 F --> H 
 F --> I 
 F --> J 
 F --> K 
 F --> CIE 
 
 %% === VALIDACIÓN Y REPORTE === 
 G --> L["✅ VALIDACIÓN AUTOMÁTICA"] 
 H --> L 
 I --> L 
 J --> L 
 K --> L 
 CIE --> L 
 
 L --> M["📄 REPORTE ÚNICO FINAL"] 
 E --> M 
 P --> Q["💬 Comentario insertado en Plane"] 
 Q --> R["🏷️ Marcado como procesado"] 
 ROI --> M 
 ATP --> M 
 
 M --> S["🎁 ENTREGA A JEFE"] 
 
 %% === REGLAS GRABADAS EN PIEDRA === 
 T["🪨 REGLAS GRABADAS EN PIEDRA"] --> B 
 
 subgraph Reglas ["📜 REGLAS OPERATIVAS"] 
 U["1️⃣ No pedir tareas manuales automatizables"] 
 V["2️⃣ No usar wacli"] 
 W["3️⃣ WhatsApp siempre con Reasoner (NIVEL DIOS)"] 
 X["4️⃣ Acceso a Plane por BD directa"] 
 Y["5️⃣ Cargar contexto tras reset"] 
 Z["6️⃣ Dashboard tiempo real"]
 AA["7️⃣ Validación post-configuración (Telegram+WhatsApp+Dashboard)"] 
 BB["8️⃣ LaunchAgent > crontab para entorno completo"] 
 CC["9️⃣ Registro modificaciones en Plane"] 
 JOY["🔟 NO DEJES PARA MAÑANA LO QUE PUEDES HACER JOY"] 
 REGLA11["1️⃣1️⃣ Órdenes Jefe Gus se encolan por defecto"] 
 end 
 
 T --> U 
 T --> V 
 T --> W 
 T --> X 
 T --> Y 
 T --> Z 
 T --> AA 
 T --> BB 
 T --> CC 
 T --> JOY 
 T --> REGLA11 
 
 %% === SISTEMA PLANE-KEEPER === 
 X --> K 
 X --> AB["📦 Plane-Keeper Sistema"] 
 
 subgraph Herramientas ["🔧 HERRAMIENTAS PLANE"] 
 AC["🔧 plane_db_helper.py"] 
 AD["📝 plane_keeper.py"] 
 AE["🎯 Registro automático 'Inicio + Final'"] 
 AF["👁️ plane_monitor.py"] 
 end 
 
 AB --> AC 
 AB --> AD 
 AB --> AE 
 AB --> AF 
 
 %% === MANTENIMIENTO AUTOMÁTICO PLANE === 
 K --> AG["🔄 Mantenimiento automático Plane"] 
 
 subgraph Funcionalidades ["📈 FUNCIONALIDADES PLANE"] 
 AH["📊 Issues actualizados"] 
 AI["🏷️ Labels sincronizados"] 
 AJ["📈 Métricas automatizadas"] 
 AK["💬 Comentarios monitoreados"] 
 end 
 
 AG --> AH 
 AG --> AI 
 AG --> AJ 
 AG --> AK 
 
 %% === DASHBOARD TIEMPO REAL === 
 Z --> AL["⚡ Refresh manual = instantáneo"] 
 Z --> AM["🔄 Auto-refresh cada 5 min"] 
 Z --> AN["📡 Datos Shopify/DeepSeek real-time"] 
 
 %% === EXPANSIÓN PROYECTO ROI === 
 ROI --> ROI1["📈 Análisis CSV histórico"] 
 ROI --> ROI2["💰 Tracking gastos por agente"] 
 ROI --> ROI3["📊 Dashboard métricas ROI"] 
 ROI --> ROI4["🤖 Decisiones inteligentes modelos"] 
 
 ROI1 --> CSV["💾 CSV histórico: $60.83 USD (1-25 marzo)"] 
 CSV --> CSV1["💵 Reasoner: $57.30 USD (94.2%)"] 
 
 %% === ASIGNACIÓN DE CLASES === 
 class A jefe 
 class B metiche 
 class N bot 
 class D0 decision 
 class C decision 
 class D,E,P,ROI,ATP proyecto 
 class G,H,I,J,K,CIE enjambre 
 class U,V,W,X,Y,Z,AA,BB,CC,JOY,REGLA11 regla 
 class O,AB,AC,AD,AE,AF,AG,AH,AI,AJ,AK sistema 
 class ROUTER,CHAT,REASONER,REASONER_WA,METRICAS optimizacion 
 class MEM_API,MEM_DB,MEM_RULES,MEM_DECISIONS,MEM_ERRORS,MEM_SUCCESS memoria 
 class PROG_217,PROG_218,PROG_219,BLOQ_208,BLOQ_204,BLOQ_203,URG_91,URG_93,URG_94,HIGH_89,HIGH_90,HIGH_92,MED_206,MED_210,MED_212,LOW_201,LOW_202,LOW_211 monticulo 
 class COLA_FIFO cola 
 class S entrega
```

### Capas arquitectónicas (estado actual)

- Operativa: flujo de tareas, decisiones, ejecución, cola y validación (`app/domain/tasks`).
- Memoria narrativa: eventos, candidatos y crónicas (`app/domain/narrative` + tablas narrativas).
- Validación multicanal real: Telegram, WhatsApp, Shopify, Dashboard, Deepseek (`app/domain/validators`).
- Proyecciones: bitácora Markdown exportable (`app/projections/bitacora.py`).
- Integración externa: Plane para registrar fallas de validación (`app/integrations/plane.py`).

### Componentes de visión (próximamente)

El diagrama incluye piezas estratégicas todavía no implementadas en este repositorio como API `/memory`, Plane-Keeper completo, y automatización total de Plane; se mantienen como hoja de ruta.

## Características Principales

- Gestión de tareas y rutas de decisión (`run`, cola, procesamiento siguiente).
- Cola de prioridad con buckets operativos (`blocking`, `urgent`, `high`, `medium`, `low`).
- Validación real por canal y validación manual por `task_id`.
- Emisión de `validation_attempt` como eventos operativos.
- Narrativa automática con nivel de asombro (3, 4, 5 según resultado).
- CLI de operación (`run`, `validate`, `narrator-tick`, `--cuentame`, `build-bitacora`).
- API HTTP para tareas, narrativa y salud.
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
git clone <tu-repo-url>
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

PLANE_BASE_URL=https://api.plane.so
PLANE_WORKSPACE_SLUG=<slug>
PLANE_PROJECT_ID=<id>
PLANE_API_KEY=<token>
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

## API HTTP

### Levantar API

```bash
uvicorn app.main:app --reload --port 8000
```

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

### Ejemplos curl

```bash
curl -s http://127.0.0.1:8000/health | jq
```

```bash
curl -s -X POST http://127.0.0.1:8000/tasks/run \
  -H "Content-Type: application/json" \
  -d '{
    "title": "probar validador shopify",
    "description": "prueba técnica",
    "task_type": "shopify",
    "execution_mode": "immediate"
  }' | jq
```

```bash
curl -s http://127.0.0.1:8000/tasks/<task_id>/flow | jq
```

## Integración con Plane

Cuando `PLANE_SYNC_ENABLED=true` y la validación falla:

- Se crea un issue con contexto de canales fallidos.
- Se agrega comentario al issue con resumen de la falla.

Cliente de integración:

- `app/integrations/plane.py` (`create_issue`, `update_issue`, `comment_on_issue`).

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

No en este repositorio actual. Aparece en la visión/roadmap del diagrama como **próximamente**.

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
