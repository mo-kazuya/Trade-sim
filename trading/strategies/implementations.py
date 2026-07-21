"""Concrete trading strategies used for backtesting."""

import numpy as np
import pandas as pd

from .base import Param, Strategy


class BuyAndHold(Strategy):
    key = "buy_and_hold"
    label = "Buy & Hold（買い持ち）"
    description = "初日に全額買って最後まで保有し続ける、比較の基準となる戦略。"
    params: list[Param] = []

    def generate_positions(self, df):
        return pd.Series(1, index=df.index)


class SMACrossover(Strategy):
    key = "sma_crossover"
    label = "移動平均クロス（SMA Crossover）"
    description = (
        "短期移動平均が長期移動平均を上抜けたら買い（ゴールデンクロス）、"
        "下抜けたら売り（デッドクロス）。"
    )
    params = [
        Param("short_window", "短期移動平均の期間", 20, "int", 2, 400),
        Param("long_window", "長期移動平均の期間", 50, "int", 3, 800),
    ]

    def generate_positions(self, df):
        short = df["close"].rolling(int(self.short_window)).mean()
        long = df["close"].rolling(int(self.long_window)).mean()
        pos = (short > long).astype(int)
        # No signal until both averages are defined.
        pos[long.isna() | short.isna()] = 0
        return pos


class RSIStrategy(Strategy):
    key = "rsi"
    label = "RSI（逆張り）"
    description = (
        "RSIが売られすぎ水準を下回ったら買い、買われすぎ水準を上回ったら売る逆張り戦略。"
    )
    params = [
        Param("period", "RSIの期間", 14, "int", 2, 200),
        Param("oversold", "買いに転じる下限（売られすぎ）", 30, "int", 1, 99),
        Param("overbought", "売りに転じる上限（買われすぎ）", 70, "int", 1, 99),
    ]

    def _rsi(self, close, period):
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def generate_positions(self, df):
        rsi = self._rsi(df["close"], int(self.period))
        oversold = float(self.oversold)
        overbought = float(self.overbought)
        # Build a stateful position: enter long below oversold, exit above overbought.
        pos = np.zeros(len(df), dtype=int)
        holding = 0
        rsi_values = rsi.to_numpy()
        for i, value in enumerate(rsi_values):
            if not np.isnan(value):
                if holding == 0 and value < oversold:
                    holding = 1
                elif holding == 1 and value > overbought:
                    holding = 0
            pos[i] = holding
        return pd.Series(pos, index=df.index)


class BollingerBands(Strategy):
    key = "bollinger"
    label = "ボリンジャーバンド（逆張り）"
    description = (
        "終値が下側バンドを割り込んだら買い、中央線（移動平均）へ戻したら売る逆張り戦略。"
    )
    params = [
        Param("window", "移動平均の期間", 20, "int", 2, 400),
        Param("num_std", "バンド幅（標準偏差の倍数）", 2.0, "float", 0.5, 5.0),
    ]

    def generate_positions(self, df):
        window = int(self.window)
        num_std = float(self.num_std)
        ma = df["close"].rolling(window).mean()
        std = df["close"].rolling(window).std()
        lower = ma - num_std * std
        close = df["close"].to_numpy()
        lower_v = lower.to_numpy()
        ma_v = ma.to_numpy()
        pos = np.zeros(len(df), dtype=int)
        holding = 0
        for i in range(len(df)):
            if not np.isnan(lower_v[i]):
                if holding == 0 and close[i] < lower_v[i]:
                    holding = 1
                elif holding == 1 and close[i] >= ma_v[i]:
                    holding = 0
            pos[i] = holding
        return pd.Series(pos, index=df.index)


class MACDStrategy(Strategy):
    key = "macd"
    label = "MACD（順張り）"
    description = "MACD線がシグナル線を上抜けたら買い、下抜けたら売る順張り戦略。"
    params = [
        Param("fast", "短期EMAの期間", 12, "int", 2, 200),
        Param("slow", "長期EMAの期間", 26, "int", 3, 400),
        Param("signal", "シグナル線の期間", 9, "int", 2, 200),
    ]

    def generate_positions(self, df):
        fast = df["close"].ewm(span=int(self.fast), adjust=False).mean()
        slow = df["close"].ewm(span=int(self.slow), adjust=False).mean()
        macd = fast - slow
        signal = macd.ewm(span=int(self.signal), adjust=False).mean()
        pos = (macd > signal).astype(int)
        warmup = int(self.slow)
        pos.iloc[:warmup] = 0
        return pos
