#!/usr/bin/env node
/**
 * deepseek_balance_egress.mjs — SALDO de DeepSeek por el EGRESS PROXY del gateway.
 *
 * Issue #598 «Migrar saldo DeepSeek del dashboard al egress proxy».
 *
 * QUÉ HACE
 *   Consulta https://api.deepseek.com/user/balance y deja el resultado normalizado en
 *   dashboard_parts/deepseek_balance.json. El dashboard (dashboard-server.mjs, :5063) LEE
 *   ese archivo; ya NO necesita la llave cruda en su process.env.
 *
 * POR QUÉ UN FETCHER APARTE (y no dentro del dashboard)
 *   El egress proxy del gateway (secrets.egressProxy) sólo sustituye el sentinel por el
 *   secreto real en SUBPROCESOS hospedados por el gateway (Gateway-hosted exec). Un server
 *   suelto (el dashboard) ni recibe el proxy ni el sentinel. Por eso la consulta la hace
 *   este script —que corre como comando del gateway— y el dashboard consume el archivo.
 *
 * CREDENCIAL
 *   Lee DEEPSEEK_API_KEY del entorno. Con secrets.egressProxy.enabled=true el gateway
 *   entrega un SENTINEL y lo sustituye por el secreto del store sólo en egress hacia
 *   api.deepseek.com (binding `--allow-host api.deepseek.com`). Este script NUNCA ve la
 *   llave. Sin el proxy sigue funcionando si el entorno trae la llave real (fallback).
 *
 * USO
 *   node deepseek_balance_egress.mjs            # consulta y escribe el JSON
 *   node deepseek_balance_egress.mjs --print     # imprime el JSON (no escribe)
 *   node deepseek_balance_egress.mjs --dry-run   # no escribe, sólo reporta
 *   node deepseek_balance_egress.mjs --check-env # diagnóstico de entorno (sin red)
 *   node deepseek_balance_egress.mjs --strict    # exit!=0 si falló (default: fail-soft)
 */
import { promises as fs } from "node:fs";
import path from "node:path";
import os from "node:os";

const OUT_FILE =
  process.env.DEEPSEEK_BALANCE_FILE ||
  path.join(os.homedir(), ".openclaw", "workspace", "dashboard_parts", "deepseek_balance.json");
const API_URL = process.env.DEEPSEEK_BALANCE_URL || "https://api.deepseek.com/user/balance";
const TIMEOUT_MS = Number(process.env.DEEPSEEK_BALANCE_TIMEOUT_MS || 10000);
const MAX_AGE_MS = Number(process.env.DEEPSEEK_BALANCE_MAX_AGE_MS || 900000); // 15 min

const args = new Set(process.argv.slice(2));
const PRINT = args.has("--print");
const CHECK_ENV = args.has("--check-env");
const DRY = args.has("--dry-run") || PRINT || CHECK_ENV;
const STRICT = args.has("--strict");

function nowIso() {
  return new Date().toISOString();
}

async function readExisting() {
  try {
    return JSON.parse(await fs.readFile(OUT_FILE, "utf-8"));
  } catch {
    return null;
  }
}

function isFreshOk(obj) {
  if (!obj || obj.ok !== true || !obj.fetched_at) return false;
  const age = Date.now() - Date.parse(obj.fetched_at);
  return Number.isFinite(age) && age >= 0 && age < MAX_AGE_MS;
}

async function writeOut(obj) {
  await fs.mkdir(path.dirname(OUT_FILE), { recursive: true });
  const tmp = OUT_FILE + ".tmp";
  await fs.writeFile(tmp, JSON.stringify(obj, null, 2) + "\n", "utf-8");
  await fs.rename(tmp, OUT_FILE);
}

