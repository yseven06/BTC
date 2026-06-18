"""
TradeMinds AI – PDF Report Generator

Produces a clean, branded PDF for a single signal: header, levels, scores,
engine breakdown, and explanation. Uses ReportLab — zero external services.
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
)
from reportlab.pdfgen.canvas import Canvas

# ── Brand colors (mirror frontend palette) ────────────────────────────────────
BG_DARK     = colors.HexColor("#0b1020")
PANEL       = colors.HexColor("#161b2e")
ACCENT      = colors.HexColor("#f97316")     # orange
ACCENT_2    = colors.HexColor("#8b5cf6")     # purple
BULLISH     = colors.HexColor("#00e676")
BEARISH     = colors.HexColor("#ff5252")
TEXT_DIM    = colors.HexColor("#94a3b8")
TEXT_MAIN   = colors.HexColor("#f8fafc")


def _styles() -> Dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title":   ParagraphStyle("title",   parent=base["Heading1"], fontSize=22, textColor=ACCENT, spaceAfter=4),
        "subtitle":ParagraphStyle("subtitle",parent=base["Normal"],   fontSize=10, textColor=TEXT_DIM),
        "h2":      ParagraphStyle("h2",      parent=base["Heading2"], fontSize=12, textColor=TEXT_MAIN, spaceBefore=14, spaceAfter=6),
        "body":    ParagraphStyle("body",    parent=base["Normal"],   fontSize=10, textColor=TEXT_MAIN, leading=14),
        "muted":   ParagraphStyle("muted",   parent=base["Normal"],   fontSize=9,  textColor=TEXT_DIM),
        "mono":    ParagraphStyle("mono",    parent=base["Normal"],   fontSize=10, textColor=TEXT_MAIN, fontName="Courier-Bold"),
    }


def _page_decoration(canvas: Canvas, _doc) -> None:
    """Dark background + footer on every page."""
    w, h = A4
    canvas.saveState()
    # Full-page dark background
    canvas.setFillColor(BG_DARK)
    canvas.rect(0, 0, w, h, stroke=0, fill=1)
    # Brand strip top
    canvas.setFillColor(ACCENT)
    canvas.rect(0, h - 0.4 * cm, w, 0.4 * cm, stroke=0, fill=1)
    # Footer
    canvas.setFillColor(TEXT_DIM)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(2 * cm, 1 * cm, "TradeMinds AI · Otomatik üretilmiş analiz raporu")
    canvas.drawRightString(w - 2 * cm, 1 * cm, f"Sayfa {canvas.getPageNumber()}")
    canvas.restoreState()


def _kv_table(rows: List[List[Any]]) -> Table:
    t = Table(rows, colWidths=[5.5 * cm, 10 * cm])
    t.setStyle(TableStyle([
        ("FONT",        (0, 0), (-1, -1), "Helvetica", 10),
        ("TEXTCOLOR",   (0, 0), (0, -1), TEXT_DIM),
        ("TEXTCOLOR",   (1, 0), (1, -1), TEXT_MAIN),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS",(0, 0), (-1, -1), [PANEL, BG_DARK]),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",(0, 0), (-1, -1), 10),
        ("TOPPADDING",  (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 6),
    ]))
    return t


def _badge(text: str, color) -> Paragraph:
    return Paragraph(
        f'<para backColor="{color.hexval()}" textColor="#FFFFFF" '
        f'leftIndent="6" rightIndent="6" spaceBefore="2" spaceAfter="2">'
        f'<b>{text}</b></para>',
        ParagraphStyle("badge", fontSize=9),
    )


def _fmt_num(value: Any, dec: int = 2) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):,.{dec}f}".replace(",", " ")
    except Exception:
        return str(value)


def generate_signal_pdf(signal: Dict[str, Any]) -> bytes:
    """
    Generate a PDF report for a single signal.

    `signal` mirrors SignalDetailResponse:
      symbol, asset_name, signal_type, direction, confidence_score,
      probability_score, risk_level, entry_zone_low/high, stop_loss,
      tp1/tp2/tp3, explanation_tr, engines_data, generated_at, timeframe.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=1.6 * cm, bottomMargin=1.6 * cm,
    )
    S = _styles()
    story: List[Any] = []

    symbol = signal.get("symbol") or signal.get("asset", {}).get("symbol", "—")
    name   = signal.get("asset_name") or signal.get("asset", {}).get("name", "")
    tf     = signal.get("timeframe") or "1h"
    direction = (signal.get("direction") or "neutral").upper()
    sig_type  = (signal.get("signal_type") or "HOLD").upper()
    is_long   = direction == "BULLISH"

    # ── Header ──
    story.append(Paragraph(f"AI Sinyal Raporu — {symbol}", S["title"]))
    story.append(Paragraph(
        f"{name} · {tf} · {datetime.utcnow().strftime('%d.%m.%Y %H:%M')} UTC",
        S["subtitle"],
    ))
    story.append(Spacer(1, 14))

    # ── Badges row ──
    dir_badge = _badge(f"{'LONG' if is_long else 'SHORT'}", BULLISH if is_long else BEARISH)
    type_badge = _badge(sig_type.replace("_", " "), ACCENT)
    risk_badge = _badge(f"Risk: {(signal.get('risk_level') or 'medium').upper()}", ACCENT_2)
    story.append(Table(
        [[dir_badge, type_badge, risk_badge]],
        colWidths=[5 * cm, 5 * cm, 5 * cm],
        style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), BG_DARK)]),
    ))
    story.append(Spacer(1, 12))

    # ── Scores ──
    story.append(Paragraph("Skorlar", S["h2"]))
    story.append(_kv_table([
        ["Güven Skoru",    f"{signal.get('confidence_score', 0):.1f} / 100"],
        ["Olasılık Skoru", f"{(signal.get('probability_score') or 0):.1f} / 100"],
        ["Risk Skoru",     f"{(signal.get('risk_score') or 0):.1f} / 10"],
    ]))

    # ── Levels ──
    story.append(Paragraph("Seviyeler", S["h2"]))
    story.append(_kv_table([
        ["Giriş Bölgesi", f"{_fmt_num(signal.get('entry_zone_low'))} – {_fmt_num(signal.get('entry_zone_high'))}"],
        ["Zarar Durdur (SL)", _fmt_num(signal.get('stop_loss'))],
        ["Hedef 1 (TP1)", _fmt_num(signal.get('tp1'))],
        ["Hedef 2 (TP2)", _fmt_num(signal.get('tp2'))],
        ["Hedef 3 (TP3)", _fmt_num(signal.get('tp3'))],
    ]))

    # ── Engine breakdown ──
    engines = signal.get("engines_data") or signal.get("engine_results") or {}
    if engines:
        story.append(Paragraph("Motor Analizleri", S["h2"]))
        rows: List[List[Any]] = [["MOTOR", "SKOR", "EĞİLİM", "GÜVEN"]]
        # engines is either dict-of-results or list of results
        items: List[Dict[str, Any]] = []
        if isinstance(engines, dict):
            items = list(engines.values())
        elif isinstance(engines, list):
            items = engines
        for e in items:
            if not isinstance(e, dict):
                continue
            rows.append([
                (e.get("engine_name") or e.get("name") or "—").replace("_", " ").title(),
                f"{e.get('score', 0):.1f}",
                str(e.get("bias", "")).upper().replace("_", " "),
                f"{e.get('confidence', 0):.0f}%",
            ])
        if len(rows) > 1:
            t = Table(rows, colWidths=[6 * cm, 3 * cm, 3.5 * cm, 3 * cm])
            t.setStyle(TableStyle([
                ("FONT",        (0, 0), (-1, -1), "Helvetica", 9),
                ("BACKGROUND",  (0, 0), (-1, 0),  ACCENT),
                ("TEXTCOLOR",   (0, 0), (-1, 0),  colors.white),
                ("ROWBACKGROUNDS",(0, 1), (-1, -1), [PANEL, BG_DARK]),
                ("TEXTCOLOR",   (0, 1), (-1, -1), TEXT_MAIN),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING",  (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
            ]))
            story.append(t)

    # ── Explanation ──
    expl = signal.get("explanation_tr") or signal.get("explanation_en")
    if expl:
        story.append(Paragraph("AI Açıklaması", S["h2"]))
        story.append(Paragraph(expl, S["body"]))

    # ── Disclaimer ──
    story.append(Spacer(1, 20))
    story.append(Paragraph(
        "Bu rapor yatırım tavsiyesi niteliğinde değildir. AI tarafından üretilmiş "
        "analitik bir özet olup, kullanıcı kendi sorumluluğunda işlem yapmalıdır.",
        S["muted"],
    ))

    doc.build(story, onFirstPage=_page_decoration, onLaterPages=_page_decoration)
    return buf.getvalue()


