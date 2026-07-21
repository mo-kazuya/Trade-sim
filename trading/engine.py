"""The backtesting engine.

Runs a strategy over a price DataFrame and produces an equity curve, a list of
trades, and summary performance metrics. To avoid look-ahead bias, target
positions produced from a bar's close are executed on the *next* bar.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class TradeRecord:
    date: object
    side: str  # "BUY" or "SELL"
    price: float
    shares: float
    value: float
    pnl: float | None = None


@dataclass
class BacktestResult:
    equity_curve: list = field(default_factory=list)  # [{"date": str, "value": float}]
    trades: list = field(default_factory=list)  # list[TradeRecord]
    initial_cash: float = 0.0
    final_value: float = 0.0
    total_return: float = 0.0
    buy_hold_return: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    num_trades: int = 0
    win_rate: float = 0.0


def run_backtest(df: pd.DataFrame, strategy, initial_cash=100_000.0, commission=0.001):
    """Execute ``strategy`` over ``df`` and return a :class:`BacktestResult`.

    ``df`` must be indexed by date and have a ``close`` column (open/high/low/
    volume optional). ``commission`` is a fraction charged on the traded value.
    """
    df = df.sort_index()
    if df.empty:
        return BacktestResult(initial_cash=initial_cash, final_value=initial_cash)

    # Target positions, shifted so a signal known at close of day t is acted on
    # at day t+1 (no look-ahead).
    target = strategy.generate_positions(df).reindex(df.index).fillna(0)
    target = target.shift(1).fillna(0).astype(int)

    closes = df["close"].to_numpy(dtype=float)
    dates = df.index
    positions = target.to_numpy(dtype=int)

    cash = float(initial_cash)
    shares = 0.0
    entry_price = 0.0  # average price of the current open position
    trades: list[TradeRecord] = []
    equity = np.empty(len(df), dtype=float)

    for i in range(len(df)):
        price = closes[i]
        want = positions[i]
        holding = 1 if shares > 0 else 0

        if want == 1 and holding == 0:
            # Enter: spend all cash, accounting for commission.
            invest = cash / (1.0 + commission)
            bought = invest / price
            fee = invest * commission
            cash -= invest + fee
            shares = bought
            entry_price = price
            trades.append(
                TradeRecord(dates[i], "BUY", price, bought, invest)
            )
        elif want == 0 and holding == 1:
            # Exit: sell everything.
            proceeds = shares * price
            fee = proceeds * commission
            cash += proceeds - fee
            pnl = (price - entry_price) * shares - fee
            trades.append(
                TradeRecord(dates[i], "SELL", price, shares, proceeds, pnl)
            )
            shares = 0.0
            entry_price = 0.0

        equity[i] = cash + shares * price

    result = _summarize(
        dates, closes, equity, trades, initial_cash, commission
    )
    return result


def _summarize(dates, closes, equity, trades, initial_cash, commission):
    final_value = float(equity[-1])
    total_return = final_value / initial_cash - 1.0

    buy_hold_return = float(closes[-1] / closes[0] - 1.0)

    # Max drawdown of the equity curve.
    running_max = np.maximum.accumulate(equity)
    drawdowns = equity / running_max - 1.0
    max_drawdown = float(drawdowns.min())

    # Sharpe ratio from daily returns (annualized, ~252 trading days).
    returns = np.diff(equity) / equity[:-1]
    if returns.size > 1 and returns.std() > 0:
        sharpe = float(np.sqrt(252) * returns.mean() / returns.std())
    else:
        sharpe = 0.0

    sells = [t for t in trades if t.side == "SELL"]
    wins = [t for t in sells if (t.pnl or 0) > 0]
    win_rate = (len(wins) / len(sells)) if sells else 0.0

    equity_curve = [
        {"date": pd.Timestamp(d).strftime("%Y-%m-%d"), "value": round(float(v), 2)}
        for d, v in zip(dates, equity)
    ]

    return BacktestResult(
        equity_curve=equity_curve,
        trades=trades,
        initial_cash=float(initial_cash),
        final_value=final_value,
        total_return=total_return,
        buy_hold_return=buy_hold_return,
        max_drawdown=max_drawdown,
        sharpe_ratio=sharpe,
        num_trades=len(trades),
        win_rate=win_rate,
    )
