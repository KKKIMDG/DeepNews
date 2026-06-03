from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import SCHEMA_SQL_PATH, settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, future=True) if settings.database_url else None
SessionLocal = (
    sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    if engine is not None
    else None
)


@contextmanager
def get_session():
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is required for database-backed endpoints.")
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db_session() -> Session:
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is required for database-backed endpoints.")
    return SessionLocal()


def ensure_schema() -> None:
    if engine is None or not SCHEMA_SQL_PATH.exists():
        return

    sql = SCHEMA_SQL_PATH.read_text(encoding="utf-8")
    connection = engine.raw_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql)
        connection.commit()
    finally:
        connection.close()
