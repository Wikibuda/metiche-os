# Diagramas de Metiche-OS

Este documento centraliza diagramas de arquitectura y flujo operativo.

## 1) Arquitectura general

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
    P3[Worker plane-watch]
    P4[Pull run:enjambre]
    P5[Issue y comentario]
  end

  B --> P1
  P1 --> P2 --> P3 --> P4 --> P5
  P4 --> B
  H --> P5

  subgraph DASHBOARD[Dashboard]
    direction TB
    D1[operativo.html]
    D2[swarm-console.html]
  end

  B --> D1
  B --> D2
```

La arquitectura de Metiche-OS se organiza en torno a un coordinador central (Metiche) que recibe ordenes del Jefe (Gus) o de Plane (a traves del notificador). Las tareas pueden ejecutarse de forma inmediata (lanzando enjambres) o encolarse en una cola FIFO con prioridades (blocking, urgent, high, medium, low).

Los enjambres ejecutan trabajo en background a traves de agentes especializados (Dashboard, WhatsApp, Shopify, DeepSeek, Plane, Control de Ingresos/Egresos). Una validacion automatica consolida los resultados en un reporte unico que se entrega al Jefe.

El sistema narrativo registra cada evento (`task_events`), los promueve a candidatos (`narrative_candidates`) y los convierte en cronicas (`narrative_entries`) que alimentan la bitacora de asombros.

La integracion con Plane es bidireccional:

- Metiche -> Plane: a traves del adaptador DB/API, puede crear y actualizar issues (por ejemplo, cuando una tarea falla).
- Plane -> Metiche: el worker `plane-watch` detecta issues con etiqueta `run:enjambre` y lanza enjambres en Metiche (flecha `P4 --> B`).

El dashboard ofrece dos vistas principales: `operativo.html` (monitoreo general) y `swarm-console.html` (control de enjambres).

## 2) Flujo webhook de WhatsApp

```mermaid
sequenceDiagram
  participant OC as OpenClaw
  participant API as Metiche API
  participant MEM as Channel Memory
  participant EV as task_events
  participant DB as Dashboard

  OC->>API: POST /webhooks/openclaw/whatsapp
  API->>API: Normaliza payload (phone/text)
  API->>EV: Inserta whatsapp_message_received
  API->>MEM: Actualiza conversation_history
  API-->>OC: {ok:true}
  DB->>API: GET /dashboard/conversations
  API-->>DB: Historial por cliente
```

Cuando un cliente envia un mensaje a traves de WhatsApp Business, OpenClaw lo reenvia al webhook de Metiche (`POST /webhooks/openclaw/whatsapp`). La API normaliza el payload extrayendo el numero de telefono (`from`) y el texto (`content`). A continuacion, registra el evento `whatsapp_message_received` en `task_events` (para trazabilidad) y actualiza el historial de la conversacion en `channel_memory` (clave por numero de telefono). El webhook responde con `{ok:true}` para que OpenClaw no reintente.

El dashboard, al consultar `GET /dashboard/conversations`, recupera el historial completo agrupado por cliente, mostrando los mensajes en orden cronologico. Este flujo convierte a Metiche en un "cronista silencioso" de las conversaciones reales, sin interferir en la operacion del bot "Masa Madre".

## 3) Flujo Plane -> Enjambre

```mermaid
sequenceDiagram
  participant W as Worker (plane-watch)
  participant PL as Plane DB
  participant PS as plane_sync (tabla)
  participant SW as Swarm Service
  participant PI as Plane Issue

  loop Cada intervalo (ej. 30s)
    W->>PL: list_issues(labels=[run:enjambre])
    PL-->>W: Lista de issues candidatos
    alt Por cada issue
        W->>PS: SELECT processed = plane_sync WHERE issue_id = ?
        alt Si NO existe (no procesado)
            PS-->>W: no registrado
            W->>SW: create_swarm(..., parent_issue_id)
            W->>SW: run_swarm_cycle(...)
            W->>PS: INSERT (issue_id, swarm_id, sync_status='success')
            W->>PI: comment_on_issue(resultado)
            W->>PI: update_issue(state)
        else Si YA existe (procesado)
            PS-->>W: ya procesado
            W->>W: skip (log: already processed)
        end
    end
  end
```

El worker `plane-watch` consulta periodicamente (por defecto cada 30 segundos) los issues de Plane que tienen la etiqueta `run:enjambre`. Para cada issue candidato, verifica en la tabla `plane_sync` si ya ha sido procesado.

Si no existe un registro, crea un enjambre vinculado al issue (`parent_issue_id`), ejecuta su ciclo, y registra la operacion en `plane_sync` (guardando el `issue_id` y el `swarm_id`). A continuacion, anade un comentario en el issue de Plane con el resultado y actualiza su estado (por ejemplo, a In Progress o Done).

Si el issue ya existe en `plane_sync`, el worker lo omite (log como "already processed"). Esto garantiza idempotencia: un mismo issue no lanza multiples enjambres, incluso si el worker se reinicia o si el issue se actualiza por otros motivos (como anadir un comentario).

## 4) Flujo de operacion diaria recomendado

```mermaid
flowchart LR
  A[Revisar dashboard] --> B[Validar canales]
  B --> C[Revisar conversaciones]
  C --> D[Atender incidentes]
  D --> E[Lanzar enjambre si aplica]
  E --> F[Ver resultado en Plane]
  F --> G[Actualizar bitacora y cierre]
```

## 5) Referencias cruzadas

- [README](../README.md)
- [Operacion diaria](OPERACION.md)
- [Despliegue](DESPLIEGUE.md)
- [Integracion Plane](INTEGRACION_PLANE.md)
