"""Database helpers."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def create_session_factory(db_path: str) -> sessionmaker:
    """Create a SQLAlchemy session factory for the configured SQLite path."""

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{path}", future=True)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
