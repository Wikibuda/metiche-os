import { createServer } from "node:http";
import { promises as fs } from "node:fs";
import path from "node:path";
import os from "node:os";
import { spawn } from "node:child_process";
import net from "node:net";
import { fileURLToPath } from "node:url";

const HOME = os.homedir();
const OPENCLAW_ROOT = path.join(HOME, ".openclaw");
const WORKSPACE_PERSONAL = path.join(OPENCLAW_ROOT, "workspace-personal");
const MODULE_DIR = path.dirname(fileURLToPath(import.meta.url));
const DASHBOARD_FILE = process.env.DASHBOARD_FILE || path.join(MODULE_DIR, "operativo.html");
const ADMIN_DASHBOARD_FILE = path.join(MODULE_DIR, "admin-dashboard-lab.html");
const LEGACY_DASHBOARD_FILE = path.join(WORKSPACE_PERSONAL, "admin-dashboard-lab.html");
const OPENCLAW_CONFIG = path.join(OPENCLAW_ROOT, "openclaw.json");
const PROD_LOG = path.join(OPENCLAW_ROOT, "logs", "gateway.log");
const PROD_ERR_LOG = path.join(OPENCLAW_ROOT, "logs", "gateway.err.log");
const PORT = Number(process.env.DASHBOARD_PORT || 5063);
const METICHE_OS_BASE = process.env.METICHE_OS_BASE || "http://127.0.0.1:8091";
const METICHE_TIMEOUT_MS = Number(process.env.METICHE_TIMEOUT_MS || 4500);

// Archivos de datos para dashboards
const SHOPIFY_SALES_FILE = path.join(OPENCLAW_ROOT, "workspace", "dashboard_parts", "shopify_today_simple.json");
const DEEPSEEK_PRICING_FILE = path.join(OPENCLAW_ROOT, "workspace", "dashboard_parts", "deepseek_pricing.json");

const ACTIONS = {
  "prod-status": { cmd: "openclaw", args: ["daemon", "status"] },
  "prod-start": { cmd: "openclaw", args: ["daemon", "start"] },
  "prod-stop": { cmd: "openclaw", args: ["daemon", "stop"] },
  "prod-restart": { cmd: "openclaw", args: ["daemon", "restart"] },
  "dev-status": { cmd: "openclaw", args: ["--profile", "dev", "daemon", "status"] },
  "dev-start": { cmd: "openclaw", args: ["--profile", "dev", "daemon", "start"] },
  "dev-stop": { cmd: "openclaw", args: ["--profile", "dev", "daemon", "stop"] },
  "dev-restart": { cmd: "openclaw", args: ["--profile", "dev", "daemon", "restart"] },
  "sakura-status": { cmd: "bash", args: [path.join(WORKSPACE_PERSONAL, "sakura-status.sh")] },
  "sakura-start": { cmd: "bash", args: [path.join(WORKSPACE_PERSONAL, "sakura-start.sh")] },
  "sakura-stop": { cmd: "bash", args: [path.join(WORKSPACE_PERSONAL, "sakura-stop.sh")] }
};

function sendJson(res, statusCode, payload) {
  const body = JSON.stringify(payload);
  res.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
    "Content-Length": Buffer.byteLength(body)
  });
  res.end(body);
}

function sendHtml(res, html) {
  res.writeHead(200, {
    "Content-Type": "text/html; charset=utf-8",
    "Cache-Control": "no-store"
  });
  res.end(html);
}

function runCommand(action, timeoutMs = 15000) {
  const task = ACTIONS[action];
  if (!task) {
    return Promise.resolve({
      ok: false,
      action,
      error: "Acción no permitida"
    });
  }
  return new Promise((resolve) => {
    const child = spawn(task.cmd, task.args, {
      cwd: WORKSPACE_PERSONAL,
      env: process.env,
      stdio: ["ignore", "pipe", "pipe"]
    });
    let stdout = "";
    let stderr = "";
    const timer = setTimeout(() => {
      child.kill("SIGTERM");
    }, timeoutMs);
    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      resolve({
        ok: code === 0,
        action,
        code,
        stdout: stdout.trim(),
        stderr: stderr.trim()
      });
    });
    child.on("error", (error) => {
      clearTimeout(timer);
      resolve({
        ok: false,
        action,
        error: error.message
      });
    });
  });
}

