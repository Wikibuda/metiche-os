import time
from pathlib import Path

import typer
from sqlmodel import Session

from app.bootstrap.seed_core import seed_core_data
from app.cli.commands.narrative_commands import (
    parse_day_or_today,
    resolve_seed_input_history_path,
    run_cuentame,
    run_momento,
    run_resumen_diario,
    seed_foundational_plan,
    seed_from_input_history,
)
from app.cli.validation_commands import register_validation_commands
from app.core.config import settings
from app.core.db import create_db_and_tables, engine
from app.domain.narrative.narrator_selector import MinimalNarratorSelector
from app.domain.tasks.models import TaskRunCreate
from app.domain.tasks.service import process_next_task, run_task_flow
from app.projections.bitacora import build_bitacora
from app.services.plane_comment_watcher import process_plane_comment_commands
from app.services.plane_bridge_service import process_plane_enjambre_pull

cli = typer.Typer(no_args_is_help=True)
register_validation_commands(cli)


def _try_seed_input_history(session: Session, enabled: bool) -> None:
    if not enabled:
        return
    source_path = resolve_seed_input_history_path()
    if not source_path:
        typer.echo("No se encontro input_history.json en proyecto ni en Downloads.")
        return
    inserted = seed_from_input_history(session, source_path)
    if inserted:
        typer.echo(f"Semilla cargada desde {source_path}: {inserted} entradas.")


@cli.callback(invoke_without_command=True)
def root(
    ctx: typer.Context,
    cuentame: bool = typer.Option(False, "--cuentame", help="Cuenta narrativas recientes."),
    resumen_diario: bool = typer.Option(False, "--resumen_diario", help="Muestra resumen diario."),
    fecha: str = typer.Option("", "--fecha", help="Fecha objetivo YYYY-MM-DD para --resumen_diario."),
    momento: str = typer.Option("", "--momento", help="Registra un momento narrativo manual."),
    dias: int = typer.Option(7, "--dias", min=1, max=30, help="Rango de dias para --cuentame."),
    limite: int = typer.Option(7, "--limite", min=1, max=30, help="Maximo de entradas a mostrar."),
    seed_input_history: bool = typer.Option(False, "--seed-input-history", help="Carga input_history.json como semilla."),
) -> None:
    if ctx.invoked_subcommand:
        return
    if not cuentame and not resumen_diario and not momento:
        return

    create_db_and_tables()
    seed_core_data()
    with Session(engine) as session:
        _try_seed_input_history(session, seed_input_history)
        if cuentame:
            run_cuentame(session, days=dias, limit=limite)
        if resumen_diario:
            run_resumen_diario(session, day=parse_day_or_today(fecha))
        if momento:
            created_id = run_momento(session, text_value=momento, narrator_code="gus", wonder_level=4)
            typer.echo(f"Momento narrativo registrado: {created_id}")


@cli.command("init-db")
def init_db() -> None:
    create_db_and_tables()
    seed_core_data()
    typer.echo("metiche-os db lista")


@cli.command("build-bitacora")
def build_bitacora_command() -> None:
    create_db_and_tables()
    seed_core_data()
    with Session(engine) as session:
        path = build_bitacora(session, Path(settings.projections_root) / "bitacora" / "bitacora_de_asombros.md")
    typer.echo(str(path))


@cli.command("run-worker")
def run_worker() -> None:
    create_db_and_tables()
    seed_core_data()
    selector = MinimalNarratorSelector()
    last_plane_watch_at = 0.0
    last_plane_comment_watch_at = 0.0
    while True:
        with Session(engine) as session:
            result = process_next_task(session)
            now_ts = time.time()
            if (
                settings.plane_sync_enabled
                and settings.plane_watch_enabled
                and now_ts - last_plane_watch_at >= max(5, settings.plane_watch_interval_seconds)
            ):
                pull_result = process_plane_enjambre_pull(session, limit=settings.plane_watch_limit)
                if pull_result.get("ok") and pull_result.get("launched"):
                    typer.echo(
                        "plane-watch lanzó enjambres: "
                        f"launched={pull_result.get('launched')} scanned={pull_result.get('scanned')}"
                    )
                last_plane_watch_at = now_ts
            if (
                settings.plane_sync_enabled
                and settings.plane_comment_watch_enabled
                and now_ts - last_plane_comment_watch_at >= max(5, settings.plane_comment_watch_interval_seconds)
            ):
                command_result = process_plane_comment_commands(limit=settings.plane_comment_watch_limit)
                if command_result.get("ok") and command_result.get("processed"):
                    typer.echo(
                        "plane-comments procesados: "
                        f"processed={command_result.get('processed')} skipped={command_result.get('skipped')}"
                    )
                last_plane_comment_watch_at = now_ts
            selected = selector.tick(session)
            promoted = selector.promote_pending_candidates(session, limit=50)
            build_bitacora(session, Path(settings.projections_root) / "bitacora" / "bitacora_de_asombros.md")
        if result:
            typer.echo(f"worker procesó {result.flow.task.title} | retry={result.retry_scheduled}")
        if selected or promoted:
            typer.echo(f"narrator selector: candidatos={selected} | promovidos={promoted}")
        time.sleep(settings.worker_poll_seconds)


