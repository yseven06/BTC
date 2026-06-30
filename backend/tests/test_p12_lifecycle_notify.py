"""P12-2: format_lifecycle_message + notify_lifecycle fan-out (opt-in gated, fail-open)."""
import asyncio
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

import app.notifications.service as svc
from app.notifications.telegram import format_lifecycle_message


def test_format_lifecycle_message():
    msg = format_lifecycle_message(
        symbol="BTCUSDT", timeframe="4h", direction="bullish",
        new_status="invalidating", new_status_tr="Geçersizleşiyor",
        old_status_tr="Aktif", reason="Yapı bozuldu", price=12345.6789)
    assert "BTCUSDT" in msg and "Geçersizleşiyor" in msg
    assert "Yapı bozuldu" in msg and "Aktif" in msg and "12,345.6789" in msg  # comma thousands sep


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    async def __aenter__(self):
        db = AsyncMock()
        result = NS(all=lambda: self._rows)

        async def ex(*a, **k):
            return result
        db.execute = ex
        return db

    async def __aexit__(self, *a):
        return False


def _run(**kw):
    base = dict(symbol="BTC", timeframe="4h", direction="bullish",
                old_status="active", new_status="invalidating", reason="x", price=100.0)
    base.update(kw)
    asyncio.run(svc.notify_lifecycle(**base))


def test_notify_lifecycle_optin_fanout():
    settings = NS(user_id="u1", telegram_bot_token="tok", telegram_chat_id="chat")
    user = NS(id="u1")
    sent = AsyncMock(return_value={"ok": True, "error": None})
    with patch.object(svc, "async_session_factory", lambda: _FakeSession([(settings, user)])), \
         patch.object(svc, "send_telegram_message", sent), \
         patch.object(svc, "_user_can_use_telegram", AsyncMock(return_value=True)):
        _run()
    sent.assert_awaited_once()
    assert sent.await_args.args[0] == "tok" and sent.await_args.args[1] == "chat"


def test_notify_lifecycle_tier_gate_blocks():
    settings = NS(user_id="u1", telegram_bot_token="tok", telegram_chat_id="chat")
    user = NS(id="u1")
    sent = AsyncMock(return_value={"ok": True})
    with patch.object(svc, "async_session_factory", lambda: _FakeSession([(settings, user)])), \
         patch.object(svc, "send_telegram_message", sent), \
         patch.object(svc, "_user_can_use_telegram", AsyncMock(return_value=False)):  # not Pro+
        _run()
    sent.assert_not_awaited()


def test_notify_lifecycle_skips_non_alert_state():
    sent = AsyncMock(return_value={"ok": True})
    with patch.object(svc, "send_telegram_message", sent):
        _run(new_status="weakening")        # not in LIFECYCLE_ALERT_STATES
    sent.assert_not_awaited()


def test_notify_lifecycle_never_raises():
    def boom(*a, **k):
        raise RuntimeError("db down")
    with patch.object(svc, "async_session_factory", boom):
        _run()                              # must swallow, not raise


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t(); print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} P12-2 lifecycle-notify tests PASSED")