function isWorkspacePathAllowed(workspacePath) {
  if (typeof workspacePath !== "string" || workspacePath.length === 0) return false;
  const normalized = path.resolve(workspacePath);
  if (!normalized.startsWith(OPENCLAW_ROOT)) return false;
  return path.basename(normalized).startsWith("workspace");
}

function listProcesses() {
  return new Promise((resolve) => {
    const child = spawn("ps", ["-axo", "pid=,command="], {
      env: process.env,
      stdio: ["ignore", "pipe", "pipe"]
    });
    let stdout = "";
    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    child.on("close", () => {
      const rows = stdout
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean)
        .map((line) => {
          const firstSpace = line.indexOf(" ");
          if (firstSpace < 1) return null;
          const pid = Number(line.slice(0, firstSpace).trim());
          const command = line.slice(firstSpace + 1).trim();
          if (!Number.isInteger(pid) || !command) return null;
          return { pid, command };
        })
        .filter(Boolean);
      resolve(rows);
    });
    child.on("error", () => resolve([]));
  });
}

function isAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function emergencyStopWorkspace(workspacePath) {
  if (!isWorkspacePathAllowed(workspacePath)) {
    return {
      ok: false,
      error: "Workspace inválido o fuera de alcance permitido"
    };
  }
  const processes = await listProcesses();
  const normalizedWorkspace = path.resolve(workspacePath);
  const includeRegex = /\b(openclaw|node|python|bun|deno|npm|pnpm|tsx|uvicorn|gunicorn)\b/i;
  const candidates = processes.filter((proc) => {
    if (proc.pid === process.pid) return false;
    if (!proc.command.includes(normalizedWorkspace)) return false;
    if (!includeRegex.test(proc.command)) return false;
    if (proc.command.includes("dashboard-server.mjs")) return false;
    if (proc.command.includes("openclaw gateway run")) return false;
    if (proc.command.includes("openclaw daemon")) return false;
    if (proc.command.includes("curl ")) return false;
    if (proc.command.includes("trae-sandbox")) return false;
    if (proc.command.includes("CheckCommandStatus")) return false;
    return true;
  });

  const terminated = [];
  const forced = [];
  for (const proc of candidates) {
    try {
      process.kill(proc.pid, "SIGTERM");
      terminated.push(proc);
    } catch {}
  }
  await sleep(450);
  for (const proc of terminated) {
    if (!isAlive(proc.pid)) continue;
    try {
      process.kill(proc.pid, "SIGKILL");
      forced.push(proc.pid);
    } catch {}
  }

  const finalDead = terminated.filter((proc) => !isAlive(proc.pid));
  const finalAlive = terminated.filter((proc) => isAlive(proc.pid));
  return {
    ok: true,
    workspace: normalizedWorkspace,
    matched: candidates.length,
    terminated: finalDead.length,
    forced: forced.length,
    stillAlive: finalAlive.length,
    sample: candidates.slice(0, 6).map((proc) => ({
      pid: proc.pid,
      command: proc.command.slice(0, 180)
    }))
  };
}

async function safeReadJson(filePath) {
  try {
    const content = await fs.readFile(filePath, "utf-8");
    return JSON.parse(content);
  } catch {
    return null;
  }
}

