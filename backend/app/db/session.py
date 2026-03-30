from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.config.settings import settings
from app.db.models import Base, SessionRuntimeStateModel


BACKEND_DIR = Path(__file__).resolve().parents[2]


def _resolve_database_url(raw_database_url: str) -> str:
    if not raw_database_url.startswith("sqlite:///"):
        return raw_database_url

    database_path = Path(raw_database_url.removeprefix("sqlite:///"))
    if not database_path.is_absolute():
        database_path = (BACKEND_DIR / database_path).resolve()

    database_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{database_path}"


engine = create_engine(_resolve_database_url(settings.database_url), connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        states = db.scalars(select(SessionRuntimeStateModel)).all()
        changed = False
        for state in states:
            if state.active_turn_json or state.pending_frontend_tool_json:
                state.active_turn_json = None
                state.pending_frontend_tool_json = None
                changed = True
        if changed:
            db.commit()
