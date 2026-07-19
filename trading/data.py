"""Data helpers: turning stored PriceBars into DataFrames and generating
synthetic price history for demos/tests."""

import datetime as dt

import numpy as np
import pandas as pd


def bars_to_dataframe(bars):
    """Convert an iterable of PriceBar into a DataFrame indexed by date."""
    rows = [
        {
            "date": b.date,
            "open": b.open,
            "high": b.high,
            "low": b.low,
            "close": b.close,
            "volume": b.volume,
        }
        for b in bars
    ]
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date").sort_index()


def generate_synthetic_ohlc(
    days=750,
    start_price=100.0,
    annual_drift=0.08,
    annual_vol=0.25,
    seed=None,
    start_date=None,
):
    """Generate a geometric-random-walk OHLCV series (business days only).

    Returns a list of dicts suitable for creating PriceBar rows.
    """
    rng = np.random.default_rng(seed)
    dt_step = 1.0 / 252.0
    mu = annual_drift
    sigma = annual_vol

    if start_date is None:
        start_date = dt.date.today() - dt.timedelta(days=int(days * 1.5))

    dates = pd.bdate_range(start=start_date, periods=days)

    # Daily log returns of a geometric Brownian motion.
    shocks = rng.normal(
        (mu - 0.5 * sigma**2) * dt_step,
        sigma * np.sqrt(dt_step),
        size=days,
    )
    close = start_price * np.exp(np.cumsum(shocks))

    bars = []
    prev_close = start_price
    for i, date in enumerate(dates):
        c = float(close[i])
        o = float(prev_close * (1 + rng.normal(0, 0.002)))
        intraday = abs(rng.normal(0, sigma * np.sqrt(dt_step))) * c
        hi = max(o, c) + intraday * rng.uniform(0.1, 1.0)
        lo = min(o, c) - intraday * rng.uniform(0.1, 1.0)
        volume = int(rng.uniform(500_000, 5_000_000))
        bars.append(
            {
                "date": date.date(),
                "open": round(o, 2),
                "high": round(hi, 2),
                "low": round(max(lo, 0.01), 2),
                "close": round(c, 2),
                "volume": volume,
            }
        )
        prev_close = c
    return bars
