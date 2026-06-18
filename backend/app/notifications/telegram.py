"""
TradeMinds AI – Telegram Notification Service

Sends formatted messages to a Telegram chat using the Bot API.
No third-party library needed — uses httpx against the public Bot API.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"

SIGNAL_EMOJI = {
    "STRONG_BUY": "🟢🟢",
    "BUY": "🟢",
    "HOLD": "⚪",
    "SELL": "🔴",
    "STRONG_SELL": "🔴🔴",
}

SIGNAL_LABEL_TR = {
    "STRONG_BUY": "GÜÇLÜ AL",
    "BUY": "AL",
    "HOLD": "BEKLE",
    "SELL": "SAT",
    "STRONG_SELL": "GÜÇLÜ SAT",
}


async def send_telegram_message(
    bot_token: str,
    chat_id: str,
    text: str,
) -> Dict[str, Any]:
    """
    Send a single HTML-formatted message. Returns a result dict
    {"ok": bool, "error": Optional[str]}.
    """
    if not bot_token or not chat_id:
        return {"ok": False, "error": "Bot token veya chat id eksik."}

    url = f"{TELEGRAM_API}/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            data = resp.json()
            if not data.get("ok"):
                desc = data.get("description", "Bilinmeyen hata")
                logger.warning("Telegram send failed: %s", desc)
                return {"ok": False, "error": desc}
            return {"ok": True, "error": None}
    except Exception as exc:
        logger.error("Telegram request error: %s", exc)
        return {"ok": False, "error": str(exc)}


def format_signal_message(
    symbol: str,
    signal_type: str,
    confidence: float,
    direction: str,
    entry_low: Optional[float],
    entry_high: Optional[float],
    stop_loss: Optional[float],
    tp1: Optional[float],
    tp2: Optional[float],
    timeframe: str,
    risk_level: str,
) -> str:
    """Build a rich HTML message for a generated signal."""
    emoji = SIGNAL_EMOJI.get(signal_type, "⚪")
    label = SIGNAL_LABEL_TR.get(signal_type, signal_type)

    def fmt(v: Optional[float]) -> str:
        return f"{v:,.4f}".rstrip("0").rstrip(".") if v is not None else "—"

    lines = [
        f"{emoji} <b>{symbol}</b> · <b>{label}</b>",
        f"⏱ Zaman dilimi: {timeframe}  |  🎯 Güven: <b>%{confidence:.1f}</b>",
        "",
        f"📥 Giriş: <code>{fmt(entry_low)} – {fmt(entry_high)}</code>",
        f"🛑 Stop-Loss: <code>{fmt(stop_loss)}</code>",
        f"✅ TP1: <code>{fmt(tp1)}</code>",
        f"✅ TP2: <code>{fmt(tp2)}</code>",
        f"⚠️ Risk: {risk_level}",
        "",
        "<i>TradeMinds AI</i>",
    ]
    return "\n".join(lines)
