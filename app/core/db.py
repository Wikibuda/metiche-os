from pathlib import Path
from typing import Generator

from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings
from app.domain.narrative.models import NarrativeEntry
from app.domain.rules import Rule
from app.domain.soul.models import Actor, CanonicalPhrase, SoulProfile
from app.domain.tasks.models import Decision, EngineDispatch, Execution, QueueEntry, RouteResolution, Task, Validation

engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})


def _apply_sql_bootstrap_files() -> None:
    # Narrative/expansion tables are maintained via raw SQL files.
    # Keep startup idempotent by applying all *.sql files on every boot.
    sql_dir = Path(__file__).resolve().parent.parent / "sql"
    if not sql_dir.exists():
        return

    backend = engine.url.get_backend_name()
    if backend != "sqlite":
        return

    for sql_file in sorted(sql_dir.glob("*.sql")):
        script = sql_file.read_text(encoding="utf-8")
        conn = engine.raw_connection()
        try:
            conn.executescript(script)
            conn.commit()
        finally:
            conn.close()


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)
    _apply_sql_bootstrap_files()


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
