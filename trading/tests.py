import datetime as dt
from unittest import mock

import numpy as np
import pandas as pd
from django.test import TestCase

from .data import generate_synthetic_ohlc
from .engine import run_backtest
from .forecast import run_forecast
from .models import Backtest, Forecast, PriceBar, Stock, Trade
from .news import news_adjustments, score_news
from .providers import DataProviderError, parse_chart_payload
from .services import import_yahoo_data, run_and_save, run_and_save_forecast
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


def _yahoo_payload():
    """A minimal but realistic Yahoo chart JSON payload for two bars."""
    return {
        "chart": {
            "error": None,
            "result": [
                {
                    "meta": {
                        "symbol": "AAPL",
                        "currency": "USD",
                        "exchangeName": "NMS",
                        "longName": "Apple Inc.",
                    },
                    "timestamp": [1704067200, 1704153600],
                    "indicators": {
                        "quote": [
                            {
                                "open": [100.0, 102.0],
                                "high": [103.0, 104.0],
                                "low": [99.0, 101.0],
                                "close": [102.0, 103.5],
                                "volume": [1000000, 1200000],
                            }
                        ],
                        "adjclose": [{"adjclose": [101.5, 103.0]}],
                    },
                }
            ],
        }
    }


class YahooProviderTests(TestCase):
    def test_parse_payload_extracts_bars(self):
        info, bars = parse_chart_payload(_yahoo_payload())
        self.assertEqual(info["symbol"], "AAPL")
        self.assertEqual(info["currency"], "USD")
        self.assertEqual(info["name"], "Apple Inc.")
        self.assertEqual(len(bars), 2)
        # Adjusted close is preferred when present.
        self.assertEqual(bars[0]["close"], 101.5)
        self.assertEqual(bars[0]["open"], 100.0)
        self.assertEqual(bars[0]["volume"], 1000000)

    def test_parse_skips_incomplete_rows(self):
        payload = _yahoo_payload()
        payload["chart"]["result"][0]["indicators"]["quote"][0]["close"][1] = None
        payload["chart"]["result"][0]["indicators"]["adjclose"][0]["adjclose"][1] = None
        _info, bars = parse_chart_payload(payload)
        self.assertEqual(len(bars), 1)

    def test_parse_raises_on_error_payload(self):
        payload = {"chart": {"error": {"description": "Not Found"}, "result": None}}
        with self.assertRaises(DataProviderError):
            parse_chart_payload(payload)

    def test_import_yahoo_data_upserts(self):
        info = {"symbol": "AAPL", "name": "Apple Inc.", "currency": "USD"}
        bars = [
            {"date": dt.date(2024, 1, 1), "open": 100, "high": 103,
             "low": 99, "close": 101.5, "volume": 1_000_000},
            {"date": dt.date(2024, 1, 2), "open": 102, "high": 104,
             "low": 101, "close": 103.0, "volume": 1_200_000},
        ]
        with mock.patch("trading.services.fetch_yahoo_ohlc",
                        return_value=(info, bars)) as m:
            stock, created = import_yahoo_data("aapl", range_="1y")
        m.assert_called_once()
        self.assertEqual(stock.symbol, "AAPL")
        self.assertEqual(stock.name, "Apple Inc.")
        self.assertEqual(created, 2)

        # Re-importing the same bars should insert nothing (dedup by date).
        with mock.patch("trading.services.fetch_yahoo_ohlc",
                        return_value=(info, bars)):
            stock, created = import_yahoo_data("AAPL")
        self.assertEqual(created, 0)
        self.assertEqual(stock.bars.count(), 2)


class NewsTests(TestCase):
    def test_positive_news_scores_positive(self):
        s, matched = score_news("A社をTOBで買収、上方修正も発表")
        self.assertGreater(s, 0)
        self.assertTrue(any(m["polarity"] == "pos" for m in matched))

    def test_negative_news_scores_negative(self):
        s, matched = score_news("業績を下方修正、赤字転落で急落")
        self.assertLess(s, 0)
        self.assertTrue(any(m["polarity"] == "neg" for m in matched))

    def test_english_case_insensitive(self):
        s, _ = score_news("Company BEATS estimates and raised guidance")
        self.assertGreater(s, 0)

    def test_neutral_news_is_zero(self):
        s, matched = score_news("本日は晴天なり")
        self.assertEqual(s, 0.0)
        self.assertEqual(matched, [])

    def test_sentiment_is_bounded(self):
        s, _ = score_news("買収 " * 50)
        self.assertLessEqual(s, 1.0)
        self.assertGreater(s, 0.9)

    def test_positive_sentiment_increases_drift_and_vol(self):
        drift, vol = news_adjustments(0.8)
        self.assertGreater(drift, 0)
        self.assertGreater(vol, 1.0)
        neg_drift, neg_vol = news_adjustments(-0.8)
        self.assertLess(neg_drift, 0)
        self.assertGreater(neg_vol, 1.0)  # bad news also raises uncertainty


