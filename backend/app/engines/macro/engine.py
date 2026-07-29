"""
Zate Trade – Macro Analysis Engine

Looks at the broader economic backdrop that affects every asset:

  • TR assets   → TCMB FX (USD/TRY, EUR/TRY) — strong lira ⇒ bullish for BIST
  • US assets   → Fed Funds Rate, 10Y yield, USD broad index, CPI
  • Crypto      → US macro stance (risk on / risk off via Fed Funds)

When FRED is not configured (no API key), the US side returns neutral and
confidence drops accordingly so the engine still works on TR assets.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.engines.base import BaseEngine, EngineResult, SignalBias
from app.collectors.macro_collector import MacroCollector
from app.services.dependency_health import (
    CONFIDENCE_SEMANTICS,
    NOT_APPLICABLE,
    NOT_CONFIGURED,
    engine_entry,
    worst_status,
)

logger = logging.getLogger(__name__)


class MacroEngine(BaseEngine):
    """Macro/global context engine. Weight: 0.05 (5 % of composite)."""

    @property
    def name(self) -> str:
        return "macro_analysis"

    @property
    def weight(self) -> float:
        return 0.05

    async def analyze(
        self,
        symbol: str,
        timeframe: str,
        ohlcv_data: Any,
        **kwargs: Any,
    ) -> EngineResult:
        asset_type: str = kwargs.get("asset_type", "crypto")
        findings: List[str] = []
        supporting: Dict[str, Any] = {"asset_type": asset_type}
        warnings: List[str] = []

        # CP-DEP-HEALTH-1 — cleared per run so a previous scan's state can never
        # be reported as this one's. Read only by the orchestrator, for telemetry.
        self._dependency_health = None

        is_backtest = kwargs.get("is_backtest", False)
        if is_backtest:
            self._record_health(
                configured=None, statuses={}, components=0, expected=0,
                fallback_reason="backtest_simulated", overall=NOT_APPLICABLE)
            return EngineResult(
                engine_name=self.name,
                score=50.0,
                bias=SignalBias.NEUTRAL,
                confidence=50.0,
                key_findings=["Backtest modu: Makro veriler simüle edildi."],
                supporting_data=supporting,
                warnings=[],
            )

        score = 50.0
        components = 0

        collector = MacroCollector()
        try:
            us_macro = await collector.fetch_us_macro_snapshot()
            usd_try  = None
            if asset_type == "stock" or symbol.upper().endswith(".IS"):
                usd_try = await collector.fetch_tcmb_usd_try()
        finally:
            await collector.close()

        # ── US Macro (impacts crypto and US stocks) ──────────────────────────
        if us_macro["configured"]:
            ff  = us_macro["fed_funds_rate"]
            y10 = us_macro["ten_year_yield"]
            supporting["fed_funds_rate"] = ff
            supporting["ten_year_yield"] = y10

            if ff is not None:
                # Tight policy = risk-off; easy policy = risk-on
                if ff >= 5.0:
                    score -= 10
                    findings.append(f"FED faizi yüksek (%{ff:.2f}) — risk-off ortam.")
                elif ff <= 2.0:
                    score += 10
                    findings.append(f"FED faizi düşük (%{ff:.2f}) — risk-on ortam.")
                else:
                    findings.append(f"FED faizi nötr seviyede (%{ff:.2f}).")
                components += 1

            if y10 is not None:
                supporting["ten_year_yield"] = y10
                if y10 >= 5.0:
                    score -= 5
                    findings.append(f"10Y tahvil getirisi yüksek (%{y10:.2f}) — risk varlıkları için baskı.")
                elif y10 <= 3.0:
                    score += 5
                components += 1
        else:
            warnings.append("FRED API key tanımlı değil — US makro veri alınamadı.")

        # ── TCMB FX (BIST stocks) ────────────────────────────────────────────
        if usd_try is not None:
            supporting["usd_try"] = usd_try
            findings.append(f"USD/TRY: {usd_try:.2f}")
            components += 1
            # Note: We don't bias score by USD/TRY level alone — it's contextual.
            # Frontend can use this for display purposes.

        # ── Finalize ─────────────────────────────────────────────────────────
        score = max(0.0, min(100.0, score))
        bias = self._score_to_bias(score)

        if components == 0:
            confidence = 25.0
            warnings.append("Makro veriler alınamadı, nötr varsayıldı.")
        else:
            confidence = min(40 + components * 15, 85)

        if not findings:
            findings.append("Makro çerçeve nötr.")

        # CP-DEP-HEALTH-1 — record WHY this engine ended where it did. Placed
        # after every branch above has run and before the result is built, so it
        # observes the finished state without being able to influence it.
        # `components` is the same local the confidence expression above used.
        self._record_health(
            configured=bool(us_macro.get("configured")),
            statuses=getattr(collector, "last_status", {}) or {},
            components=components,
            # Crypto consults exactly two FRED series (fed funds, 10Y). A TR
            # asset adds the TCMB leg, which is the only other component that
            # can increment the counter.
            expected=3 if (asset_type == "stock" or symbol.upper().endswith(".IS")) else 2,
            fallback_reason=(
                "no_api_key" if not us_macro.get("configured")
                else ("no_data" if components == 0 else None)
            ),
        )

        return EngineResult(
            engine_name=self.name,
            score=round(score, 2),
            bias=bias,
            confidence=round(confidence, 2),
            key_findings=findings,
            supporting_data=supporting,
            warnings=warnings,
        )

    def _record_health(self, *, configured, statuses, components, expected,
                       fallback_reason, overall=None) -> None:
        """Stash this run's dependency health on the instance. Never raises.

        The orchestrator reads it off the engine object rather than off
        `EngineResult`, deliberately: `decision["engine_results"]` is dumped
        straight into `signals.engines_data` and served by `/api/reports`, so a
        new EngineResult field would change a public payload. This channel
        cannot reach it. A fresh `AIDecisionEngine()` — and therefore a fresh
        engine instance — is constructed per scan, so there is no shared state.
        """
        try:
            per_call = {k: v.get("fetch_status") for k, v in statuses.items()}
            self._dependency_health = engine_entry(
                configured=configured,
                fetch_status=overall or (
                    worst_status(per_call.values()) if per_call else NOT_CONFIGURED),
                fallback_used=bool(fallback_reason),
                fallback_reason=fallback_reason,
                input_completeness=components,
                input_expected=expected,
                served_from_cache=any(v.get("served_from_cache") for v in statuses.values()),
                data_freshness_s=max(
                    (v.get("data_freshness_s") or 0.0) for v in statuses.values()
                ) if statuses else None,
                confidence_semantic_type=CONFIDENCE_SEMANTICS.get(self.name, "unknown"),
                components=per_call or None,
            )
        except Exception as exc:  # noqa: BLE001 — telemetry may never decide
            logger.debug("[MacroEngine] dependency health not recorded: %s", exc)
            self._dependency_health = None

    @staticmethod
    def _score_to_bias(score: float) -> SignalBias:
        if score >= 70: return SignalBias.STRONG_BULLISH
        if score >= 55: return SignalBias.BULLISH
        if score <= 30: return SignalBias.STRONG_BEARISH
        if score <= 45: return SignalBias.BEARISH
        return SignalBias.NEUTRAL