def generate_performance_pdf(stats: Dict[str, Any], symbols: List[Dict[str, Any]]) -> bytes:
    """Portfolio-style performance summary PDF."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=1.6 * cm, bottomMargin=1.6 * cm,
    )
    S = _styles()
    story: List[Any] = []

    story.append(Paragraph("Performans Özeti", S["title"]))
    story.append(Paragraph(
        f"Tüm sinyal geçmişi · {datetime.utcnow().strftime('%d.%m.%Y %H:%M')} UTC",
        S["subtitle"],
    ))
    story.append(Spacer(1, 14))

    story.append(Paragraph("Genel İstatistikler", S["h2"]))
    story.append(_kv_table([
        ["Toplam Sinyal",     str(stats.get("total_signals", 0))],
        ["Kazanılan",         str(stats.get("win_count", 0))],
        ["Kaybedilen",        str(stats.get("loss_count", 0))],
        ["Berabere",          str(stats.get("breakeven_count", 0))],
        ["Aktif",             str(stats.get("active_count", 0))],
        ["Kazanma Oranı",     f"{stats.get('win_rate', 0):.1f}%"],
        ["Ortalama Getiri",   f"{(stats.get('average_return') or 0):.2f}%"],
        ["TP1 Hit Rate",      f"{stats.get('tp1_hit_rate', 0):.1f}%"],
        ["TP2 Hit Rate",      f"{stats.get('tp2_hit_rate', 0):.1f}%"],
    ]))

    if symbols:
        story.append(Paragraph("Sembol Bazlı Performans", S["h2"]))
        rows: List[List[Any]] = [["SEMBOL", "TOPLAM", "KAZANMA %", "KALİTE"]]
        for sym in symbols[:30]:
            rows.append([
                sym.get("symbol", "—"),
                str(sym.get("total", 0)),
                f"{sym.get('win_rate', 0):.1f}%",
                f"{sym.get('quality_score', 0):.1f}/10",
            ])
        t = Table(rows, colWidths=[5 * cm, 3 * cm, 4 * cm, 4 * cm])
        t.setStyle(TableStyle([
            ("FONT",          (0, 0), (-1, -1), "Helvetica", 9),
            ("BACKGROUND",    (0, 0), (-1, 0), ACCENT),
            ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [PANEL, BG_DARK]),
            ("TEXTCOLOR",     (0, 1), (-1, -1), TEXT_MAIN),
            ("LEFTPADDING",   (0, 0), (-1, -1), 8),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(t)

    doc.build(story, onFirstPage=_page_decoration, onLaterPages=_page_decoration)
    return buf.getvalue()
