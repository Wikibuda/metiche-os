import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from app.api.routes_channel_memory import router as channel_memory_router
from app.api.routes_dashboard import router as dashboard_router
from app.api.routes_health import router as health_router
from app.api.routes_memory import router as memory_router
from app.api.routes_narrative import router as narrative_router
from app.api.routes_plane_commands import router as plane_commands_router
from app.api.routes_rules import router as rules_router
from app.api.routes_soul import router as soul_router
from app.api.routes_swarm import router as swarm_router
from app.api.routes_tasks import router as tasks_router
from app.api.routes_webhooks import router as webhooks_router
from app.bootstrap.seed_core import seed_core_data
from app.core.config import settings
from app.core.db import create_db_and_tables
from app.services.openclaw_autoreply_poller import OpenClawAutoReplyPoller


@asynccontextmanager
async def lifespan(_: FastAPI):
    poller_task: asyncio.Task[None] | None = None
    create_db_and_tables()
    seed_core_data()
    if settings.openclaw_autoreply_polling_enabled:
        poller = OpenClawAutoReplyPoller()
        poller_task = asyncio.create_task(poller.run_forever())
    try:
        yield
    finally:
        if poller_task is not None:
            poller_task.cancel()
            with suppress(asyncio.CancelledError):
                await poller_task


app = FastAPI(title="metiche-os", version="0.1.0", lifespan=lifespan)
app.include_router(health_router)
app.include_router(channel_memory_router)
app.include_router(tasks_router)
app.include_router(soul_router)
app.include_router(narrative_router)
app.include_router(memory_router)
app.include_router(rules_router)
app.include_router(dashboard_router)
app.include_router(swarm_router)
app.include_router(webhooks_router)
app.include_router(plane_commands_router)


@app.get("/admin-dashboard.html", include_in_schema=False)
def admin_dashboard_alias() -> RedirectResponse:
    return RedirectResponse(url="/dashboard/swarm-console.html", status_code=307)
