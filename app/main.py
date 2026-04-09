from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes_health import router as health_router
from app.api.routes_narrative import router as narrative_router
from app.api.routes_rules import router as rules_router
from app.api.routes_soul import router as soul_router
from app.api.routes_tasks import router as tasks_router
from app.bootstrap.seed_core import seed_core_data
from app.core.db import create_db_and_tables


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_db_and_tables()
    seed_core_data()
    yield


app = FastAPI(title="metiche-os", version="0.1.0", lifespan=lifespan)
app.include_router(health_router)
app.include_router(tasks_router)
app.include_router(soul_router)
app.include_router(narrative_router)
app.include_router(rules_router)