async function getDeepSeekBalance() {
  const DEEPSEEK_TOKEN = String(process.env.DEEPSEEK_API_KEY || "").trim();
  const API_URL = "https://api.deepseek.com/user/balance";

  if (!DEEPSEEK_TOKEN) {
    return {
      ok: false,
      error: "DEEPSEEK_API_KEY no configurada",
      timestamp: new Date().toISOString()
    };
  }
  
  try {
    const response = await fetch(API_URL, {
      method: "GET",
      headers: {
        "Authorization": `Bearer ${DEEPSEEK_TOKEN}`,
        "Content-Type": "application/json"
      }
    });
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    
    const data = await response.json();
    
    // Nueva estructura de respuesta (balance_infos array)
    let total_balance = "0.00";
    let granted_balance = "0.00";
    let topped_up_balance = "0.00";
    let currency = "USD";
    
    if (data.balance_infos && data.balance_infos.length > 0) {
      const balanceInfo = data.balance_infos[0];
      total_balance = balanceInfo.total_balance || "0.00";
      granted_balance = balanceInfo.granted_balance || "0.00";
      topped_up_balance = balanceInfo.topped_up_balance || "0.00";
      currency = balanceInfo.currency || "USD";
    } else if (data.total_balance) {
      // Estructura antigua (compatibilidad)
      total_balance = data.total_balance;
      granted_balance = data.granted_balance || "0.00";
      topped_up_balance = data.topped_up_balance || "0.00";
      currency = data.currency || "USD";
    }
    
    return {
      ok: true,
      total_balance: total_balance,
      granted_balance: granted_balance,
      topped_up_balance: topped_up_balance,
      currency: currency,
      timestamp: new Date().toISOString()
    };
  } catch (error) {
    return {
      ok: false,
      error: error.message,
      timestamp: new Date().toISOString()
    };
  }
}

async function getDeepSeekUsageHistory() {
  const USAGE_FILE = "/Users/gusluna/.openclaw/workspace-personal/deepseek_usage.json";
  try {
    const data = await safeReadJson(USAGE_FILE);
    if (!data) {
      throw new Error("Archivo de uso no encontrado");
    }
    return {
      ok: true,
      ...data,
      timestamp: new Date().toISOString()
    };
  } catch (error) {
    return {
      ok: false,
      error: error.message,
      timestamp: new Date().toISOString()
    };
  }
}

async function getShopifyRealtime(path = "/admin/api/2025-10/products.json") {
  const SHOPIFY_TOKEN_PATH = "/Users/gusluna/.openclaw/workspace-masa-madre/shopify_token.json";
  const SHOPIFY_STORE = "masamadremonterrey.myshopify.com";
  
  try {
    // Leer token
    const tokenData = await safeReadJson(SHOPIFY_TOKEN_PATH);
    if (!tokenData || !tokenData.token) {
      throw new Error("Token Shopify no disponible");
    }
    
    const token = tokenData.token;
    const fullUrl = `https://${SHOPIFY_STORE}${path}`;
    
    const response = await fetch(fullUrl, {
      method: "GET",
      headers: {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json",
        "Accept": "application/json"
      }
    });
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    
    const data = await response.json();
    return {
      ok: true,
      data: data,
      url: fullUrl,
      timestamp: new Date().toISOString()
    };
  } catch (error) {
    return {
      ok: false,
      error: error.message,
      timestamp: new Date().toISOString()
    };
  }
}

function checkPort(port) {
  return new Promise((resolve) => {
    const socket = new net.Socket();
    let finished = false;
    const finish = (open) => {
      if (finished) return;
      finished = true;
      socket.destroy();
      resolve(open);
    };
    socket.setTimeout(750);
    socket.once("connect", () => finish(true));
    socket.once("timeout", () => finish(false));
    socket.once("error", () => finish(false));
    socket.connect(port, "127.0.0.1");
  });
}

function formatDate(value) {
  if (!value) return "N/A";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "N/A";
  return d.toISOString();
}

