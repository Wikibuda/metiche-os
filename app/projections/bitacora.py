from pathlib import Path

from sqlmodel import Session, select

from app.domain.narrative.models import NarrativeEntry

# El worker reescribe esta bitacora en cada vuelta. Con las 6,163 entradas
# completas el archivo pesaba ~2 MB y se regeneraba cada 5 s. Estas dos cotas
# lo dejan legible y barato sin perder la fuente de verdad (la tabla sigue
# completa; esto es solo la proyeccion). [issue #458]
LIMITE_ENTRADAS = 300
MAX_CUERPO = 1200


def _recorte(texto: str, tope: int = MAX_CUERPO) -> str:
    texto = (texto or "").strip()
    if len(texto) <= tope:
        return texto
    return texto[:tope].rstrip() + "\n\n_(recortado; la crónica completa vive en la tabla)_"


def build_bitacora(session: Session, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    entries = session.exec(
        select(NarrativeEntry)
        .order_by(NarrativeEntry.created_at.desc())
        .limit(LIMITE_ENTRADAS)
    ).all()
    lineas = [
        "# 📖 Bitácora de Asombros",
        "",
        "_El libro vivo de Gus, Metiche y los enjambres._",
        "",
    ]
    if not entries:
        lineas.extend(["## ✨ Último asombro", "", "Aún no hay crónicas en este laboratorio."])
    else:
        latest = entries[0]
        lineas.extend([
            "## ✨ Último asombro",
            "",
            f"### {latest.title}",
            f"**Narrador:** {latest.narrator_code}",
            f"**Asombro:** {latest.wonder_level}",
            "",
            _recorte(latest.body),
            "",
            "## 🌅 Crónicas recientes",
            "",
        ])
        for entry in entries:
            lineas.extend([
                f"### {entry.title}",
                f"**Narrador:** {entry.narrator_code}",
                f"**Tipo:** {entry.narrative_type}",
                f"**Asombro:** {entry.wonder_level}",
                "",
                _recorte(entry.body),
                "",
            ])
    output_path.write_text("\n".join(lineas).strip() + "\n", encoding="utf-8")
    return output_path
