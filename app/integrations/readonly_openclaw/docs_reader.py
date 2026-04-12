from pathlib import Path

from app.core.config import settings


def list_workspace_docs() -> list[str]:
    root = Path(settings.openclaw_readonly_root) / "workspace"
    if not root.exists():
        return []
    return sorted(str(path) for path in root.glob("*.md"))[:50]