async function collectTreeStats(rootDir, maxEntries = 4000) {
  let files = 0;
  let directories = 0;
  let newest = 0;
  const stack = [rootDir];
  let scanned = 0;
  while (stack.length > 0 && scanned < maxEntries) {
    const current = stack.pop();
    let entries = [];
    try {
      entries = await fs.readdir(current, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const entry of entries) {
      if (entry.name.startsWith(".git")) continue;
      const fullPath = path.join(current, entry.name);
      scanned += 1;
      if (scanned > maxEntries) break;
      let stat;
      try {
        stat = await fs.stat(fullPath);
      } catch {
        continue;
      }
      if (stat.mtimeMs > newest) newest = stat.mtimeMs;
      if (entry.isDirectory()) {
        directories += 1;
        stack.push(fullPath);
      } else {
        files += 1;
      }
    }
  }
  return { files, directories, newest, scanned, capped: scanned >= maxEntries };
}

async function readTail(filePath, maxLines = 60) {
  try {
    const content = await fs.readFile(filePath, "utf-8");
    const lines = content.split("\n");
    return lines.slice(Math.max(0, lines.length - maxLines)).join("\n");
  } catch {
    return "";
  }
}

async function fetchJson(url) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), METICHE_TIMEOUT_MS);
  try {
    const response = await fetch(url, {
      headers: { Accept: "application/json" },
      signal: controller.signal
    });
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

async function fetchJsonDetailed(url) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), METICHE_TIMEOUT_MS);
  try {
    const response = await fetch(url, {
      headers: { Accept: "application/json" },
      signal: controller.signal
    });
    const contentType = response.headers.get("content-type") || "";
    let payload = null;
    if (contentType.includes("application/json")) {
      payload = await response.json();
    } else {
      const text = await response.text();
      payload = text ? { detail: text } : null;
    }
    return {
      ok: response.ok,
      status: response.status,
      data: response.ok ? payload : null,
      error: response.ok ? null : payload?.detail || payload?.error || `HTTP ${response.status}`
    };
  } catch (error) {
    return {
      ok: false,
      status: 0,
      data: null,
      error: error.message
    };
  } finally {
    clearTimeout(timer);
  }
}

async function postJsonDetailed(url, payload = null) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), METICHE_TIMEOUT_MS);
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: payload === null ? null : JSON.stringify(payload),
      signal: controller.signal
    });
    const contentType = response.headers.get("content-type") || "";
    let data = null;
    if (contentType.includes("application/json")) {
      data = await response.json();
    } else {
      const text = await response.text();
      data = text ? { detail: text } : null;
    }
    return {
      ok: response.ok,
      status: response.status,
      data: response.ok ? data : null,
      error: response.ok ? null : data?.detail || data?.error || `HTTP ${response.status}`
    };
  } catch (error) {
    return {
      ok: false,
      status: 0,
      data: null,
      error: error.message
    };
  } finally {
    clearTimeout(timer);
  }
}

async function buildMeticheOverview() {
  const [health, overview] = await Promise.all([
    fetchJson(`${METICHE_OS_BASE}/health`),
    fetchJson(`${METICHE_OS_BASE}/tasks/overview`)
  ]);
  return {
    online: Boolean(health?.ok),
    baseUrl: METICHE_OS_BASE,
    overview
  };
}

async function buildMeticheTaskDetail(taskId) {
  const cleanTaskId = String(taskId || "").trim();
  if (!cleanTaskId) {
    return { ok: false, error: "taskId es obligatorio" };
  }

  const [tasksResp, routeResp, dispatchResp, escalationResp, flowResp, queueResp] = await Promise.all([
    fetchJsonDetailed(`${METICHE_OS_BASE}/tasks`),
    fetchJsonDetailed(`${METICHE_OS_BASE}/tasks/${encodeURIComponent(cleanTaskId)}/route`),
    fetchJsonDetailed(`${METICHE_OS_BASE}/tasks/${encodeURIComponent(cleanTaskId)}/dispatch`),
    fetchJsonDetailed(`${METICHE_OS_BASE}/tasks/${encodeURIComponent(cleanTaskId)}/escalation`),
    fetchJsonDetailed(`${METICHE_OS_BASE}/tasks/${encodeURIComponent(cleanTaskId)}/flow`),
    fetchJsonDetailed(`${METICHE_OS_BASE}/tasks/queue`)
  ]);

  const tasks = Array.isArray(tasksResp.data) ? tasksResp.data : [];
  const queueEntries = Array.isArray(queueResp.data) ? queueResp.data : [];
  const task = tasks.find((item) => item?.id === cleanTaskId) || null;
  const matchedQueue = queueEntries.filter((entry) => entry?.task_id === cleanTaskId);

  return {
    ok: Boolean(task),
    task_id: cleanTaskId,
    baseUrl: METICHE_OS_BASE,
    task,
    route: routeResp.data,
    dispatch: dispatchResp.data,
    escalation: escalationResp.data,
    flow: flowResp.data,
    queue_entries: matchedQueue,
    sources: {
      tasks: tasksResp.status,
      route: routeResp.status,
      dispatch: dispatchResp.status,
      escalation: escalationResp.status,
      flow: flowResp.status,
      queue: queueResp.status
    },
    error: task ? null : "Tarea no encontrada"
  };
}

