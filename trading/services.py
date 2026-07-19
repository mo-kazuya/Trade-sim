"""High-level orchestration: run a strategy against a stock and persist results."""

from .data import bars_to_dataframe
from .engine import run_backtest
from .models import Backtest, PriceBar, Stock, Trade
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
