"""
TradeMinds AI – Historical Backtesting Engine

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

logger = logging.getLogger(__name__)


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
    tp1_hit: bool = False
    tp2_hit: bool = False
    tp3_hit: bool = False
    max_price_reached: float = 0.0
    min_price_reached: float = 999999999.0
    age: int = 0  # Number of candles held
    remaining_share: float = 1.0
    realized_pnl_capital: float = 0.0
    current_sl: float = 0.0
    is_expired: bool = False

    def __post_init__(self):
        if self.current_sl == 0.0:
            self.current_sl = self.stop_loss


def resolve_inside_bar_ambiguity(direction: str, open_price: float, close_price: float, execution_model: str) -> str:
    """Resolve inside-bar ambiguity where both Stop Loss and TP are hit on the same candle."""
    if execution_model == "conservative":
        return "sl"
    elif execution_model == "optimistic":
        return "tp"
    else:  # neutral
        if direction == "bullish":
            return "tp" if close_price >= open_price else "sl"
        else:
            return "tp" if close_price <= open_price else "sl"



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
        max_age: int = 48,      # Expiration after 48 bars
        execution_model: str = "conservative",
    ) -> BacktestReport:
        """Run step-by-step backtest simulation."""
        n = len(df)
        min_bars = 60  # Require at least 60 bars of history for sub-engines to compute EMAs, etc.
        
        if n < min_bars + 10:
            raise ValueError(f"Insufficient history ({n} bars) for backtesting. Minimum required is {min_bars + 10} bars.")

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
                
                # Track the true high/low envelope of the trade. Direction only
                # changes how it is interpreted as adverse/favourable excursion
                # below (BUG-13: the short branch previously fed lows into the
                # adverse-high field, understating short max-drawdown).
                trade.max_price_reached = max(trade.max_price_reached, current_high)
                trade.min_price_reached = min(trade.min_price_reached, current_low)

                # Check Stop Loss hit
                sl_hit = current_low <= trade.current_sl if trade.direction == "bullish" else current_high >= trade.current_sl
                
                # Check Take Profits hit
                if trade.direction == "bullish":
                    tp1_triggered = current_high >= trade.tp1 and not trade.tp1_hit
                    tp2_triggered = current_high >= trade.tp2 and not trade.tp2_hit
                    tp3_triggered = current_high >= trade.tp3 and not trade.tp3_hit
                else:
                    tp1_triggered = current_low <= trade.tp1 and not trade.tp1_hit
                    tp2_triggered = current_low <= trade.tp2 and not trade.tp2_hit
                    tp3_triggered = current_low <= trade.tp3 and not trade.tp3_hit
                
                tp_hit = tp1_triggered or tp2_triggered or tp3_triggered
                
                # Inside bar ambiguity resolution
                if sl_hit and tp_hit:
                    winner = resolve_inside_bar_ambiguity(trade.direction, current_open, current_price, execution_model)
                    if winner == "sl":
                        tp_hit = False
                        tp1_triggered = tp2_triggered = tp3_triggered = False
                    else:
                        sl_hit = False
                
                # Process hits
                if sl_hit:
                    # Close remaining share at stop loss
                    ret_sl = ((trade.current_sl - trade.entry_price) / trade.entry_price) if trade.direction == "bullish" else ((trade.entry_price - trade.current_sl) / trade.entry_price)
                    trade.realized_pnl_capital += trade.remaining_share * trade.allocated_capital * ret_sl
                    trade.remaining_share = 0.0
                elif tp_hit:
                    # Sequential take profits
                    if tp1_triggered:
                        trade.tp1_hit = True
                        portion = 0.50
                        ret_tp1 = ((trade.tp1 - trade.entry_price) / trade.entry_price) if trade.direction == "bullish" else ((trade.entry_price - trade.tp1) / trade.entry_price)
                        trade.realized_pnl_capital += portion * trade.allocated_capital * ret_tp1
                        trade.remaining_share -= portion
                        # Move SL to Break Even
                        trade.current_sl = trade.entry_price
                        
                    if tp2_triggered and trade.remaining_share > 0:
                        trade.tp2_hit = True
                        portion = min(0.30, trade.remaining_share)
                        ret_tp2 = ((trade.tp2 - trade.entry_price) / trade.entry_price) if trade.direction == "bullish" else ((trade.entry_price - trade.tp2) / trade.entry_price)
                        trade.realized_pnl_capital += portion * trade.allocated_capital * ret_tp2
                        trade.remaining_share -= portion
                        
                    if tp3_triggered and trade.remaining_share > 0:
                        trade.tp3_hit = True
                        portion = trade.remaining_share
                        ret_tp3 = ((trade.tp3 - trade.entry_price) / trade.entry_price) if trade.direction == "bullish" else ((trade.entry_price - trade.tp3) / trade.entry_price)
                        trade.realized_pnl_capital += portion * trade.allocated_capital * ret_tp3
                        trade.remaining_share = 0.0
                
                    # After processing TP, check if the same candle hits the new stop loss (BE)
                    if trade.remaining_share > 0:
                        sl_hit_after_tp = current_low <= trade.current_sl if trade.direction == "bullish" else current_high >= trade.current_sl
                        if sl_hit_after_tp:
                            ret_sl = ((trade.current_sl - trade.entry_price) / trade.entry_price) if trade.direction == "bullish" else ((trade.entry_price - trade.current_sl) / trade.entry_price)
                            trade.realized_pnl_capital += trade.remaining_share * trade.allocated_capital * ret_sl
                            trade.remaining_share = 0.0
                
                # Check Expiration
                if trade.remaining_share > 0 and trade.age >= max_age:
                    trade.is_expired = True
                    portion = trade.remaining_share
                    ret_close = ((current_price - trade.entry_price) / trade.entry_price) if trade.direction == "bullish" else ((trade.entry_price - current_price) / trade.entry_price)
                    trade.realized_pnl_capital += portion * trade.allocated_capital * ret_close
                    trade.remaining_share = 0.0
                    expired_count += 1
                
                # Check if resolved
                if trade.remaining_share <= 0.0:
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
                    
                    # Calculate drawdown from maximum reached during trade
                    max_dd_trade = 0.0
                    if trade.direction == "bullish":
                        max_dd_trade = ((trade.entry_price - trade.min_price_reached) / trade.entry_price) * 100.0
                    else:
                        max_dd_trade = ((trade.max_price_reached - trade.entry_price) / trade.entry_price) * 100.0
                        
                    # Calculate average exit price
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

            # 2. Check for New Signal (only if no open trades to prevent overlap in simulation)
            # IMPORTANT: The signal is generated from data up to and including bar i
            # (the closed bar).  We then enter on bar i+1's open price to eliminate
            # lookahead bias — you cannot trade the close of the candle that just
            # produced the signal in a live system.
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

                        # Entry is the OPEN of the NEXT bar — no lookahead bias
                        next_open = float(opens[i + 1])

                        # Calculate allocated capital based on risk engine recommendations
                        pos_pct = 5.0  # default fallback
                        for res in decision.get("engine_results", []):
                            if res["engine_name"] == "risk_management":
                                pos_pct = res["supporting_data"].get("recommended_position_pct", 5.0)

                        allocated_capital = capital * (pos_pct / 100.0)

                        # Scale SL and TP levels by the ratio of next-open to signal close
                        # so that the RR structure relative to entry is preserved.
                        signal_close = float(closes[i])
                        if signal_close > 0 and direction == "bullish":
                            offset = next_open - signal_close
                            adj_sl  = decision["stop_loss"] + offset
                            adj_tp1 = decision["tp1"]  + offset
                            adj_tp2 = decision["tp2"]  + offset
                            adj_tp3 = decision["tp3"]  + offset
                        elif signal_close > 0 and direction == "bearish":
                            offset = next_open - signal_close
                            adj_sl  = decision["stop_loss"] + offset
                            adj_tp1 = decision["tp1"]  + offset
                            adj_tp2 = decision["tp2"]  + offset
                            adj_tp3 = decision["tp3"]  + offset
                        else:
                            adj_sl  = decision["stop_loss"]
                            adj_tp1 = decision["tp1"]
                            adj_tp2 = decision["tp2"]
                            adj_tp3 = decision["tp3"]

                        new_trade = Trade(
                            id=f"T-{trade_counter}",
                            direction=direction,
                            entry_price=next_open,
                            stop_loss=adj_sl,
                            tp1=adj_tp1,
                            tp2=adj_tp2,
                            tp3=adj_tp3,
                            risk_pct=risk_pct,
                            allocated_capital=allocated_capital,
                            entry_index=i + 1,
                            entry_time=timestamps[i + 1],
                        )
                        active_trades.append(new_trade)

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
            equity_curve=equity_curve,
            trades_log=trades_log,
        )

