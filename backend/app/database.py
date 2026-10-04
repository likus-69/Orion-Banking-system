"""Database engine, session, and declarative base."""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


# SQLite needs check_same_thread=False for FastAPI request threads;
# PostgreSQL doesn't care about this kwarg.
_connect_args = (
    {"check_same_thread": False}
    if settings.database_url.startswith("sqlite")
    else {}
)

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args=_connect_args,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Declarative base for all Orion models."""

    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yields a scoped session, ensures close on exit."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
