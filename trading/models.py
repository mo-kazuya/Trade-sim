from django.db import models


class Stock(models.Model):
    """A tradable instrument (stock / ticker)."""

    symbol = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["symbol"]

    def __str__(self):
        return self.symbol

    @property
    def bar_count(self):
        return self.bars.count()


class PriceBar(models.Model):
    """A single OHLCV bar of historical price data for a stock."""

    stock = models.ForeignKey(Stock, on_delete=models.CASCADE, related_name="bars")
    date = models.DateField()
    open = models.FloatField()
    high = models.FloatField()
    low = models.FloatField()
    close = models.FloatField()
    volume = models.BigIntegerField(default=0)

    class Meta:
        ordering = ["date"]
        unique_together = ("stock", "date")
        indexes = [models.Index(fields=["stock", "date"])]

    def __str__(self):
        return f"{self.stock.symbol} {self.date} {self.close}"


class Backtest(models.Model):
    """A single backtest run of a strategy over a stock's price history."""

    stock = models.ForeignKey(Stock, on_delete=models.CASCADE, related_name="backtests")
    strategy_key = models.CharField(max_length=50)
    strategy_label = models.CharField(max_length=120)
    parameters = models.JSONField(default=dict, blank=True)

    initial_cash = models.FloatField(default=100_000.0)
    commission = models.FloatField(default=0.001, help_text="Fraction charged per trade")

    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    # Result metrics (populated after the run)
    final_value = models.FloatField(null=True, blank=True)
    total_return = models.FloatField(null=True, blank=True)
    buy_hold_return = models.FloatField(null=True, blank=True)
    max_drawdown = models.FloatField(null=True, blank=True)
    sharpe_ratio = models.FloatField(null=True, blank=True)
    num_trades = models.IntegerField(default=0)
    win_rate = models.FloatField(null=True, blank=True)

    # Serialized equity curve: list of {"date": ..., "value": ...}
    equity_curve = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.strategy_label} on {self.stock.symbol} ({self.created_at:%Y-%m-%d})"


class Trade(models.Model):
    """An executed buy/sell within a backtest."""

    BUY = "BUY"
    SELL = "SELL"
    SIDE_CHOICES = [(BUY, "Buy"), (SELL, "Sell")]

    backtest = models.ForeignKey(Backtest, on_delete=models.CASCADE, related_name="trades")
    date = models.DateField()
    side = models.CharField(max_length=4, choices=SIDE_CHOICES)
    price = models.FloatField()
    shares = models.FloatField()
    value = models.FloatField()
    # Realized profit/loss for a SELL (relative to the matching buy). Null for buys.
    pnl = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["date", "id"]

    def __str__(self):
        return f"{self.side} {self.shares:.2f} @ {self.price:.2f}"


class Forecast(models.Model):
    """A Monte-Carlo forecast of the probability of a large upside move.

    Estimates P(price reaches reference * (1 + threshold) at any point within
    ``horizon_days`` trading days), optionally tilted by same-day news
    sentiment.
    """

    METHOD_CHOICES = [
        ("ensemble", "アンサンブル（ブートストラップ＋GBM）"),
        ("bootstrap", "ヒストリカル・ブートストラップ"),
        ("gbm", "パラメトリック GBM"),
    ]

    stock = models.ForeignKey(Stock, on_delete=models.CASCADE, related_name="forecasts")

    horizon_days = models.IntegerField(default=5)
    threshold = models.FloatField(default=0.10, help_text="Upside target as a fraction")
    n_sims = models.IntegerField(default=10_000)
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default="ensemble")

    reference_price = models.FloatField()

    # Headline result: probability of hitting the target within the horizon.
    hit_probability = models.FloatField()
    prob_up = models.FloatField(default=0.0)

    expected_max_return = models.FloatField(default=0.0)
    median_max_return = models.FloatField(default=0.0)
    p5_return = models.FloatField(default=0.0)
    p50_return = models.FloatField(default=0.0)
    p95_return = models.FloatField(default=0.0)

    # News influence.
    news_text = models.TextField(blank=True)
    news_sentiment = models.FloatField(default=0.0)
    drift_adjust = models.FloatField(default=0.0)
    vol_adjust = models.FloatField(default=1.0)
    matched_keywords = models.JSONField(default=list, blank=True)

    # Per-day percentile price bands for the fan chart.
    bands = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.stock.symbol} +{self.threshold:.0%} in {self.horizon_days}d "
            f"= {self.hit_probability:.1%}"
        )

    @property
    def target_price(self):
        return self.reference_price * (1 + self.threshold)
