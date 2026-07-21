import json

from django.contrib import messages
from django.db.models import Max, Min
from django.shortcuts import get_object_or_404, redirect, render

from .forms import BacktestForm, ForecastForm, YahooImportForm
from .models import Backtest, Forecast, Stock
from .providers import DataProviderError
from .services import import_yahoo_data, run_and_save, run_and_save_forecast
from .strategies import STRATEGY_CLASSES, get_strategy_class


def _strategy_metadata():
    """Serializable metadata used by the form template / JS to render params."""
    meta = []
    for cls in STRATEGY_CLASSES:
        meta.append(
            {
                "key": cls.key,
                "label": cls.label,
                "description": cls.description,
                "params": [
                    {
                        "name": p.name,
                        "label": p.label,
                        "default": p.default,
                        "kind": p.kind,
                        "min": p.min,
                        "max": p.max,
                        "help": p.help,
                    }
                    for p in cls.params
                ],
            }
        )
    return meta


def index(request):
    stocks = Stock.objects.all()
    backtests = Backtest.objects.select_related("stock")[:15]
    forecasts = Forecast.objects.select_related("stock")[:10]
    context = {
        "form": BacktestForm(),
        "import_form": YahooImportForm(),
        "forecast_form": ForecastForm(),
        "stocks": stocks,
        "backtests": backtests,
        "forecasts": forecasts,
        "strategies": STRATEGY_CLASSES,
        "strategy_meta_json": json.dumps(_strategy_metadata(), ensure_ascii=False),
    }
    return render(request, "trading/index.html", context)


def run_forecast_view(request):
    if request.method != "POST":
        return redirect("trading:index")

    form = ForecastForm(request.POST)
    if not form.is_valid():
        for field, errors in form.errors.items():
            for err in errors:
                messages.error(request, f"{field}: {err}")
        return redirect("trading:index")

    data = form.cleaned_data
    try:
        forecast = run_and_save_forecast(
            stock=data["stock"],
            horizon_days=data["horizon_days"],
            threshold=data["threshold"],
            n_sims=data["n_sims"],
            method=data["method"],
            news_text=data["news_text"],
        )
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("trading:index")

    messages.success(request, "予測を実行しました。")
    return redirect("trading:forecast_detail", pk=forecast.pk)


def forecast_detail(request, pk):
    forecast = get_object_or_404(
        Forecast.objects.select_related("stock"), pk=pk
    )
    context = {
        "forecast": forecast,
        "bands_json": json.dumps(forecast.bands),
        "news_lines": [ln for ln in forecast.news_text.splitlines() if ln.strip()],
    }
    return render(request, "trading/forecast_detail.html", context)


def import_yahoo_view(request):
    if request.method != "POST":
        return redirect("trading:index")

    form = YahooImportForm(request.POST)
    if not form.is_valid():
        for field, errors in form.errors.items():
            for err in errors:
                messages.error(request, f"{field}: {err}")
        return redirect("trading:index")

    data = form.cleaned_data
    try:
        stock, created = import_yahoo_data(
            data["symbol"],
            range_=data["range_"],
            interval=data["interval"],
        )
    except (DataProviderError, ValueError) as exc:
        messages.error(request, str(exc))
        return redirect("trading:index")

    messages.success(
        request,
        f"{stock.symbol}: {created} 本の新規バーを取り込みました"
        f"（合計 {stock.bar_count} 本）。",
    )
    return redirect("trading:stock_detail", symbol=stock.symbol)


def run_backtest_view(request):
    if request.method != "POST":
        return redirect("trading:index")

    form = BacktestForm(request.POST)
    if not form.is_valid():
        for field, errors in form.errors.items():
            for err in errors:
                messages.error(request, f"{field}: {err}")
        return redirect("trading:index")

    data = form.cleaned_data
    strategy_key = data["strategy"]
    strategy_cls = get_strategy_class(strategy_key)

    # Collect strategy-specific params from POST, named "<key>__<param>".
    params = {}
    for p in strategy_cls.params:
        raw = request.POST.get(f"{strategy_key}__{p.name}", "")
        try:
            params[p.name] = p.coerce(raw)
        except (TypeError, ValueError):
            params[p.name] = p.default

    try:
        backtest = run_and_save(
            stock=data["stock"],
            strategy_key=strategy_key,
            params=params,
            initial_cash=data["initial_cash"],
            commission=data["commission"],
        )
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("trading:index")

    messages.success(request, "バックテストを実行しました。")
    return redirect("trading:backtest_detail", pk=backtest.pk)


def backtest_detail(request, pk):
    backtest = get_object_or_404(
        Backtest.objects.select_related("stock"), pk=pk
    )
    trades = backtest.trades.all()
    context = {
        "backtest": backtest,
        "trades": trades,
        "equity_json": json.dumps(backtest.equity_curve),
        "params_items": list(backtest.parameters.items()),
    }
    return render(request, "trading/backtest_detail.html", context)


def compare_view(request, symbol):
    """Run every strategy (with defaults) on one stock and compare results."""
    stock = get_object_or_404(Stock, symbol=symbol)
    if not stock.bars.exists():
        messages.error(request, "この銘柄には価格データがありません。")
        return redirect("trading:index")

    results = []
    for cls in STRATEGY_CLASSES:
        backtest = run_and_save(
            stock=stock,
            strategy_key=cls.key,
            params=cls.param_defaults(),
        )
        results.append(backtest)

    results.sort(key=lambda b: b.total_return or 0, reverse=True)
    context = {
        "stock": stock,
        "results": results,
        "series_json": json.dumps(
            [
                {"label": b.strategy_label, "curve": b.equity_curve}
                for b in results
            ],
            ensure_ascii=False,
        ),
    }
    return render(request, "trading/compare.html", context)


def stock_detail(request, symbol):
    stock = get_object_or_404(Stock, symbol=symbol)
    agg = stock.bars.aggregate(first=Min("date"), last=Max("date"))
    price_series = list(stock.bars.values("date", "close"))
    context = {
        "stock": stock,
        "first_date": agg["first"],
        "last_date": agg["last"],
        "backtests": stock.backtests.all()[:20],
        "forecasts": stock.forecasts.all()[:10],
        "price_json": json.dumps(
            [
                {"date": p["date"].strftime("%Y-%m-%d"), "value": p["close"]}
                for p in price_series
            ]
        ),
    }
    return render(request, "trading/stock_detail.html", context)