class ForecastEngineTests(TestCase):
    def setUp(self):
        bars = generate_synthetic_ohlc(days=400, seed=99)
        self.closes = [b["close"] for b in bars]

    def test_probability_is_in_unit_interval(self):
        r = run_forecast(self.closes, horizon_days=5, threshold=0.10,
                         n_sims=5000, seed=1)
        self.assertGreaterEqual(r.hit_probability, 0.0)
        self.assertLessEqual(r.hit_probability, 1.0)
        self.assertEqual(len(r.bands["p50"]), 6)  # horizon + day 0

    def test_higher_threshold_lowers_probability(self):
        low = run_forecast(self.closes, threshold=0.05, n_sims=8000, seed=2)
        high = run_forecast(self.closes, threshold=0.30, n_sims=8000, seed=2)
        self.assertGreater(low.hit_probability, high.hit_probability)

    def test_longer_horizon_raises_probability(self):
        short = run_forecast(self.closes, horizon_days=3, threshold=0.10,
                             n_sims=8000, seed=3)
        long = run_forecast(self.closes, horizon_days=15, threshold=0.10,
                            n_sims=8000, seed=3)
        self.assertGreaterEqual(long.hit_probability, short.hit_probability)

    def test_positive_drift_raises_probability(self):
        base = run_forecast(self.closes, threshold=0.10, n_sims=10000,
                            drift_adjust=0.0, seed=4)
        tilted = run_forecast(self.closes, threshold=0.10, n_sims=10000,
                              drift_adjust=0.02, seed=4)
        self.assertGreater(tilted.hit_probability, base.hit_probability)

    def test_reference_price_is_last_close(self):
        r = run_forecast(self.closes, n_sims=1000, seed=5)
        self.assertEqual(r.reference_price, self.closes[-1])


class ForecastServiceTests(TestCase):
    def setUp(self):
        self.stock = Stock.objects.create(symbol="FCT", name="Forecast Co")
        bars = generate_synthetic_ohlc(days=300, seed=21)
        PriceBar.objects.bulk_create(
            [PriceBar(stock=self.stock, **b) for b in bars]
        )

    def test_run_and_save_forecast_persists(self):
        f = run_and_save_forecast(
            self.stock, horizon_days=5, threshold=0.10, n_sims=3000,
            news_text="買収を発表、上方修正", seed=7,
        )
        self.assertIsInstance(f, Forecast)
        self.assertEqual(Forecast.objects.count(), 1)
        self.assertGreater(f.news_sentiment, 0)
        self.assertGreater(f.drift_adjust, 0)
        self.assertGreater(f.vol_adjust, 1.0)
        self.assertGreaterEqual(f.hit_probability, 0.0)
        self.assertLessEqual(f.hit_probability, 1.0)

    def test_forecast_without_data_raises(self):
        empty = Stock.objects.create(symbol="NONE")
        with self.assertRaises(ValueError):
            run_and_save_forecast(empty)


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

    def test_run_forecast_post_creates_and_redirects(self):
        resp = self.client.post("/forecast/", {
            "stock": self.stock.id,
            "horizon_days": 5,
            "threshold": 0.10,
            "n_sims": 2000,
            "method": "ensemble",
            "news_text": "上方修正を発表",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Forecast.objects.count(), 1)
        detail = self.client.get(resp.url)
        self.assertEqual(detail.status_code, 200)

    def test_import_yahoo_view(self):
        info = {"symbol": "MSFT", "name": "Microsoft", "currency": "USD"}
        bars = [{"date": dt.date(2024, 3, 1), "open": 400, "high": 405,
                 "low": 398, "close": 402, "volume": 900_000}]
        with mock.patch("trading.services.fetch_yahoo_ohlc",
                        return_value=(info, bars)):
            resp = self.client.post("/import/yahoo/", {
                "symbol": "MSFT", "range_": "1y", "interval": "1d",
            })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Stock.objects.filter(symbol="MSFT").exists())
