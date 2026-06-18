"""
TradeMinds AI – On-Chain Analysis Engine

Analyzes blockchain and market sentiment metrics that price action alone
cannot reveal:

  * Fear & Greed Index — contrarian indicator (extreme fear = buy, extreme greed = sell)
  * BTC network activity — hash rate, mempool congestion, transaction volume
  * Coin metadata — distance from ATH, dev/community scores, supply pressure

Only applies to crypto. Stocks return a neutral result without external calls.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.engines.base import BaseEngine, EngineResult, SignalBias
from app.collectors.onchain_collector import OnchainCollector, symbol_to_gecko_id

logger = logging.getLogger(__name__)


class OnchainEngine(BaseEngine):
    """On-Chain & Sentiment Analysis Engine.

    Weight: 0.10 (10 % of composite score).

    Scoring (0-100, 50 = neutral):
      + Extreme fear         → +15 (contrarian buy)
      + Distance below ATH   → up to +10 (mean-reversion potential)
      + Healthy hash rate    → +5  (network secure)
      + Low mempool fees     → +5  (low congestion, smooth onboarding)
      + High dev score       → +5  (active development)
      - Extreme greed        → -15
      - Above ATH            → -10
      - Severe congestion    → -5
    """

    @property
    def name(self) -> str:
        return "onchain_analysis"

    @property
    def weight(self) -> float:
        return 0.10

    async def analyze(
        self,
        symbol: str,
        timeframe: str,
        ohlcv_data: Any,
        **kwargs: Any,
    ) -> EngineResult:
        warnings: List[str] = []
        asset_type = kwargs.get("asset_type", "crypto")
        findings: List[str] = []
        supporting: Dict[str, Any] = {"asset_type": asset_type}

        # Try to extract data from kwargs
        is_backtest = kwargs.get("is_backtest", False)

        # ── Stocks: no on-chain data → neutral result ──
        if asset_type == "stock":
            return EngineResult(
                engine_name=self.name,
                score=50.0,
                bias=SignalBias.NEUTRAL,
                confidence=20.0,
                key_findings=["Hisse senedi varlığı — on-chain analiz uygulanamaz."],
                supporting_data=supporting,
                warnings=["On-chain analiz sadece kripto varlıklar için geçerlidir."],
            )

        if is_backtest:
            return EngineResult(
                engine_name=self.name,
                score=50.0,
                bias=SignalBias.NEUTRAL,
                confidence=50.0,
                key_findings=["Backtest modu: On-chain verileri simüle edildi."],
                supporting_data=supporting,
                warnings=[],
            )

        score = 50.0
        score_components = 0   # count of components that contributed

        collector = OnchainCollector()
        try:
            fng_data = await collector.fetch_fear_greed()
            btc_net  = await collector.fetch_btc_network()

            gecko_id = symbol_to_gecko_id(symbol)
            coin_meta = await collector.fetch_coin_metadata(gecko_id) if gecko_id else {}
        finally:
            await collector.close()

        # ── 1. Fear & Greed (contrarian) ─────────────────────────────────────
        fng = fng_data.get("value")
        if fng is not None:
            supporting["fear_greed_value"] = fng
            supporting["fear_greed_classification"] = fng_data.get("classification")
            if fng <= 20:
                score += 15
                findings.append(f"Piyasa aşırı korkuda (F&G={fng}) — contrarian alım fırsatı.")
            elif fng <= 40:
                score += 5
                findings.append(f"Piyasa korkuda (F&G={fng}) — temkinli pozitif.")
            elif fng >= 80:
                score -= 15
                findings.append(f"Piyasa aşırı açgözlülükte (F&G={fng}) — düzeltme riski yüksek.")
            elif fng >= 60:
                score -= 5
                findings.append(f"Piyasa açgözlülükte (F&G={fng}) — dikkat.")
            else:
                findings.append(f"Piyasa nötr (F&G={fng}).")
            score_components += 1
        else:
            warnings.append("Fear & Greed verisi alınamadı.")

        # ── 2. ATH distance (mean reversion potential) ───────────────────────
        ath_dist = coin_meta.get("ath_distance_pct")
        if ath_dist is not None:
            supporting["ath_distance_pct"] = round(ath_dist, 2)
            if ath_dist <= -70:
                score += 10
                findings.append(f"ATH'ın %{abs(ath_dist):.0f} altında — yüksek ortalamaya dönüş potansiyeli.")
            elif ath_dist <= -40:
                score += 5
                findings.append(f"ATH'ın %{abs(ath_dist):.0f} altında — birikim bölgesinde.")
            elif ath_dist >= -5:
                score -= 10
                findings.append("Fiyat ATH'a çok yakın — düzeltme riski.")
            score_components += 1

        # ── 3. BTC network health (only for BTC) ─────────────────────────────
        if symbol.upper().startswith("BTC"):
            hash_rate = btc_net.get("hash_rate_ths")
            if hash_rate:
                supporting["btc_hash_rate_ths"] = hash_rate
                # Healthy hash rate above historic baseline (~500M TH/s in 2024+)
                if hash_rate > 500_000_000:
                    score += 5
                    findings.append("BTC hash rate güçlü — ağ güvenliği yüksek.")
                score_components += 1

            fee = btc_net.get("fast_fee_sat_vb")
            if fee is not None:
                supporting["btc_fast_fee_sat_vb"] = fee
                if fee <= 10:
                    score += 5
                    findings.append(f"BTC mempool sakin (ücret={fee} sat/vB) — düşük tıkanıklık.")
                elif fee >= 100:
                    score -= 5
                    findings.append(f"BTC mempool tıkalı (ücret={fee} sat/vB) — yüksek aktivite.")
                score_components += 1

        # ── 4. Developer & community activity ────────────────────────────────
        dev_score = coin_meta.get("developer_score")
        com_score = coin_meta.get("community_score")
        if dev_score is not None:
            supporting["developer_score"] = round(dev_score, 1)
            if dev_score >= 70:
                score += 5
                findings.append(f"Geliştirici aktivitesi güçlü (skor: {dev_score:.0f}).")
            score_components += 1
        if com_score is not None:
            supporting["community_score"] = round(com_score, 1)

        # ── 5. Market cap rank ───────────────────────────────────────────────
        rank = coin_meta.get("market_cap_rank")
        if rank is not None:
            supporting["market_cap_rank"] = rank
            findings.append(f"Piyasa değeri sıralaması: #{rank}")

        # ── Finalize ─────────────────────────────────────────────────────────
        score = max(0.0, min(100.0, score))
        bias = self._score_to_bias(score)

        # Confidence based on how much data we got
        if score_components == 0:
            confidence = 20.0
            warnings.append("Hiçbir on-chain veri alınamadı.")
        else:
            confidence = min(40 + score_components * 12, 90)

        if not findings:
            findings.append("On-chain veriler nötr.")

        return EngineResult(
            engine_name=self.name,
            score=round(score, 2),
            bias=bias,
            confidence=round(confidence, 2),
            key_findings=findings,
            supporting_data=supporting,
            warnings=warnings,
        )

    @staticmethod
    def _score_to_bias(score: float) -> SignalBias:
        if score >= 75: return SignalBias.STRONG_BULLISH
        if score >= 58: return SignalBias.BULLISH
        if score <= 25: return SignalBias.STRONG_BEARISH
        if score <= 42: return SignalBias.BEARISH
        return SignalBias.NEUTRAL
