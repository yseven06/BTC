"""
Async database engine and session management.

Provides the async SQLAlchemy engine connected to Supabase PostgreSQL,
an async session factory, and a FastAPI dependency for request-scoped sessions.
"""

from typing import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

# Create the async engine with connection pooling tuned for the Supabase
# Supavisor pooler. Supavisor (session mode) hard-caps this project at 15
# concurrent client connections — the old pool_size=20 + max_overflow=10 asked
# for up to 30, so under any real concurrency the engine tried to open more
# server connections than the pooler allows and got "max clients reached
# (pool_size: 15)". Keep the ceiling (pool_size + max_overflow) safely below 15
# and leave a few slots free for one-off admin/migration scripts that connect
# through the same pooler. pool_recycle is shortened so the engine proactively
# drops connections the pooler would otherwise reclaim out from under it; with
# pool_pre_ping a stale connection is detected and replaced on checkout rather
# than surfacing as a query error. reset-on-return defaults to a rollback, which
# is what keeps a returned connection from lingering "idle in transaction".
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=8,
    max_overflow=2,
    pool_timeout=20,
    pool_recycle=600,
    pool_pre_ping=True,
)


# Safety net against orphaned "idle in transaction" sessions. When a worker is
# killed mid-transaction — uvicorn --reload restarting on a code edit, or a
# crash — its server-side connection is left stuck "idle in transaction" inside
# the Supavisor pooler, which never reaps it. These accumulate (we found ones
# 6 days old) until the pooler's 15-client cap is exhausted and the backend can
# no longer open ANY connection — surfacing as "server unreachable" on login.
# Postgres' idle_in_transaction_session_timeout auto-rolls-back + closes any
# session left idle inside a transaction past the limit, so an orphan can never
# linger. It MUST be applied per-connection via SET: the Supavisor pooler
# ignores asyncpg startup server_settings but honours a post-connect SET
# (empirically verified). 180s is far above any legitimate hold (the tracker /
# alert sweeps keep a txn open only for seconds while fetching prices) yet
# reaps genuine orphans promptly. See the db-idle-in-transaction-leak note.
@event.listens_for(engine.sync_engine, "connect")
def _set_idle_in_transaction_timeout(dbapi_connection, connection_record):
    dbapi_connection.run_async(
        lambda conn: conn.execute(
            "SET idle_in_transaction_session_timeout = '180000'"
        )
    )


# Session factory bound to the engine
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy ORM models.

    All database models in the application should inherit from this class
    to be included in migrations and schema generation.
    """

    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that provides an async database session.

    Yields a session scoped to the request lifecycle. The session
    is automatically closed when the request finishes, and any
    uncommitted changes are rolled back on error.

    Yields:
        AsyncSession: An active database session.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """
    Initialize the database by creating all tables.

    Should only be used in development. In production, use Alembic migrations.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Dispose the database engine and close all connections."""
    await engine.dispose()
