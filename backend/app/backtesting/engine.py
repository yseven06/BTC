"""
Zate Trade – Historical Backtesting Engine

Simulates walk-forward, candle-by-candle trade execution historically, tracking
portfolio values, active trades (SL, TP1/TP2/TP3, Expiration), and calculating
institutional-grade metrics (Sharpe, Sortino, Drawdowns, Expectancy).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from app.engines.ai_decision.engine import AIDecisionEngine
from app.engines.ai_decision.signal_generator import _price_round
from app.backtesting.resolution_core import (
    step_bar, new_walk_state, WalkState, resolve_inside_bar_ambiguity,
)
from app.services.candle_window import UnknownTimeframeError, closed_candles
from app.services.trade_geometry import planned_rr

logger = logging.getLogger(__name__)


def _realized_r(entry: float, sl: float, pnl_pct: float) -> Optional[float]:
    """Realized return expressed in R-multiples = realized% / risk% (risk = |entry-sl|
    as a percent of entry). None when the stop distance is zero. P11-0 observability."""
    if not entry or sl is None:
        return None
    risk_pct = abs(entry - sl) / entry * 100.0
    if risk_pct == 0:
        return None
    return round(pnl_pct / risk_pct, 4)


@dataclass
class Trade:
    """A simulated trade position."""

    id: str
    direction: str  # "bullish" (long) or "bearish" (short)
    entry_price: float
    stop_loss: float
    tp1: float
    tp2: float
    tp3: float
    risk_pct: float
    allocated_capital: float
    entry_index: int
    entry_time: str
    age: int = 0  # Number of candles held
    realized_pnl_capital: float = 0.0
    is_expired: bool = False
    # Per-bar resolution geometry (shared with the live tracker via step_bar).
    # Holds current_sl, remaining_share, hit flags, MFE/MAE, fills, etc.
    state: Optional["WalkState"] = None


# F1-B' — the contract this backtest runs under. Constants rather than literals so
# a report and a test cannot drift apart on what the run actually did.
BACKTEST_INPUT_VERSION = "closed_candle_v1"
# Features see history through the decision bar, which is itself already closed.
FEATURE_CUTOFF_POLICY = "through_previous_closed_decision_bar"
# The trade's first resolution bar is the one after the decision bar.
EXECUTION_START_POLICY = "next_closed_bar"
# Historical OHLCV has no intrabar path, so the decision bar's close is the closest
# no-lookahead stand-in for the live price production anchors on.
DECISION_PRICE_POLICY = "previous_closed_bar_close_proxy"
# Consequence of the line above: close, not a price a minute into the next candle.
PRODUCTION_INTRABAR_PARITY = "approximate"
# is_backtest=True skips the live MTF fetch and no caller supplies mtf_data, so
# mtf_trends is always empty here while production computes it from 15m/1h/4h.
MTF_PARITY = "unavailable"


def apply_backtest_bar(trade, k: int, bar, max_age: int) -> bool:
    """Advance ONE backtest trade by one candle: the shared resolution_core.step_bar
    geometry + capital-weighted fill accounting + bar-count expiry. Mutates ``trade``
    (its WalkState ``state``, ``realized_pnl_capital`` and ``is_expired``). Returns
    True once the trade is fully resolved.

    Single source of the per-bar geometry — the SAME ``step_bar`` the live tracker
    uses. Capital accounting replays ``state.fills`` in execution order with the EXACT
    same float ops as the legacy inline loop (no ULP drift). Bar-count expiry (book
    the remainder at this bar's close) is the backtest's own semantic, kept here."""
    st = trade.state
    prev = len(st.fills)
    done = step_bar(st, k, bar)
    for portion, ret in st.fills[prev:]:
        trade.realized_pnl_capital += portion * trade.allocated_capital * ret
    if not done and st.remaining_share > 0 and (k + 1) >= max_age:
        close_price = bar[3]
        ret_close = ((close_price - trade.entry_price) / trade.entry_price) if st.is_bull \
            else ((trade.entry_price - close_price) / trade.entry_price)
        trade.realized_pnl_capital += st.remaining_share * trade.allocated_capital * ret_close
        st.remaining_share = 0.0
        trade.is_expired = True
        done = True
    return done or st.remaining_share <= 0.0


@dataclass
class BacktestReport:
    """Aggregate statistics for a historical backtest run."""

    total_trades: int
    wins: int
    losses: int
    breakevens: int
    expired: int
    win_rate: float
    loss_rate: float
    profit_factor: float
    sharpe_ratio: float
    sortino_ratio: Optional[float]  # None when undefined (no/low downside variance)
    max_drawdown_pct: float
    average_return_pct: float
    average_rr: float
    expectancy_pct: float
    max_consecutive_wins: int
    max_consecutive_losses: int
    equity_curve: List[Dict[str, Any]] = field(default_factory=list)
    trades_log: List[Dict[str, Any]] = field(default_factory=list)
    # P11-0 additive observability (TP1-based R:R + per-TP reach + realized-R) — make
    # a future TP/SL/R:R change measurable before/after; existing metrics unchanged.
    avg_planned_rr_tp1: Optional[float] = None
    median_planned_rr_tp1: Optional[float] = None
    sub_1_rr_pct: Optional[float] = None
    tp1_reach_rate: float = 0.0
    tp2_reach_rate: float = 0.0
    tp3_reach_rate: float = 0.0
    avg_realized_r: Optional[float] = None
    median_realized_r: Optional[float] = None
    # F1-B' — what this run's numbers actually mean. Stated rather than assumed,
    # because "backtest PF" and "live PF" are only comparable to the degree these
    # policies match production, and three of them currently do not.
    backtest_input_version: str = BACKTEST_INPUT_VERSION
    feature_cutoff_policy: str = FEATURE_CUTOFF_POLICY
    execution_start_policy: str = EXECUTION_START_POLICY
    decision_price_policy: str = DECISION_PRICE_POLICY
    production_intrabar_parity: str = PRODUCTION_INTRABAR_PARITY
    mtf_parity: str = MTF_PARITY
    # How many trailing rows the closed-candle cut removed. Non-zero means the
    # fetch included a candle that was still forming — the run is unaffected, but
    # the number says so out loud rather than leaving it to be inferred.
    dropped_forming_bars: int = 0


class BacktestEngine:
    """Historical trading simulator."""

    def __init__(self) -> None:
        self.decision_engine = AIDecisionEngine()

    async def run_backtest(
        self,
        symbol: str,
        timeframe: str,
        df: pd.DataFrame,
        initial_capital: float = 10000.0,
        risk_pct: float = 2.0,  # 2% risk of current capital per trade
        max_age: int = 48,      # signal lifetime in WALL-CLOCK HOURS (live = fixed 48h)
        execution_model: str = "conservative",
    ) -> BacktestReport:
        """Run step-by-step backtest simulation."""
        # F1-B' — bound the dataset to bars that have definitively closed, ONCE,
        # before the walk begins.
        #
        # The decision side was already correct: bar i is closed when it is scored
        # and the trade it produces starts at i+1. What was not bounded is the far
        # end. The backtest fetches live (signals.py:1012, limit=300), so the final
        # row is usually the candle still forming, and while the `i < n - 1` guard
        # keeps it out of the FEATURES, nothing kept it out of EXECUTION: a
        # decision at i = n-2 sets entry_index = n-1, so a trade could open on a
        # partial bar and be resolved against its incomplete high/low.
        #
        # That is not feature look-ahead — it is executing against a bar that has
        # not finished happening. Cutting here fixes both, and makes the walk
        # deterministic: without it the same historical backtest could return
        # different numbers depending on what minute of the candle it was run in.
        raw_bars = len(df) if df is not None else 0
        df = closed_candles(df, timeframe)
        dropped_forming = max(0, raw_bars - len(df))

        n = len(df)
        min_bars = 60  # Require at least 60 bars of history for sub-engines to compute EMAs, etc.

        if n < min_bars + 10:
            raise ValueError(f"Insufficient history ({n} bars) for backtesting. Minimum required is {min_bars + 10} bars.")

        # KEY1-c (D3): max_age is WALL-CLOCK HOURS — the live signal lifetime is a fixed
        # 48h (timeframe-independent). Convert to a per-timeframe bar count so the backtest
        # expires at the SAME real-time horizon as live (1h: 48 bars; 4h: 12; 15m: 192).
        _TF_HOURS = {"1m": 1 / 60, "5m": 5 / 60, "15m": 0.25, "30m": 0.5,
                     "1h": 1.0, "4h": 4.0, "1d": 24.0, "1w": 168.0}
        max_age_bars = max(1, round(max_age / _TF_HOURS.get(timeframe, 1.0)))

        capital = initial_capital
        equity_curve: List[Dict[str, Any]] = []
        trades_log: List[Dict[str, Any]] = []
        active_trades: List[Trade] = []
        
        trade_counter = 0
        consecutive_wins = 0
        consecutive_losses = 0
        current_win_streak = 0
        current_loss_streak = 0
        
        wins_count = 0
        losses_count = 0
        breakevens_count = 0
        expired_count = 0

        # Open/High/Low/Close columns
        opens = df["open"].values
        highs = df["high"].values
        lows = df["low"].values
        closes = df["close"].values
        timestamps = df.index.astype(str).tolist()

        # Track peak capital for drawdown
        peak_capital = initial_capital
        max_drawdown = 0.0

        # Begin step-by-step walk-forward loop
        for i in range(min_bars, n):
            current_price = closes[i]
            current_open = opens[i]
            current_high = highs[i]
            current_low = lows[i]
            current_time = timestamps[i]

            # 1. Update Active Trades
            resolved_trades: List[Trade] = []
            for trade in active_trades:
                trade.age += 1
                bar = (current_open, current_high, current_low, current_price)
                if apply_backtest_bar(trade, trade.age - 1, bar, max_age_bars):
                    if trade.is_expired:
                        expired_count += 1
                    pnl_pct = (trade.realized_pnl_capital / trade.allocated_capital) * 100.0

                    if pnl_pct > 0.5:
                        outcome = "win"
                        wins_count += 1
                        current_win_streak += 1
                        consecutive_wins = max(consecutive_wins, current_win_streak)
                        current_loss_streak = 0
                    elif pnl_pct < -0.5:
                        outcome = "loss"
                        losses_count += 1
                        current_loss_streak += 1
                        consecutive_losses = max(consecutive_losses, current_loss_streak)
                        current_win_streak = 0
                    else:
                        outcome = "breakeven"
                        breakevens_count += 1
                        current_win_streak = 0
                        current_loss_streak = 0

                    capital += trade.realized_pnl_capital

                    # Max adverse excursion during the trade (== the legacy min/max-price calc).
                    max_dd_trade = trade.state.max_drawdown

                    if trade.direction == "bullish":
                        avg_exit_price = trade.entry_price * (1.0 + (trade.realized_pnl_capital / trade.allocated_capital))
                    else:
                        avg_exit_price = trade.entry_price * (1.0 - (trade.realized_pnl_capital / trade.allocated_capital))

                    trades_log.append({
                        "trade_id": trade.id,
                        "direction": trade.direction,
                        "entry_price": trade.entry_price,
                        "exit_price": _price_round(avg_exit_price),
                        "stop_loss": trade.stop_loss,
                        "tp1": trade.tp1,
                        "tp2": trade.tp2,
                        "tp3": trade.tp3,
                        "return_pct": round(pnl_pct, 2),
                        "capital_impact": round(trade.realized_pnl_capital, 2),
                        "entry_time": trade.entry_time,
                        "exit_time": current_time,
                        "outcome": outcome,
                        "max_drawdown": round(max(0.0, max_dd_trade), 2),
                        "age": trade.age,
                        "is_expired": trade.is_expired,
                        # P11-0 additive (does not affect resolution/accounting):
                        "reached_tp1": bool(getattr(trade.state, "hit_tp1", False)),
                        "reached_tp2": bool(getattr(trade.state, "hit_tp2", False)),
                        "reached_tp3": bool(getattr(trade.state, "hit_tp3", False)),
                        "planned_rr_tp1": planned_rr(trade.entry_price, trade.stop_loss, trade.tp1),
                        "realized_r": _realized_r(trade.entry_price, trade.stop_loss, pnl_pct),
                    })
                    resolved_trades.append(trade)

            # Remove resolved trades
            for r_trade in resolved_trades:
                active_trades.remove(r_trade)

            # Update Peak and Drawdown
            peak_capital = max(peak_capital, capital)
            dd = ((peak_capital - capital) / peak_capital) * 100.0
            max_drawdown = max(max_drawdown, dd)

            # Log Equity
            equity_curve.append({
                "time": current_time,
                "capital": round(capital, 2),
                "drawdown": round(dd, 2),
            })

            # 2. Check for New Signal — SINGLE-POSITION SAMPLING (BUG-14): the backtest
            # holds at most one position at a time (the len==0 guard below) to avoid
            # double-allocating capital, whereas PRODUCTION issues independent signals
            # regardless of open positions. The backtest sample is therefore sparser and
            # biased toward periods with no open trade — read its win-rate / profit-factor
            # as BEFORE/AFTER deltas (vs a baseline run), NOT as absolute live
            # expectations. Documented, not changed (a configurable-overlap mode is
            # BP2-gated and deferred).
            # TIMING (corrected F1-B': the previous note claimed entry at bar i+1's
            # OPEN price, which the code has never done):
            #
            #   features   bars 0..i        — i is closed when it is scored
            #   price      close[i]         — anchors the entry zone and levels
            #   execution  bar i+1 onward   — the trade's first resolution bar
            #
            # No look-ahead: nothing after bar i is visible to the decision, and the
            # bar that produced a signal never resolves that same signal (the trade
            # is appended at the END of this iteration, while resolution runs at the
            # TOP of the next one).
            #
            # The entry FILL is the published zone's midpoint, not bar i+1's open —
            # the same assumption the live tracker makes. That is a fill-realism
            # assumption (the midpoint may not have traded in bar i+1), not a
            # look-ahead one.
            #
            # Production anchors on the live intrabar price a minute or two into the
            # forming candle; close[i] is the closest no-lookahead proxy available in
            # historical OHLCV. Measured on 24k bar pairs, open[i+1] differs from
            # close[i] by a median 0.02 %, so the choice is close to immaterial — it
            # is recorded in the report metadata rather than argued about here.
            if len(active_trades) == 0 and i < n - 1:
                # Slice dataframe up to and including the current closed bar
                sub_df = df.iloc[:i + 1]

                try:
                    # Run Orchestrator with backtest flag to skip live MTF fetches
                    decision = await self.decision_engine.analyze_and_decide(
                        symbol=symbol,
                        timeframe=timeframe,
                        ohlcv_data=sub_df,
                        portfolio_size=capital,
                        risk_pct=risk_pct,
                        is_backtest=True,
                    )

                    sig_type = decision.get("signal_type")
                    direction = decision.get("direction")

                    # We simulate entry on BUY / SELL signals
                    if sig_type in ["STRONG_BUY", "BUY", "SELL", "STRONG_SELL"]:
                        trade_counter += 1

                        # KEY1-c (D2): enter at the entry-zone MIDPOINT with the
                        # UNSHIFTED published levels — the SAME assumption the LIVE
                        # tracker makes (it fills at the zone midpoint and resolves the
                        # signal's stop_loss/tp1/2/3 directly). This makes the backtest a
                        # faithful mirror of live (a valid BP2 gate). No look-ahead: the
                        # midpoint + levels come from data up to bar i (the closed bar);
                        # only the post-signal bars (i+1 onward) drive resolution.
                        entry_mid = (float(decision["entry_zone_low"]) + float(decision["entry_zone_high"])) / 2.0

                        # Position size from the risk engine recommendation.
                        pos_pct = 5.0  # default fallback
                        for res in decision.get("engine_results", []):
                            if res["engine_name"] == "risk_management":
                                pos_pct = res["supporting_data"].get("recommended_position_pct", 5.0)
                        allocated_capital = capital * (pos_pct / 100.0)

                        adj_sl  = float(decision["stop_loss"])
                        adj_tp1 = float(decision["tp1"])
                        adj_tp2 = float(decision["tp2"])
                        adj_tp3 = float(decision["tp3"])

                        new_trade = Trade(
                            id=f"T-{trade_counter}",
                            direction=direction,
                            entry_price=entry_mid,
                            stop_loss=adj_sl,
                            tp1=adj_tp1,
                            tp2=adj_tp2,
                            tp3=adj_tp3,
                            risk_pct=risk_pct,
                            allocated_capital=allocated_capital,
                            entry_index=i + 1,
                            entry_time=timestamps[i + 1],
                            state=new_walk_state(direction=direction, entry=entry_mid,
                                                 sl=adj_sl, tp1=adj_tp1, tp2=adj_tp2,
                                                 tp3=adj_tp3, execution_model=execution_model),
                        )
                        active_trades.append(new_trade)

                except UnknownTimeframeError:
                    # NOT swallowed. This is a configuration error, not a bar the
                    # engines happened to fail on: it would recur on every single
                    # bar and the run would finish "successfully" with zero trades,
                    # which reads as "the strategy found no setups". Fail loudly on
                    # the first occurrence instead.
                    raise
                except Exception as e:
                    # Log engine failure but continue simulation
                    logger.debug(f"Backtest engine analysis skipped at index {i}: {str(e)}")

        # 3. Calculate Performance Metrics
        total_resolved = wins_count + losses_count + breakevens_count
        win_rate = (wins_count / total_resolved * 100.0) if total_resolved > 0 else 0.0
        loss_rate = (losses_count / total_resolved * 100.0) if total_resolved > 0 else 0.0

        # Profit Factor: Sum of wins / Sum of losses
        total_wins_profit = sum(t["capital_impact"] for t in trades_log if t["outcome"] == "win")
        total_losses_cost = abs(sum(t["capital_impact"] for t in trades_log if t["outcome"] == "loss"))
        profit_factor = (total_wins_profit / total_losses_cost) if total_losses_cost > 0 else (1.0 if total_wins_profit == 0 else 999.0)

        # Average Return
        returns = [t["return_pct"] for t in trades_log]
        avg_return = sum(returns) / len(returns) if returns else 0.0

        # Per-trade Sharpe & Sortino (NOT annualized, no risk-free term — ratios
        # over the per-trade return distribution; surfaces should label them so).
        sharpe = 0.0
        sortino: Optional[float] = None
        if returns and len(returns) > 1:
            mean_ret = np.mean(returns)
            std_ret = np.std(returns)
            sharpe = (mean_ret / std_ret) if std_ret > 0 else 0.0

            # Sortino over downside returns only. Undefined (None) when there are
            # too few losers or zero downside variance — do NOT fabricate a ratio
            # from a sentinel std (BUG-12: the old 0.0001 emitted a fake ~5-figure
            # ratio for any run with no losing trades).
            downside_ret = [r for r in returns if r < 0]
            if len(downside_ret) > 1:
                std_downside = float(np.std(downside_ret))
                if std_downside > 0:
                    sortino = mean_ret / std_downside

        # Average Risk / Reward
        rr_vals = []
        for t in trades_log:
            entry = t["entry_price"]
            sl = t["stop_loss"]
            tp3 = t["tp3"]
            risk = abs(entry - sl)
            reward = abs(tp3 - entry)
            if risk > 0:
                rr_vals.append(reward / risk)
        avg_rr = sum(rr_vals) / len(rr_vals) if rr_vals else 0.0

        # P11-0 additive observability: TP1-based planned R:R (the field P1.1 targets,
        # vs avg_rr above which is TP3-based), per-TP reach rates, and realized-R.
        # Pure aggregation over trades_log — no effect on the metrics above.
        n_log = len(trades_log)
        prr1 = [t["planned_rr_tp1"] for t in trades_log if t.get("planned_rr_tp1") is not None]
        avg_planned_rr_tp1 = round(sum(prr1) / len(prr1), 4) if prr1 else None
        median_planned_rr_tp1 = round(float(np.median(prr1)), 4) if prr1 else None
        sub_1_rr_pct = round(sum(1 for x in prr1 if x < 1.0) / len(prr1) * 100.0, 2) if prr1 else None
        tp1_reach_rate = round(sum(1 for t in trades_log if t.get("reached_tp1")) / n_log * 100.0, 2) if n_log else 0.0
        tp2_reach_rate = round(sum(1 for t in trades_log if t.get("reached_tp2")) / n_log * 100.0, 2) if n_log else 0.0
        tp3_reach_rate = round(sum(1 for t in trades_log if t.get("reached_tp3")) / n_log * 100.0, 2) if n_log else 0.0
        rr_realized = [t["realized_r"] for t in trades_log if t.get("realized_r") is not None]
        avg_realized_r = round(sum(rr_realized) / len(rr_realized), 4) if rr_realized else None
        median_realized_r = round(float(np.median(rr_realized)), 4) if rr_realized else None

        # Expectancy: (Win Rate * Avg Win) - (Loss Rate * Avg Loss)
        avg_win_pct = np.mean([t["return_pct"] for t in trades_log if t["outcome"] == "win"]) if wins_count > 0 else 0.0
        avg_loss_pct = abs(np.mean([t["return_pct"] for t in trades_log if t["outcome"] == "loss"])) if losses_count > 0 else 0.0
        expectancy = ((win_rate / 100.0) * avg_win_pct) - ((loss_rate / 100.0) * avg_loss_pct)

        return BacktestReport(
            total_trades=total_resolved,
            wins=wins_count,
            losses=losses_count,
            breakevens=breakevens_count,
            expired=expired_count,
            win_rate=round(win_rate, 2),
            loss_rate=round(loss_rate, 2),
            profit_factor=round(profit_factor, 2),
            sharpe_ratio=round(sharpe, 3),
            sortino_ratio=(round(sortino, 3) if sortino is not None else None),
            max_drawdown_pct=round(max_drawdown, 2),
            average_return_pct=round(avg_return, 2),
            average_rr=round(avg_rr, 2),
            expectancy_pct=round(expectancy, 2),
            max_consecutive_wins=consecutive_wins,
            max_consecutive_losses=consecutive_losses,
            dropped_forming_bars=dropped_forming,
            equity_curve=equity_curve,
            trades_log=trades_log,
            avg_planned_rr_tp1=avg_planned_rr_tp1,
            median_planned_rr_tp1=median_planned_rr_tp1,
            sub_1_rr_pct=sub_1_rr_pct,
            tp1_reach_rate=tp1_reach_rate,
            tp2_reach_rate=tp2_reach_rate,
            tp3_reach_rate=tp3_reach_rate,
            avg_realized_r=avg_realized_r,
            median_realized_r=median_realized_r,
        )

