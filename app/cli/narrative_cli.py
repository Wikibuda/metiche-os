import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path

import typer
from sqlmodel import Session, select

from app.domain.narrative.models import NarrativeEntry, NarrativeEntryCreate
from app.domain.narrative.service import (
    create_narrative_entry,
    list_narratives_for_day,
    list_recent_narratives,
    search_narratives,
)


def emoji_for_wonder(level: int) -> str:
    if level >= 5:
        return "🌟"
    if level == 4:
        return "✨"
    if level == 3:
        return "📖"
    return "📝"


def render_entry(entry: NarrativeEntry) -> str:
    stamp = entry.created_at.strftime("%Y-%m-%d %H:%M")
    header = f"{emoji_for_wonder(entry.wonder_level)} [{stamp}] {entry.title}"
    meta = f"Narrador: {entry.narrator_code} | Tipo: {entry.narrative_type} | Asombro: {entry.wonder_level}"
    return "\n".join([header, meta, entry.body.strip()])


def extract_input_texts(node: object, output: list[str]) -> None:
    if isinstance(node, dict):
        text = node.get("inputText")
        if isinstance(text, str) and text.strip():
            output.append(text.strip())
        for value in node.values():
            extract_input_texts(value, output)
    elif isinstance(node, list):
        for item in node:
            extract_input_texts(item, output)



def seed_from_input_history(session: Session, source_path: Path, limit: int = 40) -> int:
    if not source_path.exists():
        return 0

    already_seeded = session.exec(
        select(NarrativeEntry).where(NarrativeEntry.narrative_type == "seed_input_history").limit(1)
    ).first()
    if already_seeded:
        return 0

    payload = json.loads(source_path.read_text(encoding="utf-8"))
    texts: list[str] = []
    extract_input_texts(payload, texts)
    if not texts:
        return 0

    inserted = 0
    for idx, text in enumerate(texts[:limit], start=1):
        preview = text.replace("\n", " ").strip()
        title = f"Semilla contexto #{idx}"
        body = preview if len(preview) <= 600 else (preview[:597] + "...")
        create_narrative_entry(
            session,
            NarrativeEntryCreate(
                title=title,
                body=body,
                narrative_type="seed_input_history",
                wonder_level=2,
                narrator_code="gus",
            ),
        )
        inserted += 1
    return inserted


def run_cuentame(session: Session, days: int, limit: int) -> None:
    safe_days = max(1, min(days, 30))
    safe_limit = max(1, min(limit, 30))
    entries = list_recent_narratives(session, limit=safe_limit)
    typer.echo(f"\n[cuentame] Ultimos {safe_days} dia(s), max {safe_limit} cronicas:\n")
    if not entries:
        typer.echo("No hay cronicas en la bitacora.\n")
        return
    for item in entries:
        row = NarrativeEntry.model_validate(item.model_dump())
        typer.echo(render_entry(row))
        typer.echo("-" * 72)


def run_resumen_diario(session: Session, day: date) -> None:
    entries = list_narratives_for_day(session, day)
    typer.echo(f"\n🗓️ Resumen diario {day.isoformat()}\n")
    if not entries:
        typer.echo("No hay cronicas registradas para ese dia.\n")
        return

    by_type = Counter(item.narrative_type for item in entries)
    by_narrator = Counter(item.narrator_code for item in entries)
    avg_wonder = round(sum(item.wonder_level for item in entries) / len(entries), 2)

    typer.echo(f"Total de cronicas: {len(entries)}")
    typer.echo(f"Asombro promedio: {avg_wonder}")
    typer.echo("Tipos: " + ", ".join([f"{k}={v}" for k, v in by_type.items()]))
    typer.echo("Narradores: " + ", ".join([f"{k}={v}" for k, v in by_narrator.items()]))
    typer.echo("\nUltimos momentos del dia:\n")

    for item in entries[:5]:
        row = NarrativeEntry.model_validate(item.model_dump())
        typer.echo(render_entry(row))
        typer.echo("-" * 72)


def run_momento(session: Session, query: str, limit: int) -> None:
    safe_limit = max(1, min(limit, 20))
    items = search_narratives(session, query=query, limit=safe_limit)
    typer.echo(f'\n🔎 Momento: "{query}"\n')
    if not items:
        typer.echo("No hay cronicas para esa busqueda.\n")
        return
    for item in items:
        row = NarrativeEntry.model_validate(item.model_dump())
        typer.echo(render_entry(row))
        typer.echo("-" * 72)


def parse_day_or_today(day_text: str) -> date:
    if not day_text.strip():
        return datetime.now().date()
    return datetime.strptime(day_text.strip(), "%Y-%m-%d").date()


def resolve_seed_input_history_path() -> Path | None:
    candidates = [
        Path("input_history.json"),
        Path.home() / "Downloads" / "input_history.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None
