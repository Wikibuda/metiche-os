import json

import typer
from sqlmodel import Session

from app.core.db import create_db_and_tables, engine
from app.domain.tasks.service import validate_task_by_id


def register_validation_commands(cli: typer.Typer) -> None:
    @cli.command("validate")
    def validate_command(
        task_id: str = typer.Option(..., "--task-id", help="ID de la tarea a validar."),
    ) -> None:
        create_db_and_tables()
        with Session(engine) as session:
            result = validate_task_by_id(session, task_id)
        if not result:
            typer.echo(f"Tarea no encontrada: {task_id}")
            raise typer.Exit(code=1)
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