async function runMeticheAction(action, taskId = "") {
  const cleanAction = String(action || "").trim();
  const cleanTaskId = String(taskId || "").trim();
  if (cleanAction === "process-next") {
    const resp = await postJsonDetailed(`${METICHE_OS_BASE}/tasks/process-next`);
    return {
      ok: resp.ok,
      action: cleanAction,
      status: resp.status,
      data: resp.data,
      error: resp.error
    };
  }

  if (cleanAction !== "rerun-task" && cleanAction !== "requeue-task") {
    return {
      ok: false,
      action: cleanAction,
      status: 400,
      error: "Acción no soportada"
    };
  }

  if (!cleanTaskId) {
    return {
      ok: false,
      action: cleanAction,
      status: 400,
      error: "taskId es obligatorio"
    };
  }

  const tasksResp = await fetchJsonDetailed(`${METICHE_OS_BASE}/tasks`);
  const tasks = Array.isArray(tasksResp.data) ? tasksResp.data : [];
  const task = tasks.find((item) => item?.id === cleanTaskId);
  if (!task) {
    return {
      ok: false,
      action: cleanAction,
      status: 404,
      error: "Tarea no encontrada para la acción"
    };
  }

  const basePayload = {
    title: task.title || `Reproceso ${cleanTaskId}`,
    description: task.description || null,
    task_type: task.task_type || "analysis"
  };

  if (cleanAction === "requeue-task") {
    const payload = {
      ...basePayload,
      priority: task.priority || "normal"
    };
    const resp = await postJsonDetailed(`${METICHE_OS_BASE}/tasks/enqueue`, payload);
    return {
      ok: resp.ok,
      action: cleanAction,
      status: resp.status,
      source_task_id: cleanTaskId,
      payload,
      data: resp.data,
      error: resp.error
    };
  }

  const payload = {
    ...basePayload,
    execution_mode: task.execution_mode || "sync",
    requested_by: "dashboard-lab"
  };
  const resp = await postJsonDetailed(`${METICHE_OS_BASE}/tasks/run`, payload);
  return {
    ok: resp.ok,
    action: cleanAction,
    status: resp.status,
    source_task_id: cleanTaskId,
    payload,
    data: resp.data,
    error: resp.error
  };
}

