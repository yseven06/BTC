"""
TradeMinds AI – Explanation Generator

Generates detailed, structured explanations in Turkish and English, translating
technical metrics, market structures, and support/resistance zones into readable insights.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.engines.base import EngineResult, SignalBias
from app.engines.ai_decision.signal_generator import GeneratedSignalData

logger = logging.getLogger(__name__)


def generate_explanation(
    signal: GeneratedSignalData,
    results: List[EngineResult],
    asset_type: str = "crypto",
) -> Dict[str, str]:
    """Compile comprehensive analysis explanation in both Turkish and English."""
    results_map = {r.engine_name: r for r in results}

    # Extract sub-engine results
    tech_res = results_map.get("technical_analysis")
    ms_res = results_map.get("market_structure")
    smc_res = results_map.get("smart_money_concepts")
    crt_res = results_map.get("candle_range_theory")
    vol_res = results_map.get("volume_analysis")
    risk_res = results_map.get("risk_management")
    fund_res = results_map.get("fundamental_analysis")

    # ═══════════════════════════════════════════════════════════════════════════
    # TURKISH EXPLANATION GENERATOR
    # ═══════════════════════════════════════════════════════════════════════════
    tr_paragraphs = []

    # 1. Summary
    if signal.direction == "bullish":
        sig_str = "AL (BUY)" if signal.signal_type == "BUY" else "GÜÇLÜ AL (STRONG BUY)"
        tr_summary = (
            f"Analiz motorlarımız {signal.confidence_score}% güven oranı ile {sig_str} sinyali üretmiştir. "
            f"Fiyat yapısı ve hacim göstergeleri yükseliş yönündeki momentumu desteklemekte olup, "
            f"fiyatın iskontolu bölgeden tepki alarak yukarı yönlü bir hareket başlatması beklenmektedir."
        )
    elif signal.direction == "bearish":
        sig_str = "SAT (SELL)" if signal.signal_type == "SELL" else "GÜÇLÜ SAT (STRONG SELL)"
        tr_summary = (
            f"Analiz motorlarımız {signal.confidence_score}% güven oranı ile {sig_str} sinyali üretmiştir. "
            f"Satış baskısı ve piyasa yapısındaki kırılımlar düşüş trendini teyit etmekte olup, "
            f"belirlenen direnç seviyelerinden aşağı yönlü tepkiler gelmesi muhtemeldir."
        )
    else:
        tr_summary = (
            "Piyasa yapısındaki kararsızlık ve indikatörlerin nötr duruşu sebebiyle sistemimiz BEKLE (HOLD) "
            "konumunu korumaktadır. Aktif bir pozisyon açılması riskli görülmektedir."
        )
    tr_paragraphs.append(f"### Özet Analiz\n{tr_summary}")

    # 2. Supporting/Conflicting Factors
    tr_factors = ["### Destekleyici ve Kısıtlayıcı Unsurlar"]
    for res in results:
        bias_tr = _translate_bias_tr(res.bias)
        findings = ", ".join(res.key_findings[:2])
        tr_factors.append(f"- **{_translate_engine_name_tr(res.engine_name)}**: {bias_tr} (Skor: {res.score:.1f}) — *{findings}*")
    tr_paragraphs.append("\n".join(tr_factors))

    # 3. Market Structure & Volume
    tr_struct_parts = ["### Piyasa Yapısı ve Hacim Yorumu"]
    if ms_res:
        trend = ms_res.supporting_data.get("current_trend", "neutral")
        trend_tr = "Yükseliş Trendi (Uptrend)" if trend == "uptrend" else "Düşüş Trendi (Downtrend)" if trend == "downtrend" else "Yatay Bant (Range)"
        tr_struct_parts.append(f"- **Trend Yapısı**: Piyasa şu anda `{trend_tr}` yapısı sergilemektedir.")
        if ms_res.supporting_data.get("nearest_support") and ms_res.supporting_data.get("nearest_resistance"):
            sup = ms_res.supporting_data["nearest_support"]
            res_val = ms_res.supporting_data["nearest_resistance"]
            tr_struct_parts.append(f"- **S/R Seviyeleri**: En yakın destek seviyesi `{sup:.4f}`, en yakın direnç seviyesi ise `{res_val:.4f}` olarak belirlenmiştir.")

    if vol_res:
        ratio = vol_res.supporting_data.get("volume_trend_ratio", 1.0)
        poc = vol_res.supporting_data.get("volume_profile", {}).get("poc_price", 0.0)
        tr_struct_parts.append(f"- **Hacim Profili**: Mevcut hacim ortalamanın `{ratio:.1f}x` katıdır. Yoğun işlem bölgesi (Point of Control) `{poc:.4f}` seviyesindedir.")
    tr_paragraphs.append("\n".join(tr_struct_parts))

    # 4. SMC / CRT Concepts
    tr_smc_parts = ["### Smart Money (SMC) ve Candle Range (CRT) Analizi"]
    if smc_res:
        pd_zone = smc_res.supporting_data.get("premium_discount", {}).get("current_zone", "equilibrium")
        pd_zone_tr = "İskonto (Discount - Alım)" if pd_zone == "discount" else "Premium (Satış)" if pd_zone == "premium" else "Denge (Equilibrium)"
        tr_smc_parts.append(f"- **Değer Bölgesi**: Fiyat şu anda `{pd_zone_tr}` bölgesindedir.")
        
        bull_ob = smc_res.supporting_data.get("unmitigated_bullish_ob_count", 0)
        bear_ob = smc_res.supporting_data.get("unmitigated_bearish_ob_count", 0)
        if bull_ob > 0 or bear_ob > 0:
            tr_smc_parts.append(f"- **Emir Blokları (Order Blocks)**: Test edilmemiş `{bull_ob}` adet Alıcı, `{bear_ob}` adet Satıcı bloğu tespit edilmiştir.")

    if crt_res:
        sweeps = crt_res.supporting_data.get("sweeps_count", 0)
        if sweeps > 0:
            tr_smc_parts.append(f"- **Likidite Temizliği**: Son barlarda `{sweeps}` adet likidite süpürme (sweep) hareketi teyit edilmiştir.")
    tr_paragraphs.append("\n".join(tr_smc_parts))

    # 5. Risk Assessment & Trade Plan
    tr_risk_parts = ["### Risk Değerlendirmesi ve İşlem Planı"]
    tr_risk_parts.append(f"- **Risk Seviyesi**: `{signal.risk_level.upper()}` (Skor: {signal.risk_score}/10)")
    if risk_res:
        pos_size = risk_res.supporting_data.get("recommended_position_pct", 2.0)
        tr_risk_parts.append(f"- **Önerilen Pozisyon Büyüklüğü**: Portföyün en fazla `% {pos_size:.1f}` oranı ile işleme girilmesi tavsiye edilir.")
    
    if signal.direction != "neutral":
        tr_risk_parts.append(f"- **Giriş Bölgesi**: `{signal.entry_zone_low:.4f} – {signal.entry_zone_high:.4f}`")
        tr_risk_parts.append(f"- **Zarar Kes (Stop Loss)**: `{signal.stop_loss:.4f}`")
        tr_risk_parts.append(f"- **Hedefler (Take Profit)**: Hedef 1: `{signal.tp1:.4f}` | Hedef 2: `{signal.tp2:.4f}` | Hedef 3: `{signal.tp3:.4f}`")
        tr_risk_parts.append(f"- **Geçersizlik Şartları**: {signal.invalidation_conditions}")
    else:
        tr_risk_parts.append("- **İşlem Planı**: Aktif sinyal bulunmadığı için aktif zarar kes veya kar al seviyeleri tanımlanmamıştır.")
    tr_paragraphs.append("\n".join(tr_risk_parts))

    # Join Turkish explanation
    explanation_tr = "\n\n".join(tr_paragraphs)

    # ═══════════════════════════════════════════════════════════════════════════
    # ENGLISH EXPLANATION GENERATOR
    # ═══════════════════════════════════════════════════════════════════════════
    en_paragraphs = []

    # 1. Summary
    if signal.direction == "bullish":
        sig_str = "BUY" if signal.signal_type == "BUY" else "STRONG BUY"
        en_summary = (
            f"Our analysis engines have generated a {sig_str} signal with a confidence score of {signal.confidence_score}%. "
            f"Price action and volume indicators strongly support upward momentum, indicating the asset is reacting "
            f"positively off a discount zone and is poised for an upward correction."
        )
    elif signal.direction == "bearish":
        sig_str = "SELL" if signal.signal_type == "SELL" else "STRONG SELL"
        en_summary = (
            f"Our analysis engines have generated a {sig_str} signal with a confidence score of {signal.confidence_score}%. "
            f"Selling pressure and structural market shifts confirm a bearish trend, suggesting potential continuation "
            f"downwards after retesting nearby resistance levels."
        )
    else:
        en_summary = (
            "Due to market uncertainty and neutral indicator readings, our system remains on a HOLD stance. "
            "Opening active trades on this asset is currently deemed high-risk."
        )
    en_paragraphs.append(f"### Summary Analysis\n{en_summary}")

    # 2. Supporting/Conflicting Factors
    en_factors = ["### Key Supporting and Conflicting Factors"]
    for res in results:
        bias_en = res.bias.value.replace("_", " ").upper()
        findings = ", ".join(res.key_findings[:2])
        en_factors.append(f"- **{res.engine_name.replace('_', ' ').title()}**: {bias_en} (Score: {res.score:.1f}) — *{findings}*")
    en_paragraphs.append("\n".join(en_factors))

    # 3. Market Structure & Volume
    en_struct_parts = ["### Market Structure & Volume Interpretation"]
    if ms_res:
        trend = ms_res.supporting_data.get("current_trend", "neutral")
        trend_en = trend.upper()
        en_struct_parts.append(f"- **Trend Structure**: The market currently exhibits a `{trend_en}` structure.")
        if ms_res.supporting_data.get("nearest_support") and ms_res.supporting_data.get("nearest_resistance"):
            sup = ms_res.supporting_data["nearest_support"]
            res_val = ms_res.supporting_data["nearest_resistance"]
            en_struct_parts.append(f"- **S/R Boundaries**: Nearest support is identified at `{sup:.4f}`, and resistance is at `{res_val:.4f}`.")

    if vol_res:
        ratio = vol_res.supporting_data.get("volume_trend_ratio", 1.0)
        poc = vol_res.supporting_data.get("volume_profile", {}).get("poc_price", 0.0)
        en_struct_parts.append(f"- **Volume Profile**: Current trading volume is `{ratio:.1f}x` average. Point of Control (POC) rests at `{poc:.4f}`.")
    en_paragraphs.append("\n".join(en_struct_parts))

    # 4. SMC / CRT Concepts
    en_smc_parts = ["### Smart Money Concepts (SMC) & Candle Range Theory (CRT)"]
    if smc_res:
        pd_zone = smc_res.supporting_data.get("premium_discount", {}).get("current_zone", "equilibrium")
        en_smc_parts.append(f"- **Value Zone**: Price is trading inside the `{pd_zone.upper()}` zone.")
        
        bull_ob = smc_res.supporting_data.get("unmitigated_bullish_ob_count", 0)
        bear_ob = smc_res.supporting_data.get("unmitigated_bearish_ob_count", 0)
        if bull_ob > 0 or bear_ob > 0:
            en_smc_parts.append(f"- **Order Blocks**: Found `{bull_ob}` unmitigated Bullish OB(s) and `{bear_ob}` Bearish OB(s).")

    if crt_res:
        sweeps = crt_res.supporting_data.get("sweeps_count", 0)
        if sweeps > 0:
            en_smc_parts.append(f"- **Liquidity Sweeps**: Confirmed `{sweeps}` liquidity sweep(s) in recent candles.")
    en_paragraphs.append("\n".join(en_smc_parts))

    # 5. Risk Assessment & Trade Plan
    en_risk_parts = ["### Risk Assessment & Trade Plan"]
    en_risk_parts.append(f"- **Risk Level**: `{signal.risk_level.upper()}` (Score: {signal.risk_score}/10)")
    if risk_res:
        pos_size = risk_res.supporting_data.get("recommended_position_pct", 2.0)
        en_risk_parts.append(f"- **Recommended Sizing**: We recommend allocating no more than `{pos_size:.1f}%` of your trading balance to this setup.")
    
    if signal.direction != "neutral":
        en_risk_parts.append(f"- **Entry Zone**: `{signal.entry_zone_low:.4f} – {signal.entry_zone_high:.4f}`")
        en_risk_parts.append(f"- **Stop Loss**: `{signal.stop_loss:.4f}`")
        en_risk_parts.append(f"- **Targets**: Target 1: `{signal.tp1:.4f}` | Target 2: `{signal.tp2:.4f}` | Target 3: `{signal.tp3:.4f}`")
        en_risk_parts.append(f"- **Invalidation Details**: {signal.invalidation_conditions.replace('zarar kes', 'stop loss').replace('kar al', 'take profit')}")
    else:
        en_risk_parts.append("- **Trade Plan**: No active levels established due to neutral market stance.")
    en_paragraphs.append("\n".join(en_risk_parts))

    # Join English explanation
    explanation_en = "\n\n".join(en_paragraphs)

    return {
        "tr": explanation_tr,
        "en": explanation_en,
    }


# Helper translator helpers
def _translate_bias_tr(bias: SignalBias) -> str:
    mapping = {
        SignalBias.STRONG_BULLISH: "Güçlü Boğa (Alım)",
        SignalBias.BULLISH: "Boğa (Alım)",
        SignalBias.NEUTRAL: "Nötr (Bekle)",
        SignalBias.BEARISH: "Ayı (Satım)",
        SignalBias.STRONG_BEARISH: "Güçlü Ayı (Satım)",
    }
    return mapping.get(bias, "Nötr")


def _translate_engine_name_tr(name: str) -> str:
    mapping = {
        "technical_analysis": "Teknik Analiz Motoru",
        "market_structure": "Piyasa Yapısı Motoru",
        "smart_money_concepts": "Smart Money (SMC) Motoru",
        "candle_range_theory": "Mum Aralığı (CRT) Motoru",
        "volume_analysis": "Hacim Analiz Motoru",
        "risk_management": "Risk Yönetimi Motoru",
        "fundamental_analysis": "Temel Analiz Motoru",
    }
    return mapping.get(name, name.replace("_", " ").title())

