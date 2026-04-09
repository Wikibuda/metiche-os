from sqlmodel import Session, select

from app.domain.soul.models import Actor, CanonicalPhrase, SoulProfile


def get_metiche_soul(session: Session) -> dict:
    actor = session.exec(select(Actor).where(Actor.code == "metiche")).first()
    if not actor:
        return {"ok": False, "error": "Metiche no existe todavía"}
    soul = session.get(SoulProfile, actor.id)
    phrases = session.exec(select(CanonicalPhrase).where(CanonicalPhrase.actor_id == actor.id)).all()
    return {
        "ok": True,
        "actor": actor.model_dump(),
        "soul": soul.model_dump() if soul else None,
        "phrases": [phrase.model_dump() for phrase in phrases],
    }
