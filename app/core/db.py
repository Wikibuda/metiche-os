from typing import Generator

from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings
from app.domain.narrative.models import NarrativeEntry
from app.domain.rules import Rule
from app.domain.soul.models import Actor, CanonicalPhrase, SoulProfile
from app.domain.tasks.models import Decision, EngineDispatch, Execution, QueueEntry, RouteResolution, Task, Validation

engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
