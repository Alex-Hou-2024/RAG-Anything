"""Postgres database lifecycle for persistent document metadata."""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import Settings
class Base(DeclarativeBase): pass
def create_session_factory(settings: Settings):
    if not settings.database_url: raise RuntimeError('DATABASE_URL is required for persistent metadata')
    return sessionmaker(bind=create_engine(settings.database_url, pool_pre_ping=True), expire_on_commit=False)