@cli.command("cuentame")
def cuentame_command(
    dias: int = typer.Option(7, "--dias", min=1, max=30, help="Rango de dias."),
    limite: int = typer.Option(7, "--limite", min=1, max=30, help="Maximo de entradas."),
    seed_input_history: bool = typer.Option(False, "--seed-input-history", help="Carga input_history.json como semilla."),
) -> None:
    create_db_and_tables()
    seed_core_data()
    with Session(engine) as session:
        _try_seed_input_history(session, seed_input_history)
        run_cuentame(session, days=dias, limit=limite)


@cli.command("resumen-diario")
def resumen_diario_command(
    dia: str = typer.Option("", "--dia", "--fecha", help="Dia objetivo YYYY-MM-DD, vacio=today."),
    seed_input_history: bool = typer.Option(False, "--seed-input-history", help="Carga input_history.json como semilla."),
) -> None:
    create_db_and_tables()
    seed_core_data()
    with Session(engine) as session:
        _try_seed_input_history(session, seed_input_history)
        run_resumen_diario(session, day=parse_day_or_today(dia))


@cli.command("momento")
def momento_command(
    texto: str = typer.Argument(..., help="Texto narrativo del momento."),
    narrador: str = typer.Option("gus", "--narrador", help="Codigo del narrador."),
    asombro: int = typer.Option(4, "--asombro", min=1, max=5, help="Nivel de asombro del momento."),
    seed_input_history: bool = typer.Option(False, "--seed-input-history", help="Carga input_history.json como semilla."),
) -> None:
    create_db_and_tables()
    seed_core_data()
    with Session(engine) as session:
        _try_seed_input_history(session, seed_input_history)
        created_id = run_momento(session, text_value=texto, narrator_code=narrador, wonder_level=asombro)
        typer.echo(f"Momento narrativo registrado: {created_id}")


@cli.command("seed-fundacional")
def seed_fundacional_command(
    source: str = typer.Option("", "--source", help="Ruta a input_history.json (default: proyecto o Downloads)."),
    narrador: str = typer.Option("gus", "--narrador", help="Codigo del narrador."),
    limite: int = typer.Option(120, "--limite", min=1, max=1000, help="Numero maximo de entradas a cargar."),
) -> None:
    create_db_and_tables()
    seed_core_data()
    source_path = Path(source) if source else resolve_seed_input_history_path()
    if not source_path:
        typer.echo("No se encontro input_history.json. Usa --source para indicar la ruta.")
        raise typer.Exit(code=1)
    with Session(engine) as session:
        inserted = seed_foundational_plan(session, source_path=source_path, narrator_code=narrador, limit=limite)
    typer.echo(f"Carga fundacional completada desde {source_path}: {inserted} entradas.")


@cli.command("narrator-tick")
def narrator_tick_command(
    promover: bool = typer.Option(True, "--promover/--solo-candidatos", help="Promueve candidatos a cronicas."),
    limite: int = typer.Option(100, "--limite", min=1, max=500, help="Maximo de candidatos a promover."),
) -> None:
    create_db_and_tables()
    seed_core_data()
    selector = MinimalNarratorSelector()
    with Session(engine) as session:
        selected = selector.tick(session)
        promoted = selector.promote_pending_candidates(session, limit=limite) if promover else 0
    typer.echo(f"narrator tick completado: candidatos={selected} | promovidos={promoted}")


@cli.command("run")
def run_command(
    task: str = typer.Option(..., "--task", help="Titulo de la tarea."),
    description: str = typer.Option("", "--description", help="Descripcion opcional."),
    task_type: str = typer.Option("planning", "--task-type", help="Tipo de tarea/canal."),
    execution_mode: str = typer.Option("immediate", "--execution-mode", help="Modo de ejecucion."),
) -> None:
    create_db_and_tables()
    seed_core_data()
    with Session(engine) as session:
        flow = run_task_flow(
            session,
            TaskRunCreate(
                title=task,
                description=description or None,
                task_type=task_type,
                execution_mode=execution_mode,
            ),
        )
    typer.echo(
        f"run completado: task_id={flow.task.id} | task_status={flow.task.status} | validation={flow.validation.status}"
    )


if __name__ == "__main__":
    cli()
