from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "service": "metiche-os",
        "environment": settings.metiche_env,
        "readonly_root": settings.openclaw_readonly_root,
    }
