#!/usr/bin/env python3
"""carriles.py — las 4 pilas (carriles) del tablero, para pintarlas en el War Room.

#530 · 05-oct-2026 · orden de Gus. Origen de la regla: `scripts/pilas.py` (#528).

QUÉ ES
El tablero no es UNA cola sino CUATRO pilas — `negocio → roi → operacion → archivo`
(precedencia fija), y dentro de cada una el issue MÁS NUEVO va primero (LIFO). Este módulo
le da al War Room (FastAPI) la misma clasificación que usa el MOTOR, para que lo que se
pinta y lo que se ejecuta no diverjan.

FUENTE ÚNICA
La clasificación canónica vive en `scripts/pilas.py`. Aquí se REUTILIZA cuando el workspace
de OpenClaw está montado (Docker: `/mnt/openclaw-ro/workspace/scripts`, host:
`~/.openclaw/workspace/scripts`). Si no está disponible, cae a una copia determinista
EQUIVALENTE (abajo), para que el panel nunca se quede sin carril aunque el montaje falte.
Cualquier cambio de reglas se hace en `scripts/pilas.py`; el fallback solo lo refleja.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
import unicodedata

CARRILES = ("negocio", "roi", "operacion", "archivo")
PRECEDENCIA = CARRILES
FIN = ("Done", "Cancelled")
PRIORIDADES = ("urgent", "high", "medium", "low", "none")

_RUTAS_PILAS = (
    os.environ.get("PILAS_PATH", ""),                                  # override explícito
    "/mnt/openclaw-ro/workspace/scripts",                             # Docker (metiche-os)
    os.path.join(os.path.expanduser("~"), ".openclaw", "workspace", "scripts"),  # host Mac
)


def _cargar_pilas():
    """Devuelve el módulo `pilas` canónico si se puede importar; si no, None."""
    for ruta in _RUTAS_PILAS:
        if not ruta or not os.path.isfile(os.path.join(ruta, "pilas.py")):
            continue
        if ruta not in sys.path:
            sys.path.insert(0, ruta)
        try:
            import pilas  # type: ignore
            return pilas
        except Exception:  # noqa: BLE001 — nunca tumbar el panel por un import
            continue
    return None


PILAS = _cargar_pilas()


# ---------------------------------------------------------------- fallback determinista
# Copia de la lógica de scripts/pilas.py. Solo se usa si `pilas.py` no está disponible.
ALIAS_CARRIL = {
    "negocio": "negocio", "negocios": "negocio", "business": "negocio", "ventas": "negocio",
    "roi": "roi", "retorno": "roi", "dinero": "roi", "costos": "roi",
    "operacion": "operacion", "operaciones": "operacion", "ops": "operacion",
    "infra": "operacion", "infraestructura": "operacion",
    "archivo": "archivo", "archivado": "archivo", "archive": "archivo",
}

_SENALES = {
    "negocio": (
        "venta", "vender", "cliente", "pedido", "precio", "campana", "anuncio",
        "catalogo", "margen", "promocion", "shopify", "whatsapp", "producto",
        "ingreso", "cobrar", "lead", "conversion",
    ),
    "roi": (
        "gasto", "costo", "costos", "token", "tokens", "suscripcion", "recorte",
        "presupuesto", "apagar", "ahorro", "ahorrar", "duplicado", "proveedor",
        "saldo", "deepseek", "tarifa", "roi",
    ),
    "operacion": (
        "motor", "servidor", "gateway", "dashboard", "tablero", "impresora", "nodo",
        "respaldo", "backup", "monitoreo", "cron", "sesion", "bot", "docker",
        "postgres", "cloudflare", "tunel", "deploy", "despliegue", "log", "swap",
    ),
    "archivo": (
        "archivar", "archivado", "historico", "obsoleto", "deprecado", "superseded",
        "poda de backlog",
    ),
}


def _norm(texto: str) -> str:
    t = unicodedata.normalize("NFKD", str(texto or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def _etiquetas(fila) -> list:
    return [str(x) for x in (fila.get("labels") or [])]


def _fecha(texto):
    if not texto:
        return None
    try:
        limpio = str(texto).replace("Z", "+00:00")
        d = dt.datetime.fromisoformat(limpio)
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except ValueError:
        try:
            return dt.datetime.strptime(str(texto)[:10], "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
        except ValueError:
            return None


def _dias_desde(texto) -> float:
    d = _fecha(texto)
    if not d:
        return -1.0
    return (dt.datetime.now(dt.timezone.utc) - d).total_seconds() / 86400.0


def _carril_explicito(fila):
    for e in _etiquetas(fila):
        if e.startswith("carril:"):
            clave = _norm(e.split(":", 1)[1]).strip()
            if clave in ALIAS_CARRIL:
                return ALIAS_CARRIL[clave]
    return None


def _carril_por_retorno(fila):
    for e in _etiquetas(fila):
        base = ":".join(e.split(":")[:2]) if e.startswith("roi:") else e
        if base == "roi:ingreso":
            return "negocio"
        if base == "roi:ahorro":
            return "roi"
        if base == "roi:higiene":
            return "operacion"
    return None


def _carril_por_dueno(fila):
    etiquetas = _etiquetas(fila)
    if "agent:masa-madre" in etiquetas:
        return "negocio"
    if any(e.startswith("machine:") for e in etiquetas):
        return "operacion"
    return None


def _es_archivo(fila, dias_archivo: int = 30) -> bool:
    etiquetas = [e.lower() for e in _etiquetas(fila)]
    if any(e in ("archivo", "archivado", "archive") for e in etiquetas):
        return True
    if any(e.startswith("era:") for e in etiquetas):
        return True
    if str(fila.get("state")) == "Backlog":
        if _dias_desde(fila.get("updated")) >= dias_archivo:
            return True
    return False


def _puntajes(fila):
    texto = _norm((fila.get("name") or "") + " " + (fila.get("desc") or ""))
    return dict((c, sum(1 for p in pals if p in texto)) for c, pals in _SENALES.items())


def _clasificar_fallback(fila, dias_archivo: int = 30):
    explicito = _carril_explicito(fila)
    if explicito:
        return explicito, "etiqueta carril:%s" % explicito
    if _es_archivo(fila, dias_archivo):
        return "archivo", "señal de archivo (era:*/archivo/Backlog añejo)"
    por_retorno = _carril_por_retorno(fila)
    if por_retorno:
        return por_retorno, "retorno roi:*"
    por_dueno = _carril_por_dueno(fila)
    if por_dueno:
        return por_dueno, "dueño/etiqueta dura"
    pun = _puntajes(fila)
    mejor = max(pun, key=lambda c: pun[c])
    if pun[mejor] > 0:
        return mejor, "palabras (%s=%d)" % (mejor, pun[mejor])
    return "operacion", "default (trabajo interno)"


def _clave_lifo(fila, respetar_prioridad: bool = True):
    try:
        seq = -int(fila.get("seq"))
    except (TypeError, ValueError):
        seq = 0
    fecha = _fecha(fila.get("updated")) or dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)
    base = (seq, -fecha.timestamp())
    if respetar_prioridad:
        rango = dict((n, i) for i, n in enumerate(PRIORIDADES))
        return (rango.get(str(fila.get("priority")), 9),) + base
    return base


def _ordenar_fallback(filas, respetar_prioridad: bool = True):
    return sorted(filas, key=lambda f: _clave_lifo(f, respetar_prioridad))


# ---------------------------------------------------------------- API pública
def clasificar(fila, dias_archivo: int = 30):
    """(carril, motivo). Delegado a `pilas` canónico si está; si no, al fallback."""
    if PILAS is not None and hasattr(PILAS, "carril_de"):
        try:
            return PILAS.carril_de(fila, dias_archivo)
        except TypeError:  # versión sin el parámetro
            return PILAS.carril_de(fila)
    return _clasificar_fallback(fila, dias_archivo)


def carril_de(fila, dias_archivo: int = 30):
    """Compatibilidad: devuelve SOLO el carril."""
    return clasificar(fila, dias_archivo)[0]


def ordenar(filas, respetar_prioridad: bool = True, dias_archivo: int = 30,
            incluir_archivo: bool = True):
    """Lista plana: carril por carril (precedencia) y LIFO dentro de cada carril."""
    if PILAS is not None and hasattr(PILAS, "ordenar"):
        try:
            return PILAS.ordenar(filas, respetar_prioridad, dias_archivo, incluir_archivo)
        except TypeError:
            pass
    pilas = agrupar(filas, respetar_prioridad, dias_archivo)
    orden = []
    for c in PRECEDENCIA:
        if c == "archivo" and not incluir_archivo:
            continue
        orden.extend(pilas[c])
    return orden


def agrupar(filas, respetar_prioridad: bool = True, dias_archivo: int = 30,
            incluir_cerradas: bool = False):
    """{carril: [filas LIFO]} — siempre las cuatro llaves, aunque estén vacías."""
    if PILAS is not None and hasattr(PILAS, "agrupar"):
        try:
            return PILAS.agrupar(filas, respetar_prioridad, dias_archivo, incluir_cerradas)
        except TypeError:
            pass
    pilas = dict((c, []) for c in CARRILES)
    for f in filas:
        if not incluir_cerradas and str(f.get("state")) in FIN:
            continue
        carril, _motivo = clasificar(f, dias_archivo)
        pilas[carril].append(f)
    for c in CARRILES:
        pilas[c] = _ordenar_fallback(pilas[c], respetar_prioridad)
    return pilas


def fuente() -> str:
    """De dónde salió la clasificación: 'pilas.py' canónico o 'fallback'."""
    return "pilas.py" if PILAS is not None else "fallback"
