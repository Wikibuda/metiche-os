from __future__ import annotations

from typing import Any

from app.services.knowledge_service import KnowledgeService


def buscar_sitio(query: str, *, top_k: int = 5) -> dict[str, Any]:
    return KnowledgeService().search(query, top_k=top_k)

