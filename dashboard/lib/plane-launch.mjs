// plane-launch.mjs — [#530 · 05-oct-2026] Acciones de host del War Room sobre Plane.
//
// El War Room NO ejecuta: el botón «Lanzar» ENCOLA el issue en la MISMA cola que el
// Orquestador ya drena con `scripts/plane_orquestador.py publicar` (un solo cerebro).
// Este módulo vive fuera del contenedor (lo importa dashboard-server.mjs, que corre en el
// host) porque la cola está en ~/.openclaw/workspace y el contenedor la monta read-only.

import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";

const HOME = os.homedir();
const WORKSPACE = process.env.WARROOM_WORKSPACE || path.join(HOME, ".openclaw", "workspace");

export const PLANE_PENDIENTES =
  process.env.WARROOM_PLANE_PENDIENTES || path.join(WORKSPACE, ".plane_cambios_pendientes.jsonl");
export const RUNNER_CONFIG = process.env.WARROOM_RUNNER_CONFIG || path.join(WORKSPACE, ".runner_config.json");
export const RUNNER_PAUSA = process.env.WARROOM_RUNNER_PAUSA || path.join(WORKSPACE, ".runner_pausado");

// Lee la cola de cambios pendientes del Orquestador (una línea JSON por cambio).
export async function readPendingChanges() {
  try {
    const raw = await fs.readFile(PLANE_PENDIENTES, "utf-8");
    return raw
      .split("\n")
      .map((linea) => linea.trim())
      .filter(Boolean)
      .map((linea) => {
        try { return JSON.parse(linea); } catch { return null; }
      })
      .filter(Boolean);
  } catch {
    return [];
  }
}

// Botón «Lanzar»: deja la orden en la cola del Orquestador. NO ejecuta nada aquí.
export async function enqueuePlaneLaunch(seq) {
  const limpio = String(seq || "").trim();
  if (!/^[0-9]{1,6}$/.test(limpio)) {
    return { ok: false, error: "seq inválido (solo dígitos)" };
  }
  const numero = Number(limpio);
  const cambio = {
    tipo: "estado",
    seq: numero,
    estado: "Todo",
    motivo: "lanzado desde el War Room (botón «Lanzar»)",
    origen: "war-room-530",
    cuando: new Date().toISOString()
  };
  try {
    const existentes = await readPendingChanges();
    const yaEncolado = existentes.some(
      (c) => Number(c?.seq) === numero && c?.tipo === "estado" && String(c?.estado) === "Todo"
    );
    if (yaEncolado) {
      return {
        ok: true, seq: numero, queued: false, ya_encolado: true, cola: PLANE_PENDIENTES,
        nota: `El issue #${numero} ya tenía una orden de lanzamiento en la cola.`
      };
    }
    await fs.appendFile(PLANE_PENDIENTES, JSON.stringify(cambio) + "\n", "utf-8");
    return {
      ok: true, seq: numero, queued: true, cola: PLANE_PENDIENTES, cuando: cambio.cuando,
      nota: `Encolado #${numero} para el motor. El Orquestador lo publica en Plane y el runner lo toma.`
    };
  } catch (error) {
    return { ok: false, seq: numero, error: `No pude escribir la cola: ${error.message}` };
  }
}

// Estado del MOTOR para que el War Room lo muestre. Solo lee; no cambia nada.
export async function buildMotorStatus() {
  let config = {};
  try {
    config = JSON.parse(await fs.readFile(RUNNER_CONFIG, "utf-8")) || {};
  } catch {
    config = {};
  }
  let pausado = config.pausado === true;
  let pausaArchivo = null;
  try {
    await fs.access(RUNNER_PAUSA);
    pausaArchivo = RUNNER_PAUSA;
    pausado = true;
  } catch {
    /* sin archivo de pausa */
  }
  return {
    ok: true,
    pausado,
    pilas: Boolean(config.pilas),
    max_por_corrida: config.max_por_corrida ?? null,
    max_dia: config.max_dia ?? null,
    ventana: config.ventana ?? null,
    pausa_archivo: pausaArchivo,
    nota: pausado
      ? 'El motor está EN PAUSA (.runner_pausado / "pausado": true). Encenderlo es decisión de Gus/Orquestador.'
      : "El motor está activo."
  };
}
