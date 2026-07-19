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
