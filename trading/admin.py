from django.contrib import admin

from .models import Backtest, PriceBar, Stock, Trade


@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = ("symbol", "name", "bar_count", "created_at")
    search_fields = ("symbol", "name")


@admin.register(PriceBar)
class PriceBarAdmin(admin.ModelAdmin):
    list_display = ("stock", "date", "open", "high", "low", "close", "volume")
    list_filter = ("stock",)
    date_hierarchy = "date"


class TradeInline(admin.TabularInline):
    model = Trade
    extra = 0
    readonly_fields = ("date", "side", "price", "shares", "value", "pnl")
    can_delete = False


@admin.register(Backtest)
class BacktestAdmin(admin.ModelAdmin):
    list_display = (
        "id", "stock", "strategy_label", "total_return",
        "buy_hold_return", "num_trades", "created_at",
    )
    list_filter = ("strategy_key", "stock")
    inlines = [TradeInline]


@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
    list_display = ("backtest", "date", "side", "price", "shares", "value", "pnl")
    list_filter = ("side",)
