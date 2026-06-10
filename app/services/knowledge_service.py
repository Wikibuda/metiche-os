from __future__ import annotations

import os
import sqlite3
import time
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings


@dataclass(frozen=True)
class KnowledgeHit:
    score: float
    url: str
    title: str
    snippet: str


def _resolve_db_path(explicit: str | None = None) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    env_value = os.environ.get("WEBSITE_EMBEDDINGS_PATH", "").strip()
    if env_value:
        candidates.append(Path(env_value))
    candidates.extend(
        [
            Path(getattr(settings, "website_embeddings_path", "") or ""),
            Path(getattr(settings, "openclaw_readonly_root", "") or "") / "website_embeddings.sqlite",
            Path("/app/data/website_embeddings.sqlite"),
            Path("/mnt/openclaw-ro/website_embeddings.sqlite"),
            Path("/Users/gusluna/.openclaw/workspace/website_embeddings.sqlite"),
        ]
    )
    for candidate in candidates:
        if not candidate:
            continue
        if candidate.exists() and candidate.is_file():
            return candidate
    return Path("/app/data/website_embeddings.sqlite")


def _resolve_ollama_url() -> str:
    env_value = os.environ.get("OLLAMA_EMBEDDINGS_URL", "").strip()
    if env_value:
        return env_value
    settings_value = str(getattr(settings, "ollama_embeddings_url", "") or "").strip()
    if settings_value:
        return settings_value
    return "http://host.docker.internal:11434/api/embeddings"


def _running_in_docker() -> bool:
    return Path("/.dockerenv").exists()


