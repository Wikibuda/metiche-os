-- Week 1 seed data (UUID reales) para pruebas rapidas de enjambres.
-- Compatible con PostgreSQL y SQLite.

BEGIN;

INSERT INTO swarms (id, name, goal, policy, status, parent_issue_id)
VALUES
('2f8f44f0-0d77-4c8a-8dc8-b4693a8f4c2a', 'Swarm Inventario Omnicanal', 'Validar stock y continuidad WhatsApp-Telegram', 'narrative-consensus', 'created', NULL);

INSERT INTO swarm_agents (id, swarm_id, agent_name, task_id, status)
VALUES
('0d2b7d5a-e131-4af2-a9ec-304a57c71053', '2f8f44f0-0d77-4c8a-8dc8-b4693a8f4c2a', 'whatsapp', NULL, 'idle'),
('f7234d19-bf94-463c-8c2a-fbb95f3beabb', '2f8f44f0-0d77-4c8a-8dc8-b4693a8f4c2a', 'shopify', NULL, 'idle'),
('5c85092c-4d25-4d10-b4cb-d4a73a2e8c4e', '2f8f44f0-0d77-4c8a-8dc8-b4693a8f4c2a', 'telegram', NULL, 'idle');

INSERT INTO swarm_cycles (id, swarm_id, cycle_number, phase, outcome, correlation_id)
VALUES
('7f197090-6a4f-4edf-a7c8-c38fc8f0575d', '2f8f44f0-0d77-4c8a-8dc8-b4693a8f4c2a', 1, 'completed', 'Consenso alcanzado: notificar reposicion y actualizar canal', '67c5c524-52fa-4b7d-a4ee-9f1add3521dc');

INSERT INTO swarm_votes (id, cycle_id, agent_name, vote, argument)
VALUES
('f28b65d4-b3d1-4cae-a5ab-e7e74df6f5fc', '7f197090-6a4f-4edf-a7c8-c38fc8f0575d', 'whatsapp', 'accept', 'El cliente reporta faltante recurrente; urge confirmar inventario.'),
('dd5a8691-4dda-4199-b55d-10a4e95f58be', '7f197090-6a4f-4edf-a7c8-c38fc8f0575d', 'shopify', 'accept', 'El stock esta bajo segun el ultimo corte; recomiendo aviso preventivo.'),
('2f9117ed-8ab7-4e80-be31-31f5ec1d17e7', '7f197090-6a4f-4edf-a7c8-c38fc8f0575d', 'telegram', 'abstain', 'No hay mensaje nuevo del cliente en Telegram durante este ciclo.');

-- Solo insertar en task_events si ya existe un task_id valido en tu entorno.
-- Si no hay task_id, omitir este bloque o reemplazar por uno existente.
-- INSERT INTO task_events (
--   id, task_id, execution_id, event_type, event_summary, importance_level, wonder_level,
--   payload_json, occurred_at, swarm_id, cycle_id, correlation_id, client_key, severity
-- ) VALUES (
--   'fd24d4b2-d925-4d3d-b7dd-6e63fba17f2f',
--   '<task_id_existente>',
--   NULL,
--   'swarm.cycle.completed',
--   'Ciclo completado con consenso narrativo',
--   'high',
--   4,
--   '{"outcome":"ok"}',
--   CURRENT_TIMESTAMP,
--   '2f8f44f0-0d77-4c8a-8dc8-b4693a8f4c2a',
--   '7f197090-6a4f-4edf-a7c8-c38fc8f0575d',
--   '67c5c524-52fa-4b7d-a4ee-9f1add3521dc',
--   'cliente-44',
--   'info'
-- );

COMMIT;
