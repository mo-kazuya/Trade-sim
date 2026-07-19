"""Monte-Carlo forecasting of a large short-term upside move.

Estimates the probability that a stock's price reaches ``reference * (1 +
threshold)`` at some point within a horizon of trading days, by simulating many
future price paths. News sentiment (see :mod:`trading.news`) can tilt the daily
drift and volatility of the simulation.

Notes / assumptions:
* The *reference* price is the most recent close, used as a proxy for the next
  trading day's open (unknown at prediction time).
* Paths are simulated from daily **close-to-close** log returns, so the
  probability of touching the target is a mild *under*-estimate versus one that
  used intraday highs.
"""

from dataclasses import dataclass, field

import numpy as np


@dataclass
class ForecastResult:
    reference_price: float
    horizon_days: int
    threshold: float
    method: str
    n_sims: int
    hit_probability: float          # P(touch reference*(1+threshold) within horizon)
    prob_up: float                  # P(end above reference)
    expected_max_return: float      # mean of the per-path max return
    median_max_return: float
    p5_return: float                # terminal-return percentiles
    p50_return: float
    p95_return: float
    drift_adjust: float = 0.0
    vol_adjust: float = 1.0
    bands: dict = field(default_factory=dict)   # per-day percentile price bands
    max_return_hist: dict = field(default_factory=dict)  # histogram of max returns


def log_returns(closes):
    closes = np.asarray(closes, dtype=float)
    closes = closes[closes > 0]
    if closes.size < 2:
        raise ValueError("価格データが不足しています（2 本以上必要です）。")
    return np.diff(np.log(closes))


def simulate_multipliers(lr, horizon, n_sims, method, drift_adjust, vol_adjust, rng):
    """Return an (n_sims, horizon) array of price multipliers vs. the reference.

    Column ``t`` is the simulated price at day ``t+1`` divided by the reference
    price (cumulative through that day).
    """
    mu = float(np.mean(lr))
    sigma = float(np.std(lr, ddof=1)) if lr.size > 1 else 0.0
    sigma_adj = max(sigma * vol_adjust, 1e-9)

    def gbm(n):
        return rng.normal(mu + drift_adjust, sigma_adj, size=(n, horizon))

    def bootstrap(n):
        idx = rng.integers(0, lr.size, size=(n, horizon))
        sampled = lr[idx]
        # Re-center, scale volatility, then re-apply the (adjusted) drift.
        return mu + (sampled - mu) * vol_adjust + drift_adjust

    if method == "gbm":
        draws = gbm(n_sims)
    elif method == "bootstrap":
        draws = bootstrap(n_sims)
    else:  # ensemble
        half = n_sims // 2
        draws = np.vstack([gbm(half), bootstrap(n_sims - half)])

    return np.exp(np.cumsum(draws, axis=1))


def run_forecast(closes, *, horizon_days=5, threshold=0.10, n_sims=10_000,
                 method="ensemble", drift_adjust=0.0, vol_adjust=1.0, seed=None):
    """Run the Monte-Carlo forecast and return a :class:`ForecastResult`."""
    horizon_days = int(horizon_days)
    n_sims = int(n_sims)
    if horizon_days < 1:
        raise ValueError("horizon_days は 1 以上にしてください。")
    if n_sims < 1:
        raise ValueError("n_sims は 1 以上にしてください。")

    rng = np.random.default_rng(seed)
    lr = log_returns(closes)
    reference = float(np.asarray(closes, dtype=float)[-1])

    mult = simulate_multipliers(
        lr, horizon_days, n_sims, method, drift_adjust, vol_adjust, rng
    )

    path_max = mult.max(axis=1)
    terminal = mult[:, -1]

    hit_probability = float(np.mean(path_max >= (1.0 + threshold)))
    prob_up = float(np.mean(terminal >= 1.0))
    expected_max_return = float(np.mean(path_max) - 1.0)
    median_max_return = float(np.median(path_max) - 1.0)
    p5, p50, p95 = (np.percentile(terminal, [5, 50, 95]) - 1.0)

    # Per-day percentile bands (prices) for a fan chart. Day 0 = reference.
    pct = {"p10": 10, "p25": 25, "p50": 50, "p75": 75, "p90": 90}
    bands = {"days": list(range(horizon_days + 1))}
    for name, q in pct.items():
        band = np.percentile(mult, q, axis=0) * reference
        bands[name] = [round(reference, 2)] + [round(float(v), 2) for v in band]

    # Histogram of per-path max returns for a distribution view.
    max_returns = path_max - 1.0
    counts, edges = np.histogram(max_returns, bins=30)
    max_return_hist = {
        "counts": counts.astype(int).tolist(),
        "edges": [round(float(e), 4) for e in edges],
    }

    return ForecastResult(
        reference_price=reference,
        horizon_days=horizon_days,
        threshold=threshold,
        method=method,
        n_sims=n_sims,
        hit_probability=hit_probability,
        prob_up=prob_up,
        expected_max_return=expected_max_return,
        median_max_return=median_max_return,
        p5_return=float(p5),
        p50_return=float(p50),
        p95_return=float(p95),
        drift_adjust=drift_adjust,
        vol_adjust=vol_adjust,
        bands=bands,
        max_return_hist=max_return_hist,
    )