async function buildOverview() {
  const config = await safeReadJson(OPENCLAW_CONFIG);
  const agents = Array.isArray(config?.agents?.list) ? config.agents.list : [];
  const workspaceMap = new Map();
  for (const agent of agents) {
    if (!agent?.workspace) continue;
    if (!workspaceMap.has(agent.workspace)) {
      workspaceMap.set(agent.workspace, []);
    }
    workspaceMap.get(agent.workspace).push({
      id: agent.id || "sin-id",
      name: agent.name || agent.id || "sin-nombre",
      model: agent.model || "sin-modelo"
    });
  }

  const rootEntries = await fs.readdir(OPENCLAW_ROOT, { withFileTypes: true });
  const workspaceDirs = rootEntries
    .filter((entry) => entry.isDirectory() && entry.name.startsWith("workspace"))
    .map((entry) => path.join(OPENCLAW_ROOT, entry.name));

  const workspaceRows = [];
  let totalMemoryNotes = 0;
  for (const workspacePath of workspaceDirs) {
    const stats = await collectTreeStats(workspacePath);
    const memoryDir = path.join(workspacePath, "memory");
    let memoryNotes = 0;
    try {
      const memoryEntries = await fs.readdir(memoryDir, { withFileTypes: true });
      memoryNotes = memoryEntries.filter((entry) => entry.isFile() && entry.name.endsWith(".md")).length;
    } catch {
      memoryNotes = 0;
    }
    totalMemoryNotes += memoryNotes;
    const attachedAgents = workspaceMap.get(workspacePath) || [];
    workspaceRows.push({
      name: path.basename(workspacePath),
      path: workspacePath,
      files: stats.files,
      directories: stats.directories,
      lastUpdate: formatDate(stats.newest),
      memoryNotes,
      scopedAgents: attachedAgents,
      scannedEntries: stats.scanned,
      scanCapped: stats.capped
    });
  }

  workspaceRows.sort((a, b) => a.name.localeCompare(b.name, "es"));

  const prodGatewayOpen = await checkPort(18789);
  const prodLogTail = await readTail(PROD_LOG);
  const prodErrLogTail = await readTail(PROD_ERR_LOG, 40);
  const metiche = await buildMeticheOverview();

  return {
    generatedAt: new Date().toISOString(),
    summary: {
      totalWorkspaces: workspaceRows.length,
      totalAgents: agents.length,
      totalMemoryNotes,
      activeGateways: prodGatewayOpen ? 1 : 0,
      meticheQueueDepth: metiche?.overview?.queue_depth || 0,
      meticheFallbackTasks: metiche?.overview?.fallback_tasks || 0,
      meticheFailedTasks: metiche?.overview?.failed_tasks || 0
    },
    gateways: {
      prod: { label: "Producción", port: 18789, online: prodGatewayOpen }
    },
    labs: {
      meticheOs: metiche
    },
    workspaces: workspaceRows,
    logs: {
      prod: prodLogTail,
      prodErr: prodErrLogTail
    }
  };
}

async function parseRequestBody(req) {
  const chunks = [];
  for await (const chunk of req) {
    chunks.push(chunk);
  }
  if (chunks.length === 0) return {};
  const body = Buffer.concat(chunks).toString("utf-8");
  try {
    return JSON.parse(body);
  } catch {
    return {};
  }
}

async function loadDashboardHtml(preferredPath = DASHBOARD_FILE) {
  try {
    return await fs.readFile(preferredPath, "utf-8");
  } catch {
    try {
      return await fs.readFile(DASHBOARD_FILE, "utf-8");
    } catch {
      return await fs.readFile(LEGACY_DASHBOARD_FILE, "utf-8");
    }
  }
}

async function proxyDashboardApi(req, res, requestUrl) {
  const upstreamUrl = `${METICHE_OS_BASE}${requestUrl.pathname}${requestUrl.search}`;
  const method = req.method || "GET";
  const headers = { Accept: "application/json" };
  let body = undefined;

  if (method !== "GET" && method !== "HEAD") {
    headers["Content-Type"] = "application/json";
    const parsedBody = await parseRequestBody(req);
    body = JSON.stringify(parsedBody || {});
  }

  try {
    const upstream = await fetch(upstreamUrl, { method, headers, body });
    const contentType = upstream.headers.get("content-type") || "application/json; charset=utf-8";
    const text = await upstream.text();
    res.writeHead(upstream.status, {
      "Content-Type": contentType,
      "Cache-Control": "no-store"
    });
    res.end(text);
  } catch (error) {
    sendJson(res, 502, {
      ok: false,
      error: "No se pudo conectar con API de metiche-os",
      detail: error.message
    });
  }
}