def _candidate_ollama_urls(explicit: str | None = None) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()
    raw_candidates: list[str] = []

    if explicit:
        raw_candidates.append(explicit)
    env_value = os.environ.get("OLLAMA_EMBEDDINGS_URL", "").strip()
    if env_value:
        raw_candidates.append(env_value)
    settings_value = str(getattr(settings, "ollama_embeddings_url", "") or "").strip()
    if settings_value:
        raw_candidates.append(settings_value)

    if _running_in_docker():
        raw_candidates.extend(
            [
                "http://host.docker.internal:11434/api/embeddings",
                "http://ollama:11434/api/embeddings",
                "http://localhost:11434/api/embeddings",
                "http://127.0.0.1:11434/api/embeddings",
            ]
        )
    else:
        raw_candidates.extend(
            [
                "http://127.0.0.1:11434/api/embeddings",
                "http://localhost:11434/api/embeddings",
                "http://host.docker.internal:11434/api/embeddings",
            ]
        )

    for candidate in raw_candidates:
        clean = (candidate or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        candidates.append(clean)
    return candidates


def _resolve_embed_model() -> str:
    env_value = os.environ.get("WEBSITE_EMBEDDINGS_MODEL", "").strip()
    if env_value:
        return env_value
    settings_value = str(getattr(settings, "website_embeddings_model", "") or "").strip()
    if settings_value:
        return settings_value
    return "nomic-embed-text:latest"


def _safe_snippet(text: str, *, max_chars: int = 320) -> str:
    collapsed = " ".join((text or "").replace("\n", " ").split()).strip()
    if len(collapsed) <= max_chars:
        return collapsed
    return collapsed[: max_chars - 3] + "..."


def _cosine_similarity(query_vec: array, query_norm: float, item_vec: array, item_norm: float) -> float:
    if not query_norm or not item_norm:
        return 0.0
    dot = 0.0
    for qv, iv in zip(query_vec, item_vec):
        dot += float(qv) * float(iv)
    return float(dot / (query_norm * item_norm))


def _vector_norm(vec: array) -> float:
    acc = 0.0
    for v in vec:
        acc += float(v) * float(v)
    return float(acc**0.5)


def _keyword_fallback_score(query: str, text: str) -> float:
    q = (query or "").strip().lower()
    if not q:
        return 0.0
    tokens = [t for t in (q.replace("¿", " ").replace("?", " ").replace(",", " ").split()) if len(t) >= 3]
    if not tokens:
        return 0.0
    hay = (text or "").lower()
    hits = sum(1 for tok in tokens if tok in hay)
    return hits / max(len(tokens), 1)


class KnowledgeService:
    def __init__(
        self,
        *,
        db_path: str | None = None,
        embeddings_url: str | None = None,
        model: str | None = None,
        timeout_seconds: int = 30,
    ) -> None:
        self._db_path = _resolve_db_path(db_path)
        self._embeddings_url = embeddings_url or _resolve_ollama_url()
        self._embeddings_url_candidates = _candidate_ollama_urls(embeddings_url)
        self._model = model or _resolve_embed_model()
        self._timeout_seconds = int(timeout_seconds)
        self._cache_rows: list[tuple[str, str, str, array, float]] | None = None
        self._cache_mtime_ns: int | None = None
        self._active_embeddings_url: str | None = None
        self._last_query_dimensions: int | None = None

    @property
    def db_path(self) -> str:
        return str(self._db_path)

    def _load_rows(self) -> list[tuple[str, str, str, array, float]]:
        try:
            mtime_ns = self._db_path.stat().st_mtime_ns
        except Exception:
            mtime_ns = None

        if self._cache_rows is not None and self._cache_mtime_ns == mtime_ns:
            return self._cache_rows

        if not self._db_path.exists():
            self._cache_rows = []
            self._cache_mtime_ns = mtime_ns
            return self._cache_rows

        conn = sqlite3.connect(str(self._db_path))
        try:
            rows = conn.execute("SELECT url, title, content, embedding FROM chunks").fetchall()
        finally:
            conn.close()

        parsed: list[tuple[str, str, str, array, float]] = []
        for url, title, content, emb_bytes in rows:
            if not emb_bytes:
                continue
            vec = array("f")
            try:
                vec.frombytes(emb_bytes)
            except Exception:
                continue
            norm = _vector_norm(vec)
            parsed.append((str(url or ""), str(title or ""), str(content or ""), vec, norm))

        self._cache_rows = parsed
        self._cache_mtime_ns = mtime_ns
        return parsed

    def _embed_query(self, query: str) -> tuple[array | None, float | None, str | None]:
        query_text = (query or "").strip()
        if not query_text:
            return None, None, "empty_query"
        errors: list[str] = []
        for url in self._embeddings_url_candidates or [self._embeddings_url]:
            try:
                with httpx.Client(timeout=self._timeout_seconds) as client:
                    response = client.post(
                        url,
                        json={"model": self._model, "prompt": query_text},
                    )
                response.raise_for_status()
                payload = response.json()
                embedding = payload.get("embedding")
                if not isinstance(embedding, list) or not embedding:
                    errors.append(f"{url}:invalid_embedding_payload")
                    continue
                vec = array("f", [float(v) for v in embedding])
                self._active_embeddings_url = url
                self._last_query_dimensions = len(vec)
                return vec, _vector_norm(vec), None
            except Exception as exc:
                errors.append(f"{url}:{exc}")
        return None, None, "embeddings_unavailable:" + " | ".join(errors[:3])

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
    ) -> dict[str, Any]:
        started_at = time.time()
        query_text = (query or "").strip()
        top_k = max(1, min(int(top_k), 10))

        rows = self._load_rows()
        query_vec, query_norm, embed_error = self._embed_query(query_text)

        scored: list[tuple[float, str, str, str]] = []
        degraded = False

        if query_vec is None or query_norm is None:
            degraded = True
            for url, title, content, _, _ in rows:
                score = _keyword_fallback_score(query_text, f"{title}\n{content}\n{url}")
                if score <= 0:
                    continue
                scored.append((float(score), url, title, content))
        else:
            for url, title, content, vec, norm in rows:
                if len(vec) != len(query_vec):
                    continue
                score = _cosine_similarity(query_vec, float(query_norm), vec, float(norm))
                scored.append((float(score), url, title, content))

        scored.sort(key=lambda item: item[0], reverse=True)
        hits: list[KnowledgeHit] = []
        for score, url, title, content in scored[:top_k]:
            hits.append(
                KnowledgeHit(
                    score=score,
                    url=url,
                    title=title or "Sin título",
                    snippet=_safe_snippet(content),
                )
            )

        duration_ms = int((time.time() - started_at) * 1000)
        return {
            "ok": True,
            "query": query_text,
            "results": [
                {"score": round(hit.score, 4), "url": hit.url, "title": hit.title, "snippet": hit.snippet}
                for hit in hits
            ],
            "meta": {
                "db_path": str(self._db_path),
                "rows_loaded": len(rows),
                "top_k": top_k,
                "degraded": degraded,
                "embed_model": self._model,
                "query_dimensions": self._last_query_dimensions,
                "embeddings_url": self._embeddings_url,
                "embed_url_used": self._active_embeddings_url,
                "embed_error": embed_error,
                "duration_ms": duration_ms,
            },
        }


def buscar_sitio(query: str, *, top_k: int = 5) -> dict[str, Any]:
    return KnowledgeService().search(query, top_k=top_k)
