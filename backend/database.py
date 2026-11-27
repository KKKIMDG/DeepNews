from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine, make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import SCHEMA_SQL_DIR, settings


class Base(DeclarativeBase):
    pass


def build_engine_url(database_url: str):
    url = make_url(database_url)
    # SQLAlchemy 2.1+ maps plain postgresql:// to psycopg 3; this project ships psycopg2.
    return url.set(drivername="postgresql+psycopg2") if url.drivername == "postgresql" else url


# pre_ping: a pooled connection dropped by a DB restart or pooler is replaced instead of failing the request with a 500.
engine = create_engine(build_engine_url(settings.database_url), future=True, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@contextmanager
def get_session():
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
    return SessionLocal()


# Arbitrary constant: serializes schema setup when several API processes start at once.
SCHEMA_LOCK_ID = 727301


def ensure_schema() -> None:
    """Apply backend/sql/*.sql in name order, each file once, recorded in schema_migration.

    Files must still be idempotent: databases created before schema_migration existed replay them once.
    """
    sql_files = sorted(SCHEMA_SQL_DIR.glob("*.sql"))
    if not sql_files:
        return

    connection = engine.raw_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("select pg_advisory_lock(%s)", (SCHEMA_LOCK_ID,))
            try:
                cursor.execute(
                    "create table if not exists public.schema_migration ("
                    " filename varchar(255) primary key, applied_at timestamptz not null default now())"
                )
                cursor.execute("select filename from public.schema_migration")
                applied = {row[0] for row in cursor.fetchall()}
                for sql_file in sql_files:
                    if sql_file.name in applied:
                        continue
                    cursor.execute(sql_file.read_text(encoding="utf-8"))
                    cursor.execute("insert into public.schema_migration (filename) values (%s)", (sql_file.name,))
                    connection.commit()
            finally:
                connection.rollback()  # a failed file leaves the transaction aborted; the session lock survives
                cursor.execute("select pg_advisory_unlock(%s)", (SCHEMA_LOCK_ID,))
                connection.commit()
    finally:
        connection.close()
