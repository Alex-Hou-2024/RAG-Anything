"""Database lifecycle and idempotent metadata migrations."""

from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import Settings


class Base(DeclarativeBase):
    """Base for the small set of application-owned relational models."""


class Database:
    """Own the SQLAlchemy engine and apply metadata schema migrations once."""

    def __init__(self, database_url: str) -> None:
        self.engine: Engine = create_engine(database_url, pool_pre_ping=True)
        self.session_factory: sessionmaker[Session] = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> "Database":
        if not settings.database_url:
            raise RuntimeError("DATABASE_URL is required for persistent document metadata")
        return cls(settings.database_url)

    async def run_migrations(self) -> None:
        """Create/upgrade the documents table without blocking the event loop."""
        await asyncio.to_thread(self._run_migrations)

    def _run_migrations(self) -> None:
        # Production is Postgres and uses the checked-in SQL migration. SQLite
        # is supported only as a lightweight test backend, where Postgres-only
        # JSONB and UUID syntax is not accepted.
        if self.engine.dialect.name == "postgresql":
            migration = (
                Path(__file__).resolve().parent.parent
                / "migrations"
                / "versions"
                / "0001_documents.sql"
            )
            statements = migration.read_text(encoding="utf-8").split(";")
            with self.engine.begin() as connection:
                for statement in statements:
                    if statement.strip():
                        connection.exec_driver_sql(statement)
            return

        # Importing registers DocumentRow on Base without creating a circular
        # import while this module itself is imported by api.models.
        from . import models as _models  # noqa: F401

        Base.metadata.create_all(self.engine)

    async def dispose(self) -> None:
        """Release connections during FastAPI shutdown."""
        await asyncio.to_thread(self.engine.dispose)


def create_session_factory(settings: Settings) -> sessionmaker[Session]:
    """Compatibility helper for callers that only need a configured factory."""
    return Database.from_settings(settings).session_factory
