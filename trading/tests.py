import numpy as np
import pandas as pd
from django.test import TestCase

from .data import generate_synthetic_ohlc
from .engine import run_backtest
from .models import Backtest, PriceBar, Stock, Trade
from .services import run_and_save
from .strategies import STRATEGIES, build_strategy


def _rising_df(n=60, start=100.0, step=1.0):
    dates = pd.bdate_range("2020-01-01", periods=n)
    close = np.arange(start, start + n * step, step)[:n]
    return pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": 1000},
        index=dates,
    )


class EngineTests(TestCase):
    def test_buy_and_hold_matches_entry_to_exit_return(self):
        df = _rising_df()
        strat = build_strategy("buy_and_hold")
        result = run_backtest(df, strat, initial_cash=100_000, commission=0.0)
        # Positions are shifted one bar to avoid look-ahead, so entry is at the
        # 2nd bar's close. Without commission the return should equal the price
        # move from that entry bar to the final bar.
        entry = df["close"].iloc[1]
        exit_ = df["close"].iloc[-1]
        expected = exit_ / entry - 1.0
        self.assertAlmostEqual(result.total_return, expected, places=4)
        self.assertGreater(result.total_return, 0)

    def test_no_look_ahead_positions_are_shifted(self):
        df = _rising_df()
        strat = build_strategy("buy_and_hold")
        result = run_backtest(df, strat, initial_cash=100_000, commission=0.0)
        # First buy happens on the 2nd bar because positions are shifted by one.
        self.assertEqual(result.trades[0].side, "BUY")
        self.assertEqual(result.trades[0].date, df.index[1])

    def test_commission_reduces_return(self):
        df = _rising_df()
        strat = build_strategy("buy_and_hold")
        no_fee = run_backtest(df, strat, commission=0.0)
        fee = run_backtest(df, strat, commission=0.01)
        self.assertLess(fee.total_return, no_fee.total_return)

    def test_equity_curve_length(self):
        df = _rising_df(n=40)
        result = run_backtest(df, build_strategy("sma_crossover"))
        self.assertEqual(len(result.equity_curve), 40)

    def test_all_strategies_run(self):
        df = pd.DataFrame(
            generate_synthetic_ohlc(days=200, seed=42)
        ).set_index("date")
        df.index = pd.to_datetime(df.index)
        for key in STRATEGIES:
            result = run_backtest(df, build_strategy(key))
            self.assertEqual(len(result.equity_curve), 200)
            self.assertGreaterEqual(result.num_trades, 0)


class ServiceTests(TestCase):
    def setUp(self):
        self.stock = Stock.objects.create(symbol="TEST", name="Test Co")
        bars = generate_synthetic_ohlc(days=150, seed=7)
        PriceBar.objects.bulk_create(
            [PriceBar(stock=self.stock, **b) for b in bars]
        )

    def test_run_and_save_persists_backtest_and_trades(self):
        bt = run_and_save(self.stock, "sma_crossover",
                          params={"short_window": 5, "long_window": 20})
        self.assertIsInstance(bt, Backtest)
        self.assertEqual(Backtest.objects.count(), 1)
        self.assertEqual(bt.parameters["short_window"], 5)
        self.assertEqual(Trade.objects.filter(backtest=bt).count(), bt.num_trades)

    def test_run_without_data_raises(self):
        empty = Stock.objects.create(symbol="EMPTY")
        with self.assertRaises(ValueError):
            run_and_save(empty, "buy_and_hold")


class ViewTests(TestCase):
    def setUp(self):
        self.stock = Stock.objects.create(symbol="VUE", name="View Co")
        bars = generate_synthetic_ohlc(days=120, seed=11)
        PriceBar.objects.bulk_create(
            [PriceBar(stock=self.stock, **b) for b in bars]
        )

    def test_index_loads(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "バックテスト")

    def test_run_backtest_post_creates_and_redirects(self):
        resp = self.client.post("/run/", {
            "stock": self.stock.id,
            "strategy": "sma_crossover",
            "sma_crossover__short_window": 10,
            "sma_crossover__long_window": 30,
            "initial_cash": 100000,
            "commission": 0.001,
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Backtest.objects.count(), 1)

    def test_compare_view(self):
        resp = self.client.get(f"/stock/{self.stock.symbol}/compare/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Backtest.objects.count(), len(STRATEGIES))
