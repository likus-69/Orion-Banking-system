"""Base repository with common CRUD primitives."""
from __future__ import annotations

from typing import Generic, Type, TypeVar

from sqlalchemy.orm import Session

from app.database import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Thin wrapper around SQLAlchemy session for a single model."""

    model: Type[ModelT]

    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, pk: int) -> ModelT | None:
        return self.db.get(self.model, pk)

    def add(self, instance: ModelT) -> ModelT:
        self.db.add(instance)
        self.db.flush()
        return instance

    def refresh(self, instance: ModelT) -> ModelT:
        self.db.refresh(instance)
        return instance
