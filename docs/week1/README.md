# Semana 1 - Ready Pack (Fase 2: Enjambres y Canales)

Estado: **Ready for Review**
Version de contratos: **v1alpha1**

## 1) Entregables incluidos

### Migraciones SQL

- `app/sql/migrations/week1/up_postgres.sql`
- `app/sql/migrations/week1/up_sqlite.sql`
- `app/sql/migrations/week1/down_postgres.sql`
- `app/sql/migrations/week1/down_sqlite.sql`
- `app/sql/migrations/week1/seed_week1.sql`

Cobertura:

- Tablas: `swarms`, `swarm_agents`, `swarm_cycles`, `swarm_votes`.
- Extension de `memory_entries` (Opcion B): `source`, `related_channel`, `client_key`, `correlation_id`.
- Indices: `idx_memory_client`, `idx_memory_correlation`, `idx_memory_multicanal`, `idx_task_events_swarm`.
- Constraint: `CHECK` de `memory_entries.source` con enum (`system`, `channel`, `swarm`).
- Rollback SQLite con estrategia de reconstruccion de tabla.

### Contratos JSON v1alpha1

- `contracts/v1alpha1/UnifiedTask.json`
- `contracts/v1alpha1/Swarm.json`
- `contracts/v1alpha1/task_events.json`

Cobertura:

- Versionado explicito (`version: v1alpha1`).
- Validaciones: campos requeridos, enums, longitudes maximas, formatos UUID/date-time.
- Ejemplos: `happy_path`, `edge_case`, `error_case` en cada contrato.

## 2) Seed de prueba

Archivo: `app/sql/migrations/week1/seed_week1.sql`

- Usa UUIDs reales para `swarms`, `swarm_agents`, `swarm_cycles`, `swarm_votes`.
- Incluye bloque opcional (comentado) para `task_events` si existe `task_id` valido.

## 3) Checklist DoD (Definition of Done)

### Historia 1.1 - Modelo de datos Swarm + UnifiedTask

- [x] Existen scripts `up` y `down` separados para PostgreSQL y SQLite.
- [x] Se crean tablas `swarms`, `swarm_agents`, `swarm_cycles`, `swarm_votes`.
- [x] Se definen llaves primarias, foraneas, enums y limites de longitud.
- [x] Existen indices para consultas operativas y trazabilidad.
- [x] Hay seed SQL con UUIDs reales.

### Historia 1.2 - Integracion de memoria narrativa

- [x] `memory_entries` extiende Opcion B con 4 columnas nuevas.
- [x] Existe `CHECK` para `memory_entries.source`.
- [x] Existe indice compuesto multicanal (`source`, `related_channel`, `client_key`).
- [x] Se agrega indice de correlacion (`correlation_id`) para trazabilidad.
- [x] Rollback SQLite preserva datos al reconstruir tabla.

### Historia 1.3 - Catalogo task_events y observabilidad

- [x] Contrato `task_events` versionado en `v1alpha1`.
- [x] Catalogo incluye evento, severidad y campos requeridos por tipo.
- [x] Esquema define limites y formatos.
- [x] Se agregan columnas de correlacion de enjambre en BD (`swarm_id`, `cycle_id`, `correlation_id`, `client_key`, `severity`).
- [x] Existe indice `idx_task_events_swarm`.

### DoD transversal

- [x] Archivos ubicados en rutas estables y predecibles.
- [x] SQL separado por motor para evitar sintaxis cruzada.
- [x] Contratos y checklist documentados para handoff a Semana 2.

## 4) Orden recomendado de ejecucion

### PostgreSQL

1. Ejecutar `up_postgres.sql`.
2. Ejecutar `seed_week1.sql`.
3. Validar inserts y consultas basicas.
4. Si se requiere rollback, ejecutar `down_postgres.sql`.

### SQLite

1. Ejecutar `up_sqlite.sql`.
2. Ejecutar `seed_week1.sql`.
3. Validar inserts y consultas basicas.
4. Si se requiere rollback, ejecutar `down_sqlite.sql`.

## 5) Notas de implementacion para Semana 2

- `task_events` ya permite correlacion completa por `swarm_id` y `cycle_id`.
- `memory_entries` ya soporta continuidad multicanal por `client_key` y `related_channel`.
- `swarm_votes.argument` habilita politica `narrative-consensus`.
- IDs normalizados en formato UUID.