function normalize(data) {
  let total = "0.00";
  let granted = "0.00";
  let topped = "0.00";
  let currency = "USD";
  if (Array.isArray(data && data.balance_infos) && data.balance_infos.length) {
    const b = data.balance_infos[0];
    total = b.total_balance != null ? b.total_balance : total;
    granted = b.granted_balance != null ? b.granted_balance : granted;
    topped = b.topped_up_balance != null ? b.topped_up_balance : topped;
    currency = b.currency != null ? b.currency : currency;
  } else if (data && data.total_balance != null) {
    total = data.total_balance;
    granted = data.granted_balance != null ? data.granted_balance : granted;
    topped = data.topped_up_balance != null ? data.topped_up_balance : topped;
    currency = data.currency != null ? data.currency : currency;
  }
  return {
    total_balance: String(total),
    granted_balance: String(granted),
    topped_up_balance: String(topped),
    currency: String(currency)
  };
}

async function fetchBalance(token) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(API_URL, {
      method: "GET",
      headers: {
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json",
        "Accept": "application/json"
      },
      signal: ctrl.signal
    });
    if (!res.ok) throw new Error("HTTP " + res.status + " " + res.statusText);
    const data = await res.json();
    return Object.assign({ ok: true, fetched_at: nowIso(), source: "egress" }, normalize(data));
  } finally {
    clearTimeout(timer);
  }
}

function proxyInfo() {
  return {
    https_proxy: process.env.HTTPS_PROXY || process.env.https_proxy || null,
    http_proxy: process.env.HTTP_PROXY || process.env.http_proxy || null,
    node_use_env_proxy: process.env.NODE_USE_ENV_PROXY || null,
    extra_ca: process.env.NODE_EXTRA_CA_CERTS || null
  };
}

function looksSentinel(v) {
  return /^oc-sent-v2.*end$/i.test(v || "");
}

async function main() {
  const token = String(process.env.DEEPSEEK_API_KEY || "").trim();

  if (CHECK_ENV) {
    console.log(
      JSON.stringify(
        {
          out_file: OUT_FILE,
          has_key: !!token,
          key_is_sentinel: looksSentinel(token),
          proxy: proxyInfo(),
          api_url: API_URL
        },
        null,
        2
      )
    );
    return 0;
  }

  if (!token) {
    const out = {
      ok: false,
      error: "DEEPSEEK_API_KEY no presente en el entorno",
      fetched_at: nowIso(),
      source: "egress"
    };
    console.error("[deepseek-egress] " + out.error);
    if (!DRY) {
      const ex = await readExisting();
      if (!isFreshOk(ex)) await writeOut(out);
    }
    if (PRINT) console.log(JSON.stringify(out, null, 2));
    return STRICT ? 1 : 0;
  }

  let result;
  try {
    result = await fetchBalance(token);
  } catch (err) {
    result = {
      ok: false,
      error: String(err && err.message ? err.message : err),
      fetched_at: nowIso(),
      source: "egress",
      proxy: proxyInfo()
    };
  }

  if (PRINT) {
    console.log(JSON.stringify(result, null, 2));
    return result.ok || !STRICT ? 0 : 1;
  }
  if (DRY) {
    console.log("[deepseek-egress] dry-run: " + JSON.stringify(result));
    return result.ok || !STRICT ? 0 : 1;
  }

  if (result.ok) {
    await writeOut(result);
    console.log(
      "[deepseek-egress] OK " + result.total_balance + " " + result.currency + " \u2192 " + OUT_FILE
    );
  } else {
    const ex = await readExisting();
    if (isFreshOk(ex)) {
      console.log(
        "[deepseek-egress] fallo (" + result.error + "); conservo \u00faltimo OK de " + ex.fetched_at
      );
    } else {
      await writeOut(result);
      console.log("[deepseek-egress] fallo y sin OK reciente \u2192 escribo error: " + result.error);
    }
  }
  return result.ok || !STRICT ? 0 : 1;
}

main()
  .then((code) => process.exit(code))
  .catch((e) => {
    console.error("[deepseek-egress] error inesperado:", e);
    process.exit(STRICT ? 1 : 0);
  });
