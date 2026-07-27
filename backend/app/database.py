"""
Async database engine and session management.

Provides the async SQLAlchemy engine connected to Supabase PostgreSQL,
an async session factory, and a FastAPI dependency for request-scoped sessions.
"""

import logging
import socket
from typing import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# A command that never returns must never be able to hang a caller forever.
# The path to Supabase runs through a GRE-tunnelled network whose ICMP is
# filtered (see the vps-mtu-mss-clamp note), so a server connection can vanish
# without the FIN ever reaching us. asyncpg has NO command timeout by default:
# the read on such a half-open socket blocks indefinitely, and because the
# scheduler jobs run with max_instances=1 a single hung sweep silently stops
# that job for good — production lost performance tracking and price alerts for
# three hours this way, with zero errors logged.
#
# 90s is deliberately generous: the slowest sweep query measured in production
# took 45.8s, so this is ~2x the worst real case and cannot fire on legitimate
# work. It exists to convert "hangs until the container is restarted" into an
# ordinary error the job wrapper reports.
_COMMAND_TIMEOUT_SECONDS = 90

# Idle-connection keepalive: probe after 60s idle, retry every 15s, give up
# after 4 failures — a dead peer is detected in ~2 minutes.
_KEEPALIVE_IDLE_SECONDS = 60
_KEEPALIVE_INTERVAL_SECONDS = 15
_KEEPALIVE_FAILED_PROBES = 4


def _enable_tcp_keepalive(raw_connection) -> None:
    """Turn on TCP keepalive for one asyncpg connection. Best effort by design.

    Complements _COMMAND_TIMEOUT_SECONDS rather than duplicating it: a
    connection sitting IDLE in the pool is executing nothing, so no command
    timeout can ever fire on it. Without keepalive the kernel never probes the
    peer, a half-open socket stays ESTABLISHED indefinitely, and the first
    thing to touch it — including pool_pre_ping's own liveness check — blocks
    on that dead socket. With keepalive the kernel tears the socket down on its
    own and the pool transparently opens a fresh one.

    asyncpg 0.29 exposes no keepalive parameter, so the socket is only
    reachable through the transport, which is a private attribute. Hence the
    guard: if a future asyncpg moves it, connections keep working exactly as
    before instead of every one of them failing to open.
    """
    try:
        transport = getattr(raw_connection, "_transport", None)
        sock = transport.get_extra_info("socket") if transport is not None else None
        if sock is None:
            return
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        for option, value in (
            ("TCP_KEEPIDLE", _KEEPALIVE_IDLE_SECONDS),
            ("TCP_KEEPINTVL", _KEEPALIVE_INTERVAL_SECONDS),
            ("TCP_KEEPCNT", _KEEPALIVE_FAILED_PROBES),
        ):
            if hasattr(socket, option):  # Linux; absent on macOS/Windows
                sock.setsockopt(socket.IPPROTO_TCP, getattr(socket, option), value)
    except Exception:  # noqa: BLE001 — never block a connection over telemetry
        logger.debug("TCP keepalive could not be applied to this connection",
                     exc_info=True)

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
    connect_args={"command_timeout": _COMMAND_TIMEOUT_SECONDS},
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
def _harden_new_connection(dbapi_connection, connection_record):
    async def _configure(conn):
        _enable_tcp_keepalive(conn)
        await conn.execute("SET idle_in_transaction_session_timeout = '180000'")

    dbapi_connection.run_async(_configure)


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