const server = createServer(async (req, res) => {
  try {
    const requestUrl = new URL(req.url || "/", `http://${req.headers.host || "localhost"}`);
    console.log(`📡 Request: ${req.method} ${requestUrl.pathname} (host: ${req.headers.host})`);

    if (
      req.method === "GET" &&
      (
        requestUrl.pathname === "/admin-dashboard.html" ||
        requestUrl.pathname === "/admin-dashboard-lab.html" ||
        requestUrl.pathname === "/swarm-console.html"
      )
    ) {
      const html = await loadDashboardHtml(ADMIN_DASHBOARD_FILE);
      sendHtml(res, html);
      return;
    }

    if (
      req.method === "GET" &&
      (requestUrl.pathname === "/" || requestUrl.pathname === "/lab" || requestUrl.pathname === "/operativo.html")
    ) {
      const html = await loadDashboardHtml();
      sendHtml(res, html);
      return;
    }

    if (
      (req.method === "GET" || req.method === "POST") &&
      (
        requestUrl.pathname.startsWith("/dashboard/") ||
        requestUrl.pathname.startsWith("/memory") ||
        requestUrl.pathname === "/swarm" ||
        requestUrl.pathname.startsWith("/swarm/")
      )
    ) {
      await proxyDashboardApi(req, res, requestUrl);
      return;
    }

    if (req.method === "GET" && requestUrl.pathname === "/api/overview") {
      const overview = await buildOverview();
      sendJson(res, 200, overview);
      return;
    }

    if (req.method === "GET" && requestUrl.pathname === "/api/labs/metiche-os/overview") {
      const overview = await buildMeticheOverview();
      sendJson(res, overview?.online ? 200 : 503, overview);
      return;
    }

    if (req.method === "GET" && requestUrl.pathname === "/api/labs/metiche-os/task-detail") {
      const taskId = (requestUrl.searchParams.get("taskId") || "").trim();
      if (!taskId) {
        sendJson(res, 400, { ok: false, error: "Parámetro taskId requerido" });
        return;
      }
      const detail = await buildMeticheTaskDetail(taskId);
      sendJson(res, detail.ok ? 200 : 404, detail);
      return;
    }

    if (req.method === "POST" && requestUrl.pathname === "/api/labs/metiche-os/action") {
      const body = await parseRequestBody(req);
      const action = typeof body.action === "string" ? body.action : "";
      const taskId = typeof body.taskId === "string" ? body.taskId : "";
      const result = await runMeticheAction(action, taskId);
      sendJson(res, result.ok ? 200 : result.status || 400, result);
      return;
    }

    if (req.method === "POST" && requestUrl.pathname === "/api/action") {
      const body = await parseRequestBody(req);
      const action = typeof body.action === "string" ? body.action : "";
      const result = await runCommand(action);
      sendJson(res, result.ok ? 200 : 400, result);
      return;
    }

    if (req.method === "POST" && requestUrl.pathname === "/api/workspace/emergency-stop") {
      const body = await parseRequestBody(req);
      const workspacePath = typeof body.workspacePath === "string" ? body.workspacePath : "";
      const result = await emergencyStopWorkspace(workspacePath);
      sendJson(res, result.ok ? 200 : 400, result);
      return;
    }

    if (req.method === "GET" && requestUrl.pathname === "/health") {
      sendJson(res, 200, { ok: true, service: "workspace-personal-dashboard" });
      return;
    }

    if (req.method === "GET" && requestUrl.pathname === "/api/shopify/today-sales") {
      try {
        const data = await fs.readFile(SHOPIFY_SALES_FILE, "utf-8");
        const jsonData = JSON.parse(data);
        sendJson(res, 200, jsonData);
      } catch (error) {
        sendJson(res, 500, { ok: false, error: "No se pudieron cargar las ventas de Shopify" });
      }
      return;
    }

    if (req.method === "GET" && requestUrl.pathname === "/api/deepseek/pricing") {
      try {
        // Datos de pricing de DeepSeek API (actualizados manualmente)
        const pricingData = {
          "model_prices": {
            "deepseek-reasoner": {
              "input_per_million_tokens": 0.80,
              "output_per_million_tokens": 3.20,
              "currency": "USD"
            },
            "deepseek-chat": {
              "input_per_million_tokens": 0.14,
              "output_per_million_tokens": 0.56,
              "currency": "USD"
            }
          },
          "last_updated": "2026-03-23T13:30:00Z",
          "source": "DeepSeek API Pricing Documentation"
        };
        sendJson(res, 200, pricingData);
      } catch (error) {
        sendJson(res, 500, { ok: false, error: "Error cargando pricing" });
      }
      return;
    }

    // ========== ENDPOINTS TIEMPO REAL ==========
    if (req.method === "GET" && requestUrl.pathname === "/api/deepseek/balance-realtime") {
      const balanceData = await getDeepSeekBalance();
      sendJson(res, balanceData.ok ? 200 : 500, balanceData);
      return;
    }
    
    if (req.method === "GET" && requestUrl.pathname === "/api/deepseek/usage-history") {
      const usageData = await getDeepSeekUsageHistory();
      sendJson(res, usageData.ok ? 200 : 500, usageData);
      return;
    }
    
    if (req.method === "GET" && requestUrl.pathname === "/api/shopify/realtime") {
      const path = requestUrl.searchParams.get("path") || "/admin/api/2025-10/products.json?limit=10";
      const shopifyData = await getShopifyRealtime(path);
      sendJson(res, shopifyData.ok ? 200 : 500, shopifyData);
      return;
    }
    
    if (req.method === "GET" && requestUrl.pathname === "/api/shopify/today-orders") {
      const today = new Date().toISOString().split('T')[0];
      const path = `/admin/api/2025-10/orders.json?status=any&created_at_min=${today}&limit=50&fields=id,total_price,created_at,customer,line_items`;
      const shopifyData = await getShopifyRealtime(path);
      sendJson(res, shopifyData.ok ? 200 : 500, shopifyData);
      return;
    }
    
    if (req.method === "GET" && requestUrl.pathname === "/api/shopify/inventory") {
      const path = "/admin/api/2025-10/products.json?limit=50&fields=id,title,variants,inventory_quantity";
      const shopifyData = await getShopifyRealtime(path);
      sendJson(res, shopifyData.ok ? 200 : 500, shopifyData);
      return;
    }
    
    if (req.method === "GET" && requestUrl.pathname === "/api/system/status") {
      const deepseekBalance = await getDeepSeekBalance();
      const shopifyProducts = await getShopifyRealtime("/admin/api/2025-10/products.json?limit=5");
      
      const status = {
        timestamp: new Date().toISOString(),
        deepseek: deepseekBalance.ok ? {
          balance: deepseekBalance.total_balance,
          currency: deepseekBalance.currency,
          status: "connected"
        } : {
          status: "error",
          error: deepseekBalance.error
        },
        shopify: shopifyProducts.ok ? {
          product_count: shopifyProducts.data.products?.length || 0,
          status: "connected"
        } : {
          status: "error", 
          error: shopifyProducts.error
        },
        dashboard: {
          server: "running",
          port: PORT,
          uptime: process.uptime()
        }
      };
      
      sendJson(res, 200, status);
      return;
    }
    // ========== FIN ENDPOINTS TIEMPO REAL ==========

    if (req.method === "GET" && requestUrl.pathname === "/") {
      try {
        const html = await loadDashboardHtml();
        res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
        res.end(html);
        return;
      } catch (error) {
        sendJson(res, 500, { ok: false, error: "No se pudo cargar el dashboard" });
        return;
      }
    }

    sendJson(res, 404, { ok: false, error: "Ruta no encontrada" });
  } catch (error) {
    sendJson(res, 500, { ok: false, error: error.message });
  }
});

server.listen(PORT, () => {
  process.stdout.write(`Dashboard operativo en puerto ${PORT}\n`);
});
