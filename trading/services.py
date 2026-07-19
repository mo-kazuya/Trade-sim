"""High-level orchestration: run a strategy against a stock and persist results."""

from .data import bars_to_dataframe
from .engine import run_backtest
from .forecast import run_forecast
from .models import Backtest, Forecast, PriceBar, Stock, Trade
from .news import news_adjustments, score_news
from .providers import fetch_yahoo_ohlc
from .strategies import build_strategy, get_strategy_class


def import_yahoo_data(symbol, *, range_="1y", start=None, end=None,
                      interval="1d", name=""):
    """Download OHLCV data from Yahoo Finance and store it as PriceBars.

    Creates the Stock if needed and inserts only bars that don't already exist
    (existing dates are left untouched). Returns ``(stock, num_created)``.
    """
    symbol = symbol.strip().upper()
    if not symbol:
        raise ValueError("銘柄コードを入力してください。")

    info, bars = fetch_yahoo_ohlc(
        symbol, range_=range_, start=start, end=end, interval=interval
    )

    stock, _ = Stock.objects.get_or_create(symbol=symbol)
    display_name = name or info.get("name") or stock.name
    if display_name and stock.name != display_name:
        stock.name = display_name
        stock.save(update_fields=["name"])

    existing = set(
        stock.bars.values_list("date", flat=True)
    )
    new_bars = [
        PriceBar(stock=stock, **bar)
        for bar in bars
        if bar["date"] not in existing
    ]
    PriceBar.objects.bulk_create(new_bars)
    return stock, len(new_bars)


def run_and_save(stock, strategy_key, params=None, initial_cash=100_000.0,
                 commission=0.001, start_date=None, end_date=None):
    """Run a backtest for ``stock`` and store the result as a Backtest row."""
    strategy_cls = get_strategy_class(strategy_key)

    bars_qs = stock.bars.all()
    if start_date:
        bars_qs = bars_qs.filter(date__gte=start_date)
    if end_date:
        bars_qs = bars_qs.filter(date__lte=end_date)
    df = bars_to_dataframe(bars_qs)
    if df.empty:
        raise ValueError("この銘柄には価格データがありません。")

    strategy = build_strategy(strategy_key, params)
    result = run_backtest(
        df, strategy, initial_cash=initial_cash, commission=commission
    )

    backtest = Backtest.objects.create(
        stock=stock,
        strategy_key=strategy_key,
        strategy_label=strategy_cls.label,
        parameters=strategy.values,
        initial_cash=initial_cash,
        commission=commission,
        start_date=df.index.min().date(),
        end_date=df.index.max().date(),
        final_value=result.final_value,
        total_return=result.total_return,
        buy_hold_return=result.buy_hold_return,
        max_drawdown=result.max_drawdown,
        sharpe_ratio=result.sharpe_ratio,
        num_trades=result.num_trades,
        win_rate=result.win_rate,
        equity_curve=result.equity_curve,
    )

    Trade.objects.bulk_create(
        [
            Trade(
                backtest=backtest,
                date=t.date.date() if hasattr(t.date, "date") else t.date,
                side=t.side,
                price=round(t.price, 4),
                shares=round(t.shares, 6),
                value=round(t.value, 2),
                pnl=None if t.pnl is None else round(t.pnl, 2),
            )
            for t in result.trades
        ]
    )
    return backtest


def run_and_save_forecast(stock, *, horizon_days=5, threshold=0.10, n_sims=10_000,
                          method="ensemble", news_text="", seed=None):
    """Forecast the probability of a large upside move and persist the result.

    Combines a Monte-Carlo simulation of future price paths with same-day news
    sentiment, which tilts the simulation's drift and volatility.
    """
    closes = list(stock.bars.order_by("date").values_list("close", flat=True))
    if len(closes) < 2:
        raise ValueError("この銘柄には十分な価格データがありません（2 本以上必要です）。")

    sentiment, matched = score_news(news_text)
    drift_adjust, vol_adjust = news_adjustments(sentiment)

    result = run_forecast(
        closes,
        horizon_days=horizon_days,
        threshold=threshold,
        n_sims=n_sims,
        method=method,
        drift_adjust=drift_adjust,
        vol_adjust=vol_adjust,
        seed=seed,
    )

    return Forecast.objects.create(
        stock=stock,
        horizon_days=result.horizon_days,
        threshold=result.threshold,
        n_sims=result.n_sims,
        method=result.method,
        reference_price=result.reference_price,
        hit_probability=result.hit_probability,
        prob_up=result.prob_up,
        expected_max_return=result.expected_max_return,
        median_max_return=result.median_max_return,
        p5_return=result.p5_return,
        p50_return=result.p50_return,
        p95_return=result.p95_return,
        news_text=news_text,
        news_sentiment=sentiment,
        drift_adjust=drift_adjust,
        vol_adjust=vol_adjust,
        matched_keywords=matched,
        bands={**result.bands, "hist": result.max_return_hist},
    )
