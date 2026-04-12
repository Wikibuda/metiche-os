import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4

import typer
from sqlalchemy import text
from sqlmodel import Session, select

from app.domain.narrative.models import NarrativeEntry, NarrativeEntryCreate
from app.domain.narrative.service import (
    create_narrative_entry,
    list_narratives_for_day,
    list_recent_narratives,
)


FUNDATIONAL_COLLECTION_KEY = "planificacion-fundacional-metiche"
FUNDATIONAL_COLLECTION_TITLE = "Planificacion Fundacional de Metiche"


def emoji_for_wonder(level: int) -> str:
    if level >= 5:
        return "*"
    if level == 4:
        return "+"
    if level == 3:
        return "="
    return "-"


def render_entry(entry: NarrativeEntry) -> str:
    stamp = entry.created_at.strftime("%Y-%m-%d %H:%M")
    header = f"{emoji_for_wonder(entry.wonder_level)} [{stamp}] {entry.title}"
    meta = f"Narrador: {entry.narrator_code} | Tipo: {entry.narrative_type} | Asombro: {entry.wonder_level}"
    return "\n".join([header, meta, entry.body.strip()])


def extract_input_texts(node: object, output: list[str]) -> None:
    if isinstance(node, dict):
        text_value = node.get("inputText")
        if isinstance(text_value, str) and text_value.strip():
            output.append(text_value.strip())
        for value in node.values():
            extract_input_texts(value, output)
    elif isinstance(node, list):
        for item in node:
            extract_input_texts(item, output)


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
    for idx, text_item in enumerate(texts[:limit], start=1):
        preview = text_item.replace("\n", " ").strip()
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
    typer.echo(f"\n[resumen_diario] {day.isoformat()}\n")
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


def run_momento(session: Session, text_value: str, narrator_code: str = "gus", wonder_level: int = 4) -> str:
    body = text_value.strip()
    if not body:
        raise ValueError("El texto del momento no puede estar vacio.")
    title = body if len(body) <= 72 else body[:69] + "..."
    created = create_narrative_entry(
        session,
        NarrativeEntryCreate(
            title=f"Momento: {title}",
            body=body,
            narrative_type="momento_manual",
            wonder_level=max(1, min(wonder_level, 5)),
            narrator_code=narrator_code,
        ),
    )
    return created.id


def _upsert_fundational_collection(session: Session) -> str:
    conn = session.connection()
    existing = conn.execute(
        text("SELECT id FROM narrative_collections WHERE collection_key = :collection_key LIMIT 1"),
        {"collection_key": FUNDATIONAL_COLLECTION_KEY},
    ).first()
    if existing:
        return existing[0]

    collection_id = str(uuid4())
    conn.execute(
        text(
            """
            INSERT INTO narrative_collections (
                id, collection_key, collection_type, title, description, curator_code, status, created_at
            ) VALUES (
                :id, :collection_key, :collection_type, :title, :description, :curator_code, :status, :created_at
            )
            """
        ),
        {
            "id": collection_id,
            "collection_key": FUNDATIONAL_COLLECTION_KEY,
            "collection_type": "milestone",
            "title": FUNDATIONAL_COLLECTION_TITLE,
            "description": "Entradas historicas recuperadas desde input_history.json.",
            "curator_code": "gus",
            "status": "open",
            "created_at": datetime.utcnow(),
        },
    )
    return collection_id


def seed_foundational_plan(
    session: Session,
    source_path: Path,
    narrator_code: str = "gus",
    limit: int = 120,
) -> int:
    if not source_path.exists():
        return 0
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    texts: list[str] = []
    extract_input_texts(payload, texts)
    if not texts:
        return 0

    collection_id = _upsert_fundational_collection(session)
    conn = session.connection()
    existing_count_row = conn.execute(
        text("SELECT COUNT(*) FROM narrative_collection_items WHERE collection_id = :collection_id"),
        {"collection_id": collection_id},
    ).fetchone()
    item_order = int(existing_count_row[0]) if existing_count_row else 0

    inserted = 0
    for text_item in texts[:limit]:
        preview = text_item.replace("\n", " ").strip()
        if not preview:
            continue

        dedup = session.exec(
            select(NarrativeEntry)
            .where(NarrativeEntry.narrative_type == "milestone")
            .where(NarrativeEntry.body == preview)
            .limit(1)
        ).first()
        if dedup:
            continue

        entry = NarrativeEntry(
            title=f"Hito fundacional #{inserted + 1}",
            body=preview if len(preview) <= 2000 else (preview[:1997] + "..."),
            narrative_type="milestone",
            wonder_level=5,
            narrator_code=narrator_code,
        )
        session.add(entry)
        session.flush()

        item_order += 1
        conn.execute(
            text(
                """
                INSERT INTO narrative_collection_items (
                    id, collection_id, narrative_entry_id, item_order, include_reason, created_at
                ) VALUES (
                    :id, :collection_id, :narrative_entry_id, :item_order, :include_reason, :created_at
                )
                """
            ),
            {
                "id": str(uuid4()),
                "collection_id": collection_id,
                "narrative_entry_id": entry.id,
                "item_order": item_order,
                "include_reason": "seed_fundacional_input_history",
                "created_at": datetime.utcnow(),
            },
        )
        inserted += 1

    session.commit()
    return inserted
