"""CP-6.5: a dead database connection must never hang a caller forever.

Production lost performance tracking and price alerts for three hours because a
half-open socket to the Supabase pooler stayed ESTABLISHED with no keepalive and
no command timeout: the coroutine that checked that connection out suspended
permanently, and APScheduler's max_instances=1 then skipped every later trigger.
Not one error was logged — the failure mode is silence.

Two independent guards are pinned here because they cover different states:
  • command_timeout  — bounds a hang while a command is IN FLIGHT
  • TCP keepalive    — detects a dead peer while the connection sits IDLE in the
                       pool, where no command timeout can ever fire
"""
import asyncio
import socket
from unittest.mock import MagicMock

import pytest
from sqlalchemy import event

from app import database


# ── command_timeout ─────────────────────────────────────────────────────────
def test_command_timeout_is_above_the_slowest_measured_query():
    """45.8s was the slowest real sweep query measured in production. A timeout
    at or below that would start failing legitimate work — the guard must only
    ever fire on a genuinely stuck connection."""
    assert database._COMMAND_TIMEOUT_SECONDS >= 90


def test_command_timeout_is_actually_passed_to_the_driver():
    """The constant is worthless if it never reaches asyncpg.

    Checked at the `do_connect` hook, which sees exactly the parameters
    SQLAlchemy is about to hand the driver. The handler aborts there, so no
    connection is ever opened and no network is touched.

    Only the one key is copied out — never the parameter dict, which also
    carries the database password and would otherwise be printed verbatim in a
    pytest assertion diff.
    """
    seen = {}

    class _Abort(Exception):
        pass

    @event.listens_for(database.engine.sync_engine, "do_connect")
    def _capture(dialect, conn_rec, cargs, cparams):  # noqa: ARG001
        seen["command_timeout"] = cparams.get("command_timeout")
        raise _Abort

    try:
        with pytest.raises(Exception):
            asyncio.run(_open())
    finally:
        event.remove(database.engine.sync_engine, "do_connect", _capture)

    assert seen.get("command_timeout") == database._COMMAND_TIMEOUT_SECONDS


async def _open():
    async with database.engine.connect():
        pass


# ── TCP keepalive ───────────────────────────────────────────────────────────
class _Sock:
    def __init__(self):
        self.opts = {}

    def setsockopt(self, level, option, value):
        self.opts[(level, option)] = value


def _conn_with(sock):
    transport = MagicMock()
    transport.get_extra_info.return_value = sock
    conn = MagicMock()
    conn._transport = transport
    return conn


def test_keepalive_is_enabled_on_the_socket():
    sock = _Sock()
    database._enable_tcp_keepalive(_conn_with(sock))
    assert sock.opts[(socket.SOL_SOCKET, socket.SO_KEEPALIVE)] == 1


@pytest.mark.skipif(not hasattr(socket, "TCP_KEEPIDLE"), reason="Linux-only options")
def test_keepalive_probe_timings_are_applied():
    sock = _Sock()
    database._enable_tcp_keepalive(_conn_with(sock))
    assert sock.opts[(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE)] == database._KEEPALIVE_IDLE_SECONDS
    assert sock.opts[(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL)] == database._KEEPALIVE_INTERVAL_SECONDS
    assert sock.opts[(socket.IPPROTO_TCP, socket.TCP_KEEPCNT)] == database._KEEPALIVE_FAILED_PROBES


def test_dead_peer_is_detected_within_the_pool_recycle_window():
    """Detection must beat pool_recycle (600s), otherwise recycling would always
    win the race and keepalive would be decorative."""
    worst_case = (database._KEEPALIVE_IDLE_SECONDS
                  + database._KEEPALIVE_INTERVAL_SECONDS * database._KEEPALIVE_FAILED_PROBES)
    assert worst_case < 600


# ── fail-soft: keepalive must never break connection setup ──────────────────
def test_missing_transport_is_tolerated():
    """asyncpg 0.29 only exposes the socket through the private _transport. If a
    future version moves it, connections must keep opening exactly as before."""
    conn = MagicMock(spec=[])          # no _transport at all
    database._enable_tcp_keepalive(conn)   # must not raise


def test_transport_without_socket_is_tolerated():
    transport = MagicMock()
    transport.get_extra_info.return_value = None
    conn = MagicMock()
    conn._transport = transport
    database._enable_tcp_keepalive(conn)   # must not raise


def test_setsockopt_failure_is_tolerated():
    class _Angry:
        def setsockopt(self, *a):
            raise OSError("no such option")

    database._enable_tcp_keepalive(_conn_with(_Angry()))   # must not raise


# ── the connect hook still does what it did before ──────────────────────────
def test_connect_hook_still_sets_idle_in_transaction_timeout():
    """The idle-in-transaction reaper predates this checkpoint and guards a
    different failure (orphaned sessions exhausting the pooler). Folding the
    keepalive call into the same hook must not drop it."""
    captured = {}

    class _DbapiConn:
        def run_async(self, fn):
            captured["fn"] = fn

    database._harden_new_connection(_DbapiConn(), None)
    assert "fn" in captured

    statements = []

    class _RawConn:
        _transport = None

        async def execute(self, sql):
            statements.append(sql)

    asyncio.run(captured["fn"](_RawConn()))
    assert any("idle_in_transaction_session_timeout" in s for s in statements)
    assert any("180000" in s for s in statements)


def test_connect_hook_applies_keepalive_to_every_new_connection(monkeypatch):
    """The constants and the helper are useless if the hook stops calling it —
    and nothing else in the suite would notice."""
    calls = []
    monkeypatch.setattr(database, "_enable_tcp_keepalive", lambda conn: calls.append(conn))

    captured = {}

    class _DbapiConn:
        def run_async(self, fn):
            captured["fn"] = fn

    class _RawConn:
        async def execute(self, sql):
            return None

    database._harden_new_connection(_DbapiConn(), None)
    raw = _RawConn()
    asyncio.run(captured["fn"](raw))

    assert calls == [raw], "every new connection must get keepalive enabled"
