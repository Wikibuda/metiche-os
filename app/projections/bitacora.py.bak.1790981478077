from pathlib import Path

from sqlmodel import Session, select

from app.domain.narrative.models import NarrativeEntry


def build_bitacora(session: Session, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    entries = session.exec(select(NarrativeEntry).order_by(NarrativeEntry.created_at.desc())).all()
    lines = [
        "# 📖 Bitácora de Asombros",
        "",
        "_El libro vivo de Gus, Metiche y los enjambres._",
        "",
    ]
    if not entries:
        lines.extend(["## ✨ Último asombro", "", "Aún no hay crónicas en este laboratorio."])
    else:
        latest = entries[0]
        lines.extend([
            "## ✨ Último asombro",
            "",
            f"### {latest.title}",
            f"**Narrador:** {latest.narrator_code}",
            f"**Asombro:** {latest.wonder_level}",
            "",
            latest.body,
            "",
            "## 🌅 Crónicas recientes",
            "",
        ])
        for entry in entries:
            lines.extend([
                f"### {entry.title}",
                f"**Narrador:** {entry.narrator_code}",
                f"**Tipo:** {entry.narrative_type}",
                f"**Asombro:** {entry.wonder_level}",
                "",
                entry.body,
                "",
            ])
    output_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return output_path
